#!/usr/bin/env python3
"""SMK (National Gallery Denmark) novel art source real-byte verification.

Museum public-domain works only. Date is production_date, not acquisition date
or artist birth/death. Metadata records do not count as acquired images.
"""
import hashlib, io, json, re, time
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,urlopen
from PIL import Image
BASE="https://api.smk.dk/api/v1/art/search/?"
OUT=Path("audit-smk-flat-art")
IMAGES=OUT/"samples"
IMAGES.mkdir(parents=True,exist_ok=True)
UA="QuietArtGallery/1.0 (public domain museum art research; https://github.com/treesky0103-dot/quiet-art-gallery)"
OFFSETS=(0,2000,5000,10000,20000,30000,38000)
MAX_FILES=12
MAX_FILE_BYTES=12*1024*1024
def fetch(url,binary=False,timeout=28):
    req=Request(url,headers={"User-Agent":UA,"Accept":"image/jpeg,*/*" if binary else "application/json"})
    with urlopen(req,timeout=timeout) as r:
        if r.status!=200:raise RuntimeError("HTTP "+str(r.status))
        if binary:
            b=r.read(MAX_FILE_BYTES+1)
            if len(b)>MAX_FILE_BYTES:raise RuntimeError("Image >12MB")
            return b
        return json.load(r)
def good_ratio(w,h):
    try:w,h=int(w),int(h)
    except (ValueError,TypeError):return False
    return w>=1000 and h>=1400 and w<h and min((w/h)/.625,.625/(w/h))>=.75
def date(work):
    dates=work.get("production_date") or []
    intervals=[]
    for x in dates:
        a=re.match(r"^(\d{4})-",str(x.get("start") or ""))
        b=re.match(r"^(\d{4})-",str(x.get("end") or ""))
        if a and b:
            a=int(a.group(1));b=int(b.group(1))
            if 0<a<=b<=2026:intervals.append((a,b))
    if not intervals:return None
    lo=min(x[0] for x in intervals);hi=max(x[1] for x in intervals)
    era="1800-2026" if lo>=1800 else "pre-1800" if hi<1800 else None
    if not era:return None
    return era,lo,hi
def kind(work):
    t=" ".join(x.get("name","") for x in (work.get("object_names") or []) if isinstance(x,dict))
    t+=" "+" ".join(str(x) for x in (work.get("techniques") or []))
    s=t.lower()
    excludes=("skulptur","skulptur","fotografi","photograph","keramik","møbler",
              "installation","video","postkort","bogbind","mønt")
    if any(x in s for x in excludes):return False
    return any(x in s for x in ("grafik","tegning","maleri","radering","akvarel",
              "træsnit","litograf","woodcut","painting","drawing",
              "pastel","tryk","engraving","etching","lithograph"))
def candidate(w):
    if w.get("public_domain") is not True:return None
    if not ("publicdomain" in str(w.get("rights") or "").lower() or
            "creativecommons.org/publicdomain" in str(w.get("rights") or "").lower()):return None
    if not kind(w):return None
    y=date(w)
    if not y:return None
    if not good_ratio(w.get("image_width"),w.get("image_height")):return None
    url=w.get("image_iiif_id") or ""
    if not url.startswith("https://iip.smk.dk/iiif/jp2/"):return None
    if not w.get("image_hq",False):return None
    if w.get("image_orientation")!="portrait":return None
    name=" ".join(x.get("title","") for x in (w.get("titles") or []) if isinstance(x,dict))
    return {"id":w.get("id"),"object_number":w.get("object_number"),
      "title":name[:180],"era":y[0],"year_start":y[1],"year_end":y[2],
      "license":w.get("rights"),"source_page":w.get("frontend_url"),
      "image_iiif":url,"source_width":w.get("image_width"),"source_height":w.get("image_height")}
def image_url(c):
    # Official IIIF JP2 endpoint publishes uncropped full image by max 2400px box.
    url=c["image_iiif"].replace("https://iip.smk.dk/","https://iip-thumb.smk.dk/").rstrip("/")
    return url+"/full/!2400,2400/0/default.jpg"
def main():
    all_candidates=[];metadata_seen=set();stats={"source":"SMK National Gallery Denmark",
      "rights_status":"Public Domain Mark","sampled_pages":[],"actual_downloaded":[],
      "errors":[],"original_corpus_claimed":0,"verified_259200":False}
    for offset in OFFSETS:
        url=BASE+urlencode({"keys":"*","filters":"[has_image:true],[public_domain:true]",
                           "offset":str(offset),"rows":"100"})
        try:
            payload=fetch(url)
            works=payload.get("items") or []
            count=0
            for w in works:
                c=candidate(w)
                if not c:continue
                if c["id"] in metadata_seen:continue
                metadata_seen.add(c["id"]);all_candidates.append(c);count+=1
            stats["original_corpus_claimed"]=payload.get("found")
            stats["sampled_pages"].append({"offset":offset,"returned":len(works),
                                           "qualified_metadata":count,"error":None})
        except Exception as e:
            stats["sampled_pages"].append({"offset":offset,"returned":0,
                                           "qualified_metadata":0,"error":str(e)[:200]})
        time.sleep(.4)
    stats["metadata_candidates_non_acquired"]=len(all_candidates)
    seen=set()
    # Mix eras; first 6 of each if available.
    for era in ("1800-2026","pre-1800"):
      for c in (x for x in all_candidates if x["era"]==era):
        if len(stats["actual_downloaded"])>=MAX_FILES:break
        if sum(a["era"]==era for a in stats["actual_downloaded"])>=6:break
        url=image_url(c)
        try:
            b=fetch(url,binary=True)
            im=Image.open(io.BytesIO(b));im.load()
            if im.format not in ("JPEG","PNG","WEBP") or not good_ratio(*im.size):continue
            rgb=im.convert("RGB")
            if rgb.height>2400:rgb=rgb.resize((round(rgb.width*2400/rgb.height),2400),Image.Resampling.LANCZOS)
            saved=io.BytesIO();rgb.save(saved,format="JPEG",quality=84,optimize=True)
            blob=saved.getvalue();sha=hashlib.sha256(blob).hexdigest()
            if sha in seen:continue
            filename=IMAGES/(sha[:24]+".jpg")
            filename.write_bytes(blob)
            reread=Image.open(filename);reread.load()
            assert reread.size==rgb.size and good_ratio(*reread.size)
            assert hashlib.sha256(filename.read_bytes()).hexdigest()==sha
            seen.add(sha)
            stats["actual_downloaded"].append({**c,"sha256":sha,
               "source_image_sha256":hashlib.sha256(b).hexdigest(),
               "saved_width":reread.width,"saved_height":reread.height,
               "saved_bytes":len(blob),"saved_file":str(filename),
               "download_url":url})
            print("SMK_ACTUAL "+json.dumps({"id":c["id"],"era":era,"bytes":len(blob),
                                          "count":len(stats["actual_downloaded"])}),flush=True)
        except Exception as e:
            if len(stats["errors"])<25:stats["errors"].append({"id":c["id"],"reason":str(e)[:200]})
        time.sleep(.15)
    stats["actual_verified_files"]=len(stats["actual_downloaded"])
    stats["actual_verified_modern"]=sum(x["era"]=="1800-2026" for x in stats["actual_downloaded"])
    stats["actual_verified_old"]=sum(x["era"]=="pre-1800" for x in stats["actual_downloaded"])
    (OUT/"report.json").write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SMK_FINAL "+json.dumps({"catalog_hits_not_verified":stats["original_corpus_claimed"],
        "sampled_metadata_candidates":len(all_candidates),"actual_downloaded_and_verified":stats["actual_verified_files"],
        "modern":stats["actual_verified_modern"],"earlier":stats["actual_verified_old"],
        "errors_sample":stats["errors"][:3],"complete":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
