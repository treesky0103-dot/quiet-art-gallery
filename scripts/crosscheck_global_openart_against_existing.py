#!/usr/bin/env python3
"""Re-open all non-museum art JPEGs, deduplicate against prior 675 verified dated
museum files, and persist an explicitly UNKNOWN creation-year source manifest.
Never change the verified 1800+ year counts without original work-date evidence.
"""
from pathlib import Path
from PIL import Image
from collections import Counter
from datetime import datetime,timezone
import csv,hashlib,io,json
INPUT=Path("research-input/global-new")
OUTPUT=Path("data/verified_80pct")
OUTPUT.mkdir(parents=True,exist_ok=True)
report=json.loads((INPUT/"report.json").read_text(encoding="utf-8"))
with (INPUT/"verified_real_images.csv").open(encoding="utf-8",newline="") as f:
    new=list(csv.DictReader(f))
assert len(new)==report["saved_actual_images"]
with (OUTPUT/"verified_artwork_manifest.csv").open(encoding="utf-8-sig",newline="") as f:
    past=list(csv.DictReader(f))
audit=json.loads((OUTPUT/"cumulative_audit.json").read_text(encoding="utf-8"))
assert len(past)==audit["unique_verified_file_and_source_id_count"]
oldhash={x["file_sha256"] for x in past}
newhash=set();unique=[];dups=[];suspicious=[]
oldph=[]
for x in past:
    val=x.get("visual_dhash") or ""
    if len(val)!=16:continue
    try:oldph.append((int(val,16),x["source"],x["artwork_id"]))
    except ValueError:continue
def phash(im):
    im=im.convert("L").resize((9,8),Image.Resampling.LANCZOS)
    pixels=list(im.getdata());v=0
    if max(pixels)-min(pixels)<18:return ""
    for y in range(8):
        for x in range(8):v=(v<<1)|int(pixels[y*9+x]>pixels[y*9+x+1])
    return f"{v:016x}"
for row in new:
    f=INPUT/"artworks"/Path(row["file"]).name
    raw=f.read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    assert sha==row["sha256"]
    with Image.open(io.BytesIO(raw)) as img:
        img.load()
        w,h=img.size
        assert img.format=="JPEG" and w>=1000 and h>=1400 and w<h
        assert min((w/h)/.625,.625/(w/h))>=.75
        dh=phash(img)
    if sha in oldhash:
        dups.append({"source":row["source"],"id":row["id"],"reason":"prior_sha256"});continue
    if sha in newhash:
        dups.append({"source":row["source"],"id":row["id"],"reason":"new_sha256"});continue
    if len(dh)==16:
        near=[(sn,ident) for old,sn,ident in oldph if (old^int(dh,16)).bit_count()<=5]
        if near:suspicious.append({"id":row["id"],"potential_matching_prior":[list(x) for x in near[:5]]})
    row["visual_dhash"]=dh
    row["file"]=str(f) # historical path in expiring Actions archive, NOT durable repo path
    newhash.add(sha);unique.append(row)
out=OUTPUT/"additional_global_art_unknown_year.csv"
with out.open("w",encoding="utf-8-sig",newline="") as f:
    if new:
        wr=csv.DictWriter(f,fieldnames=list(unique[0]) if unique else list(new[0]))
        wr.writeheader();wr.writerows(unique)
result={
    "as_of_utc":datetime.now(timezone.utc).isoformat(),
    "prior_full_artwork_year_verified":len(past),
    "additional_byte_verified":len(unique),
    "additional_year_verified_1800plus":sum(x["era"]=="1800plus" for x in unique),
    "additional_year_unknown":sum(x["era"]=="unknown" for x in unique),
    "source_record_count":len(new),
    "exact_sha_duplicates_with_past_or_new":dups,
    "near_visual_matches_for_review":suspicious,
    "combined_distinct_file_sha256_count":len(past)+len(unique),
    "target_259200":259200,
    "completed":False,
    "artwork_year_80percent_verified":False,
    "files_persist_in_repo":False,
    "file_storage_note":"Actual JPG files reside in GitHub Actions artifact 43569337831 and expire; repo saves only audit metadata and SHA. Do not mistake repo CSV for durable 17 image copies.",
    "source_scope":"Commons, Library of Congress, Openverse queried; successful bytes all Commons",
    "warnings":["Source category 19th century is not individual artwork production-year proof.",
         "Per-file image duplicates only; same original artwork rephotographed across archives may remain.",
         "Legal permission beyond the source's posted terms is not independently established."]
}
(OUTPUT/"additional_global_art_audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
print("GLOBAL_EXTRA_CROSSCHECK "+json.dumps({
  k:result[k] for k in ("prior_full_artwork_year_verified","additional_byte_verified",
  "additional_year_unknown","combined_distinct_file_sha256_count",
  "files_persist_in_repo","completed")},ensure_ascii=False),flush=True)
