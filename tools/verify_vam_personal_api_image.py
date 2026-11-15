#!/usr/bin/env python3
import urllib.request,io,hashlib
from PIL import Image
url="https://framemark.vam.ac.uk/collections/2023NP5432/full/2000,/0/default.jpg"
req=urllib.request.Request(url,headers={"User-Agent":"QuietArtGalleryResearch/1.0 (+noncommercial personal display; image test)","Accept":"image/jpeg"})
try:
 with urllib.request.urlopen(req,timeout=25) as r:
  data=r.read(8*1024*1024+1)
  ct=r.headers.get("Content-Type")
  status=r.status
 assert status==200 and ct and "image/jpeg" in ct and len(data)<=8*1024*1024,(status,ct,len(data))
 with Image.open(io.BytesIO(data)) as im:
  im.load()
  w,h=im.size
  assert im.format=="JPEG" and w>=1000 and h>=1400 and h>w,(im.format,w,h)
  assert min((w/h)/.60,.60/(w/h))>=.75
 print("VAM_PERSONAL_API_PIXELS_PASS",w,h,len(data),hashlib.sha256(data).hexdigest())
except Exception as e:
 print("VAM_PERSONAL_API_PIXELS_NOT_VALIDATED",type(e).__name__,str(e)[:140],flush=True)
 raise
