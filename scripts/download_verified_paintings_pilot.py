#!/usr/bin/env python3
"""Download-and-decode verified painting images, bounded pilot, not a 259,200 claim.

Sources: Cleveland Museum of Art CC0 and Art Institute of Chicago public domain.
The output is actual image bytes + SHA256 + dHash + provenance + exact 17-slot quotas.
A file is 'acquired' only if disk readback and image decode pass.
Never ignore copyright or incorrectly count artworks without actual image files.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

try:
    from PIL import Image, ImageOps
except ImportError:
    raise SystemExit("Pillow required: python -m pip install Pillow")

BASE=Path("downloaded-paintings-audit")
IMAGES=BASE/"images"
IMAGES.mkdir(parents=True,exist_ok=True)
MAX_IMAGES=max(1,min(int(os.environ.get("MAX_IMAGES","120")),500))
MAX_PAGES=max(1,min(int(os.environ.get("MAX_PAGES","24")),100))
MAX_FILE_BYTES=10*1024*1024
TOTAL_MAX_BYTES=430*1024*1024
UA="QuietArtGalleryResearch/1.0 (https://github.com/treesky0103-dot/quiet-art-gallery)"
CMA="https://openaccess-api.clevelandart.org/api/artworks/"
AIC="https://api.artic.edu/api/v1/artworks"
BLOCK_TERMS=re.compile(r"\b(?:photograph|poster|installation|sculpture|interior of|room view|view of the gallery|exhibition|framed view|tapestry|vase|ceramic|statue)\b",re.I)
STYLE_RULES=[
 ("post-impressionism",r"\bpost[\s-]*impressionis"),
 ("neoclassicism",r"\bneo[\s-]*classic"),
 ("renaissance",r"\brenaissance\b"),
 ("baroque",r"\bbaroque\b"),
 ("rococo",r"\brococo\b"),
 ("romanticism",r"\bromanticis"),
 ("realism",r"\brealis"),
 ("impressionism",r"\bimpressionis"),
 ("expressionism",r"\bexpressionis"),
 ("cubism",r"\bcubis"),
 ("surrealism",r"\bsurreal"),
 ("abstract",r"\babstract\b"),
 ("contemporary",r"\bcontemporary\b"),
]
SLOTS=[
 ("renaissance","르네상스"),
 ("baroque","바로크"),
 ("rococo","로코코"),
 ("neoclassicism","신고전주의"),
 ("romanticism","낭만주의"),
 ("realism","사실주의"),
 ("impressionism","인상주의"),
 ("post-impressionism","후기인상주의"),
 ("expressionism","표현주의"),
 ("cubism","입체주의"),
 ("surrealism","초현실주의"),
 ("abstract","추상미술"),
 ("contemporary","현대미술"),
 ("asian","아시아 회화"),
 ("african","아프리카 미술관 소장 회화"),
 ("additional","세계 미술관 소장 회화"),
 ("modern","현대 디지털 아트·회화"),
]
assert len(SLOTS)==17

def get(url,as_json=True,timeout=25):
    error=None
    for attempt in range(3):
        try:
            req=Request(url,headers={"User-Agent":UA,"Accept":"application/json" if as_json else "image/*"})
            with urlopen(req,timeout=timeout) as f:
                if f.status!=200:raise RuntimeError("HTTP "+str(f.status))
                if as_json:return json.load(f)
                blob=f.read(MAX_FILE_BYTES+1)
                if len(blob)>MAX_FILE_BYTES:raise RuntimeError("file too large")
                return blob
        except Exception as e:
            error=e
            if attempt<2:time.sleep(1.5*(attempt+1))
    raise error

def candidates(provider,page):
    if provider=="cma":
        url=CMA+"?"+urlencode({"limit":100,"skip":page*100,"has_image":"1","cc0":"1","type":"Painting"})
        response=get(url)
        for rec in response.get("data") or []:
            img=rec.get("images") or {}
            photo=(img.get("web") or {}).get("url") or (img.get("print") or {}).get("url") or ""
            licence=str(rec.get("share_license_status") or "")
            if licence!="CC0" or not photo.startswith("https://"):continue
            ty=str(rec.get("type") or "")
            if "paint" not in ty.lower():continue
            title=str(rec.get("title") or "")
            creators=rec.get("creators") or []
            if isinstance(creators,list):
                artist=" / ".join(str(z.get("description","")) for z in creators[:2] if isinstance(z,dict))
            else:artist=""
            fields=[rec.get("period"),rec.get("style"),rec.get("culture"),rec.get("department")]
            yield {"provider":provider,"id":str(rec.get("id")),"title":title,"artist":artist,
                   "url":photo,"license":"CC0","type":ty,
                   "style_evidence":" ".join(str(v or "") for v in fields),
                   "museum_url":"https://www.clevelandart.org/art/"+str(rec.get("accession_number") or "")}
    else:
        fields="id,title,artist_title,image_id,is_public_domain,artwork_type_title,style_title,classification_title,place_of_origin,date_display"
        url=AIC+"?"+urlencode({"page":page+1,"limit":100,"fields":fields})
        response=get(url)
        for rec in response.get("data") or []:
            if not rec.get("is_public_domain") or not rec.get("image_id"):continue
            ty=str(rec.get("artwork_type_title") or rec.get("classification_title") or "")
            if "paint" not in ty.lower():continue
            image_url="https://www.artic.edu/iiif/2/"+str(rec["image_id"])+"/full/1686,/0/default.jpg"
            yield {"provider":provider,"id":str(rec.get("id")),"title":str(rec.get("title") or ""),
                   "artist":str(rec.get("artist_title") or ""),"url":image_url,
                   "license":"Public Domain","type":ty,
                   "style_evidence":str(rec.get("style_title") or ""),
                   "museum_url":"https://www.artic.edu/artworks/"+str(rec.get("id") or "")}

def classify(record):
    # A single verified painting belongs to exactly one of the existing 17 slots.
    # No guessed style from creation date or artist name.
    evidence=str(record.get("style_evidence") or "")
    for k,pattern in STYLE_RULES:
        if re.search(pattern,evidence,re.I):return k
    return "additional"

def dhash(img):
    g=ImageOps.grayscale(img).resize((9,8),Image.Resampling.LANCZOS)
    pixels=list(g.getdata())
    bits=0
    for y in range(8):
        for x in range(8):
            bits=(bits<<1)|(1 if pixels[y*9+x]>pixels[y*9+x+1] else 0)
    return bits

def valid_image(blob):
    img=Image.open(io.BytesIO(blob))
    img.load()
    if img.format not in ("JPEG","PNG","WEBP"):raise ValueError("unsupported encoding")
    if getattr(img,"n_frames",1)>1:raise ValueError("animated image")
    width,height=img.size
    if width>=height or min(width,height)<1000 or max(width,height)<1400:
        raise ValueError("portrait resolution/ratio")
    fill=min((width/height)/.625,.625/(width/height))
    if fill<.75:raise ValueError("portrait fill <75%")
    return img,width,height,fill

def main():
    seen_ids=set();seen_sha=set();seen_visual=[];saved=[];errors=[];stats={}
    bytes_stored=0;lookup_counts={"cma":0,"aic":0}
    # Search Cleveland and Chicago alternately, balancing the two distinct providers.
    for page in range(MAX_PAGES):
        for provider in ("cma","aic"):
            if len(saved)>=MAX_IMAGES or bytes_stored>=TOTAL_MAX_BYTES:break
            try:records=list(candidates(provider,page))
            except Exception as e:
                errors.append({"provider":provider,"page":page,"error":str(e)[:200]})
                print("PROVIDER_ERROR",provider,page,str(e)[:160],flush=True)
                continue
            print("PAGE",provider,page,"records",len(records),flush=True)
            lookup_counts[provider]+=len(records)
            for rec in records:
                if len(saved)>=MAX_IMAGES or bytes_stored>=TOTAL_MAX_BYTES:break
                identity=provider+":"+rec["id"]
                if identity in seen_ids:continue
                seen_ids.add(identity)
                if BLOCK_TERMS.search(rec["title"]+" "+rec["type"]):continue
                try:
                    blob=get(rec["url"],as_json=False)
                    img,width,height,fill=valid_image(blob)
                    sha=hashlib.sha256(blob).hexdigest()
                    if sha in seen_sha:continue
                    visual=dhash(img)
                    if any((visual^previous).bit_count()<=5 for previous in seen_visual):continue
                    suffix=".png" if img.format=="PNG" else ".webp" if img.format=="WEBP" else ".jpg"
                    filename=f"{len(saved)+1:05d}_{provider}_{rec['id']}{suffix}"
                    dest=IMAGES/filename
                    dest.write_bytes(blob)
                    raw=dest.read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=sha:raise RuntimeError("readback hash mismatch")
                    reimg=Image.open(io.BytesIO(raw));reimg.load()
                    if reimg.size!=(width,height):raise RuntimeError("readback decode mismatch")
                    rec.update({"path":str(dest),"sha256":sha,"dhash64":f"{visual:016x}",
                                "width":width,"height":height,"fill":round(fill,5),
                                "bytes":len(raw),"category":classify(rec)})
                    rec.pop("url",None) # local file and originating museum URL retained; never misrepresent.
                    saved.append(rec);seen_sha.add(sha);seen_visual.append(visual)
                    bytes_stored+=len(blob)
                    if len(saved)%20==0:
                        print("VERIFIED",len(saved),"bytes",bytes_stored,flush=True)
                except Exception as e:
                    if len(errors)<100:
                        errors.append({"provider":provider,"id":rec["id"],"error":str(e)[:200]})
            time.sleep(.18)
        if len(saved)>=MAX_IMAGES or bytes_stored>=TOTAL_MAX_BYTES:break
    total=259200
    distribution=[total//17+(1 if i<total%17 else 0) for i in range(17)]
    slots=[]
    for i,(cat,label) in enumerate(SLOTS):
        eligible=[x for x in saved if x["category"]==cat]
        slots.append({"index":i+1,"category":cat,"label":label,
                      "required_90days":distribution[i],"actually_downloaded":len(eligible),
                      "shortfall":distribution[i]-len(eligible)})
    report={"requested_paintings":total,"category_count":17,
            "source_scopes":["Cleveland Art Museum paintings CC0","Art Institute of Chicago public domain paintings"],
            "downloaded_decoded_sha_verified":len(saved),"downloaded_bytes":bytes_stored,
            "one_file_one_picture":True,"unique_sha256":len(seen_sha),
            "met_259200_goal":len(saved)>=total and all(z["shortfall"]==0 for z in slots),
            "minimum_screen_fill":.75,"minimum_pixels_short":1000,"minimum_pixels_long":1400,
            "eligible_classification":"official style metadata, otherwise worldwide paintings",
            "provider_candidates_seen":lookup_counts,"source_errors":errors,
            "by_category":slots,"actual_files":saved,
            "caveat":"This is a bounded real image download; not 90-day complete and no tablet APK changed."}
    (BASE/"manifest_verified.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    (BASE/"sha256sum.txt").write_text("".join(f"{x['sha256']}  {Path(x['path']).name}\n" for x in saved),encoding="utf-8")
    print("FINAL_VERIFIED",json.dumps({"downloaded":len(saved),"bytes":bytes_stored,
        "by_category":[[x["index"],x["actually_downloaded"]] for x in slots],
        "met_259200_goal":report["met_259200_goal"],"source_errors":len(errors)},ensure_ascii=False),flush=True)
    if len(saved)==0:raise SystemExit("No images verified; pilot failed")
if __name__=="__main__":main()
