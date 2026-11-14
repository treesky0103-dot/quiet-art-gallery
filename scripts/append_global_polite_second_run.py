#!/usr/bin/env python3
"""Append second verified actual multisource JPEG batch to existing unknown-year 
illustration proof without inflating modern-year count or permanent image files.
"""
import csv,hashlib,io,json
from pathlib import Path
from PIL import Image
from datetime import datetime,timezone
ROOT=Path("data/verified_80pct")
INPUT=Path("research-input/retry-polite")
data=json.loads((INPUT/"report.json").read_text(encoding="utf-8"))
with (INPUT/"verified_real_images.csv").open(encoding="utf-8",newline="") as f:
    new=list(csv.DictReader(f))
assert data["saved_actual_images"]==len(new)
oldpath=ROOT/"additional_global_art_unknown_year.csv"
with oldpath.open(encoding="utf-8-sig",newline="") as f:
    saved=list(csv.DictReader(f))
audit=json.loads((ROOT/"additional_global_art_audit.json").read_text(encoding="utf-8"))
old_baseline=json.loads((ROOT/"cumulative_audit.json").read_text(encoding="utf-8"))
with (ROOT/"verified_artwork_manifest.csv").open(encoding="utf-8-sig",newline="") as f:
    baseline=list(csv.DictReader(f))
assert len(baseline)==old_baseline["unique_verified_file_and_source_id_count"]
assert len(saved)==audit["additional_byte_verified"]
old_shas={x["file_sha256"] for x in baseline}
seen_shas={x["sha256"] for x in saved}
seen_ids={str(x["id"]) for x in saved if x["source"].startswith("Wikimedia Commons")}
accepted=0;reject_id=0;reject_sha=0;reject_base=0
for record in new:
    file=INPUT/"artworks"/Path(record["file"]).name
    binary=file.read_bytes()
    sha=hashlib.sha256(binary).hexdigest()
    assert sha==record["sha256"],"Downloaded file bytes differ from source audit"
    with Image.open(io.BytesIO(binary)) as pic:
        pic.load()
        w,h=pic.size
        assert pic.format=="JPEG" and w>=1000 and h>=1400 and w<h
        assert min((w/h)/.625,.625/(w/h))>=.75
        mono=pic.convert("L").resize((9,8),Image.Resampling.LANCZOS)
        p=list(mono.getdata())
        val=0
        if max(p)-min(p)>=18:
            for y in range(8):
                for x in range(8):val=(val<<1)|int(p[y*9+x]>p[y*9+x+1])
            visual=f"{val:016x}"
        else:visual=""
    if sha in old_shas:reject_base+=1;continue
    if record["source"].startswith("Wikimedia Commons") and str(record["id"]) in seen_ids:
        reject_id+=1;continue
    if sha in seen_shas:reject_sha+=1;continue
    assert record["era"]=="unknown","Artwork year must not be invented from category"
    record["visual_dhash"]=visual
    record["file"]=str(file)+" (expiring GitHub Actions artifact, not repo-stored JPG)"
    saved.append(record)
    seen_shas.add(sha)
    if record["source"].startswith("Wikimedia Commons"):seen_ids.add(str(record["id"]))
    accepted+=1
fields=["source","id","title","image_url","work_url","license","year_start",
        "year_end","era","sha256","source_sha256","file","width","height","bytes","visual_dhash"]
with oldpath.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(saved)
assert len(saved)==len({x["sha256"] for x in saved})
assert not {x["sha256"] for x in saved}&old_shas
audit.update({
  "as_of_utc":datetime.now(timezone.utc).isoformat(),
  "additional_byte_verified":len(saved),
  "additional_year_unknown":len(saved),
  "combined_distinct_file_sha256_count":len(baseline)+len(saved),
  "second_run":43570622654,
  "second_run_downloaded_decoded":len(new),
  "second_run_new_unique":accepted,
  "second_run_previous_page_id_overlap":reject_id,
  "second_run_sha_overlap":reject_sha,
  "second_run_prior_museum_sha_overlap":reject_base,
  "latest_file_artifact_expires":"2026-11-16 (verify exact GitHub expiry metadata)",
  "completed":False,
  "artwork_year_80percent_verified":False,
  "files_persist_in_repo":False,
})
(ROOT/"additional_global_art_audit.json").write_text(
    json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
print("MULTISOURCE_UNIQUE_APPENDED "+json.dumps({
 "new_actual_decoded":len(new),"new_unique_after_crosscheck":accepted,
 "duplicate_artwork_page_ids":reject_id,"duplicate_file_hashes":reject_sha,
 "old_675_hash_overlaps":reject_base,
 "all_extra_unknown_year_unique":len(saved),
 "total_separate_verified_image_hashes":len(baseline)+len(saved),
 "completed_259200":False
},ensure_ascii=False),flush=True)
