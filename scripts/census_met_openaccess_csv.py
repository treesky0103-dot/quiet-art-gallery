#!/usr/bin/env python3
"""Metropolitan Museum official CC0 open-access CSV full art-type/year census.

No images in CSV. Only counts public-domain flat 2D artwork object metadata
with non-straddling dates; without actual JPEG dimensions no 75% confirmation.
Does not count metadata as verified downloaded images.
"""
import csv,gzip,hashlib,json,re,time
from pathlib import Path
from urllib.request import Request,urlopen
from collections import Counter
OUT=Path("audit-met-official-dump")
OUT.mkdir(exist_ok=True)
CSV=OUT/"MetObjects.csv"
URL="https://media.githubusercontent.com/media/metmuseum/openaccess/master/MetObjects.csv"
UA="QuietArtGallery/1.0 (museum open-data art year audit; https://github.com/treesky0103-dot/quiet-art-gallery)"
MAX_BYTES=450*1024*1024
GOOD=("painting","drawing","prints","print","etching","lithograph","woodcut",
 "watercolor","watercolour","engraving","illustration","linocut","gouache",
 "pastel","oil on","ink on paper","monotype","aquatint","water colour","wood engraving")
BAD=("photograph","sculpture","ceramic","pottery","textile","vessel","coin",
 "armor","jewelry","glass","clothing","furniture","musical instrument","decorative art",
 "stamp","architecture","metalwork","manuscript","bookbinding","photogravure")
FIELDS=["object_id","title","era","year_start","year_end","object_name",
 "classification","medium","rights","object_url"]
def download():
    dig=hashlib.sha256();bytes_=0
    req=Request(URL,headers={"User-Agent":UA,"Accept":"text/csv,*/*"})
    with urlopen(req,timeout=85) as r,CSV.open("wb") as out:
        if r.status!=200:raise RuntimeError("HTTP "+str(r.status))
        for _ in range(600):
            block=r.read(1024*1024)
            if not block:break
            bytes_+=len(block)
            if bytes_>MAX_BYTES:raise RuntimeError("The Met official file exceeds 450MiB cap")
            out.write(block);dig.update(block)
    if bytes_<1*1024*1024:raise RuntimeError("MetObjects CSV is missing or only an LFS pointer")
    return {"url":URL,"bytes":bytes_,"sha256":dig.hexdigest()}
def year(a,b):
    try:
        a,b=int(a),int(b)
        if not -4000<=a<=b<=2026:return "unknown"
        return "1800plus" if a>=1800 else "older" if b<1800 else "unknown"
    except (ValueError,TypeError):return "unknown"
def flat(o):
    s=(str(o.get("Object Name") or "")+" "+str(o.get("Classification") or "")+
       " "+str(o.get("Medium") or "")).lower()
    if any(x in s for x in BAD):return False
    return any(x in s for x in GOOD)
def main():
    src=download()
    print("MET_CSV_SOURCE "+json.dumps(src),flush=True)
    counts=Counter();errors=[];seen=set();examples=[]
    with gzip.open(OUT/"Met_2d_dated_cc0_CANDIDATES_not_downloaded.csv.gz",
        "wt",encoding="utf-8",newline="",compresslevel=5) as out:
        writer=csv.DictWriter(out,fieldnames=FIELDS);writer.writeheader()
        with CSV.open("r",encoding="utf-8-sig",errors="replace",newline="") as f:
            csv.field_size_limit(2000000)
            rd=csv.DictReader(f)
            columns=rd.fieldnames or []
            required={"Object ID","Is Public Domain","Object Begin Date","Object End Date"}
            if not required.issubset(columns):raise RuntimeError("Met source CSV schema missing core fields")
            for rec in rd:
                counts["records_examined"]+=1
                rights=str(rec.get("Is Public Domain") or "").lower()
                if rights not in ("true","1","yes"):
                    counts["not_public_domain"]+=1;continue
                if not flat(rec):
                    counts["not_2d_flat"]+=1;continue
                era=year(rec.get("Object Begin Date"),rec.get("Object End Date"))
                if era=="unknown":
                    counts["ambiguous_era"]+=1;continue
                oid=str(rec.get("Object ID") or "")
                if not oid.isdigit() or oid in seen:
                    counts["id_duplicate_or_missing"]+=1;continue
                seen.add(oid)
                data={"object_id":oid,"title":str(rec.get("Title") or "")[:220],
                      "era":era,"year_start":rec.get("Object Begin Date"),
                      "year_end":rec.get("Object End Date"),
                      "object_name":rec.get("Object Name"),"classification":rec.get("Classification"),
                      "medium":str(rec.get("Medium") or "")[:120],
                      "rights":"Is Public Domain=True","object_url":rec.get("Object URL")}
                writer.writerow(data)
                counts["flat_open_source_metadata_"+era]+=1
                if len(examples)<6:examples.append(data)
                if counts["records_examined"]%50000==0:
                    print("MET_PROGRESS "+json.dumps({
                       "examined":counts["records_examined"],
                       "cc0_modern_metadata":counts["flat_open_source_metadata_1800plus"],
                       "cc0_older_metadata":counts["flat_open_source_metadata_older"]}),flush=True)
    CSV.unlink(missing_ok=True)
    out={"source":src,"counters":dict(counts),"sample_work_records":examples,
       "unique_year_2d_cc0_metadata_candidates":len(seen),
       "modern_1800plus_metadata":counts["flat_open_source_metadata_1800plus"],
       "older_metadata":counts["flat_open_source_metadata_older"],
       "actual_JPEG_file_downloads":0,"verified_259200":False,
       "issues":[
         "The Met official CSV contains no images and no image dimensions.",
         "CSV public-domain status is from institutional metadata, image URL and JPEG verification remain.",
         "Production years may include uncertain author/period ranges; no 1800 crossover accepted.",
         "Catalogue dates or rights may change with updates; source SHA256 preserves this dump."]}
    (OUT/"report.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("MET_FULL_CENSUS_FINAL "+json.dumps({
      "rows_examined":counts["records_examined"],
      "modern_2d_publicdomain_metadata":counts["flat_open_source_metadata_1800plus"],
      "older_2d_publicdomain_metadata":counts["flat_open_source_metadata_older"],
      "source_metadata_candidates":len(seen),"actual_images_downloaded":0,
      "completed_259200":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
