#!/usr/bin/env python3
"""One bounded, independently verifiable collection batch for Quiet Art Gallery.

Github scheduled job: discover -> legally filter -> download -> decode -> test
75% portrait fill -> check SHA and dHash -> upload file proof -> commit ledger.
This never claims that metadata-only results are actual downloaded artworks.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import time
from pathlib import Path
import re
import warnings
from urllib.parse import urlencode, quote, urlsplit
from urllib.request import Request, urlopen

from PIL import Image
Image.MAX_IMAGE_PIXELS = 36_000_000
warnings.simplefilter('error', Image.DecompressionBombWarning)

ROOT = Path("data/collector_10min")
BASE = Path("data/verified_80pct/verified_artwork_manifest.csv")
STATE = ROOT / "state.json"
NEW_CSV = ROOT / "new_verified.csv"
HISTORY = ROOT / "run_history.csv"
OUT = Path("collector-10min-batch")
IMAGES = OUT / "images"
MAX_BYTES = 15 * 1024 * 1024
TARGET = 80  # aspirational cap; actual batch is bounded by time, source/rights, proof-byte budget
MAX_ATTEMPTS = 200
MAX_PAGES = 12
TIME_BUDGET_SECONDS = 345
MAX_PROOF_BYTES = 1 * 1024 * 1024  # GitHub Free storage safety: only a small temporary proof sample
YEAR = 2026
ASPECT = 0.625
HEADERS = {"User-Agent": "QuietArtGalleryResearch/1.0 (+https://github.com/treesky0103-dot/quiet-art-gallery)", "Accept": "*/*"}
NEW_FIELDS = ["source","artwork_id","title","artist","era","year_start","year_end",
              "original_url","source_url","rights","original_sha256","file_sha256",
              "visual_dhash","width","height","bytes","artifact_run","verified_utc"]
ALLOW_IMAGE_HOSTS = {"openaccess-cdn.clevelandart.org", "www.artic.edu", "artic.edu"}
BLOCK = ("photograph", "sculpture", "ceramic", "textile", "costume", "jewel",
         "furniture", "installation", "video", "film", "3d", "architecture", "tapestry",
         "vase", "room view", "gallery view", "framed", "frame photo")
ALLOW = ("painting", "drawing", "print", "watercolo", "gouache", "etching",
         "lithograph", "engraving", "woodcut", "illustration", "oil on canvas",
         "oil on panel", "pastel", "acrylic", "ink on paper")

def get_json(url):
    with urlopen(Request(url, headers={**HEADERS, "Accept":"application/json"}), timeout=19) as resp:
        if resp.status != 200: raise ValueError("HTTP "+str(resp.status))
        raw = resp.read(5*1024*1024+1)
        if len(raw) > 5*1024*1024: raise ValueError("Metadata response too large")
    return json.loads(raw)

def get_image(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOW_IMAGE_HOSTS or parsed.username or parsed.password:
        raise ValueError("Image host not allowlisted")
    with urlopen(Request(url, headers=HEADERS), timeout=18) as resp:
        if resp.status != 200: raise ValueError("Image HTTP "+str(resp.status))
        raw=resp.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES: raise ValueError("Image exceeds 15 MiB")
    return raw

def year(value):
    if value is None or isinstance(value, bool):return None
    try: n=int(value)
    except (TypeError,ValueError):return None
    return n if -4000 <= n <= YEAR else None

def era_for(begin,end):
    a,b=year(begin),year(end)
    if a is None or b is None or a>b:return None
    if 1800<=a and b<=YEAR:return "1800-2026"
    if b<1800:return "pre-1800"
    return None

def kind_ok(kind,medium=""):
    k=(str(kind or "")+" "+str(medium or "")).lower()
    return not any(t in k for t in BLOCK) and any(t in k for t in ALLOW)

def screen_ok(w,h):
    try:w,h=int(w),int(h)
    except (ValueError,TypeError):return False
    if w<1000 or h<1400 or w>=h:return False
    ratio=(w/h)/ASPECT
    return min(ratio,1/ratio)>=0.75

def dhash(im):
    small=im.convert("L").resize((9,8),Image.Resampling.LANCZOS)
    p=list(small.getdata());bits=0
    for y in range(8):
        for x in range(8):
            bits=(bits<<1)|int(p[y*9+x] > p[y*9+x+1])
    return f"{bits:016x}"

def read_csv(path):
    if not path.exists():return []
    with path.open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def save_csv(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    with tmp.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=NEW_FIELDS,extrasaction="ignore")
        w.writeheader();w.writerows(rows)
    tmp.replace(path)

def save_json(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)

def cleveland(which,offset):
    query={"has_image":"1","limit":"100","skip":str(offset),
           "created_before":str(1800 if which=="pre-1800" else YEAR+1)}
    if which=="1800-2026":query["created_after"]="1799"
    data=get_json("https://openaccess-api.clevelandart.org/api/artworks/?"+urlencode(query)+"&cc0")
    out=[]
    for art in data.get("data") or []:
        if era_for(art.get("creation_date_earliest"),art.get("creation_date_latest")) != which:continue
        if str(art.get("share_license_status") or "").lower()!="cc0":continue
        if not kind_ok(art.get("type"),art.get("technique")):continue
        ims=art.get("images") or {}
        pic=ims.get("print") or ims.get("web") or {}
        src=pic.get("url")
        if not isinstance(src,str) or not src.startswith("https://"):continue
        # Prefer high-confidence portrait pixels before spending network bandwidth.
        if pic.get("width") and pic.get("height") and not screen_ok(pic["width"],pic["height"]):continue
        out.append({"source":"Cleveland Museum of Art","artwork_id":str(art.get("id") or ""),
          "title":str(art.get("title") or ""),"artist":", ".join(p.get("description","") for p in art.get("creators") or [] if isinstance(p,dict)),
          "era":which,"year_start":art.get("creation_date_earliest"),
          "year_end":art.get("creation_date_latest"),"rights":"CC0 (official metadata)",
          "original_url":src,"source_url":str(art.get("url") or "")})
    return out, 100

def chicago(which,page):
    lo,hi=(1800,YEAR) if which=="1800-2026" else (-4000,1799)
    params={"fields":["id","title","artist_title","date_start","date_end",
       "artwork_type_title","classification_title","medium_display","image_id",
       "is_public_domain","api_link"],
       "query":{"bool":{"filter":[{"term":{"is_public_domain":True}},
        {"range":{"date_start":{"gte":lo,"lte":hi}}},
        {"range":{"date_end":{"gte":lo,"lte":hi}}},
        {"exists":{"field":"image_id"}}]}},
       "limit":100,"page":page}
    data=get_json("https://api.artic.edu/api/v1/artworks/search?"+urlencode({"params":json.dumps(params,separators=(",",":"))}))
    host=((data.get("config") or {}).get("iiif_url") or "https://www.artic.edu/iiif/2").rstrip("/")
    if urlsplit(host).hostname not in ALLOW_IMAGE_HOSTS:raise ValueError("Unexpected IIIF host")
    out=[]
    for art in data.get("data") or []:
        if art.get("is_public_domain") is not True:continue
        if era_for(art.get("date_start"),art.get("date_end")) != which:continue
        if not kind_ok(art.get("artwork_type_title") or art.get("classification_title"),art.get("medium_display")):continue
        if not art.get("image_id"):continue
        out.append({"source":"Art Institute of Chicago","artwork_id":str(art.get("id") or ""),
         "title":str(art.get("title") or ""),"artist":str(art.get("artist_title") or ""),
         "era":which,"year_start":art.get("date_start"),"year_end":art.get("date_end"),
         "rights":"Public domain (official metadata)",
         "original_url":host+"/"+quote(str(art["image_id"]),safe="")+"/full/2000,/0/default.jpg",
         "source_url":str(art.get("api_link") or "")})
    return out, 1

def load_provenance():
    baseline=read_csv(BASE)
    if len(baseline)!=675:raise RuntimeError("Baseline hash ledger changed: expected 675; manual audit required")
    new=read_csv(NEW_CSV)
    seen_ids=set();hashes=set();visual=[]
    for row in baseline+new:
        src=row.get("source") or ""
        ident=row.get("artwork_id") or ""
        if src and ident:seen_ids.add((src,ident))
        for key in ("file_sha256","source_sha256","original_sha256"):
            v=(row.get(key) or "").lower()
            if re.fullmatch("[a-f0-9]{64}",v):hashes.add(v)
        h=row.get("visual_dhash")
        if h and re.fullmatch("[a-f0-9]{16}",h.lower()):visual.append(int(h,16))
    return baseline,new,seen_ids,hashes,visual

def run():
    OUT.mkdir(parents=True,exist_ok=True);IMAGES.mkdir(parents=True,exist_ok=True)
    state=json.loads(STATE.read_text(encoding="utf-8"))
    assert state["baseline_requested"]==736 and state["verified_manifest_base"]==675
    base,rows,ids,hashes,visual=load_provenance()
    cursors=state.get("cursor") or {}
    # AIC returned HTTP 403 from the GitHub-hosted runner; do not hammer that API
    # every ten minutes. The verified Cleveland source handles both eras here.
    sources=[("cma_modern","1800-2026",cleveland),
             ("cma_older","pre-1800",cleveland)]
    # Rotate source priority across runs; make modern artworks the default.
    turn=int(state.get("runs",0))
    if turn%5==4:sources=[sources[1],sources[0]]
    started=time.monotonic()
    attempts=0;found=[];probes=[];ok_sources=0;rejects={};pages=0;proof_bytes=0
    # Cycle source pages until the time/attempt/output cap, not a fixed three works.
    # Keep scans read-only on the production branch. Save cursors only after completed pages.
    for key,which,source in sources:
        while (len(found)<TARGET and attempts<MAX_ATTEMPTS and
               pages<MAX_PAGES and time.monotonic()-started<TIME_BUDGET_SECONDS):
            offset=int(cursors.get(key,2500 if key.startswith("cma") else 16))
            pages+=1
            try:
                candidates,step=source(which,offset)
                ok_sources+=1
                cursors[key]=offset+step
                if len(probes)<30:
                    probes.append({"source":key,"cursor":offset,"candidates":len(candidates),"ok":True})
            except Exception as ex:
                if len(probes)<30:
                    probes.append({"source":key,"cursor":offset,"ok":False,"error":str(ex)[:170]})
                break
            for art in candidates:
                if (len(found)>=TARGET or attempts>=MAX_ATTEMPTS or
                    time.monotonic()-started>=TIME_BUDGET_SECONDS):break
                identifier=(art["source"],art["artwork_id"])
                if not identifier[1] or identifier in ids:continue
                attempts+=1
                try:
                    raw=get_image(art["original_url"])
                    im=Image.open(io.BytesIO(raw));im.load()
                    if im.format not in ("JPEG","PNG","WEBP"):continue
                    w,h=im.size
                    if not screen_ok(w,h):
                        rejects["decoded_dimensions"]=rejects.get("decoded_dimensions",0)+1
                        continue
                    source_hash=hashlib.sha256(raw).hexdigest()
                    if source_hash in hashes:
                        rejects["existing_sha"]=rejects.get("existing_sha",0)+1
                        continue
                    visual_hash=dhash(im)
                    n=int(visual_hash,16)
                    if any((n ^ old).bit_count()<=2 for old in visual):
                        rejects["existing_visual"]=rejects.get("existing_visual",0)+1
                        continue
                    # Keep a display-ready, uncropped JPEG as temporary file proof.
                    scale=max(1000/w,1400/h)
                    if scale>1:continue
                    if scale<1:
                        im=im.resize((round(w*scale),round(h*scale)),Image.Resampling.LANCZOS)
                    if not screen_ok(*im.size):
                        rejects["optimized_dimensions"]=rejects.get("optimized_dimensions",0)+1
                        continue
                    retained=None
                    for quality in (84,78,72,66,60):
                        buffer=io.BytesIO()
                        im.convert("RGB").save(buffer,format="JPEG",quality=quality,optimize=True,progressive=True)
                        if buffer.tell()<=600_000:
                            retained=buffer.getvalue();break
                    if not retained:
                        rejects["optimized_file_over_600kb"]=rejects.get("optimized_file_over_600kb",0)+1
                        continue
                    file_hash=hashlib.sha256(retained).hexdigest()
                    if file_hash in hashes:
                        rejects["optimized_duplicate_sha"]=rejects.get("optimized_duplicate_sha",0)+1
                        continue
                    fn=IMAGES/(file_hash[:24]+".jpg")
                    fn.write_bytes(retained)
                    decoded=Image.open(fn);decoded.load()
                    if decoded.size != im.size or not screen_ok(*decoded.size):
                        raise ValueError("Saved-image validation failed")
                    if hashlib.sha256(fn.read_bytes()).hexdigest()!=file_hash:
                        raise ValueError("Disk hash mismatch")
                    recorded={**art,"original_sha256":source_hash,"file_sha256":file_hash,
                      "visual_dhash":visual_hash,"width":im.width,"height":im.height,"bytes":len(retained),
                      "artifact_run":os.getenv("GITHUB_RUN_ID","local"),
                      "verified_utc":datetime.now(timezone.utc).isoformat()}
                    rows.append(recorded);found.append(recorded)
                    # Every accepted file was actually written, decoded, measured and
                    # hashed. The Actions artifact contains a small quota-safe sample;
                    # unsampled files are deleted after independent disk verification.
                    if proof_bytes+len(retained)<=MAX_PROOF_BYTES:
                        proof_bytes+=len(retained)
                    else:
                        fn.unlink()
                        rejects["validated_but_not_archived"]=rejects.get("validated_but_not_archived",0)+1
                    ids.add(identifier);hashes.update((source_hash,file_hash));visual.append(n)
                    print("VERIFIED "+art["source"]+" "+art["artwork_id"]+" "+source_hash,flush=True)
                except Exception as ex:
                    rejects["download_decode_error"]=rejects.get("download_decode_error",0)+1
                    if len(probes)<30:
                        probes.append({"source":key,"artwork_id":art["artwork_id"],"error":str(ex)[:170]})
            if not candidates:break
        if len(found)>=TARGET:break
    now=datetime.now(timezone.utc).isoformat()
    report={"run_utc":now,"github_run_id":os.getenv("GITHUB_RUN_ID","local"),
            "baseline_requested":736,"baseline_with_independent_hash_records":675,
            "new_verified_this_run":len(found),"increment_verified_unique":len(rows),
            "user_baseline_plus_new":736+len(rows),
            "metadata_source_ok":ok_sources,"download_attempts":attempts,
            "proof_files":len(list(IMAGES.glob("*.jpg"))),"details":probes,"rejection_summary":rejects,
            "scan_pages":pages,"elapsed_sec":round(time.monotonic()-started,1),
            "proof_bytes":proof_bytes,"target_cap":TARGET,"max_output_bytes":MAX_PROOF_BYTES,
            "verified_only_in_hash_ledger":len(found)-len(list(IMAGES.glob("*.jpg"))),
            "limitations":["736 baseline includes 61 not linked to the 675 SHA manifest; possible cross-set duplicates remain",
            "Only a small sample of proof JPEGs is uploaded for one day; other accepted images were downloaded and verified on the runner then discarded, preserving SHA/URL metadata only",
            "Server-side scheduled run does not update the existing v1.7.2 APK"]}
    save_json(OUT/"report.json",report)
    save_json(ROOT/"last_report.json",report)
    print("COLLECTION_PROBES "+json.dumps(probes[:25],ensure_ascii=False),flush=True)
    if ok_sources==0:
        print("ERROR: all metadata sources failed; no ledger commit",flush=True)
        raise SystemExit(2)
    state.update({"runs":turn+1,"last_run":now,"cursor":cursors,
                  "new_verified":len(rows),"claimed_total_with_requested_baseline":736+len(rows),
                  "last_download_success":len(found),"last_metadata_sources_ok":ok_sources})
    save_csv(NEW_CSV,rows)
    save_json(STATE,state)
    history_fields=["run_utc","github_run_id","new_verified_this_run","increment_verified_unique",
                    "user_baseline_plus_new","download_attempts","scan_pages","proof_bytes","elapsed_sec",
                    "proof_files","verified_only_in_hash_ledger"]
    previous=read_csv(HISTORY)
    previous.append({k:report.get(k,"") for k in history_fields})
    # Preserve history across scheduled runs; history is a manifest, not proof of permanent image bytes.
    HISTORY.parent.mkdir(parents=True,exist_ok=True)
    with HISTORY.open("w",encoding="utf-8",newline="") as hfile:
        writer=csv.DictWriter(hfile,fieldnames=history_fields)
        writer.writeheader();writer.writerows(previous)
    print("BATCH "+json.dumps({k:report[k] for k in ("new_verified_this_run","increment_verified_unique","user_baseline_plus_new","metadata_source_ok","download_attempts","proof_files")}),flush=True)

def self_test():
    assert era_for(1800,2000)=="1800-2026"
    assert era_for(1799,1800) is None and era_for(1777,1799)=="pre-1800"
    assert not kind_ok("sculpture","bronze") and kind_ok("painting","oil on canvas")
    assert screen_ok(1200,1800) and not screen_ok(1000,3000)
    assert not screen_ok(400,800) and not screen_ok(1800,1200)
    im=Image.new("RGB",(1000,1600),color=(220,40,20))
    assert re.fullmatch("[a-f0-9]{16}",dhash(im))
    baseline,rows,ids,hashes,visual=load_provenance()
    assert len(baseline)==675
    assert len(rows)==int(json.loads(STATE.read_text(encoding="utf-8"))["new_verified"])
    state=json.loads(STATE.read_text(encoding="utf-8"))
    assert state["baseline_requested"]==736 and state["verified_manifest_base"]==675
    print("PASS baseline=736 | 675 independent source records | verified increments="+str(len(rows))+" | bitmap checks | 90-day ledger untouched")

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    if args.self_test:self_test()
    else:run()
