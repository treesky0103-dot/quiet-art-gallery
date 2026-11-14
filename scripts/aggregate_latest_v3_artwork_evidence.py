#!/usr/bin/env python3
"""V3 cross-source gallery provenance ledger.

Old 498 works are inherited from prior independently byte-verified GitHub
manifest; their image bytes are NOT re-downloaded here. New official source
artifacts are re-opened JPEG-by-JPEG to verify sha256 and pixels before adding.
Metadata and artwork identity across museums must still receive expert review.
Do not confuse provisional image file uniqueness with all-artworks uniqueness.
"""
import csv,hashlib,io,json,unicodedata,re
from collections import Counter
from pathlib import Path
from datetime import datetime,timezone
from PIL import Image
BASE=Path("research-input/v3")
ROOT=Path("data/verified_80pct")
ROOT.mkdir(exist_ok=True)
CSV_PATH=ROOT/"verified_artwork_manifest.csv"
SUMMARY=ROOT/"cumulative_audit.json"
FIELDS=["artifact","stage","source","artwork_id","era","title",
        "year_start","year_end","file_sha256","source_sha256","visual_dhash",
        "bytes","rights","source_url"]
ROOTS={
 "met":("audit-met-real-art","report.json","actual_downloaded"),
 "si_extra":("audit-smithsonian-more-actual","report.json","downloads"),
 "rijks_more":("audit-rijks-expanded-actual","report.json","actual_downloaded"),
 "nga_more":("audit-nga-real-expanded","audit.json","nga_verified_images"),
 "aic":("audit-aic-real-100","report.json","actual_downloaded")
}
ARTIFACT={
 "met":"metropolitan-original-cc0-iiif-jpeg-portrait-art-proof",
 "si_extra":"smithsonian-four-additional-museums-cc0-art-jpeg-files",
 "rijks_more":"rijks-80percent-expanded-2d-verified-file-batch",
 "nga_more":"national-gallery-of-art-second-cc0-portrait-image-files",
 "aic":"chicago-100-real-cc0-80pct-painting-iiif-jpeg"
}
def era(v):
    if v in ("1800-2026","1800plus","modern"):return "modern"
    if v in ("pre-1800","older"):return "older"
    raise ValueError("Unexpected era value: "+str(v))
def fhash(image):
    im=image.convert("L").resize((9,8),Image.Resampling.LANCZOS)
    p=list(im.getdata())
    diff=max(p)-min(p)
    if diff<18:return ""
    value=0
    for y in range(8):
        for x in range(8):
            value=value*2+int(p[y*9+x]>p[y*9+x+1])
    return f"{value:016x}"
def validate(path,sha):
    b=path.read_bytes()
    assert hashlib.sha256(b).hexdigest()==sha, "Image file SHA-256 mismatch: "+str(path)
    with Image.open(io.BytesIO(b)) as im:
        im.load()
        w,h=im.size
        assert im.format=="JPEG" and w>=1000 and h>=1400 and w<h
        assert min((w/h)/.625,.625/(w/h))>=.75
        ph=fhash(im)
    return len(b),ph
def normalize(item,kind):
    if kind=="met":
        return {"source":"Metropolitan Museum of Art","id":item["id"],
            "era":item["era"],"title":item["title"],"start":item["year_start"],"end":item["year_end"],
            "sha":item["sha256"],"source_sha":item["source_sha256"],"file":item["saved_file"],
            "rights":item["license"],"url":item.get("source_url") or item.get("source_image") or ""}
    if kind=="si_extra":
        return {"source":item["source"],"id":item["artwork_id"],
            "era":item["era"],"title":item["title"],"start":item["year_start"],"end":item["year_end"],
            "sha":item["sha256"],"source_sha":item["source_sha256"],"file":item["saved_file"],
            "rights":item["license"],"url":item.get("idsId") or ""}
    if kind=="rijks_more":
        return {"source":"Rijksmuseum","id":item["object_id"],
            "era":item["era"],"title":item["title"],"start":item["year_start"],"end":item["year_end"],
            "sha":item["sha256"],"source_sha":item["source_sha256"],"file":item["saved_file"],
            "rights":item["license"],"url":item.get("source_image_url") or ""}
    if kind=="nga_more":
        return {"source":"National Gallery of Art","id":item["object_id"],
            "era":item["era"],"title":item["title"],"start":item["begin_year"],"end":item["end_year"],
            "sha":item["saved_sha256"],"source_sha":item["source_sha256"],"file":item["image_path"],
            "rights":item["license"],"url":"NGA IIIF official source"}
    if kind=="aic":
        return {"source":"Art Institute of Chicago","id":item["id"],
            "era":item["era"],"title":item["title"],"start":item["year_start"],"end":item["year_end"],
            "sha":item["sha256"],"source_sha":item["source_sha256"],"file":item["saved_file"],
            "rights":item["license"],"url":item["image_url"]}
    raise ValueError("unsupported source")
def main():
    with CSV_PATH.open(newline="",encoding="utf-8-sig") as f:
        old=list(csv.DictReader(f))
    prior=json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert len(old)==prior["unique_verified_file_and_source_id_count"]
    assert len({(r["source"],r["artwork_id"]) for r in old})==len(old)
    records=old[:]
    existing_id={(r["source"],r["artwork_id"]) for r in old}
    existing_sha={r["file_sha256"] for r in old}
    duplicates_id=[];duplicates_sha=[];new_items=Counter();bad_year=[]
    for kind,(folder,jsonfile,arrayname) in ROOTS.items():
        source=BASE/kind/folder
        p=source/jsonfile
        if not p.exists():raise FileNotFoundError("Missing required actual decoded image proof "+str(p))
        data=json.loads(p.read_text(encoding="utf-8"))
        entries=data[arrayname]
        # Each source artifact independently verified expected image count.
        countkey={"met":"actual_downloaded_count","si_extra":"downloaded_verified_images",
          "rijks_more":"actual_downloaded_count","nga_more":"verified_image_files_this_run",
          "aic":"verified_files"}[kind]
        assert len(entries)==data[countkey],(kind,len(entries),data[countkey])
        for item in entries:
            d=normalize(item,kind)
            row_id=(d["source"],str(d["id"]))
            fpath=source/"samples"/Path(d["file"]).name
            if not fpath.exists():raise FileNotFoundError(fpath)
            bytes_,ph=validate(fpath,d["sha"])
            if row_id in existing_id:
                duplicates_id.append({"kind":kind,"id":row_id})
                continue
            if d["sha"] in existing_sha:
                duplicates_sha.append({"kind":kind,"sha256":d["sha"]})
                continue
            e=era(d["era"])
            # Verify high-level source's dates fall entirely within era.
            try:
                a,b=int(d["start"]),int(d["end"])
                assert -4000<=a<=b<=2026
                if e=="modern":assert a>=1800
                else:assert b<1800
            except (ValueError,TypeError,AssertionError):
                bad_year.append({"source":d["source"],"id":str(d["id"]),"start":d["start"],"end":d["end"]})
                continue
            rec={"artifact":ARTIFACT[kind],"stage":kind,
              "source":d["source"],"artwork_id":str(d["id"]),"era":e,
              "title":str(d["title"] or ""), "year_start":str(d["start"]),
              "year_end":str(d["end"]),"file_sha256":d["sha"],
              "source_sha256":d["source_sha"],"visual_dhash":ph,"bytes":bytes_,
              "rights":d["rights"],"source_url":d["url"]}
            records.append(rec)
            existing_id.add(row_id);existing_sha.add(d["sha"]);new_items[kind]+=1
    assert len(records)==len(existing_id)==len(existing_sha)
    assert not bad_year, "Source date proof unexpectedly ambiguous: "+str(bad_year[:4])
    with CSV_PATH.open("w",newline="",encoding="utf-8-sig") as f:
        wr=csv.DictWriter(f,fieldnames=FIELDS);wr.writeheader();wr.writerows(records)
    counts=Counter(x["era"] for x in records)
    out={**prior}
    out["as_of_utc"]=datetime.now(timezone.utc).isoformat()
    out["new_verified_unique_images_v3"]=dict(new_items)
    out["new_validated_actual_files_this_run"]=sum(new_items.values())
    out["verified_1800plus"]=counts["modern"]
    out["verified_older"]=counts["older"]
    out["unique_verified_file_and_source_id_count"]=len(records)
    out["reported_input_files"]=len(records)+len(duplicates_id)+len(duplicates_sha)+prior["exact_duplicate_source_ids_removed"]
    out["exact_duplicate_source_ids_removed"]=prior["exact_duplicate_source_ids_removed"]+len(duplicates_id)
    out["exact_duplicate_image_hashes_removed"]=prior["exact_duplicate_image_hashes_removed"]+len(duplicates_sha)
    out["actual_modern_share_percent"]=round(100*counts["modern"]/len(records),4)
    out["missing_1800plus"]=207360-counts["modern"]
    out["missing_older"]=51840-counts["older"]
    out["missing_total"]=259200-len(records)
    out["all_259200_acquired"]=False
    out["v3_provenance"]={
      "old_498_provenance":"Previously rechecked 498 actual artifact files (GitHub Actions 43561972183); only hashes/manifests inherited this run",
      "met_real_images":"43562238337","additional_smithsonian":"43562565266",
      "rijks_larger":"43562429102","NGA_second":"43562704467","AIC_new":"43562852917"}
    out["new_image_crosscheck_note"]="New source files were actually opened, decoded, size verified and SHA-256 checked. Old previously verified files have only durable SHA/provenance in Git."
    SUMMARY.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("CUMULATIVE_V3 "+json.dumps({
      "inherited_old":len(old),"new_unique":dict(new_items),
      "duplicate_id":len(duplicates_id),"duplicate_sha":len(duplicates_sha),
      "total_file_sourceid_unique":len(records),"modern":counts["modern"],
      "older":counts["older"],"remaining":out["missing_total"],
      "target_acquired":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
