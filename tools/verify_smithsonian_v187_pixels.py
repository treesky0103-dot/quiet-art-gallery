#!/usr/bin/env python3
"""Actual bytes, dimensions, response redirects, jpeg and visual fill checks.
One sample each new Smithsonian National Portrait Gallery and Cooper Hewitt.
No 3D sources, no key, bounded 8 MiB per image.
"""
import urllib.request,urllib.parse,io,json,hashlib,ssl
from PIL import Image
IMAGES={
 "NPG_LITHOGRAPH":"NPG-NPG_85_158",
 "NPG_ENGRAVING":"NPG-S-NPG_75_14",
 "NPG_OIL_PAINTING":"NPG-NPG_2019_24-000001",
 "CHNDM_SKETCH":"CHSDM-181779_01-000003",
}
for label,imgid in IMAGES.items():
 for mode in ["delivery2000","download_jpg"]:
  if mode=="delivery2000":url="https://ids.si.edu/ids/deliveryService?id="+urllib.parse.quote(imgid,safe="")+"&max=2000"
  else:url="https://ids.si.edu/ids/download?id="+urllib.parse.quote(imgid,safe="")+".jpg"
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"QuietArtGallery/1.8.7 (+personal non-commercial art gallery; capped research audit)","Accept":"image/jpeg"})
   with urllib.request.urlopen(req,timeout=27) as r:
    final=r.geturl();mime=r.headers.get("Content-Type","");status=r.status
    data=r.read(8*1024*1024+1)
   if len(data)>8*1024*1024:raise ValueError("exceeded 8MiB")
   with Image.open(io.BytesIO(data)) as im:
    im.load();w,h=im.size;format=im.format
   fit=min((w/h)/.62,.62/(w/h)) if h else 0
   ok=format=="JPEG" and min(w,h)>=1000 and max(w,h)>=1400 and h>w and fit>=.75
   print("SMITHSONIAN_PIXELS "+json.dumps({"label":label,"method":mode,"http":status,"url_final":final[:140],"redirected":final!=url,"content_type":mime,"width":w,"height":h,"bytes":len(data),"fit":round(fit,3),"valid":ok,"sha256":hashlib.sha256(data).hexdigest() if ok else ""}),flush=True)
   if ok:break
  except Exception as e:
   print("SMITHSONIAN_PIXEL_ERROR "+json.dumps({"label":label,"method":mode,"error":str(e)[:175]}),flush=True)
