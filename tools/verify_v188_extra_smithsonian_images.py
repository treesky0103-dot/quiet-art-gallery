#!/usr/bin/env python3
"""Verify CC0 NMAAHC poster bytes and sample bounded prefix of large new S3 units."""
import urllib.request,urllib.error,io,json,re,hashlib,collections
from PIL import Image
URLS={
 "nmaahc_poster1":"https://ids.si.edu/ids/deliveryService?id=NMAAHC-2016_135_6_001&max=2000",
 "nmaahc_poster2":"https://ids.si.edu/ids/deliveryService?id=NMAAHC-2016_135_6_002&max=2000",
 "fsg_james_whistler":"https://ids.si.edu/ids/deliveryService?id=FS-7435_26&max=2000",
 "fsg_japanese_painting":"https://ids.si.edu/ids/deliveryService?id=FS-5907_12&max=2000",
}
for label,url in URLS.items():
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"QuietArtGallery research/1.8.8 (noncommercial CC0 art, bounded sample)","Accept":"image/jpeg"})
  with urllib.request.urlopen(req,timeout=25) as r:
   b=r.read(8*1024*1024+1);ct=r.headers.get("Content-Type","")
  if len(b)>8*1024*1024:raise RuntimeError("too many bytes")
  with Image.open(io.BytesIO(b)) as img:
   img.load();w,h=img.size;fmt=img.format
   assert fmt=="JPEG" and w>=1000 and h>=1400 and h>w and min((w/h)/.62,.62/(w/h))>=.75,(w,h)
  print("SMITHSONIAN_NEW_PIXELS_PASS",json.dumps({"name":label,"width":w,"height":h,"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}),flush=True)
 except Exception as e:print("SMITHSONIAN_NEW_PIXELS_FAIL",label,str(e)[:180],flush=True)
for unit in ("nmah","aaa"):
 url="https://smithsonian-open-access.s3-us-west-2.amazonaws.com/metadata/edan/"+unit+"/00.txt"
 stats=collections.Counter();sample=[]
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"QuietArtGallery research 1.8.8; bounded 5MB data sample"})
  with urllib.request.urlopen(req,timeout=25) as r:
   read=0
   for raw in r:
    read+=len(raw)
    if read>5*1024*1024 or stats["rows"]>=3000:break
    stats["rows"]+=1
    try:obj=json.loads(raw)
    except Exception:continue
    d=((obj.get('content') or {}).get("descriptiveNonRepeating") or {})
    if (d.get("metadata_usage") or {}).get("access")!="CC0":continue
    stats["cc0"]+=1
    cc=(obj.get('content') or {})
    kinds=(cc.get("indexedStructured") or {}).get("object_type") or []
    valid=any(re.fullmatch(r"(?:Paintings?|Prints?|Drawings?|Watercolors?|Watercolours?|Posters?|Illustrations?|Engravings?|Lithographs?|Etchings?|Woodcuts?)",str(x),re.I) for x in kinds)
    if not valid:continue
    stats["2dart"]+=1
    m=(d.get('online_media') or {}).get('media') or []
    for img in m:
     if (img.get('usage') or {}).get('access')!="CC0" or img.get("type")!="Images":continue
     ids=img.get("idsId") or ""
     if img.get("content")!="https://ids.si.edu/ids/deliveryService?id="+ids:continue
     hires=next((r for r in img.get("resources",[]) if r.get("label")=="High-resolution JPEG"),{})
     w=int(hires.get("width") or 0);h=int(hires.get("height") or 0)
     stats["cc0image"]+=1
     if w>=1000 and h>=1400 and h>w:
      stats["portrait"]+=1
      if len(sample)<5:sample.append({"id":ids,"w":w,"h":h,"title":(d.get("title") or {}).get("content")})
  print("LARGESOURCE",json.dumps({"unit":unit,"bytes":read,"stats":stats,"sample":sample}),flush=True)
 except Exception as e:print("LARGESOURCE_ERROR",unit,str(e)[:160],flush=True)
