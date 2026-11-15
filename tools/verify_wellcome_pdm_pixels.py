#!/usr/bin/env python3
import urllib.request,io,hashlib
from PIL import Image
URL="https://iiif.wellcomecollection.org/image/V0035845/full/2000,/0/default.jpg"
req=urllib.request.Request(URL,headers={"User-Agent":"QuietArtGallery/1.8.6 (+non-commercial local exhibition; single PDM pixel audit)","Accept":"image/jpeg"})
with urllib.request.urlopen(req,timeout=25) as r:
 code=r.status;ct=r.headers.get("Content-Type")
 b=r.read(8*1024*1024+1)
assert code==200,(code,ct)
assert len(b)<=8*1024*1024,len(b)
assert ct and "image/jpeg" in ct,ct
with Image.open(io.BytesIO(b)) as im:
 im.load()
 w,h=im.size
 assert im.format=="JPEG",im.format
 assert w>=1000 and h>=1400 and w<h,(w,h)
 assert min((w/h)/.60,.60/(w/h))>=.75,(w,h)
 print("WELLCOME_PDM_PIXELS_PASS",w,h,len(b),hashlib.sha256(b).hexdigest(),flush=True)
