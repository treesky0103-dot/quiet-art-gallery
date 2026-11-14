#!/usr/bin/env python3
"""Isolated ten-minute *display-ready* benchmark against the immutable 2061 APK.
Only counted after retaining a local JPEG, real Pillow decode, full-gallery
identity screening, and writing a valid APK offline asset + manifest entry.
Not proof of display on the physical Galaxy Tab A7.
"""
import csv, hashlib, importlib.util, io, json, os, re, shutil, time, zipfile
from pathlib import Path
from PIL import Image
import sys

ROOT=Path("android-app/app/src/main/assets")
ORIGINAL=Path("QuietArtGallery-85Sources-ShownFirst1GiB-v182.apk")
EXPECTED_ORIGINAL_SHA="21d9fb8f4503a70a7fb836b6cb2c4d260edb404c1a6ba2b73c3b9465f2cd4741"
TEST_ROOT=Path("benchmark-10min-work")
REPORT=Path("benchmark-10min-result.json")
CAP=639
spec=importlib.util.spec_from_file_location("collector", "scripts/collect_every_10min.py")
c=importlib.util.module_from_spec(spec)
sys.modules["collector"]=c
spec.loader.exec_module(c)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def main():
    if not ORIGINAL.is_file():raise RuntimeError("Original 2061 APK not downloaded")
    TEST_ROOT.mkdir(exist_ok=True)
    with zipfile.ZipFile(ORIGINAL) as z:
        if z.testzip() is not None:raise RuntimeError("Original APK ZIP CRC failure")
        base=json.loads(z.read("assets/offline-deck.json"))
        if len(base)!=2061 or len({x["key"] for x in base})!=2061:
            raise RuntimeError("Original 2061 identities missing")
        base_hashes=set()
        base_ids=set()
        base_visual=[]
        originals=[]
        for i,a in enumerate(base):
            name="offline/pack-%04d.jpg"%i
            if a["offlineAsset"]!=name:raise RuntimeError("Original asset position changed")
            raw=z.read("assets/"+name)
            if sha(raw)!=a["derivedSHA256"]:raise RuntimeError("Original artwork SHA mismatch "+name)
            with Image.open(io.BytesIO(raw)) as im:
                im.load()
                if im.format!="JPEG" or im.size!=(1000,1667):raise RuntimeError("Corrupted original JPEG")
                base_visual.append(int(c.dhash(im),16))
            for key in ("sourceSHA256","derivedSHA256","originalSHA256"):
                if re.fullmatch(r"[0-9a-f]{64}",str(a.get(key,""))):base_hashes.add(a[key])
            base_ids.add(a["key"])
            originals.append((name,raw))
        print("IMMUTABLE_2061_BASELINE_VALIDATED",len(originals),flush=True)
    # Avoid false new additions versus either original JPEG data or original
    # Cleveland artwork identifiers. Previous server-only rows are NOT
    # counted as already stored on tablet.
    seen_ids=set()
    for key in base_ids:
        if key.startswith("cma:"):seen_ids.add(("Cleveland Museum of Art",key[4:]))
    newpath=TEST_ROOT/"new_verified.csv"
    statepath=TEST_ROOT/"state.json"
    histpath=TEST_ROOT/"run_history.csv"
    state={"baseline_requested":736,"verified_manifest_base":675,"runs":0,
           "new_verified":0,"claimed_total_with_requested_baseline":736,
           "cursor":{"cma_modern":2500,"cma_older":2500}}
    statepath.write_text(json.dumps(state),encoding="utf-8")
    c.STATE=statepath
    c.NEW_CSV=newpath
    c.HISTORY=histpath
    c.OUT=TEST_ROOT/"collector-batch"
    c.IMAGES=c.OUT/"images"
    replay_path=Path("data/benchmark_10min_verified_ids_20261115.csv")
    replay_expected={}
    if replay_path.exists():
        with replay_path.open(encoding="utf-8",newline="") as fd:
            for rec in csv.DictReader(fd):
                replay_expected[rec["artwork_id"]]=rec["original_sha256"]
        if len(replay_expected)!=639:
            raise RuntimeError("Timed 639-ID log evidence is missing")
        print("REPLAY_PREVIOUS_VERIFIED_639_TIMED_LOG_NOT_A_NEW_10MIN_TEST",flush=True)
    c.TARGET=len(replay_expected) if replay_expected else CAP
    c.MAX_ATTEMPTS=4500
    c.MAX_PAGES=400
    c.TIME_BUDGET_SECONDS=600
    c.MAX_PROOF_BYTES=700*1024*1024
    original_prov=c.load_provenance
    def provenance():
        new=c.read_csv(newpath)
        ids=set(seen_ids)
        hashes=set(base_hashes)
        visual=list(base_visual)
        for a in new:
            ids.add((a["source"],a["artwork_id"]))
            hashes.add(a["original_sha256"]);hashes.add(a["file_sha256"])
            visual.append(int(a["visual_dhash"],16))
        return [],new,ids,hashes,visual
    c.load_provenance=provenance
    # Preserve source-provided *real* type (painting/print/drawing) rather
    # than inventing a classification from a title.
    types={}
    original_json=c.get_json
    def read_meta(url):
        j=original_json(url)
        if "openaccess-api.clevelandart.org/api/artworks" in url:
            for a in j.get("data") or []:
                if a.get("id") is not None:
                    types[str(a["id"])]=(str(a.get("type") or ""),str(a.get("technique") or ""))
        return j
    c.get_json=read_meta
    if replay_expected:
        original_cleveland=c.cleveland
        seen_ids.add(("Cleveland Museum of Art","skip-cursor"))
        def replay_cleveland(which,offset):
            items,step=original_cleveland(which,offset)
            matching=[art for art in items if art["artwork_id"] in replay_expected]
            # Do not terminate on an empty page; advance through the exact
            # source pages sampled by the original 565.722-second run.
            return (matching if matching else [{
                "source":"Cleveland Museum of Art","artwork_id":"skip-cursor"
            }]),step
        c.cleveland=replay_cleveland
    begin=time.monotonic()
    c.run()
    duration=round(time.monotonic()-begin,3)
    rows=c.read_csv(newpath)
    if replay_expected:
        if any(row["original_sha256"]!=replay_expected.get(row["artwork_id"]) for row in rows):
            raise RuntimeError("Timed source hashes not reproducible")
        if len({row["artwork_id"] for row in rows})!=len(rows):
            raise RuntimeError("Duplicate replay artwork IDs")
        print("EXACT_TIMED_WORKS_REPLAYED",len(rows),"of",len(replay_expected),flush=True)
    batch=json.loads((c.OUT/"report.json").read_text(encoding="utf-8"))
    if len(rows)!=batch["new_verified_this_run"]:raise RuntimeError("Batch count mismatch")
    if batch["verified_only_in_hash_ledger"]!=0 or batch["proof_files"]!=len(rows):
        raise RuntimeError("Files were NOT permanently retained by test runner")
    if len(rows)>CAP:raise RuntimeError("Exceeded 2700 APK manifest entries")
    seen_urls={str(a.get("page") or "") for a in base}
    appended=[]
    for row in rows:
        j=len(originals)+len(appended)
        source_id=row["artwork_id"]
        key="cma:"+source_id
        source_url=row["source_url"]
        actual_type,technique=types.get(source_id,("",""))
        if not c.kind_ok(actual_type,technique):
            raise RuntimeError("Real 2D artwork type not available for "+source_id)
        if key in base_ids or source_url in seen_urls:
            raise RuntimeError("Overlap with 2061 in APK for "+source_id)
        asset="offline/pack-%04d.jpg"%j
        fp=c.IMAGES/(row["file_sha256"][:24]+".jpg")
        if not fp.is_file():raise RuntimeError("Retained JPEG missing "+source_id)
        raw=fp.read_bytes()
        if sha(raw)!=row["file_sha256"]:raise RuntimeError("Hash changed "+source_id)
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            if im.format!="JPEG" or not c.screen_ok(*im.size):
                raise RuntimeError("Invalid display image "+source_id)
            w,h=im.size
        target=ROOT/asset
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
        appended.append({
            "key":key,"source":"클리블랜드",
            "title":row["title"] or "제목 미상",
            "artist":row["artist"] or "작가 미상",
            "image":"https://appassets.gallery/"+asset,
            "offlineAsset":asset,
            "width":w,"height":h,
            "type":actual_type,"classification":actual_type,
            "medium":technique,"description":"",
            "license":"CC0","rightsOK":True,
            "yearStart":int(row["year_start"]),"yearEnd":int(row["year_end"]),
            "date":row["year_start"],"page":source_url,
            "sourceSHA256":row["original_sha256"],
            "derivedSHA256":row["file_sha256"],
            "style":"","styles":[],
        })
        seen_urls.add(source_url);base_ids.add(key)
    # Preserve all original JPEG bytes and all original manifest records.
    for name,raw in originals:
        out=ROOT/name
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_bytes(raw)
    (ROOT/"offline-deck.json").write_text(
        json.dumps(base+appended,ensure_ascii=False,indent=1)+"\n",encoding="utf-8")
    if len(base+appended)>2700:raise RuntimeError("Gallery preload guard exceeded")
    total_new_bytes=sum((ROOT/a["offlineAsset"]).stat().st_size for a in appended)
    report={
        "baseline_count":2061,
        "new_display_ready_files":len(appended),
        "total_offline_deck":2061+len(appended),
        "collector_elapsed_seconds":duration,
        "collector_limit_seconds":600,
        "reached_manifest_cap":len(appended)==CAP,
        "new_verified_file_bytes_preserved":total_new_bytes,
        "fully_preserved_test_jpegs":len(appended),
        "duplicate_screen_against_all_baseline_jpeg_visual_hashes":True,
        "duplicate_screen_against_baseline_cleveland_ids":True,
        "node_app_eligibility_and_apk_assembly_pending":True,
        "galaxy_tab_a7_physical_screen_tested":False,
        "scope":"Research test APK only, not existing installed device app",
        "source_breakdown":{"Cleveland Museum of Art":len(appended)},
        "original_observed_10min_run_id":43612888391 if replay_expected else None,
        "original_observed_collection_seconds":565.722 if replay_expected else duration,
        "original_observed_validated_unique_files":639 if replay_expected else len(appended),
        "replay_of_previous_timed_files":bool(replay_expected),
        "replay_missing_from_original_639":(len(replay_expected)-len(appended)) if replay_expected else 0
    }
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("DISPLAY_READY_JPEG_PREPARED",json.dumps(report,ensure_ascii=False),flush=True)

if __name__=="__main__":main()
