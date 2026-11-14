#!/usr/bin/env python3
"""Independent bulk metadata census and small decoded-image proof for NGA and Rijks.

NGA includes source object records whose date ranges can reflect artist lifespans
rather than the object's creation date: ALL resulting counts are metadata candidates,
not approved 1800+ image counts until dates are confirmed independently.
Only actual downloaded, decoded, hashed JPEG files are proven local copies.
"""
import csv, hashlib, io, json, math, re, time
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT=Path("audit-nga-real-expanded")
ROOT.mkdir(exist_ok=True)
IMAGES=ROOT/"samples"
IMAGES.mkdir(exist_ok=True)
AGENT="QuietArtGalleryPublicResearch/1.0 (https://github.com/treesky0103-dot/quiet-art-gallery)"
BASE="https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data/"
YEARS=("18??","19??","20??")
TYPES=("print","drawing","painting")
CEILING=160*1024*1024

def request(url,timeout=32):
    req=Request(url,headers={"User-Agent":AGENT,"Accept":"application/json"})
    with urlopen(req,timeout=timeout) as f:
        if f.status!=200:raise RuntimeError("HTTP "+str(f.status))
        return json.load(f)

def download_csv(name):
    target=ROOT/name
    if target.exists() and target.stat().st_size>100: return target
    url=BASE+name
    req=Request(url,headers={"User-Agent":AGENT,"Accept":"text/csv"})
    digest=hashlib.sha256();size=0
    with urlopen(req,timeout=80) as stream,target.open("wb") as out:
        while True:
            blob=stream.read(1024*1024)
            if not blob:break
            size+=len(blob)
            if size>CEILING:raise RuntimeError("Unexpected NGA data file size")
            out.write(blob);digest.update(blob)
    print("NGA_DATA "+json.dumps({"name":name,"size":size,"sha256":digest.hexdigest()}),flush=True)
    return target

def is_flat(typ,medium):
    val=(str(typ or "")+" "+str(medium or "")).lower()
    denied=("photograph","sculpture","ceramic","statue","textile","vase","pottery",
            "furniture","jewelry","jewellery","glassware","drawing of architecture","installation")
    if any(x in val for x in denied):return False
    return any(x in val for x in ("painting","drawing","watercolor","watercolour","print",
                                  "etching","lithograph","woodcut","engraving","ink on paper",
                                  "gouache","illustration","oil on canvas","pastel"))
def parse_year(x):
    try:
        y=int(x)
        return y if -4000<=y<=2026 else None
    except (ValueError,TypeError):return None
def era(a,b):
    a=parse_year(a);b=parse_year(b)
    if a is None or b is None or a>b:return "unknown"
    if a>=1800:return "1800plus"
    if b<1800:return "older"
    return "unknown"
def portrait(w,h):
    try:w=int(w);h=int(h)
    except (ValueError,TypeError):return False
    if w>=h or w<1000 or h<1400:return False
    return min((w/h)/.625,.625/(w/h))>=.75
def nga_census():
    objects=download_csv("objects.csv")
    images=download_csv("published_images.csv")
    refs={};totals={"flat_date_qualified_1800plus":0,"flat_date_qualified_older":0,
                    "flat_date_unknown":0}
    with objects.open(newline="",encoding="utf-8-sig",errors="replace") as f:
        rd=csv.DictReader(f)
        print("NGA_OBJECT_COLUMNS "+json.dumps(rd.fieldnames),flush=True)
        for row in rd:
            row={str(k).lower():v for k,v in row.items() if k is not None}
            kind=row.get("classification") or row.get("classificationname") or ""
            medium=row.get("medium") or ""
            if not is_flat(kind,medium):continue
            e=era(row.get("beginyear"),row.get("endyear"))
            if e=="unknown":totals["flat_date_unknown"]+=1;continue
            oid=row.get("objectid")
            if not oid:continue
            refs[str(oid)]={"era":e,"title":row.get("title") or "",
                            "begin_year":row.get("beginyear"),"end_year":row.get("endyear"),
                            "type":kind,"medium":medium}
            totals["flat_date_qualified_"+e]+=1
    eligible={"1800plus":0,"older":0};samples={"1800plus":[],"older":[]}
    seen_objects={"1800plus":set(),"older":set()}
    image_rows=0;published_openaccess=0;portrait_openaccess=0
    with images.open(newline="",encoding="utf-8-sig",errors="replace") as f:
        rd=csv.DictReader(f)
        print("NGA_IMAGE_COLUMNS "+json.dumps(rd.fieldnames),flush=True)
        for row in rd:
            image_rows+=1
            if (row.get("openaccess") or "").strip()!="1":continue
            published_openaccess+=1
            if not portrait(row.get("width"),row.get("height")):continue
            portrait_openaccess+=1
            oid=str(row.get("depictstmsobjectid") or "")
            item=refs.get(oid)
            if not item:continue
            kind=item["era"]
            if oid in seen_objects[kind]:continue
            seen_objects[kind].add(oid)
            eligible[kind]+=1
            iiif=(row.get("iiifURL") or row.get("iiifurl") or "").strip()
            if len(samples[kind])<1000 and iiif.startswith("https://"):
                samples[kind].append({**item,"id":oid,"iiif":iiif,
                     "image_uuid":row.get("uuid") or "",
                     "original_width":row.get("width"),
                     "original_height":row.get("height"),
                     "openaccess":1})
    for p in (objects,images):p.unlink()
    return {"object_counts":totals,
            "total_image_metadata_rows":image_rows,
            "openaccess_image_metadata_rows":published_openaccess,
            "portrait_75pct_openaccess_image_metadata_rows":portrait_openaccess,
            "unique_flat_era_and_portrait_metadata_candidates":eligible,
            "rights":"NGA openaccess=1 only. Art year may fall back to artist lifespan, independent year validation needed.",
            "actual_downloaded_image_files":0},samples

def download_sample_nga(samples):
    from PIL import Image
    valid=[];errors=[];sha_set=set()
    already=set()
    ledger=Path("data/verified_80pct/verified_artwork_manifest.csv")
    if ledger.exists():
        with ledger.open(newline="",encoding="utf-8-sig") as fp:
            for row in csv.DictReader(fp):
                if row.get("source")=="National Gallery of Art":
                    already.add(row.get("artwork_id"))
    for e,goal in (("1800plus",50),("older",13)):
        for item in samples[e]:
            if item["id"] in already:continue
            if sum(x["era"]==e for x in valid)>=goal:break
            try:
                base=item["iiif"].rstrip("/")
                if urlsplit(base).hostname not in ("api.nga.gov","images.nga.gov"):
                    raise ValueError("Unrecognized NGA IIIF host")
                url=base+"/full/!2400,2400/0/default.jpg"
                req=Request(url,headers={"User-Agent":AGENT})
                with urlopen(req,timeout=32) as f:
                    raw=f.read(16*1024*1024+1)
                if len(raw)>16*1024*1024:raise ValueError("Image >16MB test limit")
                im=Image.open(io.BytesIO(raw));im.load()
                if not portrait(*im.size):raise ValueError("Image is not usable 75% portrait")
                if len(sha_set)!=len(valid):raise AssertionError("Internal hash registry issue")
                source_hash=hashlib.sha256(raw).hexdigest()
                if source_hash in sha_set:continue
                # JPEG visual copy is never cropped or upscaled.
                if im.height>2400:
                    im=im.convert("RGB")
                    im=im.resize((round(im.width*2400/im.height),2400),Image.Resampling.LANCZOS)
                encoded=io.BytesIO();im.convert("RGB").save(encoded,"JPEG",quality=84,optimize=True)
                content=encoded.getvalue()
                dest=IMAGES/(hashlib.sha256(content).hexdigest()[:24]+".jpg")
                dest.write_bytes(content)
                check=Image.open(dest);check.load()
                assert portrait(*check.size)
                sha_set.add(source_hash)
                valid.append({"source":"National Gallery of Art","object_id":item["id"],
                    "era":e,"source_sha256":source_hash,
                    "saved_sha256":hashlib.sha256(content).hexdigest(),
                    "title":item["title"],"begin_year":item["begin_year"],
                    "end_year":item["end_year"],"image_path":str(dest),
                    "width":check.width,"height":check.height,
                    "bytes":len(content),"license":"NGA open access image"})
            except Exception as ex:
                if len(errors)<30:errors.append({"era":e,"object_id":item["id"],
                                                  "reason":str(ex)[:130]})
    return valid,errors

def rijks_census():
    requests=[];errors=[];res={}
    for typ in TYPES:
        for cent in YEARS:
            url="https://data.rijksmuseum.nl/search/collection?"+urlencode({
                "type":typ,"creationDate":cent,"imageAvailable":"true"})
            try:
                data=request(url,timeout=36)
                count=(data.get("partOf") or {}).get("totalItems")
                first=data.get("orderedItems") or []
                if count is not None and not isinstance(count,int):count=int(count)
                res[typ+"_"+cent]={"search_records":count,
                                   "page_results":len(first),"query":url,
                                   "scope":"index hits, not byte-verified artworks"}
                print("RIJKS "+json.dumps({"type":typ,"century":cent,"count":count}),flush=True)
            except Exception as ex:
                errors.append({"type":typ,"century":cent,"error":str(ex)[:170]})
            time.sleep(.4)
    return {"index_searches":res,"errors":errors,
            "actual_downloaded_decoded_images":0,
            "warning":"Index totals may overlap, partial name match, and not prove 75% portrait images"}

def main():
    result={"target_total":259200,"target_1800plus":207360,"target_other":51840}
    try:
        result["nga"],samples=nga_census()
        result["nga_verified_images"],result["nga_download_errors"]=download_sample_nga(samples)
    except Exception as e:
        result["nga_error"]=str(e)[:300]
    try:result["rijks"]=rijks_census()
    except Exception as e:result["rijks_error"]=str(e)[:300]
    result["actual_259200_ready"]=False
    result["verified_image_files_this_run"]=len(result.get("nga_verified_images",[]))
    (ROOT/"audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("AUDIT_FINAL "+json.dumps({
      "nga_metadata_portrait_candidates":(result.get("nga") or {}).get("unique_flat_era_and_portrait_metadata_candidates"),
      "nga_downloaded_and_decoded":result["verified_image_files_this_run"],
      "rijks_counts":{k:v["search_records"] for k,v in (result.get("rijks") or {}).get("index_searches",{}).items()},
      "errors":[result.get("nga_error"),result.get("rijks_error")],
      "target_fully_acquired":False},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
