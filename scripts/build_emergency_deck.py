#!/usr/bin/env python3
"""Bundle 4 independently checked public-domain paintings for emergency offline rotation.

The source is Wikimedia Commons, category-linked to named museum collections.
This requires no network on the tablet; fails the build rather than silently
shipping an empty fallback deck. Images are never upscaled or interpolated.
"""
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
import socket

OUT=Path("android-app/app/src/main/assets")
MAX_BYTES=8*1024*1024
COLLECTIONS=[
 ("암스테르담 국립미술관","Paintings in the Rijksmuseum Amsterdam"),
 ("미국 국립미술관","Paintings in the National Gallery of Art (Washington, D.C.)"),
 ("게티 미술관","Paintings in The J. Paul Getty Museum"),
 ("덴마크 국립미술관","Paintings in Statens Museum for Kunst"),
 ("런던 내셔널갤러리","Paintings in the National Gallery, London")
]
BAD=re.compile(r"(?:interior|gallery view|exhibition view|museum hall|sculpture|statue|frame|detail|reverse|verso)",re.I)
DOMAIN="upload.wikimedia.org"

def read_http(url,limit=MAX_BYTES,timeout=16):
    req=urllib.request.Request(url,headers={
      "User-Agent":"QuietArtGallery/1.6.2 (+https://github.com/treesky0103-dot/quiet-art-gallery; personal art gallery)",
      "Accept":"application/json,image/jpeg"})
    with urllib.request.urlopen(req,timeout=timeout) as conn:
        ct=conn.headers.get("Content-Type","").lower().split(";")[0].strip()
        size=int(conn.headers.get("Content-Length") or 0)
        if size>limit:raise ValueError("oversize")
        b=conn.read(limit+1)
        if len(b)>limit:raise ValueError("oversize body")
    return ct,b

def jpeg_dimensions(data):
    if data[:2]!=b"\xff\xd8":raise ValueError("Not JPEG")
    idx=2
    while idx<len(data)-10:
        if data[idx]!=255:idx+=1;continue
        while idx<len(data) and data[idx]==255:idx+=1
        if idx>=len(data):break
        marker=data[idx];idx+=1
        if marker in [0xd8,0xd9,0x01] or 0xd0<=marker<=0xd7:continue
        if idx+2>len(data):break
        n=int.from_bytes(data[idx:idx+2],"big")
        if n<2 or idx+n>len(data):break
        if marker in [0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf]:
            h=int.from_bytes(data[idx+3:idx+5],"big")
            w=int.from_bytes(data[idx+5:idx+7],"big")
            return w,h
        idx+=n
    raise ValueError("Missing JPEG SOF header")

def readable(x):
    value=re.sub(r"<[^>]*>"," ",str(x or ""))
    return re.sub(r"\s+"," ",html.unescape(value)).strip()[:120]

def main():
    target=OUT/"offline"
    target.mkdir(parents=True,exist_ok=True)
    deck=[]; seen=set()
    for museum,category in COLLECTIONS:
        if len(deck)>=4:break
        params={
          "action":"query","generator":"search","gsrsearch":'deepcategory:"'+category+'"',
          "gsrnamespace":"6","gsrlimit":"50","gsroffset":"0",
          "prop":"imageinfo","iiprop":"url|size|mime|extmetadata",
          "iiurlwidth":"2000","format":"json","formatversion":"2"
        }
        api="https://commons.wikimedia.org/w/api.php?"+urllib.parse.urlencode(params)
        try:
            mime,raw=read_http(api,4*1024*1024,22)
            if mime!="application/json":raise ValueError("Unexpected API format "+mime)
            pages=(json.loads(raw).get("query") or {}).get("pages") or []
        except Exception as ex:
            print("SOURCE ERROR",museum,repr(ex),flush=True)
            continue
        found=False
        for page in pages:
            if len(deck)>=4:break
            title=str(page.get("title") or "")
            imageinfos=page.get("imageinfo") or []
            if not imageinfos or BAD.search(title):continue
            inf=imageinfos[0]
            extra=inf.get("extmetadata") or {}
            license=readable((extra.get("LicenseShortName") or {}).get("value")).lower()
            if license not in ("public domain","pd","cc0","cc0 1.0","cc0 1.0 universal"):continue
            if inf.get("mime")!="image/jpeg":continue
            src=inf.get("thumburl") or ""
            u=urllib.parse.urlsplit(src)
            if u.scheme!="https" or u.hostname!=DOMAIN:continue
            originalw=int(inf.get("width") or 0);originalh=int(inf.get("height") or 0)
            if min(originalw,originalh)<1200 or max(originalw,originalh)<1600:continue
            id=page.get("pageid")
            if not isinstance(id,int) or id in seen:continue
            try:
                mime,pixels=read_http(src,MAX_BYTES,18)
                if mime!="image/jpeg" or len(pixels)<15000:raise ValueError("Not JPEG bytes")
                w,h=jpeg_dimensions(pixels)
                if min(w,h)<1200 or max(w,h)<1600:raise ValueError("Thumbnail not full enough")
                name="fallback-"+str(len(deck))+".jpg"
                (target/name).write_bytes(pixels)
                item={
                  "key":"commons:"+str(id),"source":museum,
                  "title":readable(re.sub(r"\.(?:jpg|jpeg)$","",title.removeprefix("File:"),flags=re.I).replace("_"," ")),
                  "artist":readable((extra.get("Artist") or {}).get("value")) or "작가 미상",
                  "image":src,"offlineAsset":"offline/"+name,
                  "width":w,"height":h,
                  "rightsOK":True,"license":"Public domain",
                  "type":"Painting","classification":"Painting","medium":"",
                  "museumRegion":"additional","verifiedCollectionCategory":True,
                  "style":"","styles":[],"date":"","page":str(inf.get("descriptionurl") or ""),
                  "sha256":hashlib.sha256(pixels).hexdigest()
                }
                deck.append(item);seen.add(id);found=True
                print("PASS offline",id,museum,w,h,len(pixels),item["title"],flush=True)
                break # 1 unique work per museum, for variety
            except Exception as ex:
                print("REJECT IMAGE",id,str(ex)[:100],flush=True)
            time.sleep(.1)
        if not found:print("NO ELIGIBLE WORK",museum,flush=True)
    if len(deck)<4:raise RuntimeError("Failed to verify 4 CC0/PD JPG paintings; refuse APK build")
    (OUT/"offline-deck.json").write_text(json.dumps(deck,ensure_ascii=False,indent=2),encoding="utf-8")
    print("PASS four high-res offline artworks, total bytes",sum((target/("fallback-"+str(i)+".jpg")).stat().st_size for i in range(4)),flush=True)

if __name__=="__main__":main()
