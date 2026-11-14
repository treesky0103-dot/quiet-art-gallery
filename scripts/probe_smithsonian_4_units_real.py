#!/usr/bin/env python3
"""Actually download visible 2D public Smithsonian artworks from other museum units.

Input: 11-museum stratified S3 metadata evidence. This verifies decoded pixels
and source/saved hashes, but creation year remains an institutional DATE HINT
until per-artwork scholarly attribution review.
"""
import io,json,hashlib,time,re
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,urlopen
from PIL import Image
ROOT=Path("audit-smithsonian-more-actual")
SAMPLE=ROOT/"samples";SAMPLE.mkdir(parents=True,exist_ok=True)
FROM=Path("research-input/si/smithsonian_11_units_16_shards_cc0_2d.json")
UA="QuietArtGallerySmithsonianArtsProof/1.0 (CC0 museum sources; https://github.com/treesky0103-dot/quiet-art-gallery)"
UNITS=("npg","fsg","hmsg","nmaahc")
MAX_FILES=20
MAX_INPUT_BYTES=18*1024*1024
def eligible(w,h):
    try:w,h=int(w),int(h)
    except (ValueError,TypeError):return False
    return w>=1000 and h>=1400 and w<h and min((w/h)/.625,.625/(w/h))>=.75
def fetch(url):
    if urlsplit(url).hostname!="ids.si.edu":raise ValueError("Untrusted image host")
    req=Request(url,headers={"User-Agent":UA})
    with urlopen(req,timeout=28) as r:
        if r.status!=200:raise RuntimeError("HTTP "+str(r.status))
        b=r.read(MAX_INPUT_BYTES+1)
        if len(b)>MAX_INPUT_BYTES:raise RuntimeError("Too large")
        return b
def main():
    data=json.loads(FROM.read_text(encoding="utf-8"))
    assert data["actual_artwork_images_downloaded"]==0 and data["source_unit_count"]==11
    entries=[x for x in data["samples"] if x["unit"] in UNITS and
             x["era"] in ("1800plus","older") and
             re.fullmatch(r"[A-Za-z0-9_.-]{3,150}",str(x.get("idsId") or ""))]
    # Interleave museums to avoid sampling only a single institution's style.
    ordered=[]
    for i in range(8):
        for unit in UNITS:
            opts=[x for x in entries if x["unit"]==unit]
            if i<len(opts):ordered.append(opts[i])
    stats={"source":"Smithsonian Open Access 4 new art museums",
          "units":list(UNITS),"input_metadata":len(ordered),
          "downloads":[],"errors":[],"rejected":[],
          "completion_259200":False}
    hashes=set();modern=older=0
    for e in ordered:
        if len(stats["downloads"])>=MAX_FILES:break
        if e["era"]=="1800plus" and modern>=16:continue
        if e["era"]=="older" and older>=4:continue
        url="https://ids.si.edu/ids/deliveryService?"+urlencode({"id":e["idsId"],"max":"2400"})
        try:
            original=fetch(url)
            im=Image.open(io.BytesIO(original));im.load()
            if im.format not in ("JPEG","PNG","WEBP") or not eligible(*im.size):
                stats["rejected"].append({"id":e["record_id"],"reason":"actual_75pct_portrait_not_met"})
                continue
            im=im.convert("RGB")
            if im.height>2400:
                im=im.resize((round(im.width*2400/im.height),2400),Image.Resampling.LANCZOS)
            buf=io.BytesIO();im.save(buf,"JPEG",quality=84,optimize=True)
            out=buf.getvalue();h=hashlib.sha256(out).hexdigest()
            if h in hashes:continue
            file=SAMPLE/(h[:24]+".jpg");file.write_bytes(out)
            review=Image.open(file);review.load()
            assert eligible(*review.size) and hashlib.sha256(file.read_bytes()).hexdigest()==h
            hashes.add(h)
            stats["downloads"].append({**e,
                 "source":"Smithsonian "+e["unit"],
                 "artwork_id":e["record_id"],"era":"1800-2026" if e["era"]=="1800plus" else "pre-1800",
                 "sha256":h,"source_sha256":hashlib.sha256(original).hexdigest(),
                 "saved_file":str(file),"saved_width":review.width,"saved_height":review.height,
                 "bytes":len(out),"license":"Smithsonian CC0 open access"})
            if e["era"]=="1800plus":modern+=1
            else:older+=1
            print("SI_MORE_VERIFIED "+json.dumps({"unit":e["unit"],"era":e["era"],
                "count":len(stats["downloads"]),"bytes":len(out)},ensure_ascii=False),flush=True)
        except Exception as ex:
            if len(stats["errors"])<20:stats["errors"].append({"id":e["record_id"],"error":str(ex)[:170]})
        time.sleep(.15)
    stats["downloaded_verified_images"]=len(stats["downloads"])
    stats["modern_verified"]=modern
    stats["older_verified"]=older
    (ROOT/"report.json").write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SI_MORE_FINAL "+json.dumps({"file_decoded":stats["downloaded_verified_images"],
      "modern":modern,"older":older,"errors":stats["errors"][:3],
      "target_259200_complete":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
