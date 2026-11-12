#!/usr/bin/env python3
"""Read-only public API audit for genuinely recent flat artworks. No download; no scraping."""
import concurrent.futures,datetime,json,re,urllib.parse,urllib.request
from pathlib import Path
CATEGORIES=[
 "21st-century paintings","Contemporary paintings","2010s paintings","2020s paintings",
 "Digital paintings","Digital art","Digital illustrations","Digital drawings",
 "Contemporary abstract paintings","Paintings by Wikipedians","Abstract digital art",
 "21st-century illustrations","21st-century paintings by country",
]
TERMS=["digital painting","digital illustration","abstract digital art",
 "contemporary original painting","surreal digital artwork","modern abstract painting"]
PD={"public domain","pd","cc0","cc0 1.0","cc0 1.0 universal"}
BLOCK=re.compile(r"(sculpture|statue|installation|interior|exhibition|gallery view|framed|detail|poster for|wallpaper desktop|photograph of|museum room|t-shirt|video|film|webcam|logo|3d render)",re.I)
def req(url,timeout=20):
 request=urllib.request.Request(url,headers={
 "Accept":"application/json",
 "User-Agent":"QuietArtGallery/1.6.4 (https://github.com/treesky0103-dot/quiet-art-gallery; open media metadata study)"})
 with urllib.request.urlopen(request,timeout=timeout) as r:
  if int(r.headers.get("Content-Length") or 0)>3_000_000:raise ValueError("too much JSON")
  return json.loads(r.read(3_000_001))
def evaluate_commons(cat):
 p={"action":"query","generator":"search","gsrsearch":'deepcategory:"'+cat+'"',
    "gsrnamespace":6,"gsrlimit":50,"gsroffset":0,"prop":"imageinfo",
    "iiprop":"url|size|mime|extmetadata","iiurlwidth":2000,
    "format":"json","formatversion":2}
 url="https://commons.wikimedia.org/w/api.php?"+urllib.parse.urlencode(p)
 out={"kind":"commons","category":cat,"count":0,"valid":0,"portrait":0,"examples":[]}
 try:
  d=req(url,25);pages=(d.get("query") or {}).get("pages") or []
  out["count"]=len(pages)
  for a in pages:
   inf=(a.get("imageinfo") or [None])[0]
   if not inf:continue
   lic=str(((inf.get("extmetadata") or {}).get("LicenseShortName") or {}).get("value") or "").lower().strip()
   w=int(inf.get("width") or 0);h=int(inf.get("height") or 0)
   title=str(a.get("title") or "")
   if lic not in PD or inf.get("mime") not in ("image/jpeg","image/png","image/webp"):continue
   if BLOCK.search(title) or min(w,h)<1200 or max(w,h)<1600:continue
   out["valid"]+=1
   if h>w and .50<=w/h<=.78125:
    out["portrait"]+=1
    if len(out["examples"])<6:
     out["examples"].append({"id":a.get("pageid"),"title":title,"w":w,"h":h,"lic":lic,"url":inf.get("thumburl")})
 except Exception as e:out["error"]=type(e).__name__+": "+str(e)[:145]
 return out
def evaluate_openverse(term):
 p={"q":term,"license":"cc0,pdm","source":"wikimedia","page_size":20,"page":1}
 url="https://api.openverse.org/v1/images/?"+urllib.parse.urlencode(p)
 out={"kind":"openverse","query":term,"count":0,"valid":0,"portrait":0,"examples":[]}
 try:
  d=req(url,25);res=d.get("results") or []
  out["count"]=len(res);out["total_results"]=d.get("result_count")
  for a in res:
   lic=str(a.get("license") or "").lower()
   w=int(a.get("width") or 0);h=int(a.get("height") or 0)
   if lic not in ("cc0","pdm") or not a.get("url") or BLOCK.search(str(a.get("title") or "")):continue
   if min(w,h)<1200 or max(w,h)<1600:continue
   out["valid"]+=1
   if h>w and .50<=w/h<=.78125:
    out["portrait"]+=1
    if len(out["examples"])<5:out["examples"].append({
      "title":a.get("title"),"url":a.get("url"),"w":w,"h":h,
      "license":lic,"source":a.get("source"),"created_on":a.get("created_on")})
 except Exception as e:out["error"]=type(e).__name__+": "+str(e)[:145]
 return out
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as p:
 futures=[p.submit(evaluate_commons,c) for c in CATEGORIES]+[p.submit(evaluate_openverse,t) for t in TERMS]
 data=[f.result() for f in futures]
for row in data:print(json.dumps(row,ensure_ascii=False),flush=True)
Path("modern_source_probe.json").write_text(json.dumps({"date":datetime.datetime.now(datetime.timezone.utc).isoformat(),"rows":data},ensure_ascii=False,indent=2),encoding="utf8")
