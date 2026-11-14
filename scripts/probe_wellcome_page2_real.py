#!/usr/bin/env python3
"""Try Wellcome Collection no-key CC0/PD/CC BY 2D art; report real decoded files only."""
import hashlib,io,json,os,re, time
from pathlib import Path
from urllib.parse import urlencode,quote,urlsplit
from urllib.request import Request,urlopen
from PIL import Image

ROOT=Path("audit-wellcome-more-art")
IMAGES=ROOT/"samples"
IMAGES.mkdir(parents=True,exist_ok=True)
AGENT="QuietArtGalleryVerifiableArt/1.0 (https://github.com/treesky0103-dot/quiet-art-gallery)"
URL="https://api.wellcomecollection.org/catalogue/v2/"
LICENSES=["pdm","cc0","cc-by"]
QUERIES=["watercolour","engraving","etching","drawing","painting","illustration"]
year_min=1800
year_max=2026
LIMIT=28
MAX_ATTEMPTS=45
MAX_IMAGE_BYTES=18*1024*1024
def fetch(url,timeout=18,binary=False):
    request=Request(url,headers={"User-Agent":AGENT,"Accept":"*/*" if binary else "application/json"})
    with urlopen(request,timeout=timeout) as res:
        if res.status!=200:raise RuntimeError("HTTP "+str(res.status))
        if binary:
            data=res.read(MAX_IMAGE_BYTES+1)
            if len(data)>MAX_IMAGE_BYTES:raise RuntimeError("Image too large")
            return data
        return json.load(res)

def fits(w,h):
    if w<1000 or h<1400 or w>=h:return False
    return min((w/h)/.625,.625/(w/h))>=.75

def year(works):
    # Work production dates can be a century range; if ambiguous reject.
    periods=[]
    for p in works.get("production",[]) or []:
        for ds in p.get("dates",[]) or []:
            dr=ds.get("range") or {}
            earliest=((dr.get("from") or {}).get("label") or
                      (dr.get("from") or {}).get("id") or
                      ds.get("label") or "")
            latest=((dr.get("to") or {}).get("label") or
                      (dr.get("to") or {}).get("id") or
                      ds.get("label") or "")
            a=re.search(r"(?<!\d)(1[0-9]{3}|20[0-2][0-9])(?!\d)",str(earliest))
            b=re.search(r"(?<!\d)(1[0-9]{3}|20[0-2][0-9])(?!\d)",str(latest))
            if a and b:
                x,y=int(a.group(1)),int(b.group(1))
                if x<=y:periods.append((x,y))
    if not periods:return None
    early=min(x for x,_ in periods);last=max(y for _,y in periods)
    if early>=1800 and last<=2026:return {"era":"1800-2026","year_start":early,"year_end":last}
    if last<1800:return {"era":"pre-1800","year_start":early,"year_end":last}
    return None

def check_flat(entry,work):
    source=entry.get("source") or {}
    terms=" ".join(str(x.get("label") or "") for x in (source.get("genres") or []) if isinstance(x,dict))
    texts=" ".join([terms,str(work.get("workType",{}).get("label") or ""),
      str(work.get("title") or "")]).lower()
    bad=("photograph","photographic","album","manuscript","book",
      "film","video","hospital","map","photogravure","collection of","photographs","postcard")
    if any(x in texts for x in bad):return False
    return any(x in texts for x in ("drawing","painting","etching","watercolour","watercolor",
             "illustration","lithograph","engraving","print","pastel","gouache"))

def image_location(entry):
    for loc in entry.get("locations") or []:
        lic=((loc.get("license") or {}).get("id") or "").lower()
        if lic not in LICENSES:continue
        url=str(loc.get("url") or "")
        if url.startswith("https://iiif.wellcomecollection.org/image/"):
            return url,lic
    return None,None

def iiif_jpg(url):
    parsed=urlsplit(url)
    if parsed.hostname!="iiif.wellcomecollection.org":raise ValueError("Non-Wellcome IIIF host")
    url=url.split("?",1)[0].rstrip("/")
    if url.endswith("/info.json"):url=url[:-10]
    if "/full/" in url:
        url=url.split("/full/",1)[0]
    if "/image/" not in url:raise ValueError("Not an IIIF image URI")
    return url+"/full/!2400,2400/0/default.jpg"

def main():
    stats={"source":"Wellcome Collection v2 images API","searches":[],"metadata_candidates":0,
       "work_year_verified_candidates":0,"file_attempts":0,
       "byte_verified_image_files":0,"files":[],"errors":[],
       "false_259200_completion":False}
    seen_ids=set()
    candidates=[]
    for q in QUERIES:
        url=URL+"images?"+urlencode({"query":q,"pageSize":50,"page":2,
             "locations.license":",".join(LICENSES),
             "source.production.dates.from":"1800-01-01",
             "source.production.dates.to":"2026-11-14"})
        try:
            data=fetch(url)
            rows=data.get("results") or []
            stats["searches"].append({"query":q,"totalResults":data.get("totalResults"),
                     "returned":len(rows),"error":None})
            stats["metadata_candidates"]+=len(rows)
            for entry in rows:
                ident=str(entry.get("id") or "")
                imageurl,licensecode=image_location(entry)
                if not ident or ident in seen_ids or not imageurl:continue
                seen_ids.add(ident)
                candidates.append((entry,imageurl,licensecode))
        except Exception as e:
            stats["searches"].append({"query":q,"totalResults":None,
                    "returned":0,"error":str(e)[:190]})
        time.sleep(.3)
    prior=set()
    ledger=Path("data/verified_80pct/verified_artwork_manifest.csv")
    if ledger.exists():
        import csv
        with ledger.open(encoding="utf-8-sig",newline="") as fh:
            for x in csv.DictReader(fh):
                if x.get("source")=="Wellcome Collection":
                    prior.add(str(x.get("artwork_id")))
    seen_sha=set()
    for entry,location,licensecode in candidates:
        if len(stats["files"])>=LIMIT or stats["file_attempts"]>=MAX_ATTEMPTS:break
        source=entry.get("source") or {}
        source_id=str(source.get("id") or "")
        if source_id in prior:continue
        if not re.fullmatch(r"[a-zA-Z0-9]{3,30}",source_id):continue
        try:
            work=fetch(URL+"works/"+quote(source_id)+"?include=production,genres")
            when=year(work)
            if not when or not check_flat(entry,work):continue
            stats["work_year_verified_candidates"]+=1
            url=iiif_jpg(location)
            stats["file_attempts"]+=1
            blob=fetch(url,binary=True,timeout=24)
            with Image.open(io.BytesIO(blob)) as original:
                original.load()
                if not fits(*original.size):continue
                im=original.convert("RGB")
                if im.height>2400:
                    im=im.resize((round(im.width*2400/im.height),2400),Image.Resampling.LANCZOS)
                filedata=io.BytesIO()
                im.save(filedata,"JPEG",quality=82,optimize=True)
                saved=filedata.getvalue()
            sha=hashlib.sha256(saved).hexdigest()
            if sha in seen_sha:continue
            path=IMAGES/(sha[:24]+".jpg")
            path.write_bytes(saved)
            im2=Image.open(path);im2.load()
            if not fits(*im2.size):path.unlink();continue
            seen_sha.add(sha)
            stats["files"].append({
              "id":str(entry.get("id")),
              "work_id":source_id,"title":work.get("title"),
              **when,"license":licensecode,"sha256":sha,
              "width":im2.width,"height":im2.height,
              "saved_bytes":len(saved),"file_path":str(path),
              "source_url":url})
            print("WELLCOME_VERIFIED "+json.dumps({
              "count":len(stats["files"]),"era":when["era"],"image_size":len(saved)}),flush=True)
        except Exception as e:
            if len(stats["errors"])<25:stats["errors"].append({"id":entry.get("id"),"error":str(e)[:200]})
        time.sleep(.12)
    stats["byte_verified_image_files"]=len(stats["files"])
    (ROOT/"audit.json").write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding="utf-8")
    print("WELLCOME_FINAL "+json.dumps({
        "metadata_candidates":stats["metadata_candidates"],
        "work_year_verified_candidates":stats["work_year_verified_candidates"],
        "byte_verified":stats["byte_verified_image_files"],
        "searches":stats["searches"],"errors_sample":stats["errors"][:3]},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
