#!/usr/bin/env python3
"""Append only real, redecoded Wellcome page-two art images to saved unique ledger.
Source identity is Work ID (not image ID). A work with multiple representations
is only counted once; image files alone do not prove different artworks.
"""
import csv,hashlib,json,io
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
from PIL import Image
L=Path("data/verified_80pct")
P=Path("research-input/wellcome2")
with (L/"verified_artwork_manifest.csv").open(encoding="utf-8-sig",newline="") as f:
    old=list(csv.DictReader(f))
audit=json.loads((L/"cumulative_audit.json").read_text(encoding="utf-8"))
assert len(old)==audit["unique_verified_file_and_source_id_count"]
prev_ids={(r["source"],r["artwork_id"]) for r in old}
prev_sha={r["file_sha256"] for r in old}
report=json.loads((P/"audit.json").read_text(encoding="utf-8"))
rows=report["files"]
assert len(rows)==report["byte_verified_image_files"]
duplicates_id=0;duplicates_hash=0;new=[];source_unique=set()
for r in rows:
    image=P/"samples"/Path(r["file_path"]).name
    blob=image.read_bytes()
    sha=hashlib.sha256(blob).hexdigest()
    assert sha==r["sha256"]
    with Image.open(io.BytesIO(blob)) as pic:
        pic.load()
        assert pic.format=="JPEG"
        w,h=pic.size
        assert w>=1000 and h>=1400 and w<h
        assert min((w/h)/.625,.625/(w/h))>=.75
    key=("Wellcome Collection",str(r["work_id"]))
    if key in prev_ids or key in source_unique:
        duplicates_id+=1
        continue
    if sha in prev_sha:
        duplicates_hash+=1
        continue
    assert r["era"]=="1800-2026"
    assert 1800<=int(r["year_start"])<=int(r["year_end"])<=2026
    rr={
      "artifact":"wellcome-page2-1800-verified-artwork-files",
      "stage":"wellcome_page2",
      "source":"Wellcome Collection",
      "artwork_id":str(r["work_id"]),
      "era":"modern",
      "title":str(r.get("title") or ""),
      "year_start":str(r["year_start"]),
      "year_end":str(r["year_end"]),
      "file_sha256":sha,
      "source_sha256":str(r.get("source_sha256") or ""),
      "visual_dhash":"",
      "bytes":len(blob),
      "rights":str(r.get("license") or ""),
      "source_url":str(r.get("source_url") or "")
    }
    old.append(rr);new.append(rr)
    source_unique.add(key)
    prev_ids.add(key);prev_sha.add(sha)
assert len(old)==len(prev_ids)==len(prev_sha)
with (L/"verified_artwork_manifest.csv").open("w",encoding="utf-8-sig",newline="") as f:
    wr=csv.DictWriter(f,fieldnames=list(old[0]));wr.writeheader();wr.writerows(old)
audit["as_of_utc"]=datetime.now(timezone.utc).isoformat()
audit["unique_verified_file_and_source_id_count"]=len(old)
audit["verified_1800plus"]=sum(r["era"]=="modern" for r in old)
audit["verified_older"]=sum(r["era"]=="older" for r in old)
audit["missing_total"]=259200-len(old)
audit["missing_1800plus"]=207360-audit["verified_1800plus"]
audit["missing_older"]=51840-audit["verified_older"]
audit["reported_input_files"]+=len(rows)
audit["exact_duplicate_source_ids_removed"]+=duplicates_id
audit["exact_duplicate_image_hashes_removed"]+=duplicates_hash
audit["actual_modern_share_percent"]=round(100*audit["verified_1800plus"]/len(old),4)
audit["wellcome_page2_crosscheck"]={
 "github_run":43563547762,"raw_verified_image_files":len(rows),
 "new_unique_work_id_and_sha":len(new),
 "repeat_work_ids_removed":duplicates_id,
 "duplicate_image_hashes_removed":duplicates_hash
}
audit["all_259200_acquired"]=False
(L/"cumulative_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
print("WELLCOME_PAGE2_APPEND "+json.dumps({
  "prior":len(old)-len(new),"source_verification_passed":len(rows),
  "new_unique":len(new),"repeat_work_id":duplicates_id,
  "same_hash":duplicates_hash,"grand_total":len(old),
  "modern":audit["verified_1800plus"],"older":audit["verified_older"],
  "remaining":audit["missing_total"],"all_259200_acquired":False
},ensure_ascii=False),flush=True)
