#!/usr/bin/env python3
"""Actual Art Institute Chicago IIIF painting/drawing/print byte acquisition from full official metadata dump.

Source provenance: GitHub Actions 43560933049, institutional is_public_domain,
explicit object production year + original thumbnail aspect/raster. This code
fetches and decodes *real* IIIF JPEG bytes, only counts saved artifact files.
"""
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlsplit
from PIL import Image
from collections import Counter
import csv,gzip,io,hashlib,json,re,time
OUT=Path("audit-aic-real-100")
FILES=OUT/"samples";FILES.mkdir(parents=True,exist_ok=True)
SOURCE=Path("research-input/aic/aic_flat_art_portrait_era_CANDIDATE_NOT_ACQUIRED.csv.gz")
AGENT="QuietArtGalleryAICVerifiedImage/1.0 (public-domain 2D artworks; https://github.com/treesky0103-dot/quiet-art-gallery)"
TARGET={"1800plus":80,"older":20}
MAX_TRIES=235
LIMIT=100
MAX_IMAGE=18*1024*1024
def good(w,h):
    try:w,h=int(w),int(h)
    except (ValueError,TypeError):return False
    return w>=1000 and h>=1400 and w<h and min((w/h)/.625,.625/(w/h))>=.75
def read_candidates():
    if not SOURCE.exists():raise FileNotFoundError(SOURCE)
    eras={"1800plus":[],"older":[]}
    with gzip.open(SOURCE,"rt",encoding="utf-8-sig",newline="") as f:
        for c in csv.DictReader(f):
            if c.get("era") not in eras:continue
            image_id=c.get("image_id")
            if not re.fullmatch(r"[a-zA-Z0-9-]{32,45}",str(image_id or "")):continue
            row={"record":c,"rank":int(hashlib.sha256(str(c.get("id")).encode()).hexdigest()[:12],16)}
            eras[c["era"]].append(row)
    for e in eras:eras[e]=[x["record"] for x in sorted(eras[e],key=lambda x:x["rank"])]
    seen=set();interleaved=[]
    for i in range(max(len(eras["1800plus"]),4*len(eras["older"]))):
        if i<len(eras["1800plus"]):
            row=eras["1800plus"][i]
            if row["id"] not in seen:interleaved.append(row);seen.add(row["id"])
        if i%4==0:
            j=i//4
            if j<len(eras["older"]):
                row=eras["older"][j]
                if row["id"] not in seen:interleaved.append(row);seen.add(row["id"])
        if len(interleaved)>=MAX_TRIES+50:break
    return interleaved,{x:len(y) for x,y in eras.items()}
def download_jpeg(row):
    url="https://www.artic.edu/iiif/2/"+row["image_id"]+"/full/!2400,2400/0/default.jpg"
    if urlsplit(url).hostname!="www.artic.edu":raise ValueError("Unexpected IIIF host")
    req=Request(url,headers={"User-Agent":AGENT,"Accept":"image/jpeg,image/png"})
    with urlopen(req,timeout=33) as f:
        if f.status!=200:raise RuntimeError("HTTP "+str(f.status))
        raw=f.read(MAX_IMAGE+1)
        if len(raw)>MAX_IMAGE:raise RuntimeError("Image above 18MB")
    with Image.open(io.BytesIO(raw)) as original:
        original.load()
        if original.format not in ("JPEG","PNG","WEBP") or not good(*original.size):
            raise ValueError("Downloaded image raster dimensions fail")
        img=original.convert("RGB")
        if img.height>2400:img=img.resize((round(img.width*2400/img.height),2400),Image.Resampling.LANCZOS)
        assert good(*img.size)
        memory=io.BytesIO();img.save(memory,"JPEG",quality=82,optimize=True)
        final=memory.getvalue()
    name=hashlib.sha256(final).hexdigest()[:24]+".jpg"
    f=FILES/name;f.write_bytes(final)
    reread=Image.open(f);reread.load()
    assert reread.format=="JPEG" and good(*reread.size)
    assert hashlib.sha256(f.read_bytes()).hexdigest()==hashlib.sha256(final).hexdigest()
    return {"sha256":hashlib.sha256(final).hexdigest(),
            "source_sha256":hashlib.sha256(raw).hexdigest(),
            "saved_file":str(f),"width":reread.width,"height":reread.height,
            "saved_bytes":len(final),"image_url":url}
def main():
    cand,counts=read_candidates()
    current={"1800plus":0,"older":0};tried=0
    stats={"source":"Art Institute of Chicago, public domain official weekly data dump",
      "metadata_candidates_by_era":counts,"actual_downloaded":[],
      "failures":[],"failure_kinds":Counter(),"attempts":0,"target_complete":False}
    seen_sha=set();ids=set()
    for row in cand:
        if len(stats["actual_downloaded"])>=LIMIT or tried>=MAX_TRIES:break
        er=row["era"]
        if current[er]>=TARGET[er]:continue
        if row["id"] in ids:continue
        tried+=1
        try:
            rec=download_jpeg(row)
            if rec["sha256"] in seen_sha:
                stats["failure_kinds"]["duplicate_saved_sha"]+=1
                continue
            seen_sha.add(rec["sha256"]);ids.add(row["id"])
            current[er]+=1
            stats["actual_downloaded"].append({**rec,
                 "source":"Art Institute of Chicago","id":row["id"],"era":er,
                 "year_start":row["year_start"],"year_end":row["year_end"],
                 "title":row["title"],"license":"Source is_public_domain=true"})
            if len(stats["actual_downloaded"])%10==0:
                print("AIC_REAL_PROGRESS "+json.dumps({"modern":current["1800plus"],
                    "older":current["older"],"decoded":len(stats["actual_downloaded"]),
                    "attempts":tried},ensure_ascii=False),flush=True)
        except Exception as e:
            key=str(e)[:140]
            stats["failure_kinds"][key]+=1
            if len(stats["failures"])<30:
                stats["failures"].append({"id":row["id"],"error":key})
        time.sleep(.23)
    stats["attempts"]=tried
    stats["verified_files"]=len(stats["actual_downloaded"])
    stats["verified_modern"]=current["1800plus"]
    stats["verified_older"]=current["older"]
    stats["failure_kinds"]=dict(stats["failure_kinds"])
    (OUT/"report.json").write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding="utf-8")
    print("AIC_REAL_FINAL "+json.dumps({"input_candidates":counts,
       "actual_decoded_files":stats["verified_files"],"modern":current["1800plus"],
       "older":current["older"],"attempts":tried,"failures":stats["failure_kinds"],
       "complete_259200":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
