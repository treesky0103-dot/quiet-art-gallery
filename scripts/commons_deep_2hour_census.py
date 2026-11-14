#!/usr/bin/env python3
"""Two-hour bounded public Commons ARTWORK METADATA census.

NEVER count search hits as acquired image files. Stores page id, photo metadata,
license tag, source category, original pixel dimensions and Commons SHA1; NONE
of this equals a verified local image JPEG / 259200 confirmed artworks.

Respect the public API with a descriptive User-Agent and paced sequential GET.
No paid account, API key or payment card.
"""
from collections import Counter,deque
import csv,gzip,hashlib,html,json,os,re,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen

OUT=Path("audit-commons-two-hour")
OUT.mkdir(exist_ok=True)
CSV=OUT/"commons_eligible_metadata_NOT_acquired.csv.gz"
UA="QuietArtGallery/1.0 (OpenAccess artwork audit; https://github.com/treesky0103-dot/quiet-art-gallery)"
API="https://commons.wikimedia.org/w/api.php"
DURATION=min(6950,max(30,int(os.environ.get("CENSUS_SECONDS","6900"))))
MAX_CATEGORIES=9000
MAX_SAVED=150000
MAX_CHILDREN_PER_CATEGORY=12
SLEEP=0.85
MIN_SHORT=1000
MIN_LONG=1400
TARGET_RATIO=.625
SAVE_FIELDS=["pageid","title","file_sha1_commons","width","height","mime",
             "license","categories_hit","year_evidence","image_url","source_page"]
ALLOW_LICENSE=re.compile(r"(?:^|[- ])(?:public\s*domain|pd|cc0|cc-by(?:-sa)?(?:\s|[-])[234]\.\d)",re.I)
DENY_TITLE=re.compile(r"\b(?:sculpture|statue|photograph of|photography of|gallery interior|museum room|installation|exhibition room|frame of|framed)\b",re.I)

def api(params,attempts=2):
    url=API+"?"+urlencode({"format":"json","formatversion":2,**params})
    for n in range(attempts):
        try:
            request=Request(url,headers={"User-Agent":UA,
                "Accept":"application/json","Accept-Encoding":"identity"})
            with urlopen(request,timeout=26) as r:
                if r.status!=200:raise RuntimeError(f"HTTP {r.status}")
                value=json.load(r)
            if "error" in value:raise ValueError(value["error"])
            return value
        except Exception as e:
            if n+1>=attempts:raise
            time.sleep(2*(n+1))

def category_seeds():
    years=[]
    for year in range(1800,2027):
        years.extend((f"{year} paintings",f"{year} drawings",f"{year} prints",
                     f"{year} illustrations"))
    period=[
        "19th-century paintings","20th-century paintings","21st-century paintings",
        "19th-century drawings","20th-century drawings","21st-century drawings",
        "19th-century prints","20th-century prints","21st-century prints",
        "19th-century engravings","20th-century engravings","19th-century illustrations",
        "20th-century illustrations","Modern paintings","Art museums",
    ]
    path=Path("research-input/global/candidate_commons_categories.csv")
    from_registry=[]
    if path.exists():
        with path.open(newline="",encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                cat=row.get("category") or ""
                if cat and len(cat)<180:from_registry.append(cat)
    data=period+years+from_registry
    unique=[];seen=set()
    for entry in data:
        title=entry.replace("Category:","").replace("_"," ").strip()
        if not title or title in seen:continue
        seen.add(title);unique.append(title)
    return unique

def artwork_year(category):
    # Provenance hint only: year-specific category is not independent per-artwork
    # creation-year evidence. Century/genre/museum categories are unknown.
    a=re.fullmatch(r"(1[89]\d\d|20[012]\d)\s+(?:paintings|drawings|prints|illustrations)",category,re.I)
    return int(a.group(1)) if a else None

def clean_value(s):
    return re.sub(r"<[^>]+>","",html.unescape(str(s or ""))).strip()

def metadata_provisional(page,category):
    info=(page.get("imageinfo") or [None])[0]
    if not info:return None,"missing_image"
    if info.get("mime","").lower() not in {"image/jpeg","image/png","image/webp"}:
        return None,"format"
    w,h=info.get("width"),info.get("height")
    if not isinstance(w,int) or not isinstance(h,int) or w<MIN_SHORT or h<MIN_LONG or w>=h:
        return None,"size"
    if min((w/h)/TARGET_RATIO,TARGET_RATIO/(w/h)) < .75:return None,"screenfill"
    if DENY_TITLE.search(str(page.get("title") or "")):return None,"nonart_filename"
    license_meta=(info.get("extmetadata") or {}).get("LicenseShortName") or {}
    license_name=clean_value(license_meta.get("value"))
    if not ALLOW_LICENSE.search(license_name):return None,"license_not_confirmed"
    url=info.get("url","")
    if not url.startswith("https://upload.wikimedia.org/"):return None,"url"
    pageid=page.get("pageid")
    if not isinstance(pageid,int):return None,"pageid"
    return {"pageid":pageid,"title":page.get("title") or "",
            "file_sha1_commons":info.get("sha1") or "",
            "width":w,"height":h,"mime":info.get("mime"),
            "license":license_name,
            "categories_hit":category,
            "year_evidence":artwork_year(category) or "",
            "image_url":url,
            "source_page":info.get("descriptionurl") or ""},None

def save_progress(started,stats,counters,pending_count,unique_count):
    report={
      "utc_logged_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "elapsed_seconds":round(time.monotonic()-started,2),
      "intended_seconds":DURATION,
      "source":"Wikimedia Commons public Action API; category member image metadata",
      "target_90day_total":259200,
      "target_post_1800":207360,
      "target_earlier":51840,
      "category_requests":stats["category_requests"],
      "subcat_requests":stats["subcat_requests"],
      "file_pages_parsed":stats["file_pages_parsed"],
      "file_metadata_records_examined":stats["file_metadata_records_examined"],
      "verified_image_downloads_this_census":0,
      "year_verified_image_files_this_census":0,
      "unique_provisional_metadata_candidates_seen":unique_count,
      "provisional_rows_saved":stats["saved"],
      "pending_queue_size":pending_count,
      "error_count":stats["errors"],
      "filter_failures":dict(counters),
      "acquisition_259200_complete":False,
      "disclaimer":"Metadata image-size/licence field checks only; image files NOT downloaded or decoded, year from category is an unverified category hint."}
    (OUT/"progress.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report

def main():
    started=time.monotonic()
    queue=deque((x,0,"files",None) for x in category_seeds())
    seed_count=len(queue)
    queued=set((x,0,"files",None) for x,_,_,_ in queue)
    visited={};seen_pages=set();seen_file_sha1=set()
    stats={"category_requests":0,"subcat_requests":0,
           "file_pages_parsed":0,"file_metadata_records_examined":0,
           "errors":0,"saved":0}
    counters=Counter()
    seen_cat=set()
    initial_categories=seed_count
    with gzip.open(CSV,"wt",newline="",encoding="utf-8",compresslevel=4) as output:
        writer=csv.DictWriter(output,fieldnames=SAVE_FIELDS)
        writer.writeheader()
        while queue and time.monotonic()-started<DURATION:
            cat,depth,kind,token=queue.popleft()
            task=(cat,depth,kind,token)
            queued.discard(task)
            if len(visited)>MAX_CATEGORIES and cat not in seen_cat:
                counters["max_category_cap"]+=1;continue
            try:
                if kind=="files":
                    args={"action":"query","generator":"categorymembers",
                      "gcmtitle":"Category:"+cat,"gcmnamespace":6,"gcmlimit":50,
                      "prop":"imageinfo","iiprop":"size|mime|extmetadata|url|sha1"}
                    if token:args["gcmcontinue"]=token
                    response=api(args)
                    stats["category_requests"]+=1
                    stats["file_pages_parsed"]+=1
                    pages=((response.get("query") or {}).get("pages") or [])
                    stats["file_metadata_records_examined"]+=len(pages)
                    for page in pages:
                        candidate,reason=metadata_provisional(page,cat)
                        if reason:
                            counters[reason]+=1;continue
                        ident=candidate["pageid"]
                        if ident in seen_pages:
                            counters["cross_category_page_duplicate"]+=1;continue
                        checksum=candidate["file_sha1_commons"]
                        if checksum and checksum in seen_file_sha1:
                            counters["cross_category_same_file_sha1"]+=1;continue
                        seen_pages.add(ident)
                        if checksum:seen_file_sha1.add(checksum)
                        if stats["saved"]<MAX_SAVED:
                            writer.writerow(candidate);stats["saved"]+=1
                        else:
                            counters["saved_limit_reached"]+=1
                    next_token=(response.get("continue") or {}).get("gcmcontinue")
                    if next_token and len(next_token)<1024:
                        nxt=(cat,depth,"files",next_token)
                        if nxt not in queued:queue.append(nxt);queued.add(nxt)
                    if cat not in seen_cat:
                        seen_cat.add(cat)
                        visited[cat]=depth
                        if depth<2:
                            nxt=(cat,depth,"subcats",None)
                            if nxt not in queued:queue.append(nxt);queued.add(nxt)
                else:
                    args={"action":"query","list":"categorymembers",
                          "cmtitle":"Category:"+cat,"cmnamespace":14,
                          "cmlimit":60}
                    response=api(args)
                    stats["subcat_requests"]+=1
                    members=((response.get("query") or {}).get("categorymembers") or [])
                    children=0
                    for entry in members:
                        title=(entry.get("title") or "").removeprefix("Category:")
                        if not title or title in seen_cat or len(title)>180:continue
                        child_name=title.lower()
                        # To keep semantic flat-art sources, skip museum rooms,
                        # portraits of buildings and mostly unrelated craft/media.
                        if any(x in child_name for x in ("sculpture","photograph","museum interiors",
                            "buildings","ceramics","textiles","architecture","statues")):continue
                        child=(title,depth+1,"files",None)
                        if child not in queued:
                            queue.append(child);queued.add(child);children+=1
                        if children>=MAX_CHILDREN_PER_CATEGORY:break
                if (stats["category_requests"]+stats["subcat_requests"])%50==0:
                    report=save_progress(started,stats,counters,len(queue),len(seen_pages))
                    print("CENSUS_PROGRESS "+json.dumps({
                      "elapsed_minutes":round(report["elapsed_seconds"]/60,2),
                      "requests":stats["category_requests"]+stats["subcat_requests"],
                      "examined":stats["file_metadata_records_examined"],
                      "metadata_candidates_not_images":len(seen_pages),
                      "pending":len(queue),"saved":stats["saved"]}),flush=True)
                    output.flush()
            except Exception as e:
                stats["errors"]+=1
                counters["request_errors"]+=1
                if stats["errors"]<=30:
                    print("SOURCE_ERROR "+json.dumps({
                      "category":cat,"kind":kind,"message":str(e)[:200]}),flush=True)
            # Gentle pacing for shared public APIs.
            time.sleep(SLEEP)
    result=save_progress(started,stats,counters,len(queue),len(seen_pages))
    result["seed_categories"]=initial_categories
    result["unique_scanned_categories"]=len(seen_cat)
    result["duration_reached"]=time.monotonic()-started>=DURATION
    result["all_seed_categories_exhausted"]=not bool(queue)
    (OUT/"final.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("CENSUS_FINAL "+json.dumps({k:result[k] for k in
       ("elapsed_seconds","seed_categories","unique_scanned_categories",
         "file_metadata_records_examined","provisional_rows_saved",
         "verified_image_downloads_this_census","acquisition_259200_complete",
         "duration_reached","all_seed_categories_exhausted")}),flush=True)

if __name__=="__main__":main()
