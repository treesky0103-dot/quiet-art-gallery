#!/usr/bin/env python3
"""Read-only Commons source audit: Smithsonian SAAM and NMAA Freer Galleries.
No API keys, payment registration, local artwork modification or user data.
Report is a sample, not a promise that all eligible paintings can be served.
"""
import json, re, sys, urllib.parse, urllib.request, time, io
from pathlib import Path
from PIL import Image
CATS={
 "saam":["Paintings in the Smithsonian American Art Museum"],
 "nmaa":["Paintings from China in the Freer Gallery",
         "Paintings from Japan in the Freer Gallery of Art",
         "Paintings from India in the Freer Gallery of Art"]
}
def request(url,max_bytes=5_000_000):
 h={"User-Agent":"QuietArtGallery/1.6.6 (Smithsonian Commons source verification; github.com/treesky0103-dot/quiet-art-gallery)","Accept":"application/json,image/jpeg"}
 with urllib.request.urlopen(urllib.request.Request(url,headers=h),timeout=23) as r:
  raw=r.read(max_bytes+1)
  if len(raw)>max_bytes:raise ValueError("response exceeds bound")
  return raw
def eligible(p):
 title=p.get("title","")
 if re.search(r"gallery (?:interior|view|room)|museum (?:interior|hall|room)|sculpture|installation|framed painting|(?:painting )?detail|verso|back side",title,re.I):
  return False
 info=(p.get("imageinfo") or [{}])[0]
 md=info.get("extmetadata") or {}
 license=(md.get("LicenseShortName") or {}).get("value","").strip().lower()
 if not (license in ("public domain","pd","cc0","cc0 1.0","cc0 1.0 universal")):return False
 if info.get("mime") not in ("image/jpeg","image/png","image/webp"):return False
 w,h=info.get("width") or 0,info.get("height") or 0
 if not (w>=1000 and h>=1400 and w<h):return False
 fill=min((w/h)/.625,.625/(w/h))
 return fill>=.75
out={"sample_only":True,"sources":{},"valid_items":{}}
Path("smithsonian_audit").mkdir(exist_ok=True)
for museum,cats in CATS.items():
 aggregate=[]
 for category in cats:
  params={"action":"query","generator":"search","gsrsearch":f'deepcategory:"{category}"',
          "gsrnamespace":"6","gsrlimit":"50","gsroffset":"0","prop":"imageinfo",
          "iiprop":"url|size|mime|extmetadata","iiurlwidth":"2000",
          "format":"json","formatversion":"2"}
  url="https://commons.wikimedia.org/w/api.php?"+urllib.parse.urlencode(params)
  try:
   data=json.loads(request(url))
   if data.get("error"):raise ValueError(str(data["error"])[:180])
   pages=((data.get("query") or {}).get("pages") or [])
   matches=[p for p in pages if eligible(p)]
   out["sources"][category]={"museum":museum,"raw":len(pages),
      "eligible_metadata":len(matches),
      "sample_titles":[p.get("title","")[:150] for p in matches[:5]],
      "error":None}
   aggregate.extend(matches)
   print(category,": raw",len(pages),"metadata eligible",len(matches),flush=True)
  except Exception as e:
   out["sources"][category]={"museum":museum,"raw":0,
      "eligible_metadata":0,"sample_titles":[],"error":str(e)[:200]}
   print("SOURCE_ERROR",category,str(e)[:200],flush=True)
  time.sleep(.25)
 out["valid_items"][museum]=[]
 seen=set()
 for p in aggregate:
  if len(out["valid_items"][museum])>=3:break
  if p.get("pageid") in seen:continue
  seen.add(p.get("pageid"))
  meta=(p.get("imageinfo") or [{}])[0]
  url=meta.get("thumburl") or meta.get("url")
  if not url:continue
  try:
   raw=request(url,max_bytes=9_000_000)
   img=Image.open(io.BytesIO(raw));img.load()
   w,h=img.size
   if min(w,h)<1000 or max(w,h)<1400:continue
   fill=min((w/h)/.625,.625/(w/h)) if w<h else 0
   if fill<.75:continue
   out["valid_items"][museum].append({"title":p.get("title"),"pageid":p.get("pageid"),
       "width":w,"height":h,"fill":round(fill,4),
       "original_width":meta.get("width"),"original_height":meta.get("height"),
       "license":(meta.get("extmetadata",{}).get("LicenseShortName") or {}).get("value"),
       "source_page":meta.get("descriptionurl")})
   print("VERIFIED_PIXELS",museum,p.get("title","")[:65],w,h,round(fill,3),flush=True)
  except Exception as e:
   print("SKIP_IMAGE",museum,p.get("title","")[:50],str(e)[:120],flush=True)
Path("smithsonian_audit/report.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf8")
assert out["valid_items"]["saam"],"No SAAM image verified; do not claim confirmed live display"
assert out["valid_items"]["nmaa"],"No NMAA image verified; do not claim confirmed live display"
print("PASS two Smithsonian museums with real CC0/PD painting pixels and >=75% portrait coverage",flush=True)
