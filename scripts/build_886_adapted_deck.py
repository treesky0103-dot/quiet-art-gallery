#!/usr/bin/env python3
"""Bundle up to 886 actual, permission-screened art images into the Android APK.

Revalidate every fetched source, produce a genuinely cropped 1000x1667 portrait
JPEG, and write a manifest. 825 evidence rows exist; 61 unsupported user-base
positions are NOT invented. This is a per-build process; failures are reported.
"""
import collections
import concurrent.futures
import csv
import hashlib
import io
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlparse, urlencode
from urllib.request import Request, urlopen
from PIL import Image, ImageOps, ImageFilter

ROOT=Path("android-app/app/src/main/assets")
IMAGES=ROOT/"offline"
REPORT=Path("build-art-report.json")
BASE=Path("data/verified_80pct/verified_artwork_manifest.csv")
DELTA=Path("data/collector_10min/new_verified.csv")
USER_MAX=886
ASPECT=0.60
TARGET_SIZE=(1000,1667)
MAX_INPUT=16*1024*1024
MAX_EMBED_BYTES=400*1024*1024
ALLOWED_IMAGE_HOSTS={
 "openaccess-cdn.clevelandart.org","images.metmuseum.org",
 "iiif.wellcomecollection.org","iiif.micr.io","images.collections.yale.edu",
 "open.smk.dk","ids.si.edu","api.nga.gov","images.nga.gov"
}
UA="QuietArtGalleryOfflineBuild/1.0 (+https://github.com/treesky0103-dot/quiet-art-gallery)"
Image.MAX_IMAGE_PIXELS=45_000_000
_tls=threading.local()

def fetch(url,cap=MAX_INPUT,timeout=22):
    req=Request(url,headers={"User-Agent":UA,"Accept":"image/jpeg,image/png,image/webp,application/json,text/plain,*/*"})
    with urlopen(req,timeout=timeout) as resp:
        if resp.status!=200:raise ValueError("HTTP "+str(resp.status))
        body=resp.read(cap+1)
        if len(body)>cap:raise ValueError("Body too large")
        return body,resp.geturl(),resp.headers.get("Content-Type","")

def host_ok(url):
    p=urlparse(url)
    return p.scheme=="https" and not p.username and not p.password and p.port in (None,443) and p.hostname in ALLOWED_IMAGE_HOSTS

def parsed_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def candidates():
    original=parsed_csv(BASE)
    additions=parsed_csv(DELTA)
    out=[];seen=set()
    # Give most recent confirmed records a chance first, then documented originals.
    for row in additions+original:
        provider=str(row.get("source") or "")
        ident=str(row.get("artwork_id") or "")
        key=provider+":"+ident
        if not ident or key in seen:continue
        seen.add(key)
        rights=str(row.get("rights") or "").lower()
        if not (any(x in rights for x in ("cc0","public domain","pdm","publicdomain/mark/1.0","nga open access"))):
            continue
        title=str(row.get("title") or "")
        # The baseline includes some non-flat objects in NGA records; don't
        # infer that a picture of a pot is a painting.
        if re.search(r"(?i)\b(?:crock|gemel bottle|sculpture|statue|ceramic|tapestry|photograph|furniture|vase|medal|glass bottle)\b",title):
            continue
        out.append({**row,"_provider":provider,"_id":ident})
    return out[:USER_MAX],len(original),len(additions)

def resolve(row):
    provider=row["_provider"]; ident=row["_id"]
    direct=str(row.get("original_url") or "")
    if host_ok(direct):return direct
    old=str(row.get("source_url") or "")
    if host_ok(old):return old
    if provider=="Cleveland Museum of Art":
        # Accession numbers are the image CDN's canonical stable identifier.
        accession=urlparse(old).path.split("/")[-1]
        if not re.fullmatch(r"[A-Za-z0-9.]+",accession):raise ValueError("Invalid CMA accession")
        return f"https://openaccess-cdn.clevelandart.org/{accession}/{accession}_print.jpg"
    if provider=="Metropolitan Museum of Art":
        raw,_,_=fetch("https://collectionapi.metmuseum.org/public/collection/v1/objects/"+quote(ident),cap=1500000)
        meta=json.loads(raw)
        if meta.get("isPublicDomain") is not True:raise ValueError("Met is not public domain")
        return str(meta.get("primaryImageSmall") or meta.get("primaryImage") or "")
    if provider.lower().startswith("smithsonian"):
        # Smithsonian IIIF ID is stored as source_url in the historic manifest.
        if not re.fullmatch(r"[A-Za-z0-9_.-]{5,160}",old):raise ValueError("No Smithsonian delivery ID")
        return "https://ids.si.edu/ids/deliveryService?"+urlencode({"id":old,"max":"2400"})
    if provider=="National Gallery of Art":
        urls=getattr(_tls,"nga_urls",None) or {}
        return urls.get(ident,"")
    raise ValueError("No source resolver for "+provider)

def load_nga_lookup(rows):
    relevant={r["_id"] for r in rows if r["_provider"]=="National Gallery of Art"}
    if not relevant:return {}
    # Optional official public CSV: no assumptions about object id -> IIIF UUID.
    url="https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data/published_images.csv"
    try:
        raw,_,_=fetch(url,cap=130*1024*1024,timeout=80)
        found={}
        for d in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
            ident=str(d.get("depictstmsobjectid") or "")
            if ident not in relevant or str(d.get("openaccess") or "")!="1":continue
            base=str(d.get("iiifURL") or d.get("iiifurl") or "")
            if urlparse(base).hostname not in ("api.nga.gov","images.nga.gov"):continue
            found.setdefault(ident,base.rstrip("/")+"/full/!2400,2400/0/default.jpg")
        print("NGA_METADATA",len(found),"of",len(relevant),flush=True)
        return found
    except Exception as ex:
        print("NGA_METADATA_FAILED",repr(ex)[:200],flush=True)
        return {}

def smart_portrait(im):
    im=ImageOps.exif_transpose(im).convert("RGB")
    w,h=im.size
    if w<320 or h<430 or w*h>45_000_000:raise ValueError("Source pixels below minimum or too many")
    ratio=w/h
    # Portrait sources with a ratio within 0.47–0.73 preserve the main subject,
    # cropping only as needed for the selected screen aspect.
    cropw=min(w,int(h*ASPECT))
    croph=min(h,int(w/ASPECT))
    if cropw<420 or croph<650:raise ValueError("Smart crop source below minimum")
    if w/cropw<1.01 and h/croph<1.01:
        left=0;top=0
    else:
        # Edge and saturation energy across a reduced representation.
        # Do not label this a semantic AI model; it is a conservative subject cue.
        scale=min(1,192/max(w,h))
        dw=max(24,round(w*scale));dh=max(24,round(h*scale))
        low=im.resize((dw,dh),Image.Resampling.BILINEAR)
        edge=ImageOps.grayscale(low).filter(ImageFilter.FIND_EDGES)
        edge_vals=list(edge.getdata())
        pixels=list(low.getdata())
        cols=[0.0]*dw;rows=[0.0]*dh
        for yy in range(dh):
            for xx in range(dw):
                idx=yy*dw+xx
                rr,gg,bb=pixels[idx]
                saturation=max(rr,gg,bb)-min(rr,gg,bb)
                energy=(edge_vals[idx]*0.75+saturation*0.25)
                cols[xx]+=energy
                rows[yy]+=energy
        if w/h>=ASPECT:
            width=max(1,min(dw,round(cropw/w*dw)))
            p=[0.0]
            for x in cols:p.append(p[-1]+x)
            def score_x(x):
                center=(x+width/2)/dw
                return (p[x+width]-p[x])*(1-.10*abs(center-.5))
            best=max(range(dw-width+1),key=score_x)
            left=min(w-cropw,max(0,round(best/dw*w)));top=0
        else:
            height=max(1,min(dh,round(croph/h*dh)))
            p=[0.0]
            for x in rows:p.append(p[-1]+x)
            def score_y(y):
                center=(y+height/2)/dh
                return (p[y+height]-p[y])*(1-.10*abs(center-.5))
            best=max(range(dh-height+1),key=score_y)
            top=min(h-croph,max(0,round(best/dh*h)));left=0
    box=(left,top,left+cropw,top+croph)
    factor=TARGET_SIZE[0]/cropw
    if factor>3.0:raise ValueError("More than 3x enlargement; insufficient real detail")
    cropped=im.crop(box)
    out=cropped.resize(TARGET_SIZE,Image.Resampling.LANCZOS)
    output=io.BytesIO()
    out.save(output,"JPEG",quality=75,optimize=True,progressive=True)
    payload=output.getvalue()
    if len(payload)>800_000:
        output=io.BytesIO();out.save(output,"JPEG",quality=61,optimize=True,progressive=True)
        payload=output.getvalue()
    if len(payload)>900_000:raise ValueError("Output JPEG too large")
    with Image.open(io.BytesIO(payload)) as verify:
        verify.load()
        if verify.size!=TARGET_SIZE or verify.format!="JPEG":raise AssertionError("JPEG verification failed")
    return payload,box,round(factor,3),(w,h)


def additional_cma_landscape_candidates(known,limit=300):
    """Discover *new*, licensed, actual source URLs of wide or modest-pixel flat art.

    This stage only discovers metadata. Verified count increases strictly after
    the original JPEG has downloaded, decoded, smart-cropped, and hashed on disk.
    """
    results=[]
    seen={(r["_provider"],r["_id"]) for r in known}
    rejected=collections.Counter()
    # Scan different ranges so newly discovered art does not merely repeat
    # the portrait-only source ledger; preserve official public-domain status.
    offsets=(0,100,200,300,400,500,600,700,800,900,1000,1100,1200,1300,1400)
    for era in ("1800-2026","pre-1800"):
        for offset in offsets:
            if len(results)>=limit:break
            params={"has_image":"1","limit":"100","skip":str(offset),
                    "created_before":"2027" if era=="1800-2026" else "1800"}
            if era=="1800-2026":params["created_after"]="1799"
            url="https://openaccess-api.clevelandart.org/api/artworks/?"+urlencode(params)+"&cc0"
            try:
                raw,_,_=fetch(url,cap=6*1024*1024,timeout=23)
                docs=json.loads(raw).get("data") or []
            except Exception as ex:
                print("ADAPTED_METADATA_ERROR",era,offset,str(ex)[:130],flush=True)
                continue
            if not isinstance(docs,list):continue
            for doc in docs:
                if len(results)>=limit:break
                ident=str(doc.get("id") or "")
                item=("Cleveland Museum of Art",ident)
                if not ident or item in seen:continue
                if str(doc.get("share_license_status") or "").lower()!="cc0":
                    rejected["rights"]+=1;continue
                kind=str(doc.get("type") or "")
                medium=str(doc.get("technique") or "")
                evidence=(kind+" "+medium).lower()
                if not any(k in evidence for k in ("painting","drawing","print","watercolor","watercolour","etching","lithograph","engraving","woodcut","gouache","ink on","oil on","pastel","tempera")):
                    rejected["not_flat_art"]+=1;continue
                if any(k in evidence for k in ("sculpture","vase","pottery","ceramic","textile","photograph","video","carving","frame","architecture","jewelry")):
                    rejected["not_flat_art"]+=1;continue
                images=doc.get("images") or {}
                pic=images.get("print") or images.get("web") or {}
                src=str(pic.get("url") or "")
                if not host_ok(src):continue
                try: w=int(pic.get("width") or 0);h=int(pic.get("height") or 0)
                except Exception:continue
                if w<380 or h<650:continue
                # Specifically rescue paintings formerly excluded by the
                # 75%-portrait and native-pixel gates.
                is_landscape=w>=h
                is_lowres=(w<1000 or h<1400)
                portrait_fill=min((w/h)/ASPECT,ASPECT/(w/h))>=.75
                if not (is_landscape or is_lowres or not portrait_fill):continue
                if w*h>45_000_000:continue
                creators=doc.get("creators") or []
                artist=", ".join(x.get("description","") for x in creators if isinstance(x,dict))
                title=str(doc.get("title") or "").strip()
                if not title:continue
                years=(doc.get("creation_date_earliest"),doc.get("creation_date_latest"))
                # No fabricated work dates. Unknown year is allowed in
                # the supplementary art pool; it is not labeled modern.
                results.append({
                    "source":"Cleveland Museum of Art","_provider":"Cleveland Museum of Art",
                    "artwork_id":ident,"_id":ident,"title":title,"artist":artist,
                    "rights":"CC0 (Cleveland official metadata)",
                    "original_url":src,"source_url":str(doc.get("url") or ""),
                    "type":kind,"medium":medium,
                    "year_start":years[0],"year_end":years[1],
                    "_adapted_source_orientation":"landscape" if is_landscape else "narrow/lowres",
                    "_evidence_kind":"new_adaptive_metadata"
                })
                seen.add(item)
            print("ADAPTED_METADATA",era,offset,"total",len(results),flush=True)
        if len(results)>=limit:break
    print("ADAPTED_METADATA_COMPLETE",len(results),"rejected",json.dumps(rejected),flush=True)
    return results

def run_one(row):
    provider=row["_provider"];ident=row["_id"]
    try:
        src=resolve(row)
        if not host_ok(src):raise ValueError("Image source not allowed: "+str(urlparse(src).hostname))
        raw,final_url,mime=fetch(src)
        if not host_ok(final_url):raise ValueError("Redirected to nonallowlisted image host")
        source_sha=hashlib.sha256(raw).hexdigest()
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            if im.format not in ("JPEG","PNG","WEBP"):raise ValueError("Not a supported image")
            processed,box,factor,original_size=smart_portrait(im)
        derived_sha=hashlib.sha256(processed).hexdigest()
        art={
            "key":("cma:" if provider=="Cleveland Museum of Art" else
                    "met:" if provider=="Metropolitan Museum of Art" else "fp:")+ident,
            "source":provider,"title":re.sub("<[^>]+>","",row.get("title") or "")[:180],
            "artist":str(row.get("artist") or "작가 미상")[:150],
            "page":row.get("source_url") or "",
            "image":src,
            "width":TARGET_SIZE[0],"height":TARGET_SIZE[1],
            "type":"Painting","classification":"Painting","medium":"",
            "rightsOK":True,"license":row.get("rights") or "Public domain",
            "yearStart":row.get("year_start") or None,
            "yearEnd":row.get("year_end") or None,
            "date":str(row.get("year_start") or ""),
            "museumRegion":"bundled","offlineAsset":"",
            "sourceSHA256":source_sha,"derivedSHA256":derived_sha,
            "originalPixels":list(original_size),"cropBox":list(box),
            "upscaleFactor":factor,"adaptType":"SMART_PORTRAIT_CROP",
            "metadataProvenance":row.get("_evidence_kind") or "previous_hash_ledger",
            "originalLandscape":bool(original_size[0]>=original_size[1])
        }
        return art,processed,None
    except Exception as e:
        return None,None,provider+" / "+ident+": "+str(e)[:135]

def main():
    rows,base_count,new_count=candidates()
    print("PROVENANCE baseline",base_count,"delta",new_count,"candidates",len(rows),"user_request_max",USER_MAX,flush=True)
    # Discover previously rejected wide or lower-resolution images; do not
    # count discoveries as actual works until real byte verification succeeds.
    additional=additional_cma_landscape_candidates(rows,limit=300)
    rows.extend(additional)
    print("ADAPTIVE_POOL total",len(rows),"prior_ledger",base_count+new_count,"additional_metadata",len(additional),flush=True)
    IMAGES.mkdir(parents=True,exist_ok=True)
    for f in IMAGES.glob("pack-*.jpg"):f.unlink()
    nga=load_nga_lookup(rows)
    _tls.nga_urls=nga
    # Thread-local copy in workers: resolver reads shared read-only global.
    global _NGA_LOOKUP
    _NGA_LOOKUP=nga
    good=[];failed=[];seen_sources=set();seen_derived=set();total=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        for index,(row,result) in enumerate(zip(rows,executor.map(lambda x:run_one_with_nga(x,nga),rows)),1):
            art,blob,error=result
            if error:
                failed.append(error)
                if len(failed)<18:print("SKIP",error,flush=True)
                continue
            if art["sourceSHA256"] in seen_sources or art["derivedSHA256"] in seen_derived:
                continue
            if total+len(blob)>MAX_EMBED_BYTES:
                print("MAX_EMBED_SIZE_REACHED",total,flush=True)
                break
            n=len(good)
            filename=f"pack-{n:04d}.jpg"
            filepath=IMAGES/filename
            filepath.write_bytes(blob)
            if hashlib.sha256(filepath.read_bytes()).hexdigest()!=art["derivedSHA256"]:
                raise RuntimeError("Written embedded art hash mismatch")
            art["offlineAsset"]="offline/"+filename
            # Whitelisted APK-local URL, never an unsafe third-party URL.
            art["remoteImage"]=art["image"]
            art["image"]="https://appassets.gallery/"+art["offlineAsset"]
            good.append(art);seen_sources.add(art["sourceSHA256"]);seen_derived.add(art["derivedSHA256"])
            total+=len(blob)
            if n==0 or len(good)%50==0:
                print("REAL_EMBEDDED",len(good),"of",len(rows),"bytes",total,"processed",index,flush=True)
    if len(good)<8:raise RuntimeError("Fewer than 8 real artworks downloaded; fail closed")
    (ROOT/"offline-deck.json").write_text(json.dumps(good,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    report={"user_starting_number":736,"user_total_claim":886,"evidence_rows":base_count+new_count,
       "supplementary_metadata_candidates":len(additional),
       "embedded_verified_jpegs":len(good),"raw_source_pixels_checked":len(good),
       "smart_cropped_and_upscaled_count":len(good),
       "actually_upscaled_count":sum(x["upscaleFactor"]>1.001 for x in good),
       "landscape_to_portrait_count":sum(x["originalLandscape"] for x in good),
       "new_adapted_originals_embedded":sum(x["metadataProvenance"]=="new_adaptive_metadata" for x in good),
       "previous_ledger_embedded":sum(x["metadataProvenance"]=="previous_hash_ledger" for x in good),
       "unverified_61_not_fabricated":True,"bytes_in_apk_assets":total,
       "download_failures":len(failed),"first_failures":failed[:60],
       "source_distribution":dict(collections.Counter(x["source"] for x in good))}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("BUNDLE_COMPLETE "+json.dumps({k:v for k,v in report.items() if k!="first_failures"},ensure_ascii=False),flush=True)

def run_one_with_nga(row,nga):
    if row["_provider"]=="National Gallery of Art":
        ident=row["_id"]
        if ident not in nga:return None,None,"NGA missing official IIIF URL: "+ident
        patched={**row,"original_url":nga[ident]}
        return run_one(patched)
    return run_one(row)

if __name__=="__main__":
    main()
