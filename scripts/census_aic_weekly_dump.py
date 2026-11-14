#!/usr/bin/env python3
"""Art Institute of Chicago official weekly JSON dump full 2D art census.

Downloads institutional metadata dump (NOT artwork image files). Determines
public-domain, dated 1800+ or older, flat art, image ID and approximate original
portrait dimensions. Never represents catalogue records as downloaded JPEGs.
"""
from collections import Counter
import csv,gzip,hashlib,io,json,re,tarfile,time
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path("audit-aic-dump-census")
ROOT.mkdir(exist_ok=True)
AGENT="QuietArtGalleryPublicArtResearch/1.0 (https://github.com/treesky0103-dot/quiet-art-gallery)"
URL="https://artic-api-data.s3.amazonaws.com/artic-api-data.tar.bz2"
MAX_DUMP=400*1024*1024
SRC=ROOT/"artic-api-data.tar.bz2"
FIELDS=["id","title","year_start","year_end","era","type","classification",
        "medium","image_id","thumbnail_width","thumbnail_height","rights","api_link"]
GOOD=("painting","drawing","print","woodblock","woodcut","etching","lithograph","engraving",
      "watercolor","watercolour","gouache","oil on","pastel","ink on","silkscreen","illustration")
BAD=("photograph","photographic","sculpture","video","installation","ceramic",
     "textile","costume","furniture","jewellery","coin","bookbinding","postcard",
     "architectural model","vessel","glassware")
def open_dump():
    if SRC.exists() and SRC.stat().st_size>1000000:return {"bytes":SRC.stat().st_size,"sha256":hashlib.sha256(SRC.read_bytes()).hexdigest()}
    req=Request(URL,headers={"User-Agent":AGENT})
    n=0;digest=hashlib.sha256()
    with urlopen(req,timeout=75) as r,SRC.open("wb") as output:
        if r.status!=200:raise RuntimeError("HTTP "+str(r.status))
        while True:
            block=r.read(1024*1024)
            if not block:break
            n+=len(block)
            if n>MAX_DUMP:raise RuntimeError("Official source metadata dump exceeds 400MiB cap")
            digest.update(block);output.write(block)
    return {"bytes":n,"sha256":digest.hexdigest()}
def flat(item):
    typ=str(item.get("artwork_type_title") or item.get("classification_title") or "")
    med=str(item.get("medium_display") or "")
    label=(typ+" "+med).lower()
    if any(x in label for x in BAD):return False
    return any(x in label for x in GOOD)
def period(item):
    a=item.get("date_start");b=item.get("date_end")
    if a is None or b is None:return "unknown"
    try:a=int(a);b=int(b)
    except (ValueError,TypeError):return "unknown"
    if not (-4000<=a<=b<=2026):return "unknown"
    if a>=1800:return "1800plus"
    if b<1800:return "older"
    return "unknown"
def ratio(w,h):
    if not isinstance(w,int) or not isinstance(h,int):return False
    if w<1000 or h<1400 or w>=h:return False
    return min((w/h)/.625,.625/(w/h))>=.75
def main():
    source_info=open_dump()
    print("AIC_DUMP_INFO "+json.dumps(source_info),flush=True)
    out=ROOT/"aic_flat_art_portrait_era_CANDIDATE_NOT_ACQUIRED.csv.gz"
    stats=Counter();ids=set();errors=[];first_examples=[]
    with gzip.open(out,"wt",newline="",encoding="utf-8",compresslevel=5) as fp:
        writer=csv.DictWriter(fp,fieldnames=FIELDS);writer.writeheader()
        with tarfile.open(SRC,mode="r|bz2") as tar:
            for member in tar:
                name=member.name
                if not (member.isfile() and re.search(r"(?:^|/)artworks/\d+\.json$",name)):
                    continue
                stats["artwork_metadata_records"]+=1
                if member.size>2*1024*1024:stats["oversize_metadata"]+=1;continue
                try:
                    f=tar.extractfile(member)
                    if f is None:continue
                    item=json.load(f)
                    # Each item is one API artwork record.
                    if not isinstance(item,dict):continue
                    if item.get("is_public_domain") is not True:
                        stats["not_public_domain"]+=1;continue
                    if not item.get("image_id"):
                        stats["missing_image_id"]+=1;continue
                    if not flat(item):
                        stats["not_flat_2d"]+=1;continue
                    er=period(item)
                    if er=="unknown":
                        stats["missing_or_ambiguous_year"]+=1;continue
                    dim=item.get("thumbnail") or {}
                    w=dim.get("width");h=dim.get("height")
                    if not ratio(w,h):
                        stats["not_metadata_portrait_75pct"]+=1;continue
                    id=str(item.get("id"))
                    if id in ids:stats["duplicate_artwork_id"]+=1;continue
                    ids.add(id)
                    record={"id":id,"title":str(item.get("title") or "")[:220],
                      "year_start":item.get("date_start"),"year_end":item.get("date_end"),
                      "era":er,"type":item.get("artwork_type_title"),
                      "classification":item.get("classification_title"),
                      "medium":str(item.get("medium_display") or "")[:150],
                      "image_id":item.get("image_id"),
                      "thumbnail_width":w,"thumbnail_height":h,
                      "rights":"source is_public_domain=true","api_link":item.get("api_link")}
                    writer.writerow(record)
                    stats["portrait_flat_era_candidate_"+er]+=1
                    if len(first_examples)<5:first_examples.append(record)
                except Exception as e:
                    stats["parse_failures"]+=1
                    if len(errors)<12:errors.append({"path":name,"error":str(e)[:200]})
                if stats["artwork_metadata_records"]%20000==0:
                    print("AIC_PROGRESS "+json.dumps({
                       "metadata_examined":stats["artwork_metadata_records"],
                       "modern_portrait_metadata":stats["portrait_flat_era_candidate_1800plus"],
                       "older_portrait_metadata":stats["portrait_flat_era_candidate_older"]}),flush=True)
    SRC.unlink(missing_ok=True)
    report={"source":"Art Institute of Chicago official weekly public data dump",
      "downloaded_dump":source_info,"records":dict(stats),"unique_candidate_ids":len(ids),
      "candidate_era_modern":stats["portrait_flat_era_candidate_1800plus"],
      "candidate_era_older":stats["portrait_flat_era_candidate_older"],
      "first_five_candidate_records":first_examples,"errors":errors,
      "actually_downloaded_decoded_image_files_this_run":0,
      "verified_259200":False,
      "caveats":[
        "Thumbnail aspect ratio is only a metadata proxy for original IIIF image ratio.",
        "Rights is derived from is_public_domain, must still verify media and individual use.",
        "IIIF image byte decoding and duplicate art identity not tested in this census.",
        "Weekly dump changed over time; source SHA256 and time from run logs identify this snapshot."]}
    (ROOT/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("AIC_FULL_DUMP_FINAL "+json.dumps({
        "source_metadata_records":stats["artwork_metadata_records"],
        "modern_portrait_metadata":stats["portrait_flat_era_candidate_1800plus"],
        "older_portrait_metadata":stats["portrait_flat_era_candidate_older"],
        "unknown_year":stats["missing_or_ambiguous_year"],
        "total_candidates_not_acquired":len(ids),"image_files_acquired":0,
        "completed_259200":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
