#!/usr/bin/env python3
"""Public Internet Archive art scan: discovery may contain copyrighted works;
only work records with explicit open licences are downloaded and pixel verified.
Never treat a book cover, thumbnail, scan copyright statement, or archive upload
date as original artwork identity/date. Bounded sequential API calls.
"""
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode,quote,urlsplit
from PIL import Image
from collections import Counter
import csv,hashlib,io,json,re,time
ROOT=Path("audit-internet-archive-art")
IMAGES=ROOT/"artworks";IMAGES.mkdir(parents=True,exist_ok=True)
UA="QuietArtGallery/1.0 (public art source research; https://github.com/treesky0103-dot/quiet-art-gallery)"
QUERIES=[
 'mediatype:image AND title:(illustration)',
 'mediatype:image AND subject:(woodcut)',
 'mediatype:image AND title:(painting)',
 'mediatype:image AND subject:(watercolor)'
]
MAX_METADATA=42
MAX_FILES=15
MAX_IMAGE_TRIES=40
MAX_BYTES=14*1024*1024
LICENSE_MARKERS=("creativecommons.org/publicdomain/zero/","creativecommons.org/publicdomain/mark/",
                 "creativecommons.org/licenses/by/","creativecommons.org/licenses/by-sa/")
def safe_origin(u):
    p=urlsplit(u)
    return (p.scheme=="https" and p.hostname in ("archive.org","www.archive.org")
            and p.username is None and p.password is None and p.port in (None,443))
def fetch(u,limit=4*1024*1024,timeout=27):
    if not safe_origin(u):raise ValueError("Only official archive.org HTTPS endpoints allowed")
    req=Request(u,headers={"User-Agent":UA,"Accept":"application/json,image/jpeg,image/png,image/webp,*/*"})
    with urlopen(req,timeout=timeout) as f:
        if f.status!=200:raise RuntimeError("HTTP "+str(f.status))
        real=urlsplit(f.geturl())
        if real.scheme!="https" or not (real.hostname in ("archive.org","www.archive.org") or
            re.fullmatch(r"ia\d{3,8}(?:\.[a-z0-9-]+)*\.archive\.org",real.hostname or "")):
            raise ValueError("Unexpected archive download server")
        data=f.read(limit+1)
        if len(data)>limit:raise ValueError("Response exceeded byte cap")
        return data
def query(q):
    p={"q":q,"fl[]":["identifier","title","year","rights","licenseurl"],"rows":"30","page":"1","output":"json"}
    url="https://archive.org/advancedsearch.php?"+urlencode(p,doseq=True)
    body=json.loads(fetch(url))
    return ((body.get("response") or {}).get("docs") or [])
def open_license(meta):
    joined=" ".join(str(meta.get(x) or "") for x in ("licenseurl","license","rights")).lower()
    return (any(marker in joined for marker in LICENSE_MARKERS) or
        ("public domain" in joined and "not public domain" not in joined))
def art_file(file):
    name=str(file.get("name") or "")
    src=str(file.get("source") or "")
    if src!="original" or not re.search(r"\.(?:jpg|jpeg|png|webp)$",name,re.I):return False
    if re.search(r"(?:^|[_\W])(?:thumb|thumbnail|preview|screenshot|cover|logo|scanpage|small)\b",name,re.I):return False
    try:return 50000<int(file.get("size") or 0)<MAX_BYTES
    except(ValueError,TypeError):return False
def screen(w,h):
    return w>=1000 and h>=1400 and w<h and min((w/h)/.625,.625/(w/h))>=.75
def main():
    stats=Counter();candidate_ids=[];unique_ids=set();errors=[];qualified=[]
    for q in QUERIES:
        try:
            docs=query(q);stats["successful_queries"]+=1;stats["search_hits"]+=len(docs)
            for record in docs:
                identifier=str(record.get("identifier") or "")
                if not re.fullmatch(r"[A-Za-z0-9_.-]{4,140}",identifier):continue
                if identifier not in unique_ids:unique_ids.add(identifier);candidate_ids.append(identifier)
        except Exception as e:
            stats["query_errors"]+=1
            errors.append({"query":q,"reason":str(e)[:150]})
        time.sleep(1.5)
    count=0;seen_hash=set();items=[]
    for identifier in candidate_ids:
        if count>=MAX_METADATA or stats["image_attempts"]>=MAX_IMAGE_TRIES or len(items)>=MAX_FILES:break
        count+=1
        try:
            meta=json.loads(fetch("https://archive.org/metadata/"+quote(identifier)))
            rights=meta.get("metadata") or {}
            if not open_license(rights):
                stats["copyright_unknown_cataloged_only"]+=1;continue
            stats["metadata_open_license"]+=1
            files=[f for f in (meta.get("files") or []) if art_file(f)]
            for f in files[:4]:
                if stats["image_attempts"]>=MAX_IMAGE_TRIES or len(items)>=MAX_FILES:break
                stats["image_attempts"]+=1
                url="https://archive.org/download/"+quote(identifier)+"/"+quote(str(f["name"]),safe="/")
                try:
                    b=fetch(url,limit=MAX_BYTES,timeout=33)
                    with Image.open(io.BytesIO(b)) as original:
                        original.load()
                        if original.format not in ("JPEG","PNG","WEBP") or not screen(*original.size):
                            stats["bad_image_shape"]+=1;continue
                        im=original.convert("RGB")
                        if im.height>2400:
                            im=im.resize((round(im.width*2400/im.height),2400),Image.Resampling.LANCZOS)
                        result=io.BytesIO();im.save(result,"JPEG",quality=83,optimize=True)
                    saved=result.getvalue();sha=hashlib.sha256(saved).hexdigest()
                    if sha in seen_hash:continue
                    path=IMAGES/(sha[:24]+".jpg");path.write_bytes(saved)
                    verify=Image.open(path);verify.load()
                    assert screen(*verify.size)
                    assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
                    seen_hash.add(sha)
                    items.append({"source":"Internet Archive","archive_id":identifier,
                        "title":str(rights.get("title") or "")[:210],
                        "license_or_rights":str(rights.get("licenseurl") or rights.get("rights") or ""),
                        "work_year_status":"unknown_venue_metadata_not_artwork_year",
                        "sha256":sha,"source_sha256":hashlib.sha256(b).hexdigest(),
                        "file":str(path),"source_url":url,
                        "width":verify.width,"height":verify.height,"bytes":len(saved)})
                    print("IA_REAL_ART "+json.dumps({"n":len(items),"archive_id":identifier,
                        "bytes":len(saved)},ensure_ascii=False),flush=True)
                except Exception as e:
                    stats["failed_image_fetches"]+=1
                    if len(errors)<25:errors.append({"image":identifier,"reason":str(e)[:150]})
                time.sleep(.4)
        except Exception as e:
            stats["failed_metadata"]+=1
            if len(errors)<30:errors.append({"identifier":identifier,"reason":str(e)[:160]})
        time.sleep(.8)
    out={"provider":"Internet Archive public AdvancedSearch / Metadata / Download",
        "stats":dict(stats),"search_queries":QUERIES,"metadata_records_examined":count,
        "images_downloaded_decoded":len(items),"actual_images":items,
        "failed_access":errors[:30],
        "year_1800_verified":0,"artwork_90days_ready":False,
        "rights_unknown_records_are_discovery_only":True,
        "note":"This is a sample of public licensed archive image files, NOT 259200 acquired unique paintings. Original source could include scans of non-art pages; expert visual curation required."}
    (ROOT/"report.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("INTERNET_ARCHIVE_FINAL "+json.dumps({"metadata_examined":count,
       "source_searches_ok":stats["successful_queries"],
       "open_license_metadata":stats["metadata_open_license"],
       "actually_decoded_files":len(items),"copyright_unknown_catalog_only":stats["copyright_unknown_cataloged_only"],
       "target_complete":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
