#!/usr/bin/env python3
import urllib.request,io,hashlib,json,time,re
from PIL import Image
headers={"User-Agent":"QuietArtGalleryResearch/1.0 (+noncommercial personal display; limited four image test)","Accept":"application/json,image/jpeg"}
def get(u):
 req=urllib.request.Request(u,headers=headers)
 with urllib.request.urlopen(req,timeout=25) as r:return r.read(8*1024*1024+1),r.headers.get("Content-Type"),r.status
data,ct,code=get("https://api.vam.ac.uk/v2/objects/search?q=watercolour&page_size=40")
objects=json.loads(data)["records"]
attempts=0
for row in objects:
 if attempts>=4:break
 pic=row.get("_images") or {}
 if pic.get("imageResolution")!="high":continue
 url=pic.get("_iiif_image_base_url") or ""
 if not re.fullmatch(r"https://framemark\.vam\.ac\.uk/collections/[a-zA-Z0-9]+/",url):continue
 attempts+=1
 try:
  raw,typ,status=get(url+"full/2000,/0/default.jpg")
  if status!=200 or len(raw)>8*1024*1024 or "image/jpeg" not in typ:
   print("VAM_SAMPLE_REJECT",attempts,"bad jpeg size/ct");continue
  with Image.open(io.BytesIO(raw)) as im:
   im.load();w,h=im.size
   eligible=im.format=="JPEG" and w>=1000 and h>=1400 and w<h and min((w/h)/.60,.60/(w/h))>=.75
   print("VAM_SAMPLE",attempts,w,h,len(raw),"suitable="+str(eligible),flush=True)
   if eligible:
    print("VAM_PERSONAL_API_PIXELS_PASS",w,h,len(raw),hashlib.sha256(raw).hexdigest(),flush=True)
    break
 except Exception as e:print("VAM_SAMPLE_ERROR",attempts,str(e)[:140],flush=True)
else:
 raise SystemExit("No suitable portrait from 4 official high-res images; keep connector disabled")
