#!/usr/bin/env python3
"""Complete CMA dated CC0 2D flat-art portrait metadata census (not image downloads).

Uses institution-issued date ranges, classification, actual source pixel metadata,
and CC0 image flags. Ensures no unfinished pagination is represented as total.
"""
import csv,gzip,json,time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
OUT=Path("audit-cma-full-metadata")
OUT.mkdir(exist_ok=True)
UA="QuietArtGallery/1.0 (public Cleveland art data audit; https://github.com/treesky0103-dot/quiet-art-gallery)"
ROOT="https://openaccess-api.clevelandart.org/api/artworks/"
PAGE=1000
FIELDS=["id","accession_number","title","era","year_start","year_end",
        "type","technique","image_url","image_width","image_height",
        "source_url","share_license_status"]
BAD=("photograph","ceramic","sculpture","installation","metalwork","textile",
     "pottery","furniture","jewelry","jewellery","costume","vase","illustrated book",
     "books","poster for","stained glass","coin","architectur")
GOOD=("painting","drawing","print","engraving","lithograph","etching",
      "watercolor","watercolour","woodcut","ink on","oil on","gouache",
      "pastel","illustration","linocut","serigraph")
def fetch(era,offset):
    q={"has_image":1,"limit":PAGE,"skip":offset,
       "created_before":1800 if era=="older" else 2027}
    if era=="modern":q["created_after"]=1799
    url=ROOT+"?"+urlencode(q)+"&cc0"
    last=None
    for i in range(3):
        try:
            req=Request(url,headers={"User-Agent":UA})
            with urlopen(req,timeout=35) as f:
                if f.status!=200:raise RuntimeError("HTTP "+str(f.status))
                return json.load(f)
        except Exception as e:
            last=e
            if i<2:time.sleep(1.8*(i+1))
    raise last
def kind(item):
    v=(str(item.get("type") or "")+" "+str(item.get("technique") or "")).lower()
    if any(x in v for x in BAD):return False
    return any(x in v for x in GOOD)
def target(item,expected):
    if not kind(item):return None,"not_2d_kind"
    if str(item.get("share_license_status") or "").lower()!="cc0":return None,"not_cc0"
    start=item.get("creation_date_earliest");end=item.get("creation_date_latest")
    if start is None or end is None:return None,"missing_year"
    try:start=int(start);end=int(end)
    except (ValueError,TypeError):return None,"bad_year"
    if not -4000<=start<=end<=2026:return None,"bad_year"
    era="modern" if start>=1800 else "older" if end<1800 else "unknown"
    if era!=expected:return None,"date_ambiguous_or_wrong"
    images=item.get("images") or {}
    im=images.get("print") or images.get("web") or {}
    try:w=int(im["width"]);h=int(im["height"])
    except (ValueError,KeyError,TypeError):return None,"missing_image_dims"
    if w<1000 or h<1400 or w>=h:return None,"resolution_orientation"
    if min((w/h)/.625,.625/(w/h))<.75:return None,"screenfill"
    url=str(im.get("url") or "")
    if not url.startswith("https://openaccess-cdn.clevelandart.org/"):return None,"nonofficial_img_url"
    return {"id":item.get("id"),"accession_number":item.get("accession_number"),
       "title":item.get("title"),"era":era,"year_start":start,"year_end":end,
       "type":item.get("type"),"technique":item.get("technique"),
       "image_url":url,"image_width":w,"image_height":h,"source_url":item.get("url"),
       "share_license_status":"CC0"},None
def main():
    candidates=OUT/"CMA_75pct_CC0_era_candidates_NOT_ACQUIRED.csv.gz"
    page_reports=[];counts=Counter();source_totals={};seen=set();errors=[]
    with gzip.open(candidates,"wt",newline="",encoding="utf-8",compresslevel=5) as fp:
        writer=csv.DictWriter(fp,fieldnames=FIELDS);writer.writeheader()
        for era in ("modern","older"):
            offset=0;expected_total=None;pages=0
            while pages<60:
                if expected_total is not None and offset>=expected_total:break
                try:
                    data=fetch(era,offset)
                    total=int((data.get("info") or {}).get("total") or 0)
                    source_totals[era]=total;expected_total=total
                    arts=data.get("data") or []
                    if not arts:break
                    qcount=0
                    for art in arts:
                        counts["metadata_examined"]+=1
                        result,reason=target(art,era)
                        if reason:
                            counts["reject_"+reason]+=1;continue
                        aid=str(result["id"])
                        if aid in seen:
                            counts["duplicate_id"]+=1;continue
                        seen.add(aid);writer.writerow(result)
                        counts["candidate_"+era]+=1;qcount+=1
                    page_reports.append({"era":era,"offset":offset,"returned":len(arts),
                         "eligible_metadata":qcount,"error":None})
                    if pages%5==0:
                        print("CMA_PAGED_PROGRESS "+json.dumps({"era":era,"offset":offset,
                           "claimed_total":total,"metadata_candidates":counts["candidate_"+era]},ensure_ascii=False),flush=True)
                    offset+=len(arts);pages+=1
                except Exception as e:
                    errors.append({"era":era,"offset":offset,"error":str(e)[:200]})
                    page_reports.append({"era":era,"offset":offset,"returned":0,
                                         "eligible_metadata":0,"error":str(e)[:200]})
                    # Do not silently skip unknown pages; report partial.
                    break
                time.sleep(.75)
            counts["completed_pages_"+era]=pages
            counts["cursor_"+era]=offset
            counts["scanning_complete_"+era]=expected_total is not None and offset>=expected_total
    report={"dataset":"Cleveland Museum of Art official CC0 public artwork API",
      "catalog_results_unverified":source_totals,
      "filter_pass_metadata_by_era":{"modern":counts["candidate_modern"],"older":counts["candidate_older"]},
      "unique_candidate_metadata_not_downloaded":len(seen),
      "page_reports":page_reports,"counters":dict(counts),"errors":errors,
      "actual_image_bytes_downloaded":0,"complete_259200":False,
      "note":"Open-access CC0 status, image-resolution and 1800 year ranges are from official JSON, not independently decoded files."}
    (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("CMA_FULL_METADATA_FINAL "+json.dumps({"catalog_counts":source_totals,
      "modern_candidates":counts["candidate_modern"],"older_candidates":counts["candidate_older"],
      "modern_fully_scanned":counts["scanning_complete_modern"],
      "older_fully_scanned":counts["scanning_complete_older"],
      "errors":len(errors),"actual_files_downloaded":0},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
