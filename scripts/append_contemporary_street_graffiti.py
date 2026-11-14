#!/usr/bin/env python3
"""Add separately verified contemporary, street-art and graffiti stills to 1510-work APK.

Input comes exclusively from the *verified* v1.7.5 APK, not from an unverified
catalog count. Copy the original 1510 embedded JPEG bytes unchanged, then
append only independently fetched, decoded, sha256-verified and usable 2D art.

Metadata screenshot/photograph copyright does not automatically license any
underlying third-party mural. Therefore this tool only includes PD/CC0 files
with own-work/clear image origin metadata and excludes known brands, copyrighted
characters and famous protected mural references. Ambiguous cases are not
included or counted. 429 means stop that source, never circumvent rate limits.
"""
import collections
import concurrent.futures
import hashlib
import html
import io
import json
import re
import time
import zipfile
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from PIL import Image,ImageOps

# Existing reviewed CPU cropping/resizing implementation
from build_886_adapted_deck import smart_portrait
from append_photo_animation_deck import adaptive_lowres_animation_still

ROOT=Path("android-app/app/src/main/assets")
DIR=ROOT/"offline"
DECK=ROOT/"offline-deck.json"
OLD_APK=Path("QuietArtGallery-886Paintings-Photos-Animation-v175.apk")
OLD_APK_SHA256="e3788d326fbea2d99eb451587324f94ef95ed5488a5f3e182d826683bddabc59"
REPORT=Path("build-contemporary-street-graffiti-report.json")
TOTAL_CAP=2110
DATA_MAX=775*1024*1024
MAX_SOURCE=13*1024*1024
TARGET_PER_GROUP=125
DEFAULT_GAP=1.2
HOSTS={"upload.wikimedia.org","commons.wikimedia.org"}
USER_AGENT="QuietArtGalleryResearch/1.0 (noncommercial personal tablet gallery)"
CATEGORIES={
    "Contemporary Art":[
        'deepcategory:"Contemporary paintings"',
        'deepcategory:"21st-century paintings"',
        'deepcategory:"Digital paintings"',
        'deepcategory:"Contemporary art"',
        '"contemporary abstract painting"',
        '"modern digital painting"'
    ],
    "Street Art":[
        'deepcategory:"Street art"',
        'deepcategory:"Street art in Germany"',
        'deepcategory:"Street art in Australia"',
        '"street art" CC0',
        '"stencil art"',
        '"urban street mural"'
    ],
    "Graffiti":[
        'deepcategory:"Graffiti"',
        '"graffiti" CC0',
        'deepcategory:"Graffiti art"',
        '"graffiti lettering"',
        '"graffiti in Berlin"',
        '"graffiti in Sydney"'
    ]
}
BLOCK_TITLES=re.compile(
    r"(?:\b(?:sculpture|statue|installation|gallery room|gallery interior|"
    r"museum interior|exhibition|t-shirt|toy|doll|costume|cosplay|"
    r"poster|logo|album cover|advertisement|advertising|"
    r"bridge view|people walking|street festival|"
    r"marvel|disney|star wars|pokemon|banksy|shepard fairey)\b)",re.I)
FLAT_HINT=re.compile(
    r"(?:painting|picture|artwork|illustration|graffiti|street.?art|"
    r"stencil|mural|spray.?paint|digital.?art|abstract|wall.?art|"
    r"urban.?art|urban.?mural)",re.I)

def local_sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b=f.read(4*1024*1024)
            if not b:break
            h.update(b)
    return h.hexdigest()

def restore_baseline():
    if not OLD_APK.is_file() or local_sha(OLD_APK)!=OLD_APK_SHA256:
        raise RuntimeError("No exact audited 1510-work APK to preserve")
    DIR.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(OLD_APK) as z:
        assert z.testzip() is None,"Old release corrupt"
        rows=json.loads(z.read("assets/offline-deck.json"))
        if len(rows)!=1510:raise ValueError("Old APK no longer contains 1510 images")
        tally=collections.Counter(x.get("type") for x in rows)
        if tally!={"Painting":886,"Photograph":600,"Animation Still":24}:
            raise AssertionError("Base art type counts changed: "+str(tally))
        for i,art in enumerate(rows):
            rel="offline/pack-%04d.jpg"%i
            assert art["offlineAsset"]==rel
            blob=z.read("assets/"+rel)
            if hashlib.sha256(blob).hexdigest()!=art["derivedSHA256"]:
                raise AssertionError("A base artwork hash failed "+rel)
            fp=ROOT/rel
            fp.write_bytes(blob)
            if fp.stat().st_size!=len(blob):raise IOError("Write incomplete")
    DECK.write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("RESTORED_IDENTICAL_1510_FROM_RELEASE",dict(tally),flush=True)
    return rows

def fetch(url,maxbytes=MAX_SOURCE,wait=True):
    if urlsplit(url).scheme!="https" or urlsplit(url).hostname not in HOSTS:
        raise ValueError("Unapproved host")
    if wait:time.sleep(DEFAULT_GAP)
    req=Request(url,headers={"User-Agent":USER_AGENT,
        "Accept":"application/json,image/jpeg,image/png,image/webp,*/*"})
    with urlopen(req,timeout=25) as r:
        if r.status!=200:raise ValueError("HTTP "+str(r.status))
        if urlsplit(r.geturl()).hostname not in HOSTS:raise ValueError("Image redirect host changed")
        if r.headers.get("Content-Length") and int(r.headers["Content-Length"])>maxbytes:
            raise ValueError("File exceeds maximum source size")
        data=r.read(maxbytes+1)
        if len(data)>maxbytes:raise ValueError("File exceeds maximum source size")
        return data

def plain(x):
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",str(x or "")))).strip()[:200]

def ext(meta,k):
    return plain((meta.get(k) or {}).get("value"))

def year_from_source(s):
    # Only explicit work creation date; not camera exposure or upload time.
    m=re.fullmatch(r"\s*(?:c(?:irca)?\.?\s*)?(1[89]\d\d|20[012]\d)\s*",str(s or ""))
    return int(m.group(1)) if m else None

def metadata_image_rows(group):
    seen=set();accepted=[];failures=[]
    # Depth 0 and 50 makes each query independent without looping forever.
    for query in CATEGORIES[group]:
        for off in (0,50,100):
            opts={"action":"query","format":"json","formatversion":"2",
                "generator":"search","gsrsearch":query,"gsrnamespace":"6",
                "gsrlimit":"50","gsroffset":str(off),"prop":"imageinfo",
                "iiprop":"url|size|mime|extmetadata","iiurlwidth":"2000"}
            try:
                payload=fetch("https://commons.wikimedia.org/w/api.php?"+urlencode(opts),3*1024*1024)
                pages=(json.loads(payload).get("query") or {}).get("pages") or []
            except HTTPError as e:
                print("COMMONS_SEARCH_HTTP",group,e.code,query,off,flush=True)
                failures.append(str(e.code)+" "+query)
                if e.code in (429,403):return accepted,failures
                continue
            except Exception as e:
                failures.append(type(e).__name__+" "+query)
                continue
            accepted_in_page=0
            for p in pages:
                info=(p.get("imageinfo") or [None])[0]
                if not isinstance(info,dict):continue
                meta=info.get("extmetadata") or {}
                mime=str(info.get("mime") or "").lower()
                if mime not in ("image/jpeg","image/png","image/webp"):continue
                lic=ext(meta,"LicenseShortName").lower().strip()
                code=ext(meta,"License").lower().strip()
                if not (lic.startswith("cc0") or lic in ("public domain","pd")
                        or code in ("cc0","pd")):continue
                url=info.get("thumburl") or info.get("url") or ""
                if urlsplit(url).hostname!="upload.wikimedia.org":continue
                key="commons:"+str(p.get("pageid") or "")
                if key in seen or key=="commons:":continue
                title=plain(str(p.get("title") or "").removeprefix("File:"))
                description=ext(meta,"ImageDescription")
                credit=ext(meta,"Credit")+" "+ext(meta,"Source")
                if BLOCK_TITLES.search(title) or BLOCK_TITLES.search(description):continue
                if group=="Contemporary Art" and not FLAT_HINT.search(title+" "+description+" "+query):
                    continue
                if group in ("Graffiti","Street Art") and not FLAT_HINT.search(title+" "+description):
                    # Reject category matches unrelated to pictorial art.
                    continue
                if group in ("Graffiti","Street Art") and "graffiti" not in title.lower() and "street art" not in title.lower() and not re.search(
                    r"\b(stencil|mural|spray.?paint|wall.?art)\b",title,re.I):
                    # Street category alone cannot prove the photo depicts art.
                    continue
                if not (re.search(r"(?:own work|own artwork|self.?published|original creation by uploader)",credit,re.I)
                        or "CC0" in lic.upper()):
                    # We only have image uploader metadata at this level. Do not
                    # claim that it proves rights in any third-party mural.
                    continue
                artist=ext(meta,"Artist")
                if group in ("Graffiti","Street Art"):
                    # Photograph author is not necessarily mural/lettering artist.
                    artist="작가 미상"
                title=re.sub(r"\.(?:jpe?g|png|webp)$","",title,flags=re.I)
                w=int(info.get("width") or 0);h=int(info.get("height") or 0)
                if w<340 or h<260 or w*h>45_000_000:continue
                # Image metadata may represent a photographer's upload, not
                # the street artist's creation date: don't invent year.
                yr=(year_from_source(ext(meta,"DateTimeOriginal")) if group=="Contemporary Art" else None)
                accepted.append({
                    "key":key,"source":"Wikimedia Commons","title":title[:170],
                    "artist":artist or "작가 미상","type":group,
                    "url":url,"page":str(info.get("descriptionurl") or ""),
                    "license":"CC0" if "cc0" in lic else "Public domain",
                    "rightsOK":True,"yearStart":yr,"yearEnd":yr,
                    "mediaCategory":group,"source_class":"commons_search:"+query,
                    "metadata_pixels":(w,h),
                    "image_creator":ext(meta,"Artist"),"photo_license":lic,
                    "work_copyright_unverified":group in ("Graffiti","Street Art")
                })
                seen.add(key);accepted_in_page+=1
            print("SEARCH",group,query,"offset",off,"matched",accepted_in_page,"total",len(accepted),flush=True)
            if len(pages)<50 or len(accepted)>=300:break
        if len(accepted)>=300:break
    return accepted,failures

def process_one(row):
    try:
        payload=fetch(row["url"])
        source_sha=hashlib.sha256(payload).hexdigest()
        with Image.open(io.BytesIO(payload)) as img:
            img.load()
            if img.format not in ("JPEG","PNG","WEBP"):raise ValueError("not static artwork image")
            iw,ih=ImageOps.exif_transpose(img).size
            # Historic wall paintings are often modest, but a minimum 260px
            # native size is still mandatory. No imaginary AI texture.
            if row["mediaCategory"] in ("Street Art","Graffiti"):
                data,box,scale,orig=adaptive_lowres_animation_still(img)
            else:
                data,box,scale,orig=smart_portrait(img)
        derived=hashlib.sha256(data).hexdigest()
        art={
            "key":row["key"],"source":row["source"],
            "title":row["title"],"artist":row["artist"],
            "page":row["page"],"image":"",
            "remoteImage":row["url"],"width":1000,"height":1667,
            "type":row["type"],"classification":row["type"],"medium":"",
            "rightsOK":True,"license":row["license"],"yearStart":row["yearStart"],
            "yearEnd":row["yearEnd"],"date":str(row["yearStart"] or ""),
            "museumRegion":"mixedMedia","offlineAsset":"","mediaKind":row["type"],
            "sourceSHA256":source_sha,"derivedSHA256":derived,
            "originalPixels":[iw,ih],"cropBox":list(box),
            "upscaleFactor":scale,"adaptType":"SMART_PORTRAIT_CROP",
            "metadataProvenance":row["source_class"],
            "originalLandscape":bool(iw>=ih),
            "photoLicense":row["photo_license"],
            "underlyingWorkCopyrightUnverified":row["work_copyright_unverified"]
        }
        return art,data,None
    except HTTPError as e:
        return None,None,"HTTP "+str(e.code)+" "+row["key"]
    except Exception as e:
        return None,None,str(e)[:150]+" "+row["key"]

def main():
    rows=restore_baseline()
    keys={x["key"] for x in rows}
    rawsha={x["sourceSHA256"] for x in rows}
    derivedsha={x["derivedSHA256"] for x in rows}
    total=sum((ROOT/x["offlineAsset"]).stat().st_size for x in rows)
    sourcecounts=collections.Counter(x["type"] for x in rows)
    groups={};fail=[]
    for cat in CATEGORIES:
        items,errs=metadata_image_rows(cat)
        groups[cat]=items
        fail.extend(errs)
    # Interleave three media groups to prevent a single API throttling event
    # leaving some genres with zero images. Never bypass provider throttling.
    order=[]
    max_size=max((len(v) for v in groups.values()),default=0)
    for i in range(max_size):
        for cat in CATEGORIES:
            if i<len(groups[cat]):order.append(groups[cat][i])
    attempts=collections.Counter()
    extra=collections.Counter()
    failures=[]
    cropped=collections.Counter()
    enlarged=collections.Counter()
    http429=0
    # Serial rate-constrained image fetching; stop the whole source on rate
    # limit rather than switch IPs, spoof requests, or otherwise circumvent.
    for item in order:
        kind=item["mediaCategory"]
        if len(rows)>=TOTAL_CAP or total>=DATA_MAX or all(extra[x]>=TARGET_PER_GROUP for x in CATEGORIES):
            break
        if extra[kind]>=TARGET_PER_GROUP or item["key"] in keys:continue
        attempts[kind]+=1
        art,data,err=process_one(item)
        if err:
            failures.append(err)
            if "HTTP 429" in err or "HTTP 403" in err:
                http429+=1
                print("REMOTE_PROVIDER_LIMIT_STOPPED",err,flush=True)
                break
            continue
        if art["sourceSHA256"] in rawsha or art["derivedSHA256"] in derivedsha:continue
        if total+len(data)>DATA_MAX:break
        idx=len(rows);name=f"offline/pack-{idx:04d}.jpg"
        p=ROOT/name;p.write_bytes(data)
        if local_sha(p)!=art["derivedSHA256"]:raise RuntimeError("SHA file mismatch "+name)
        with Image.open(p) as verify:
            verify.load()
            if verify.format!="JPEG" or verify.size!=(1000,1667):
                raise RuntimeError("Invalid derived JPEG "+name)
        art["offlineAsset"]=name
        art["image"]="https://appassets.gallery/"+name
        rows.append(art);keys.add(art["key"]);rawsha.add(art["sourceSHA256"]);derivedsha.add(art["derivedSHA256"])
        total+=len(data)
        extra[kind]+=1
        cropped[kind]+=int(art["originalLandscape"])
        enlarged[kind]+=int(float(art["upscaleFactor"])>1.001)
        if sum(extra.values())%10==0 or sum(extra.values())==1:
            print("CONTEMPORARY_STREET_GRAFFITI_EMBEDDED",dict(extra),"total",len(rows),flush=True)
    if not any(extra.values()):
        raise RuntimeError("No new copyrighted-safe art decoded; do not publish empty update")
    DECK.write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    report={
        "base_images_preserved_exactly":1510,
        "base_paintings":886,"base_photographs":600,"base_animation_stills":24,
        "added":dict(extra),"total_added":sum(extra.values()),
        "total_verified_jpegs":len(rows),"total_image_bytes":total,
        "new_landscape_to_portrait":dict(cropped),"new_upscaled":dict(enlarged),
        "candidate_counts":{k:len(v) for k,v in groups.items()},
        "attempts":dict(attempts),"source_errors":failures[:70],
        "metadata_errors":fail[:20],"rate_limited_stopped":bool(http429),
        "not_embedded_due_to_missing_authorisation":"Unknown or unproven underlying work copyright may apply to photographs of murals; files are not guaranteed for onward public distribution.",
        "photo_artwork_rights_note":"CC0 / public-domain image declarations verified from Commons metadata; graffiti underlying-work copyright needs individual assessment.",
        "image_type":"static JPEG, 1000x1667, not streaming motion",
        "release_source_apk_sha256":OLD_APK_SHA256
    }
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("STREET_GRAFFITI_VERIFIED_COMPLETED",json.dumps({k:v for k,v in report.items() if k not in ("source_errors","metadata_errors")},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
