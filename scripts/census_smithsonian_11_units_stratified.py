#!/usr/bin/env python3
"""Stratified public Smithsonian museum archive study, 11 units, 16 S3 shards each.
NO artwork image file downloads. Finds 2-D CC0 source records with original
image addresses and explicit creation-year hints. 1/16 sample per collection:
metadata counts are NOT estimated exact full-collection art totals.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from collections import Counter
import json,re,time
from pathlib import Path
from urllib.request import Request,urlopen
OUT=Path("audit-smithsonian-regional-2d")
OUT.mkdir(exist_ok=True)
UA="QuietArtGalleryMuseumDiscovery/1.0 (CC0 museum archive inspection; https://github.com/treesky0103-dot/quiet-art-gallery)"
BASE="https://smithsonian-open-access.s3-us-west-2.amazonaws.com/metadata/edan"
UNITS={
 "chndm":"Cooper Hewitt","saam":"Smithsonian American Art Museum",
 "npg":"National Portrait Gallery","fsg":"National Museum of Asian Art / Freer Sackler",
 "nmafa":"National Museum of African Art","hmsg":"Hirshhorn Museum and Sculpture Garden",
 "nmaahc":"National Museum of African American History and Culture",
 "nmah":"National Museum of American History",
 "nmai":"National Museum of the American Indian",
 "npm":"National Postal Museum","nasm":"National Air and Space Museum"}
SHARDS=[f"{i:02x}" for i in range(16)]
BAD=("sculpture","photograph","furniture","ceramic","stoneware","textile",
     "garment","medal","coin","vase","installation","film","video",
     "glass","models","model aircraft","house","fossil","documentary photograph")
GOOD=("painting","print","drawing","watercolor","watercolour","etching",
      "engraving","lithograph","illustration","woodcut","linocut","pastel",
      "collage","gouache","graphite","ink drawing")
MAX_BYTES_PER_SHARD=8*1024*1024

def flat(rec):
    c=rec.get("content") or {}
    objs=((c.get("freetext") or {}).get("objectType") or [])
    s=" ".join(str(x.get("content") or "") for x in objs if isinstance(x,dict)).lower()
    if any(v in s for v in BAD):return False
    return any(v in s for v in GOOD)
def explicit_date(rec):
    c=rec.get("content") or {}
    raw=" ".join(str(x.get("content") or "") for x in ((c.get("freetext") or {}).get("date") or []) if isinstance(x,dict))
    if not raw:return "unknown",None,None
    if re.search(r"\b(?:reprint|published|copyright|publication date)\b",raw,re.I):return "unknown",None,None
    y=[int(v) for v in re.findall(r"(?<!\d)(?:1[0-9]{3}|20[0-2][0-9])(?!\d)",raw)]
    if not y:return "unknown",None,None
    a,b=min(y),max(y)
    if a>=1800 and b<=2026:return "1800plus",a,b
    if b<1800:return "older",a,b
    return "unknown",a,b
def media(rec):
    c=rec.get("content") or {}
    dr=c.get("descriptiveNonRepeating") or {}
    if (dr.get("metadata_usage") or {}).get("access")!="CC0":return None
    ms=(dr.get("online_media") or {}).get("media") or []
    for m in ms:
        if m.get("type")!="Images":continue
        if (m.get("usage") or {}).get("access") not in ("CC0",None):continue
        sid=m.get("idsId")
        if sid:return {"idsId":sid,"width":m.get("width"),"height":m.get("height")}
    return None
def analyze(unit,shard):
    url=f"{BASE}/{unit}/{shard}.txt"
    try:
        req=Request(url,headers={"User-Agent":UA})
        with urlopen(req,timeout=30) as stream:
            b=stream.read(MAX_BYTES_PER_SHARD+1)
            if len(b)>MAX_BYTES_PER_SHARD:raise ValueError("S3 NDJSON shard >8MiB")
        c=Counter();samples=[]
        for line in b.splitlines():
            if not line:continue
            c["raw_rows"]+=1
            try:
                x=json.loads(line)
            except json.JSONDecodeError:
                c["broken_json"]+=1;continue
            if x.get("type")!="edanmdm":continue
            artwork_media=media(x)
            if not artwork_media:continue
            c["cc0_images"]+=1
            if not flat(x):
                c["nonflat"]+=1;continue
            c["cc0_2d"]+=1
            er,a,y=explicit_date(x)
            c["2d_year_"+er]+=1
            if er!="unknown" and len(samples)<4:
                dr=(x.get("content") or {}).get("descriptiveNonRepeating") or {}
                samples.append({"id":x.get("id"),
                     "title":str((dr.get("title") or {}).get("content") or "")[:160],
                     "record_id":dr.get("record_ID"),
                     "idsId":artwork_media["idsId"],"era":er,"year_start":a,
                     "year_end":y,"metadata_usage":"CC0"})
        return {"unit":unit,"shard":shard,"counts":dict(c),"samples":samples,"error":None}
    except Exception as e:
        return {"unit":unit,"shard":shard,"counts":{},"samples":[],"error":str(e)[:170]}
def main():
    tasks=[(u,shard) for u in UNITS for shard in SHARDS]
    totals={};sample_records=[];shards=[];errors=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(analyze,u,s):(u,s) for u,s in tasks}
        for future in as_completed(futures):
            result=future.result()
            shards.append({"unit":result["unit"],"shard":result["shard"],
                           "counts":result["counts"],"error":result["error"]})
            if result["error"]:errors.append({"unit":result["unit"],"shard":result["shard"],"error":result["error"]})
            c=totals.setdefault(result["unit"],Counter())
            c.update(result["counts"])
            for sample in result["samples"]:
                if sum(x["unit"]==result["unit"] for x in sample_records)>=8:break
                sample_records.append({**sample,"unit":result["unit"]})
            if len(shards)%40==0:
                print("SMITHSONIAN_REGIONAL_PROGRESS "+json.dumps({
                  "shards_processed":len(shards),"raw_records":sum(x["raw_rows"] for x in totals.values()),
                  "CC0_flat_art_hints":sum(x["cc0_2d"] for x in totals.values()),
                  "errors":len(errors)},ensure_ascii=False),flush=True)
    out={"sampled_shards_per_unit":len(SHARDS),"source_unit_count":len(UNITS),
       "sampled_shards_total":len(tasks),
       "all_units":{"%s_%s"%(unit,UNITS[unit]):dict(counts) for unit,counts in totals.items()},
       "shard_details":sorted(shards,key=lambda x:(x["unit"],x["shard"])),
       "samples":sample_records,"errors":errors,
       "actual_artwork_images_downloaded":0,"target_259200_reached":False,
       "not_full_smithsonian_census":True,
       "date_note":"Dates are museum descriptions, not independently checked actual creation years.",
       "copyright_note":"CC0 content descriptor, individual image rights and image pixel tests still required."}
    (OUT/"smithsonian_11_units_16_shards_cc0_2d.json").write_text(
         json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SMITHSONIAN_REGIONAL_FINAL "+json.dumps({
      "shards":len(shards),"unit_count":len(UNITS),
      "total_source_records":sum(x["raw_rows"] for x in totals.values()),
      "cc0_2d_metadata_hints":sum(x["cc0_2d"] for x in totals.values()),
      "1800plus_date_hints":sum(x["2d_year_1800plus"] for x in totals.values()),
      "older_date_hints":sum(x["2d_year_older"] for x in totals.values()),
      "error_count":len(errors),"actual_decoded_image_files":0},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
