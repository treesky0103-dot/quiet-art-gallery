#!/usr/bin/env python3
"""Re-verify and consolidate ACTUAL BYTE VERIFIED 80% era art files.
Source artifacts must be downloaded from exact GitHub Actions run IDs.

The persistent GitHub manifest holds hashes, provenance, dates and artifact IDs,
not the actual JPEG bytes. Those bytes remain in temporary Actions artifacts.
Never claim 259200 durable image files have been stored or installed.
"""
from collections import Counter
import csv,hashlib,io,json
from pathlib import Path
from datetime import datetime,timezone
from PIL import Image
BASE=Path("tmp")
OUTPUT=Path("data/verified_80pct")
OUTPUT.mkdir(parents=True,exist_ok=True)
required={ "modern":207360, "older":51840, "all":259200 }
def read_csv(path):
    with path.open(newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))
def validate_file(filepath,hash_,w,h):
    blob=filepath.read_bytes()
    actual=hashlib.sha256(blob).hexdigest()
    if hash_!=actual:raise ValueError("Saved byte SHA-256 mismatch: "+str(filepath))
    im=Image.open(io.BytesIO(blob));im.load()
    width,height=im.size
    if width!=int(w) or height!=int(h):raise ValueError("Image dimension mismatch: "+str(filepath))
    if width<1000 or height<1400 or width>=height:raise ValueError("Resolution/portrait mismatch")
    if min((width/height)/.625,.625/(width/height))<.75:raise ValueError("75 percent portrait fill failure")
    return len(blob)
def add_to(records,inputs,stage,source,id,era,title,year1,year2,image_file,sha,source_sha,dh,rights,source_url,artifact):
    er={"1800-2026":"modern","pre-1800":"older","1800plus":"modern","older":"older"}.get(era)
    if not er:raise ValueError("Unexpected era "+str(era))
    size=validate_file(image_file,sha,*Image.open(image_file).size)
    r={"artifact":artifact,"stage":stage,"source":source,"artwork_id":id,
       "era":er,"title":title,"year_start":str(year1 or ""),"year_end":str(year2 or ""),
       "file_sha256":sha,"source_sha256":source_sha or "",
       "visual_dhash":dh or "","bytes":size,
       "rights":rights,"source_url":source_url}
    records.append(r)
    inputs.append({"stage":stage,"artifact":artifact,"file":str(image_file),"id":id})
def read_batch(path,stage,artifact,records,inputs):
    report=json.loads((path/"audit_report.json").read_text(encoding="utf-8"))
    rows=read_csv(path/"verified_downloaded_decoded.csv")
    assert len(rows)==report["actual_downloaded_decoded"]["all"]
    for row in rows:
        fp=path/"samples"/Path(row["file"]).name
        assert fp.exists(),str(fp)
        add_to(records,inputs,stage,row["source"],str(row["id"]),row["era"],
           row.get("title",""),row.get("year_start",""),row.get("year_end",""),fp,
           row["sha256"],row.get("source_sha256",""),row.get("dhash",""),
           row.get("license",""),row.get("source_url",""),artifact)
def read_nga(path,records,inputs):
    report=json.loads((path/"audit.json").read_text(encoding="utf-8"))
    actual=report.get("nga_verified_images",[])
    assert len(actual)==report["verified_image_files_this_run"]
    for row in actual:
        fp=path/"samples"/Path(row["image_path"]).name
        assert fp.exists(),str(fp)
        add_to(records,inputs,"nga",
          row["source"],str(row["object_id"]),row["era"],
          row.get("title",""),row.get("begin_year",""),row.get("end_year",""),fp,
          row["saved_sha256"],row.get("source_sha256",""),None,
          row.get("license",""),"NGA IIIF openaccess=1", "nga-rijks-1800-era-census-and-byte-proof")
def read_new_work(path,kind,records,inputs):
    filenames={
      "wellcome":("audit.json","files","work_id","saved_file","Wellcome Collection","wellcome-1800plus-flat-art-audit"),
      "smk":("report.json","actual_downloaded","id","saved_file","SMK Denmark","smk-1800-and-early-iiif-real-image-proof"),
      "smithsonian":("report.json","actual_downloaded","source_id","saved_file","Smithsonian","smithsonian-1800plus-and-older-actual-2d-art")
    }
    fn,list_key,id_key,file_key,source,artifact=filenames[kind]
    report=json.loads((path/fn).read_text(encoding="utf-8"))
    rows=report[list_key]
    if kind=="wellcome":
        assert len(rows)==report["byte_verified_image_files"]
    elif kind=="smk":
        assert len(rows)==report["actual_verified_files"]
    else:
        assert len(rows)==report["verified_byte_count"]
    for item in rows:
        if kind=="wellcome":
            era=item["era"]
            title=item.get("title","") or ""
            y1=item.get("year_start");y2=item.get("year_end")
            sha=item["sha256"]
            rights=item.get("license") or ""
            surl=item.get("source_url") or ""
            source_sha=""
        elif kind=="smk":
            era=item["era"]
            title=item.get("title") or ""
            y1=item.get("year_start");y2=item.get("year_end")
            sha=item["sha256"]
            rights=item.get("license") or ""
            surl=item.get("source_page") or ""
            source_sha=item.get("source_image_sha256") or ""
        else:
            era=item["era"]
            title=item.get("title") or ""
            y1=item.get("year_start");y2=item.get("year_end")
            sha=item["sha256"]
            rights=item.get("license") or ""
            surl=item.get("source_url") or ""
            source_sha=item.get("source_sha256") or ""
        fp=path/"samples"/Path(item[file_key if kind!="wellcome" else "file_path"]).name
        if not fp.exists():raise FileNotFoundError(fp)
        add_to(records,inputs,kind,source,str(item[id_key]),era,title,
           y1,y2,fp,sha,source_sha,None,rights,surl,artifact)
def read_iiif_art(path,kind,records,inputs):
    cfg={
        "yale":("Yale Center for British Art","saved_sha256","artwork_id","yale-cc0-2d-actual-iiif-byte-proof"),
        "rijks":("Rijksmuseum","sha256","object_id","rijks-cc0-iiif-actual-portrait-art-proof")
    }
    source,sha_key,id_key,artifact=cfg[kind]
    report=json.loads((path/"report.json").read_text(encoding="utf-8"))
    items=report["actual_downloaded"]
    if kind=="yale":assert len(items)==report["real_files_verified"]
    else:assert len(items)==report["actual_downloaded_count"]
    for item in items:
        fp=path/"samples"/Path(item["saved_file"]).name
        if not fp.exists():raise FileNotFoundError(str(fp))
        add_to(records,inputs,kind,source,str(item[id_key]),
               item["era"],item.get("title") or "",
               item.get("year_start"),item.get("year_end"),fp,
               item[sha_key],item.get("source_sha256") or "",None,
               item.get("license") or "",
               item.get("image_url") or item.get("source_image_url") or "",
               artifact)
def main():
    records=[];inputlog=[]
    read_batch(BASE/"baseline","baseline40","verified-1800plus-80pct-paintings-sample",records,inputlog)
    for n in (101,102,103,104):
        read_batch(BASE/"batches"/f"verified-real-paintings-batch-{n}",
                  f"batch{n}",f"verified-real-paintings-batch-{n}",records,inputlog)
    read_nga(BASE/"nga",records,inputlog)
    for source in ("wellcome","smk","smithsonian"):
        read_new_work(BASE/source,source,records,inputlog)
    for source in ("yale","rijks"):
        read_iiif_art(BASE/source,source,records,inputlog)
    unique=[];duplicate_id=[];duplicate_sha=[];near_pairs=[]
    source_ids={};file_hashes={};previous_dhash=[]
    for r in records:
        key=(r["source"],r["artwork_id"])
        if key in source_ids:
            duplicate_id.append({"source":r["source"],"id":r["artwork_id"],"prior_stage":source_ids[key]["stage"],"later_stage":r["stage"]})
            continue
        if r["file_sha256"] in file_hashes:
            duplicate_sha.append({"sha256":r["file_sha256"],"prior_stage":file_hashes[r["file_sha256"]]["stage"],"later_stage":r["stage"]})
            continue
        if len(r["visual_dhash"])==16:
            try:val=int(r["visual_dhash"],16)
            except ValueError:val=None
            if val is not None:
                for prev,prior in previous_dhash:
                    if (val^prev).bit_count()<=5:
                        near_pairs.append({"new_source":r["source"],"new_id":r["artwork_id"],
                                         "prior_source":prior["source"],"prior_id":prior["artwork_id"]})
                previous_dhash.append((val,r))
        source_ids[key]=r;file_hashes[r["file_sha256"]]=r
        unique.append(r)
    modern=sum(x["era"]=="modern" for x in unique)
    older=sum(x["era"]=="older" for x in unique)
    assert len(unique)==modern+older
    assert len(unique)<=259200
    # IMPORTANT: metadata+hash validity does not certify creator/edition independence.
    with (OUTPUT/"verified_artwork_manifest.csv").open("w",encoding="utf-8-sig",newline="") as f:
        fieldnames=list(unique[0])
        writer=csv.DictWriter(f,fieldnames=fieldnames);writer.writeheader();writer.writerows(unique)
    output={"as_of_utc":datetime.now(timezone.utc).isoformat(),
        "target":required,"reported_input_files":len(records),
        "exact_duplicate_source_ids_removed":len(duplicate_id),
        "exact_duplicate_image_hashes_removed":len(duplicate_sha),
        "unique_verified_file_and_source_id_count":len(unique),
        "verified_1800plus":modern,"verified_older":older,
        "actual_modern_share_percent":round(100*modern/len(unique),4) if unique else 0,
        "missing_1800plus":207360-modern,
        "missing_older":51840-older,
        "missing_total":259200-len(unique),
        "suspected_visual_duplicate_pairs_requiring_review":len(near_pairs),
        "visual_pairs_first_30":near_pairs[:30],
        "duplicate_ids_sample":duplicate_id[:30],
        "duplicate_image_hashes_sample":duplicate_sha[:30],
        "all_259200_acquired":False,
        "evidence":{"baseline":"GitHub Actions 43555200749",
                    "four_batches":"GitHub Actions 43557017166",
                    "national_gallery_of_art":"GitHub Actions 43557443707",
                    "wellcome":"GitHub Actions 43558532875",
                    "smk":"GitHub Actions 43559855032",
                    "smithsonian":"GitHub Actions 43560141359",
                    "yale":"GitHub Actions 43561581690",
                    "rijks":"GitHub Actions 43561741983"},
        "limitations":[
            "Actual JPEG bytes remain in expiring GitHub Actions artifacts, not in this repository manifest.",
            "NGA museum creation-year ranges can use artist lifespans; independent per-artwork era audit incomplete.",
            "Perceptual similarity flags are not a conclusive same-work identity test.",
            "All 259200 durable local image files have NOT been acquired.",
            "Tablet APK unchanged; 90-day gap-free 30-sec playback NOT verified."
        ]}
    (OUTPUT/"cumulative_audit.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print("CUMULATIVE_VERIFIED "+json.dumps({k:output[k] for k in
      ("reported_input_files","exact_duplicate_source_ids_removed",
       "exact_duplicate_image_hashes_removed","unique_verified_file_and_source_id_count",
       "verified_1800plus","verified_older","missing_total",
       "suspected_visual_duplicate_pairs_requiring_review","all_259200_acquired")},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
