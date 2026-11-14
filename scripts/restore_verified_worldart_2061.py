#!/usr/bin/env python3
"""Reconstruct the exact v1.8.0 2,061-JPEG deck before packaging collector v2.

The v2 APK preserves every 1000x1667 JPEG bitwise, not only filenames.
Moving images out of the APK to persistent local app files happens through the
native cache for newly downloaded content. Bundled baseline still works offline.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image
import collections,hashlib,io,json,zipfile

ORIGINAL=Path("QuietArtGallery-397Movements-50Sources-v180.apk")
SOURCE_SHA="1c9e9ea02fe4af0627323ae0d8888c14f9973c9023dd3da07bdbac7c62b33740"
ROOT=Path("android-app/app/src/main/assets")
MANIFEST=ROOT/"offline-deck.json"
REPORT=Path("build-collector-v2-report.json")

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def main():
    if not ORIGINAL.is_file():
        raise RuntimeError("The exact previous APK must be downloaded through GitHub release first")
    with ORIGINAL.open("rb") as f:
        h=hashlib.sha256()
        for part in iter(lambda:f.read(1024*1024),b""):h.update(part)
        if h.hexdigest()!=SOURCE_SHA:raise RuntimeError("Unexpected source APK SHA256; no release allowed")
    (ROOT/"offline").mkdir(parents=True,exist_ok=True)
    count=collections.Counter()
    size=0
    with zipfile.ZipFile(ORIGINAL,"r") as z:
        if z.testzip() is not None:raise RuntimeError("Old APK CRC failed")
        manifest=z.read("assets/offline-deck.json")
        rows=json.loads(manifest)
        if len(rows)!=2061:raise RuntimeError("The official v1.8.0 APK must include exactly 2061 artworks")
        if len({a["key"] for a in rows})!=len(rows):raise RuntimeError("Non-unique artwork identity")
        if len({a["derivedSHA256"] for a in rows})!=len(rows):raise RuntimeError("Non-unique JPEG fingerprints")
        if len({a["sourceSHA256"] for a in rows})!=len(rows):raise RuntimeError("Non-unique source fingerprints")
        for i,art in enumerate(rows):
            path="offline/pack-%04d.jpg"%i
            if art.get("offlineAsset")!=path or art.get("image")!="https://appassets.gallery/"+path:
                raise RuntimeError("Expected stable artwork manifest order")
            raw=z.read("assets/"+path)
            if sha(raw)!=art["derivedSHA256"]:
                raise RuntimeError("Old image hash mismatch "+path)
            outfile=ROOT/path
            outfile.write_bytes(raw)
            if sha(outfile.read_bytes())!=art["derivedSHA256"]:
                raise RuntimeError("New image hash mismatch "+path)
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                if image.format!="JPEG" or image.size!=(1000,1667):
                    raise RuntimeError("Invalid 2D still JPEG "+path)
            count[art["type"]]+=1
            size+=len(raw)
        MANIFEST.write_bytes(manifest)
    catalog=json.loads((ROOT/"art-movements.json").read_text(encoding="utf-8"))
    sources=json.loads((ROOT/"art-providers.json").read_text(encoding="utf-8"))
    if catalog["entry_count"]!=397 or catalog["english_query_terms"]!=396:
        raise RuntimeError("Missing complete multilingual movement registry")
    if sources["requested_source_entries"]!=50 or sources["unique_source_names"]!=47:
        raise RuntimeError("Requested source registry incomplete")
    report={
      "previous_apk_sha256":SOURCE_SHA,
      "preserved_artworks_sha256_verified":len(rows),
      "total_embedded_artworks":len(rows),
      "images_added_during_this_code_upgrade":0,
      "embedded_images_unchanged_byte_for_byte":True,
      "original_media_types":dict(count),
      "embedded_jpeg_bytes":size,
      "movement_catalog_entries":catalog["entry_count"],
      "movement_english_search_aliases":catalog["english_query_terms"],
      "movements_without_english_hint":catalog["entry_count"]-catalog["english_query_terms"],
      "requested_site_rows":sources["requested_source_entries"],
      "unique_requested_sites":sources["unique_source_names"],
      "collector_tick_seconds":60,
      "collector_goal_per_30_minutes":60,
      "collector_goal_per_24_hours":2880,
      "collector_goals_are_guarantees":False,
      "foreground_only":True,
      "uses_native_host_wide_429_retry_after":True,
      "limits_local_image_cache_bytes":8*1024**3,
      "cache_cleanup_target_bytes":7*1024**3,
      "reserves_free_bytes":1536*1024**2,
      "seen_history_is_independent_of_file_cache":True,
      "90_day_no_repeat_applies_to_recorded_identity":True,
      "downloaded_artwork_growth_on_device_unverified":True,
      "tested_on_physical_galaxy_tab_a7":False,
      "warning":"New package ID; old app cache and IndexedDB history do not transfer automatically. Export/import history CSV manually."
    }
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PRESERVED_ALL_2061_ARTWORKS",dict(count),"jpeg_bytes",size,flush=True)
    print("V2_COLLECTOR_ADAPTIVE_POLICY_AUDIT",json.dumps({k:v for k,v in report.items() if k not in ('original_media_types','warning')},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
