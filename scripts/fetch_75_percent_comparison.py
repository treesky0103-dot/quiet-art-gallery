#!/usr/bin/env python3
"""Read-only visual comparison: fetch up to 10 free/PD real paintings whose original
aspect ratio fills 75%-79.9% of a 16:10 portrait display without cropping.
This does not alter APK behavior, images or museum source data.
"""
import concurrent.futures
import html
import hashlib
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from PIL import Image,ImageOps

OUT=Path("comparison_75_candidates")
OUT.mkdir(exist_ok=True)
CATS=[
 "Paintings in the Rijksmuseum Amsterdam",
 "Paintings in the National Gallery of Art (Washington, D.C.)",
 "Paintings in The J. Paul Getty Museum",
 "Paintings in Statens Museum for Kunst",
 "Paintings in Musée Carnavalet",
 "Paintings in the National Gallery, London",
 "Paintings in the Walters Art Museum",
 "Paintings in the National Gallery of Victoria",
 "Paintings in the Art Gallery of New South Wales",
 "Paintings in the National Gallery of Australia",
 "Paintings in the Art Gallery of South Australia",
 "Paintings in the Auckland Art Gallery",
 "Paintings in the Dunedin Public Art Gallery",
 "Brazilian paintings in the Museu Nacional de Belas Artes",
 "Paintings in the Museo Nacional de Bellas Artes (Argentina)",
 "Paintings in the Museo de Arte de Lima",
 "Paintings in the Museo Nacional de Artes Visuales",
 "Paintings in the Pinacoteca do Estado de São Paulo",
 "Paintings in the National Museum of Korea",
 "Japanese paintings in the Tokyo National Museum",
 "Paintings in the Kyoto National Museum",
 "Paintings in the National Palace Museum",
 "Paintings in the South African National Gallery",
 "Contemporary paintings",
 "2020s paintings",
]
UA="QuietArtGalleryPortraitComparison/1.0 (https://github.com/treesky0103-dot/quiet-art-gallery; educational preview)"
BAD=re.compile(r"(?:museum (?:interior|hall|room)|exhibition|gallery view|sculpture|statue|installation|framed|detail|verso|reverse|gallery wall|old museum|photo of|postcard|frame|photograph)",re.I)
GOOD=("portrait","flowers","landscape","woman","painting","impression","oil","girl","lady","garden","beach","river","autumn","summer","tree","study","watercolor","watercolour","abstract")
def fetch(url,timeout=22,limit=10000000,accept="application/json,image/jpeg"):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":accept})
    with urllib.request.urlopen(req,timeout=timeout) as f:
        if int(f.headers.get("Content-Length") or 0)>limit:raise ValueError("oversize")
        data=f.read(limit+1)
        if len(data)>limit:raise ValueError("oversize data")
        return data
def scan(category):
    items=[]
    for offset in [0,50]:
        p={"action":"query","generator":"search","gsrsearch":'deepcategory:"'+category+'"',
            "gsrnamespace":"6","gsrlimit":"50","gsroffset":str(offset),
            "prop":"imageinfo","iiprop":"url|size|mime|extmetadata","iiurlwidth":"1700",
            "format":"json","formatversion":"2"}
        try:data=json.loads(fetch("https://commons.wikimedia.org/w/api.php?"+urllib.parse.urlencode(p),limit=4500000))
        except Exception as e:
            print("SOURCE ERROR",category,repr(e)[:100],flush=True);break
        pages=(data.get("query") or {}).get("pages") or []
        for page in pages:
            name=str(page.get("title") or "")
            inf=(page.get("imageinfo") or [None])[0]
            if not inf or BAD.search(name):continue
            meta=inf.get("extmetadata") or {}
            lic=str((meta.get("LicenseShortName") or {}).get("value") or "").strip().lower()
            if lic not in ("public domain","pd","cc0","cc0 1.0","cc0 1.0 universal"):continue
            if inf.get("mime")!="image/jpeg":continue
            w=int(inf.get("width") or 0);h=int(inf.get("height") or 0)
            if w<1350 or h<1800 or w>=h:continue
            r=w/h;fill=min(r/.625,.625/r)
            if not (.7501<=fill<.7999):continue
            url=inf.get("thumburl") or ""
            if not (url.startswith("https://upload.wikimedia.org/") or url.startswith("https://thumb.wikimedia.org/")):continue
            clean=re.sub(r'<[^>]+>'," ",str((meta.get("Artist") or {}).get("value") or ""))
            clean=html.unescape(clean).strip()
            score=sum(3 for term in GOOD if term in name.lower())-len(name)/160
            items.append(dict(category=category,pageid=page.get("pageid"),
                title=html.unescape(name.removeprefix("File:")).replace("_"," "),
                artist=clean[:95],license=lic,
                original_width=w,original_height=h,fill=fill,
                original_url=inf.get("url"),preview_url=url,
                description_url=inf.get("descriptionurl"),score=score))
        if len(pages)<50:break
    print("SCAN",category,len(items),flush=True)
    return items
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
    all_items=[x for sub in ex.map(scan,CATS) for x in sub]
unique={}
for item in all_items:
    unique.setdefault(item["pageid"],item)
ranked=sorted(unique.values(),key=lambda x:(x["score"],x["original_width"],x["pageid"]),reverse=True)
selected=[]
seen_museum=set()
for a in ranked:
    if len(selected)>=10:break
    if a["category"] in seen_museum and len(seen_museum)<7:continue
    try:
        raw=fetch(a["preview_url"],timeout=25,limit=9500000,accept="image/jpeg")
        im=Image.open(io.BytesIO(raw))
        im.load()
        w,h=im.size;ratio=w/h;fill=min(ratio/.625,.625/ratio)
        if im.format!="JPEG" or w<1300 or h<1600 or not(.7501<=fill<.7999):continue
        a["download_width"]=w;a["download_height"]=h;a["sha256"]=hashlib.sha256(raw).hexdigest()
        a["file"]=f"candidate-{len(selected)+1:02d}.jpg"
        (OUT/a["file"]).write_bytes(raw)
        selected.append(a)
        seen_museum.add(a["category"])
        print("IMAGE",len(selected),a["category"],a["title"][:85],(w,h),round(fill,4),flush=True)
    except Exception as e:
        print("SKIP",a["title"][:65],str(e)[:75],flush=True)
(OUT/"metadata.json").write_text(json.dumps({"selected":selected,
"candidates":len(ranked),"sources_scanned":len(CATS),
"definition":"15:10? Actual portrait viewport 10:16 aspect 0.625; fill 0.75-0.80; untouched source orientation; resized only by Wikimedia for preview download",
"license":"per image Commons metadata CC0/PD"},ensure_ascii=False,indent=2),encoding="utf-8")
assert len(selected)>=3,f"Only {len(selected)} licensed genuine 75%-fill artwork JPEGs could be downloaded"
print("PASS 3+ 75%-79.9%-fill verified artworks",len(selected),flush=True)
