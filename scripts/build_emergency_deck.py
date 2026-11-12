#!/usr/bin/env python3
"""Build a small, verified OFFLINE emergency painting deck for the Android APK.

All works must be paintings, CC0 images from Cleveland Museum of Art. No image
resizing/upscaling. This is a fallback only; routine 90-day no-repeat selection
does not use it. Requires network during CI build, never at app startup.
"""
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://openaccess-api.clevelandart.org/api/artworks/"
OUT = Path("android-app/app/src/main/assets")
MAX_BYTES = 8 * 1024 * 1024
COUNT = 4

def request(url, max_bytes=6 * 1024 * 1024):
    req=urllib.request.Request(url,headers={
        "User-Agent":"QuietArtGallery/1.6.2 (noncommercial art display; open-access offline backup)",
        "Accept":"application/json,image/jpeg"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        typ=resp.headers.get("Content-Type","").split(";")[0].strip().lower()
        if int(resp.headers.get("Content-Length") or 0)>max_bytes:
            raise ValueError("Too large Content-Length")
        data=resp.read(max_bytes+1)
        if len(data)>max_bytes: raise ValueError("Oversize response")
    return typ,data

def jpeg_dimensions(data):
    if not data.startswith(b"\xff\xd8"): raise ValueError("Not JPEG")
    i=2
    while i<len(data)-9:
        if data[i]!=255:
            i+=1;continue
        while i<len(data) and data[i]==255: i+=1
        if i>=len(data):break
        marker=data[i]; i+=1
        if marker in (0xd8,0xd9,0x01) or 0xd0<=marker<=0xd7: continue
        if i+2>len(data):break
        n=int.from_bytes(data[i:i+2],"big")
        if n<2 or i+n>len(data):break
        if marker in (0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf):
            if n<7:break
            return int.from_bytes(data[i+3:i+5],"big"),int.from_bytes(data[i+5:i+7],"big")
        i+=n
    raise ValueError("JPEG dimensions absent")

def main():
    dest=OUT/"offline"
    dest.mkdir(parents=True,exist_ok=True)
    manifest=[]
    used=set()
    # Try different pages; stable order of API results, validated at build-time.
    for offset in (0,100,200,300,400,500):
        q=urllib.parse.urlencode({"type":"Painting","has_image":"1","limit":"100","skip":str(offset)})
        try:
            typ,data=request(BASE+"?cc0&"+q)
            if typ!="application/json":raise ValueError("unexpected metadata MIME "+typ)
            paintings=json.loads(data).get("data") or []
        except Exception as ex:
            print("metadata page unavailable:",offset,repr(ex),flush=True)
            continue
        for a in paintings:
            if len(manifest)>=COUNT:break
            if a.get("share_license_status")!="CC0" or str(a.get("type"))!="Painting":continue
            photos=(a.get("images") or {})
            rendition=photos.get("print") or {}
            src=rendition.get("url") or ""
            w,h=int(rendition.get("width") or 0),int(rendition.get("height") or 0)
            aid=a.get("id")
            if not src.startswith("https://") or "clevelandart.org" not in urllib.parse.urlsplit(src).hostname: continue
            if min(w,h)<1200 or max(w,h)<1600 or aid in used:continue
            if any(k in (str(a.get("title"))+" "+str(a.get("technique"))).lower()
                   for k in ("sculpture","frame","photograph","installation","tapestry","triptych","panel of")):continue
            try:
                mime,im=request(src,MAX_BYTES)
                if mime!="image/jpeg" or len(im)<20000:raise ValueError("not an image/jpeg")
                aw,ah=jpeg_dimensions(im)
                if min(aw,ah)<1200 or max(aw,ah)<1600:raise ValueError("decoded dimensions insufficient")
                filename="fallback-"+str(len(manifest))+".jpg"
                (dest/filename).write_bytes(im)
                artist=((a.get("creators") or [{}])[0].get("description") or "작가 미상")
                item={
                  "key":"cma:"+str(aid),
                  "title":str(a.get("title") or "제목 미상")[:160],
                  "artist":str(artist)[:160],
                  "source":"클리블랜드",
                  "image":src,"offlineAsset":"offline/"+filename,
                  "type":"Painting","classification":"Painting","medium":str(a.get("technique") or "Oil on canvas"),
                  "width":aw,"height":ah,"license":"CC0","rightsOK":True,
                  "style":str(a.get("style") or ""),"styles":a.get("style_titles") or [],
                  "date":str(a.get("creation_date") or ""), "page":str(a.get("url") or ""),
                  "sha256":hashlib.sha256(im).hexdigest()
                }
                manifest.append(item);used.add(aid)
                print("PASS offline",aid,aw,ah,len(im),item["title"],flush=True)
            except Exception as ex:
                print("reject",aid,repr(ex)[:120],flush=True)
            time.sleep(.1)
        if len(manifest)>=COUNT:break
    if len(manifest)<COUNT:raise RuntimeError("Could not verify 4 offline CC0 high-res paintings; refuse build")
    (OUT/"offline-deck.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print("PASS 4 OFFLINE CC0 PAINTINGS",sum((dest/("fallback-"+str(i)+".jpg")).stat().st_size for i in range(COUNT)),flush=True)

if __name__=="__main__":main()
