#!/usr/bin/env python3
"""Read-only artwork aspect-ratio metadata sample of the same 19 sources as app v1.6.2.

Outputs counts and 16:10 / 9:16 portrait viewport contain-fill fractions.
No images are copied and no production source or selection rules are changed.
Wikimedia sources are category search samples, NOT complete museum inventories.
"""
import concurrent.futures
import datetime
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ART_RE=re.compile(r"(?:gallery (?:interior|view|room)|museum (?:interior|hall|room)|exhibition (?:view|room|hall)|on (?:the )?wall|framed (?:painting|art)|sculpture|statue|installation|museum building|art gallery building|visitor|tour group|gallery entrance)",re.I)
ART_TYPES=re.compile(r"painting|drawing|print|watercolo[u]?r|etching|lithograph|woodblock|woodcut|illustration|gouache|collage|pastel|ink on paper|oil on canvas|oil on panel|acrylic on|tempera on|aquatint|serigraph|screenprint|engraving",re.I)
RIGHTS={"public domain","pd","cc0","cc0 1.0","cc0 1.0 universal"}
SRC=[
 ('asia-korea','Paintings in the National Museum of Korea'),('asia-tokyo','Japanese paintings in the Tokyo National Museum'),
 ('asia-kyoto','Paintings in the Kyoto National Museum'),('asia-nara','Paintings in the Nara National Museum'),
 ('asia-taipei','Paintings in the National Palace Museum'),
 ('africa-iziko','Paintings in the South African National Gallery'),
 ('africa-ethiopia','Paintings in the National Museum of Ethiopia'),
 ('africa-zimbabwe','Paintings in the National Gallery of Zimbabwe'),
 ('africa-johannesburg','Paintings by Paul Signac in the Johannesburg Art Gallery'),
 ('europe-rijks','Paintings in the Rijksmuseum Amsterdam'),
 ('us-nga','Paintings in the National Gallery of Art (Washington, D.C.)'),
 ('us-getty','Paintings in The J. Paul Getty Museum'),
 ('europe-smk','Paintings in Statens Museum for Kunst'),
 ('europe-paris','Paintings in Musée Carnavalet'),
 ('europe-london','Paintings in the National Gallery, London'),
 ('us-walters','Paintings in the Walters Art Museum')
]
VIEWPORTS={"tablet-16:10-portrait":10/16,"tablet-16:9-portrait":9/16}
THRESHOLDS=[0.80,0.85,0.90,0.95]
AGENT="QuietArtGalleryAspectAudit/1.0 (https://github.com/treesky0103-dot/quiet-art-gallery; sample, no image download)"

def fetchjson(url,timeout=20):
 req=urllib.request.Request(url,headers={"User-Agent":AGENT,"Accept":"application/json"})
 with urllib.request.urlopen(req,timeout=timeout) as response:
  body=response.read(6_000_001)
  if len(body)>6_000_000:raise ValueError("metadata too large")
  return json.loads(body.decode("utf-8"))
def count_criteria(items):
 out={"sample_total":len(items),"portrait":0,"valid_resolution":0}
 for v in VIEWPORTS:
  for f in THRESHOLDS:out[f"{v}-fill{int(f*100)}"]=0
 for item in items:
  w,h=item["width"],item["height"]
  if h>w:out["portrait"]+=1
  if min(w,h)>=1200 and max(w,h)>=1600:
   out["valid_resolution"]+=1
   r=w/h
   for key,viewport in VIEWPORTS.items():
    filled=min(r/viewport,viewport/r)
    for threshold in THRESHOLDS:
     if filled+1e-9>=threshold:out[f"{key}-fill{int(threshold*100)}"]+=1
 return out

def commons_one(pair):
 name,category=pair
 items=[];totalhits=None;sampled=0;errors=[];pagecounts=[]
 for offset in (0,50):
  q={"action":"query","generator":"search","gsrsearch":'deepcategory:"'+category+'"',
     "gsrnamespace":"6","gsrlimit":"50","gsroffset":str(offset),
     "prop":"imageinfo","iiprop":"url|size|mime|extmetadata",
     "iiurlwidth":"2000","format":"json","formatversion":"2"}
  url="https://commons.wikimedia.org/w/api.php?"+urllib.parse.urlencode(q)
  try:
   data=fetchjson(url,timeout=25)
   if data.get("error"):raise ValueError(str(data["error"]))
   query=data.get("query") or {}
   if totalhits is None:totalhits=(query.get("searchinfo") or {}).get("totalhits")
   pages=query.get("pages") or []
   sampled+=len(pages);pagecounts.append(len(pages))
   for p in pages:
    info=(p.get("imageinfo") or [None])[0]
    if not info or ART_RE.search(str(p.get("title") or "")):continue
    meta=info.get("extmetadata") or {}
    license=str((meta.get("LicenseShortName") or {}).get("value","")).lower().strip()
    mime=info.get("mime")
    if license not in RIGHTS or mime not in ("image/jpeg","image/png","image/webp"):continue
    w=int(info.get("width") or 0);h=int(info.get("height") or 0)
    if w==0 or h==0:continue
    items.append({"id":"commons:"+str(p.get("pageid")),"width":w,"height":h})
   if len(pages)<50:break
  except Exception as e:
   errors.append(type(e).__name__+": "+str(e)[:140])
   break
  time.sleep(.15)
 return dict(source=name,provider="Commons category",totalhits=totalhits,raw_rows=sampled,
             offsets=pagecounts,errors=errors,**count_criteria(items),items=items)

def cleveland():
 items=[];raw=0;totalhits={};errors=[]
 for typ in ("Painting","Drawing","Print"):
  # one actual page per type like v1.6.2, not any artworks outside app scope
  try:
   q=urllib.parse.urlencode({"type":typ,"limit":100,"skip":0,"has_image":1})
   data=fetchjson("https://openaccess-api.clevelandart.org/api/artworks/?cc0&"+q,timeout=18)
   totalhits[typ]=(data.get("info") or {}).get("total")
   arts=data.get("data") or [];raw+=len(arts)
   for a in arts:
    if a.get("share_license_status")!="CC0":continue
    img=(a.get("images") or {}).get("print") or (a.get("images") or {}).get("web") or {}
    w=int(img.get("width") or 0);h=int(img.get("height") or 0)
    if not w or not h:continue
    items.append({"id":"cleveland:"+str(a.get("id")),"width":w,"height":h})
  except Exception as e:errors.append(typ+": "+type(e).__name__+": "+str(e)[:110])
 return dict(source="cleveland",provider="Cleveland API",totalhits=totalhits,raw_rows=raw,errors=errors,**count_criteria(items),items=items)

def chicago():
 items=[];raw=0;errors=[];totalhits=None
 for page in (1,2):
  try:
   params={"query":{"bool":{"filter":[{"term":{"is_public_domain":True}},{"exists":{"field":"image_id"}}]}},"page":page,
           "limit":100,
           "fields":["id","artwork_type_title","medium_display","image_id","thumbnail","is_public_domain"]}
   url="https://api.artic.edu/api/v1/artworks/search?params="+urllib.parse.quote(json.dumps(params,separators=(",",":")))
   data=fetchjson(url,timeout=25)
   if totalhits is None:totalhits=(data.get("pagination") or {}).get("total")
   arts=data.get("data") or [];raw+=len(arts)
   for a in arts:
    if not a.get("is_public_domain"):continue
    kind=str(a.get("artwork_type_title") or "")+" "+str(a.get("medium_display") or "")
    if not ART_TYPES.search(kind):continue
    img=a.get("thumbnail") or {}
    w=int(img.get("width") or 0);h=int(img.get("height") or 0)
    if w==0 or h==0:continue
    # Chicago thumbnail metadata gives aspect ratio, but not decoded IIIF pixel size.
    items.append({"id":"chicago:"+str(a.get("id")),"width":w,"height":h})
   if len(arts)<100:break
  except Exception as e:errors.append("page "+str(page)+": "+type(e).__name__+": "+str(e)[:130]);break
 return dict(source="chicago",provider="AIC API (thumbnail dimensions, actual resolution unverified)",totalhits=totalhits,raw_rows=raw,
             errors=errors,**count_criteria(items),items=items)

def main():
 start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  fut={pool.submit(commons_one,pair):pair[0] for pair in SRC}
  results=[]
  for f in concurrent.futures.as_completed(fut):
   name=fut[f]
   try:res=f.result()
   except Exception as e:res={"source":name,"error":str(e)}
   print("CATEGORY",json.dumps({k:v for k,v in res.items() if k!="items"},ensure_ascii=False),flush=True)
   results.append(res)
 # Keep expensive large official APIs separate from Commons worker concurrency
 for fn in (chicago,cleveland):
  res=fn()
  results.append(res)
  print("OFFICIAL",json.dumps({k:v for k,v in res.items() if k!="items"},ensure_ascii=False),flush=True)
 # Met contains no dependable width/height in its search API; not counted.
 unique={}
 for r in results:
  for item in r.get("items",[]):unique[item["id"]]=item
 summary=count_criteria(list(unique.values()))
 data={"utc":start,"finished_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "viewport_assumption":"portrait 16:10 => W/H = .625; 16:9 => .5625",
       "fill_definition":"visible artwork area / viewport area when contain and no crop",
       "method":"Only first 1–2 50-row Commons category search result pages; rights/format/filename/resolution metadata filter. AIC thumb ratio exploratory only.",
       "metadata_not_pixel_decoded":True,
       "not_estimate_of_full_collection":True,
       "met_unmeasured":True,
       "unique_sample":summary,
       "per_source":[{k:v for k,v in x.items() if k!="items"} for x in sorted(results,key=lambda x:x["source"])],
       "duplicates_removed_by_id":sum(len(x.get("items",[])) for x in results)-len(unique)}
 Path("portrait_fill_audit_20261113.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf8")
 print("SUMMARY",json.dumps({k:v for k,v in data.items() if k!="per_source"},ensure_ascii=False),flush=True)
 print("SAVED portrait_fill_audit_20261113.json",flush=True)

if __name__=="__main__":main()
