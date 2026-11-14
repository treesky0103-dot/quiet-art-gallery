#!/usr/bin/env python3
"""Append actual photos and static animation cels/stills to 886 painting deck.

No result count is invented: every photo or still must have a documented CC0/PD
source, successful download, decoded and EXIF-corrected original, in-memory
portrait conversion, real JPEG write/read and distinct SHA256. Appends to the
existing offline-deck.json without mutating or dropping the 886 earlier works.
Animation consists of STATIC STILLS only (not motion/video/GIF reproduction).
"""
from __future__ import annotations
import collections
import concurrent.futures
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,urlopen
from PIL import Image,ImageOps

# Import the previously tested, exact same CPU-based portrait transformer
# without triggering the original painting build's __main__.
from build_886_adapted_deck import smart_portrait

ROOT=Path("android-app/app/src/main/assets")
IMG_DIR=ROOT/"offline"
DECK=ROOT/"offline-deck.json"
REPORT=Path("build-art-report.json")
NEW_REPORT=Path("build-mixed-media-report.json")
MAX_PHOTO=600
MAX_ANIMATION=110
MAX_TOTAL_ARTWORK=1800
MAX_TOTAL_ASSET_BYTES=675*1024*1024
MAX_SOURCE_BYTES=14*1024*1024
WORKERS=9
USER_AGENT="QuietArtGalleryPersonalViewer/1.0 (+https://github.com/treesky0103-dot/quiet-art-gallery)"
ALLOW_IMAGE_HOSTS={"openaccess-cdn.clevelandart.org","upload.wikimedia.org"}
ALLOW_METADATA_HOSTS={"openaccess-api.clevelandart.org","commons.wikimedia.org"}
Image.MAX_IMAGE_PIXELS=45_000_000
PHOTO_QUERIES=("Nature photography","Landscape photographs","Wildlife photographs",
    "Street photography","Portrait photographs","Historical photographs",
    "Photographs in the public domain","Photographs of nature")
ANIMATION_QUERIES=("Animation stills","Animation cels","Animation drawings",
    "Animated film screenshots","Screenshots of animated films",
    "Hand-drawn animation","Animation films in the public domain",
    "Gertie the Dinosaur","Fantasmagorie 1908","Felix the Cat animation",
    "Steamboat Willie 1928","Public domain cartoons","Early animation",
    "Little Nemo animated film")
EXCLUDE_ANIM_TITLE=re.compile(
    r"\b(?:logo|poster|advert|billboard|sculpture|figure|figurine|"
    r"costume|cosplay|t-shirt|toy|map|flag|museum room|exhibition|"
    r"photograph of|film projector|theater exterior|theme park|plush)\b",re.I)
REQUIRE_ANIM_HINT=re.compile(
    r"(?:animat|cartoon|film still|film frame|screenshot|screen shot|"
    r"cel\b|gertie|fantasmagorie|felix the cat|steamboat willie|"
    r"little nemo|silly symphon)",re.I)

def request(url, allowed_hosts, max_bytes=MAX_SOURCE_BYTES, timeout=25):
    p=urlsplit(url)
    if p.scheme!="https" or p.hostname not in allowed_hosts or p.port not in (None,443) or p.username:
        raise ValueError("Non-allowlisted host")
    req=Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/json,image/jpeg,image/png,image/webp,*/*"})
    with urlopen(req,timeout=timeout) as r:
        if r.status!=200:raise ValueError("HTTP "+str(r.status))
        target=urlsplit(r.geturl())
        if target.hostname not in allowed_hosts:raise ValueError("Redirect host changed")
        if r.headers.get("Content-Length") and int(r.headers["Content-Length"])>max_bytes:
            raise ValueError("Content length too large")
        raw=r.read(max_bytes+1)
        if len(raw)>max_bytes:raise ValueError("Response too large")
        return raw

def parse_year(y):
    try:
        n=int(y)
        return n if 0<n<=2026 else None
    except (TypeError,ValueError):return None

def get_cma_photo_candidates(total_limit=1700):
    collected=[]; seen=set()
    # CMA officially exposes "Photograph" as its type; unlike keyword searches,
    # this excludes photos of sculptures, rooms and other objects.
    for offset in range(0,2600,100):
        if len(collected)>=total_limit:break
        url="https://openaccess-api.clevelandart.org/api/artworks/?"+urlencode({
            "cc0":"","has_image":"1","type":"Photograph","limit":"100","skip":str(offset)})
        try:
            # The CMA API treats the presence of cc0 (even empty) as the filter.
            raw=request(url,ALLOW_METADATA_HOSTS,5*1024*1024,25)
            docs=json.loads(raw).get("data") or []
        except Exception as err:
            print("CMA_PHOTO_SEARCH_FAILED",offset,str(err)[:110],flush=True);continue
        if not isinstance(docs,list):break
        for d in docs:
            if not isinstance(d,dict):continue
            ident=str(d.get("id") or "")
            if not ident or ident in seen:continue
            if str(d.get("share_license_status") or "").upper()!="CC0":continue
            if str(d.get("type") or "").casefold()!="photograph":continue
            pic=((d.get("images") or {}).get("print") or
                 (d.get("images") or {}).get("web") or {})
            url=str(pic.get("url") or "")
            if not url or urlsplit(url).hostname not in ALLOW_IMAGE_HOSTS:continue
            creators=d.get("creators") or []
            artist=", ".join(str(a.get("description") or "") for a in creators
                             if isinstance(a,dict)).strip() or "작가 미상"
            title=str(d.get("title") or "").strip()
            if not title:continue
            collected.append({
                "key":"cma:"+ident,"source":"Cleveland Museum of Art",
                "url":url,"title":title,"artist":artist,
                "type":"Photograph","license":"CC0","rightsOK":True,
                "page":str(d.get("url") or "https://www.clevelandart.org/art/"+ident),
                "yearStart":parse_year(d.get("creation_date_earliest")),
                "yearEnd":parse_year(d.get("creation_date_latest")),
                "mediaCategory":"photo","source_class":"CMA Photograph"
            })
            seen.add(ident)
        print("CMA_PHOTO_DISCOVERY",offset,"page",len(docs),"candidates",len(collected),flush=True)
        if len(docs)<80:break
    return collected

def clean_plain(s):
    # Wikicommons "Artist" may include tagged HTML and encoded entities.
    import html
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",str(s or "")))).strip()[:160]

def commons_search(query, offset=0, category=False):
    base="https://commons.wikimedia.org/w/api.php?"
    opts={"action":"query","format":"json","formatversion":"2",
          "prop":"imageinfo","iiprop":"url|size|mime|extmetadata",
          "iiurlwidth":"2000"}
    if category:
        opts.update({"generator":"categorymembers","gcmtitle":"Category:"+query,
                     "gcmtype":"file","gcmlimit":"50"})
        if offset:opts["gcmstart"] = str(offset)
    else:
        opts.update({"generator":"search","gsrsearch":query,
                     "gsrnamespace":"6","gsrlimit":"50","gsroffset":str(offset)})
    raw=request(base+urlencode(opts),ALLOW_METADATA_HOSTS,6*1024*1024,26)
    obj=json.loads(raw)
    return (obj.get("query") or {}).get("pages") or []

def commons_candidates():
    out_photo=[];out_anim=[];seen=set();fail=[]
    requests=[("photo",q) for q in PHOTO_QUERIES]+[("animation",q) for q in ANIMATION_QUERIES]
    for kind,q in requests:
        # Imageinfo has all rights and media evidence in the same returned page.
        try:pages=commons_search(q)
        except Exception as e:
            fail.append((kind,q,str(e)[:90]))
            print("COMMONS_DISCOVERY_FAILED",kind,q,str(e)[:100],flush=True)
            continue
        added=0
        for p in pages:
            if not isinstance(p,dict):continue
            info=(p.get("imageinfo") or [None])[0]
            if not isinstance(info,dict):continue
            meta=info.get("extmetadata") or {}
            short=clean_plain((meta.get("LicenseShortName") or {}).get("value")).lower()
            license_code=clean_plain((meta.get("License") or {}).get("value")).lower()
            if not (short in ("public domain","pd","cc0","cc0 1.0","cc0 1.0 universal")
                    or license_code in ("pd","cc0")):continue
            mime=str(info.get("mime") or "").lower()
            if mime not in ("image/jpeg","image/png","image/webp"):continue
            source=str(info.get("thumburl") or info.get("url") or "")
            if urlsplit(source).hostname!="upload.wikimedia.org":continue
            title=clean_plain(str(p.get("title") or "").removeprefix("File:"))
            if kind=="animation" and (EXCLUDE_ANIM_TITLE.search(title) or not REQUIRE_ANIM_HINT.search(title+" "+q)):continue
            pageid=str(p.get("pageid") or "")
            if not pageid or pageid in seen:continue
            seen.add(pageid)
            artist=clean_plain((meta.get("Artist") or {}).get("value")) or "작가 미상"
            sourceYear=clean_plain((meta.get("DateTimeOriginal") or {}).get("value"))
            # Do not conflate Commons upload dates with creation years.
            yr=int(sourceYear[:4]) if re.match(r"^(?:1[7-9]\d{2}|20[0-2]\d)",sourceYear) else None
            row={"key":"commons:"+pageid,"source":"Wikimedia Commons",
                 "url":source,"title":re.sub(r"\.(?:jpg|jpeg|png|webp)$","",title,flags=re.I),
                 "artist":artist,"type":"Photograph" if kind=="photo" else "Animation Still",
                 "license":"CC0" if "cc0" in short or license_code=="cc0" else "Public domain",
                 "rightsOK":True,"page":str(info.get("descriptionurl") or ""),
                 "yearStart":yr,"yearEnd":yr,
                 "mediaCategory":kind,"source_class":"Commons category: "+q}
            (out_photo if kind=="photo" else out_anim).append(row);added+=1
        print("COMMONS_DISCOVERY",kind,q,"valid_candidate",added,flush=True)
    print("COMMONS_DISCOVERY_TOTAL",len(out_photo),len(out_anim),"errors",len(fail),flush=True)
    return out_photo,out_anim,fail

def ensure_source_truth(row):
    blob=request(row["url"],ALLOW_IMAGE_HOSTS,MAX_SOURCE_BYTES,25)
    sha=hashlib.sha256(blob).hexdigest()
    with Image.open(io.BytesIO(blob)) as im:
        im.load()
        if im.format not in ("JPEG","PNG","WEBP"):raise ValueError("Source file is not supported static image")
        image=ImageOps.exif_transpose(im)
        sourcePixels=(image.width,image.height)
        image,box,factor,original=smart_portrait(image)
    dsha=hashlib.sha256(image).hexdigest()
    a={
      "key":row["key"],"source":row["source"],
      "title":row["title"][:180],"artist":row["artist"][:150],
      "page":row["page"],"image":"",
      "remoteImage":row["url"],"width":1000,"height":1667,
      "type":row["type"],"classification":row["type"],"medium":"",
      "rightsOK":True,"license":row["license"],
      "yearStart":row["yearStart"],"yearEnd":row["yearEnd"],
      "date":str(row["yearStart"] or ""),"museumRegion":"mixedMedia",
      "mediaKind":row["type"],"offlineAsset":"",
      "sourceSHA256":sha,"derivedSHA256":dsha,
      "originalPixels":list(sourcePixels),"cropBox":list(box),
      "upscaleFactor":factor,"adaptType":"SMART_PORTRAIT_CROP",
      "metadataProvenance":row["source_class"],
      "originalLandscape":bool(sourcePixels[0]>=sourcePixels[1]),
      "mediaCategory":row["mediaCategory"]
    }
    return a,image,None

def process(row):
    try:return ensure_source_truth(row)
    except Exception as e:return None,None,f"{row['key']} ({row['source']}) {str(e)[:140]}"

def add_many(candidates,group,current,existing_keys,source_shas,derived_shas,size,limit):
    stats=collections.Counter()
    failed=[]
    if len(current)>=MAX_TOTAL_ARTWORK or limit<=0:return size,stats,failed
    # Bounded concurrency: executor.map yields in source order. All actual
    # extractions occur before counting a work as confirmed.
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for i,(row,res) in enumerate(zip(candidates,pool.map(process,candidates)),1):
            if stats["embedded"]>=limit or len(current)>=MAX_TOTAL_ARTWORK:break
            art,blob,err=res
            if err:
                stats["download_or_quality_failed"]+=1
                if len(failed)<90:failed.append(err)
                continue
            if art["key"] in existing_keys or art["sourceSHA256"] in source_shas or art["derivedSHA256"] in derived_shas:
                stats["deduplicated"]+=1;continue
            if size+len(blob)>MAX_TOTAL_ASSET_BYTES:
                stats["size_cap_hit"]+=1;break
            idx=len(current)
            filename="offline/pack-%04d.jpg"%idx
            target=ROOT/filename
            target.write_bytes(blob)
            if hashlib.sha256(target.read_bytes()).hexdigest()!=art["derivedSHA256"]:
                raise RuntimeError("Failed verification after writing image")
            with Image.open(target) as im:
                im.load()
                if im.size!=(1000,1667) or im.format!="JPEG":
                    raise RuntimeError("Invalid derived image after write")
            art["offlineAsset"]=filename
            art["image"]="https://appassets.gallery/"+filename
            current.append(art)
            size+=len(blob)
            existing_keys.add(art["key"])
            source_shas.add(art["sourceSHA256"])
            derived_shas.add(art["derivedSHA256"])
            stats["embedded"]+=1
            stats["landscape_crop"]+=int(art["originalLandscape"])
            stats["upscaled"]+=int(float(art["upscaleFactor"] or 1)>1.001)
            if stats["embedded"]==1 or stats["embedded"]%50==0:
                print("VERIFIED_EMBEDDED_"+group.upper(),stats["embedded"],"of",len(candidates),"TOTAL_FILES",len(current),flush=True)
    return size,stats,failed

def main():
    if not DECK.is_file() or not REPORT.is_file():
        raise RuntimeError("Base painting JPEG deck and report must be generated first")
    rows=json.loads(DECK.read_text(encoding="utf-8"))
    oldrep=json.loads(REPORT.read_text(encoding="utf-8"))
    if len(rows)!=886 or oldrep.get("embedded_verified_jpegs")!=886:
        raise RuntimeError("Refuse to append to a non-886 original painting deck")
    for idx,row in enumerate(rows):
        assert row["offlineAsset"]=="offline/pack-%04d.jpg"%idx
        assert row.get("type")=="Painting",row.get("type")
    keys={x["key"] for x in rows}
    source_shas={x["sourceSHA256"] for x in rows}
    derived_shas={x["derivedSHA256"] for x in rows}
    total=sum((ROOT/x["offlineAsset"]).stat().st_size for x in rows)
    print("BASE_886_PAINTINGS_PRESERVED",len(rows),"JPEG_BYTES",total,flush=True)
    photos=get_cma_photo_candidates()
    cphoto,canim,discovererrors=commons_candidates()
    photos+=cphoto
    # Supplemental animation candidates first so the most scarce category has
    # a fair chance if the final APK size or image count cap is approached.
    total,animstats,animerrors=add_many(canim,"animation",rows,keys,source_shas,derived_shas,total,MAX_ANIMATION)
    total,photostats,photoerrors=add_many(photos,"photo",rows,keys,source_shas,derived_shas,total,MAX_PHOTO)
    if photostats["embedded"]<10:
        raise RuntimeError("Photo acquisition too weak: "+str(dict(photostats))+"; fail closed")
    DECK.write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    report={
       "base_paintings":886,"photographs":int(photostats["embedded"]),
       "animation_stills":int(animstats["embedded"]),
       "animation_video_gifs":0,
       "actual_distinct_embedded":len(rows),
       "total_image_bytes":total,
       "maximum_distinct_artworks":MAX_TOTAL_ARTWORK,
       "landscape_new_photos":int(photostats["landscape_crop"]),
       "landscape_new_animation_stills":int(animstats["landscape_crop"]),
       "upscaled_new_photos":int(photostats["upscaled"]),
       "upscaled_new_animation_stills":int(animstats["upscaled"]),
       "candidate_counts":{"cma_photos":len(photos)-len(cphoto),"commons_photos":len(cphoto),"commons_animation_stills":len(canim)},
       "photo_stats":dict(photostats),"animation_stats":dict(animstats),
       "errors_sample":{"commons_discovery":discovererrors[:15],
                        "photo":photoerrors[:35],"animation":animerrors[:35]},
       "provenance":"Cleveland Museum of Art CC0 photograph metadata and/or Wikimedia Commons PD/CC0 static imageinfo metadata",
       "photo_animation_display":"1000x1667 JPEG still image with same title/artist/year label"
    }
    NEW_REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    oldrep.update(report)
    oldrep["embedded_verified_jpegs"]=len(rows)
    oldrep["bytes_in_apk_assets"]=total
    REPORT.write_text(json.dumps(oldrep,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("MIXED_BUNDLE_COMPLETE",json.dumps({k:v for k,v in report.items() if k not in ("errors_sample","photo_stats","animation_stats")},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
