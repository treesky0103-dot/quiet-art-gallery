#!/usr/bin/env python3
"""Actual Met museum public-domain 2D JPEG byte pilot from original 503k-row census.

Input is the official CSV census output from GitHub Actions; NOT acquired images.
For independent art proof, re-query individual object API, check strict year and
rights, fetch HTTPS museum original, decode actual pixels, SHA256.
"""
from pathlib import Path
from urllib.parse import urlsplit,quote
from urllib.request import Request,urlopen
from collections import Counter
from PIL import Image
import gzip,csv,hashlib,io,json,re,time
OUT=Path("audit-met-real-art")
IMAGES=OUT/"samples";IMAGES.mkdir(parents=True,exist_ok=True)
CANDIDATE=Path("research-input/met/Met_2d_dated_cc0_CANDIDATES_not_downloaded.csv.gz")
UA="QuietArtGalleryMetOriginals/1.0 (public-domain museum image verification; https://github.com/treesky0103-dot/quiet-art-gallery)"
API="https://collectionapi.metmuseum.org/public/collection/v1/objects/"
MAX_DETAILS=135
MAX_IMAGES=20
MAX_BYTES=25*1024*1024
def download(url,binary=False,timeout=28):
    req=Request(url,headers={"User-Agent":UA,"Accept":"*/*"})
    with urlopen(req,timeout=timeout) as response:
        if response.status!=200:raise RuntimeError("HTTP "+str(response.status))
        b=response.read(MAX_BYTES+1)
        if len(b)>MAX_BYTES:raise RuntimeError("Image exceeds max size")
    return b if binary else json.loads(b)
def kind(x):
    s=(str(x.get("objectName") or "")+" "+str(x.get("classification") or "")+
      " "+str(x.get("medium") or "")).lower()
    bad=("photograph","sculpture","ceramic","glass","furniture","coin","jewelry",
         "textile","carving","installation","manuscript","reliquary","tapestry")
    yes=("painting","drawing","print","watercolor","watercolour",
         "etching","engraving","lithograph","woodcut","illustration",
         "oil on canvas","ink on paper","pastel","aquatint","monotype","gouache")
    return not any(v in s for v in bad) and any(v in s for v in yes)
def era(x):
    try:a=int(x.get("objectBeginDate"));b=int(x.get("objectEndDate"))
    except (ValueError,TypeError):return None
    if not -4000<=a<=b<=2026:return None
    return "1800plus" if a>=1800 else "older" if b<1800 else None
def fits(w,h):
    try:w,h=int(w),int(h)
    except (ValueError,TypeError):return False
    return w>=1000 and h>=1400 and w<h and min((w/h)/.625,.625/(w/h))>=.75
def sample_ids():
    if not CANDIDATE.exists():raise FileNotFoundError(CANDIDATE)
    rows={"1800plus":[],"older":[]}
    with gzip.open(CANDIDATE,"rt",encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            e=row.get("era")
            if e not in rows:continue
            oid=row.get("object_id")
            if not oid or not oid.isdigit():continue
            # Stable hash reordering avoids selecting only the oldest/dominant department.
            seed=int(hashlib.sha256(oid.encode()).hexdigest()[:9],16)
            rows[e].append((seed,int(oid)))
    for k in rows:rows[k]=[v for _,v in sorted(rows[k])[:300]]
    # Alternate eras, allowing 20 actual if both have valid portrait art.
    ids=[]
    for i in range(100):
        for e in ("1800plus","older"):
            if i<len(rows[e]):ids.append((e,rows[e][i]))
    return ids,{"input_modern_ids":len(rows["1800plus"]),
                "input_older_ids":len(rows["older"])}
def main():
    ids,index=sample_ids()
    stats={"source":"Metropolitan Museum of Art official collection API / CC0",
      "metadata_input":index,"details_tried":0,"metadata_qualified":0,
      "actual_downloaded":[],"rejects":Counter(),"errors":[],
      "all_259200_acquired":False}
    seen=set()
    for expected,oid in ids:
        if stats["details_tried"]>=MAX_DETAILS:break
        if len(stats["actual_downloaded"])>=MAX_IMAGES:break
        stats["details_tried"]+=1
        try:
            item=download(API+str(oid))
            if item.get("isPublicDomain") is not True:
                stats["rejects"]["not_public_domain"]+=1;continue
            if not kind(item):
                stats["rejects"]["nonflat"]+=1;continue
            if era(item)!=expected:
                stats["rejects"]["date_mismatch"]+=1;continue
            url=item.get("primaryImage") or ""
            if urlsplit(url).hostname!="images.metmuseum.org":
                stats["rejects"]["no_official_primary_image"]+=1;continue
            stats["metadata_qualified"]+=1
            # An official "primaryImage" is a high resolution JPEG, not an object record.
            try:
                raw=download(url,binary=True,timeout=35)
                image=Image.open(io.BytesIO(raw));image.load()
                if image.format not in ("JPEG","PNG","WEBP") or not fits(*image.size):
                    stats["rejects"]["actual_image_not_usable"]+=1;continue
                img=image.convert("RGB")
                if img.height>2400:img=img.resize((round(img.width*2400/img.height),2400),Image.Resampling.LANCZOS)
                dest_buf=io.BytesIO();img.save(dest_buf,"JPEG",quality=84,optimize=True)
                jpeg=dest_buf.getvalue();sha=hashlib.sha256(jpeg).hexdigest()
                if sha in seen:continue
                name=IMAGES/(sha[:24]+".jpg");name.write_bytes(jpeg)
                im2=Image.open(name);im2.load()
                assert fits(*im2.size) and hashlib.sha256(name.read_bytes()).hexdigest()==sha
                seen.add(sha)
                record={"source":"Metropolitan Museum of Art","id":oid,"title":item.get("title"),
                  "creator":item.get("artistDisplayName"),"era":"1800-2026" if expected=="1800plus" else "pre-1800",
                  "year_start":item.get("objectBeginDate"),"year_end":item.get("objectEndDate"),
                  "source_url":item.get("objectURL"),"source_image":url,
                  "public_domain":True,"license":"CC0 from The Met Open Access",
                  "source_sha256":hashlib.sha256(raw).hexdigest(),
                  "sha256":sha,"saved_file":str(name),"bytes":len(jpeg),
                  "width":im2.width,"height":im2.height}
                stats["actual_downloaded"].append(record)
                print("MET_REAL_IMAGE "+json.dumps({"id":oid,"era":record["era"],
                    "files":len(stats["actual_downloaded"]),"saved_bytes":len(jpeg)},
                    ensure_ascii=False),flush=True)
            except Exception as e:
                stats["rejects"]["failed_image_"+str(e)[:65]]+=1
        except Exception as e:
            if len(stats["errors"])<20:stats["errors"].append({"id":oid,"error":str(e)[:150]})
        time.sleep(.32)
    stats["actual_downloaded_count"]=len(stats["actual_downloaded"])
    stats["rejects"]=dict(stats["rejects"])
    (OUT/"report.json").write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding="utf-8")
    print("MET_REAL_FINAL "+json.dumps({"details_attempted":stats["details_tried"],
       "eligible_metadata":stats["metadata_qualified"],
       "verified_actual_image_files":stats["actual_downloaded_count"],
       "modern":sum(x["era"]=="1800-2026" for x in stats["actual_downloaded"]),
       "older":sum(x["era"]=="pre-1800" for x in stats["actual_downloaded"]),
       "errors":stats["errors"][:3],"all_259200_acquired":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
