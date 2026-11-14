#!/usr/bin/env python3
"""Actual open-access portrait painting byte collector from museum-specific Commons.
Used as independent fallback for source HTTP errors. No 259,200 completion claim.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import time
import urllib.request

from PIL import Image,ImageOps
from audit_29_fields_90day import discover_repo_museum_categories,commons,MUSEUMS,USER_AGENT

ROOT=Path("downloaded-commons-paintings")
ART=ROOT/"images"
ART.mkdir(parents=True,exist_ok=True)
MAX_IMAGES=max(1,min(int(os.environ.get("MAX_IMAGES","70")),200))
MAX_CATEGORIES=max(1,min(int(os.environ.get("MAX_CATEGORIES","42")),50))
MAX_BYTES=200*1024*1024
def phash(img):
    mini=ImageOps.grayscale(img).resize((9,8),Image.Resampling.LANCZOS)
    p=list(mini.getdata());v=0
    for y in range(8):
        for x in range(8):
            v=v*2+(p[y*9+x]>p[y*9+x+1])
    return v

def fetch_image(url):
    if not url.startswith("https://upload.wikimedia.org/"):raise ValueError("non-Wikimedia CDN rejected")
    req=urllib.request.Request(url,headers={"User-Agent":USER_AGENT,"Accept":"image/*"})
    with urllib.request.urlopen(req,timeout=18) as resp:
        b=resp.read(9*1024*1024+1)
    if len(b)>9*1024*1024:raise ValueError("image >9 MiB")
    return b

def main():
    extra,registry_count=discover_repo_museum_categories()
    # Focus on paintings or paintings in collections, not museum prints/objects.
    candidates=[(kind,cat) for kind,mid,cat in extra
                if kind in ("world_museum","asian_museum","african_museum") and "paint" in cat.lower()]
    candidates += [("world_museum",cat) for mid,cat in MUSEUMS if "paint" in cat.lower()]
    # These have historically yielded the most public-domain vertical first-page hits.
    preferred=("Walters","National Palace Museum","Museo del Prado","Smithsonian American Art",
               "Lima","Colombia","Museo Nacional de Bellas","Rijksmuseum","Auckland","Kyoto","Freer",
               "Victoria","Museo del Louvre","Hermitage")
    def rank(x):
        s=x[1]
        return (next((i for i,n in enumerate(preferred) if n in s),99),s)
    selected=sorted(dict((c,(k,c)) for k,c in candidates).values(),key=rank)[:MAX_CATEGORIES]
    collected=[];hashes=set();visuals=[];bytes_stored=0;failed=[];queries=0;candidate_total=0
    for kind,category in selected:
        if len(collected)>=MAX_IMAGES or bytes_stored>=MAX_BYTES:break
        try:
            listing=commons(category)
            queries+=1
            images=listing["sample_candidates"]
            candidate_total+=len(images)
        except Exception as e:
            failed.append({"category":category,"stage":"metadata","error":str(e)[:140]})
            continue
        print("SOURCE",category,"eligible_metadata",len(images),flush=True)
        for item in images:
            if len(collected)>=MAX_IMAGES or bytes_stored>=MAX_BYTES:break
            try:
                data=fetch_image(item["url"])
                img=Image.open(io.BytesIO(data));img.load()
                if img.format not in ("JPEG","PNG","WEBP") or getattr(img,"n_frames",1)>1:
                    raise ValueError("image format")
                w,h=img.size
                fill=min((w/h)/.625,.625/(w/h))
                if w>=h or w<1000 or h<1400 or fill<.75:raise ValueError("decoded portrait")
                sha=hashlib.sha256(data).hexdigest()
                if sha in hashes:continue
                visual=phash(img)
                if any((visual^v).bit_count()<=5 for v in visuals):continue
                ext=".png" if img.format=="PNG" else ".webp" if img.format=="WEBP" else ".jpg"
                filename=f"{len(collected)+1:05d}_{item['pageid']}{ext}"
                path=ART/filename
                path.write_bytes(data)
                reloaded=path.read_bytes()
                if hashlib.sha256(reloaded).hexdigest()!=sha:raise ValueError("SHA readback")
                with Image.open(io.BytesIO(reloaded)) as second:
                    second.load()
                    if second.size!=(w,h):raise ValueError("decoded readback")
                category_slot="asian" if kind=="asian_museum" else "african" if kind=="african_museum" else "additional"
                collected.append({"slot":category_slot,"category":category,"commons_title":item["title"],
                   "pageid":item["pageid"],"license":item["license"],"path":str(path),
                   "sha256":sha,"dhash64":f"{visual:016x}","width":w,"height":h,
                   "bytes":len(data),"fill":round(fill,4)})
                hashes.add(sha);visuals.append(visual);bytes_stored+=len(data)
                if len(collected)%10==0:print("ACTUAL_DOWNLOADED",len(collected),flush=True)
            except Exception as e:
                if len(failed)<30:failed.append({"category":category,"pageid":item["pageid"],
                                                "stage":"download","error":str(e)[:120]})
        time.sleep(.2)
    summary={"target":259200,"actual_verified_downloads":len(collected),"saved_bytes":bytes_stored,
        "catalog_all_17_complete":False,"museum_categories_probed":queries,
        "metadata_eligible_first_pages":candidate_total,
        "distinct_sha":len(hashes),
        "proof_files":collected,"failures_sample":failed,
        "source_scope":"Public-domain/CC0 tagged museum paintings on Wikimedia Commons",
        "known_limit":"No proof yet that 17 strict painting fields each have 15,247+ artworks"}
    (ROOT/"manifest_verified.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    print("FINAL_COMMONS",json.dumps({"downloaded":len(collected),"bytes":bytes_stored,
        "probed":queries,"metadata_sample":candidate_total,"goal_complete":False},ensure_ascii=False),flush=True)
    if not collected:raise SystemExit("No actual images downloaded")
if __name__=="__main__":main()
