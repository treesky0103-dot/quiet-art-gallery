#!/usr/bin/env python3
"""Complete paginated SMK public-domain metadata audit, NOT downloaded image count.

The SMK search endpoint reports ~39k public domain image-bearing records.
This enumerates the full keyless result set under API caps, filters creation
year / 2D type / actual original image dimensions, without inflating to
"actual acquired" images.
"""
from collections import Counter
import csv,gzip,hashlib,json,re,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
OUT=Path("audit-smk-metadata-census")
OUT.mkdir(exist_ok=True)
UA="QuietArtGalleryArtSupplyAudit/1.0 (public non-commercial open data; https://github.com/treesky0103-dot/quiet-art-gallery)"
URL="https://api.smk.dk/api/v1/art/search/?"
ROW_LIMIT=500
MAX_PAGES=120
SLEEP=0.6
CANDIDATES=OUT/"smk_75pct_era_metadata_candidates.csv.gz"
FIELDS=["id","object_number","title","kind","era","year_start","year_end",
        "image_width","image_height","image_iiif_id","rights","frontend_url"]

def request(offset,retries=3):
    url=URL+urlencode({"keys":"*","filters":"[has_image:true],[public_domain:true]",
                      "offset":offset,"rows":ROW_LIMIT})
    last=None
    for i in range(retries):
        try:
            req=Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
            with urlopen(req,timeout=34) as res:
                if res.status!=200:raise RuntimeError("HTTP "+str(res.status))
                return json.load(res)
        except Exception as e:
            last=e
            if i+1<retries:time.sleep(1.2*(i+1))
    raise last

def year_dates(x):
    dates=x.get("production_date") or []
    intervals=[]
    for date in dates:
        a=re.match(r"^(\d{4})",str(date.get("start") or ""))
        b=re.match(r"^(\d{4})",str(date.get("end") or ""))
        if a and b:
            lo=int(a.group(1));hi=int(b.group(1))
            if 0<lo<=hi<=2026:intervals.append((lo,hi))
    if not intervals:return "unknown",None,None
    lo=min(x[0] for x in intervals);hi=max(x[1] for x in intervals)
    if lo>=1800:return "1800plus",lo,hi
    if hi<1800:return "older",lo,hi
    return "straddles1800",lo,hi

def flat_kind(x):
    names=" ".join(k.get("name","") for k in (x.get("object_names") or []) if isinstance(k,dict))
    tex=" ".join(x.get("techniques") or [])
    s=(names+" "+tex).lower()
    if any(t in s for t in ("skulptur","fotografi","photograph","keramik","porcelæn",
        "møbler","installation","postkort","bogbind","mønt","textil",
        "vase","glass","statuette")):return False,s[:60]
    return any(t in s for t in ("grafik","tegning","maleri","radering","akvarel","træsnit",
        "litograf","woodcut","painting","drawing","pastel","tryk",
        "engraving","etching","lithograph")),s[:60]

def eligible(x):
    if x.get("public_domain") is not True:return None,"rights"
    if "publicdomain" not in str(x.get("rights") or ""):return None,"license"
    ok,kind=flat_kind(x)
    if not ok:return None,"non_flat_type"
    year,lo,hi=year_dates(x)
    if year not in ("1800plus","older"):return None,year
    if x.get("image_orientation")!="portrait":return None,"not_portrait_flag"
    try:w,h=int(x.get("image_width")),int(x.get("image_height"))
    except (ValueError,TypeError):return None,"missing_dimensions"
    if w<1000 or h<1400 or w>=h:return None,"resolution"
    if min((w/h)/.625,.625/(w/h))<.75:return None,"portrait_screenfill"
    url=x.get("image_iiif_id") or ""
    if not url.startswith("https://iip.smk.dk/iiif/jp2/"):return None,"iiif_missing"
    title=" ".join(t.get("title","") for t in (x.get("titles") or []) if isinstance(t,dict))
    return {"id":x.get("id"),"object_number":x.get("object_number"),
         "title":title[:180],"kind":kind,"era":year,"year_start":lo,"year_end":hi,
         "image_width":w,"image_height":h,"image_iiif_id":url,
         "rights":x.get("rights"),"frontend_url":x.get("frontend_url")},None

def main():
    seen=set();counts=Counter();errors=[];pages=[];found_total=None
    with gzip.open(CANDIDATES,"wt",encoding="utf-8",newline="",compresslevel=5) as out:
        writer=csv.DictWriter(out,fieldnames=FIELDS);writer.writeheader()
        for i in range(MAX_PAGES):
            offset=i*ROW_LIMIT
            if found_total is not None and offset>=found_total:break
            try:
                result=request(offset)
                works=result.get("items") or []
                found_total=int(result.get("found") or 0)
                if not works:
                    pages.append({"offset":offset,"returned":0,"error":None})
                    break
                for obj in works:
                    counts["metadata_records_examined"]+=1
                    cand,err=eligible(obj)
                    if not cand:
                        counts["reject_"+str(err)]+=1
                        continue
                    key=str(cand["id"])
                    if not key or key in seen:
                        counts["duplicate_id"]+=1
                        continue
                    seen.add(key);writer.writerow(cand)
                    counts["candidates_"+cand["era"]]+=1
                pages.append({"offset":offset,"returned":len(works),"error":None})
                if i%10==0:
                    print("SMK_CENSUS_PROGRESS "+json.dumps({
                        "page":i,"total_claimed_metadata":found_total,
                        "examined":counts["metadata_records_examined"],
                        "modern_metadata_candidates":counts["candidates_1800plus"],
                        "older_metadata_candidates":counts["candidates_older"]},ensure_ascii=False),flush=True)
            except Exception as e:
                errors.append({"offset":offset,"error":str(e)[:170]})
                pages.append({"offset":offset,"returned":0,"error":str(e)[:170]})
            time.sleep(SLEEP)
    output={
      "source":"SMK National Gallery of Denmark / keyless official API",
      "claimed_eligible_search_results_unverified":found_total,
      "pages":pages,"error_count":len(errors),"errors":errors,
      "record_counts":dict(counts),"unique_portrait_flat_art_metadata_candidates":len(seen),
      "actual_downloaded_image_files_this_run":0,
      "complete_for_259200":False,
      "limitations":[
         "Only source metadata image width/height, not decoded actual files.",
         "Only explicit bounded production_date kept, not artist birth or acquisition year.",
         "Rejections may be conservative for unrecognized Danish art-type labels.",
         "Actual file license, duplicated works in other museums, image cache response must be audited separately.",
         "Page errors do NOT imply an empty source or a complete census."] }
    (OUT/"summary.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SMK_CENSUS_FINAL "+json.dumps({
      "total_unverified_search_results":found_total,"pages":len(pages),
      "errors":len(errors),"sampled_records":counts["metadata_records_examined"],
      "candidate_modern":counts["candidates_1800plus"],
      "candidate_older":counts["candidates_older"],
      "actual_file_download_count":0,"target_complete":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
