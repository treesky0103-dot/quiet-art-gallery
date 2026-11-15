#!/usr/bin/env python3
"""Explore the Library of Congress *curated free-to-reuse* public data pack.
Metadata-only, no image harvesting; short bounded reads and reporting.
"""
import urllib.request,json,collections
ROOT="https://data.labs.loc.gov/free-to-use/"
UA="QuietArtGalleryResearch/1.8.7 (review of curated public domain artworks)"
def get(name,size):
 req=urllib.request.Request(ROOT+name,headers={"User-Agent":UA,"Accept":"application/json"})
 with urllib.request.urlopen(req,timeout=25) as r:
  data=r.read(size+1)
  if len(data)>size:raise ValueError("too large "+name)
  return json.loads(data)
for name,size in [("sample-data/metadata.json",800000),("sample-data/manifest.json",100000),("manifest.json",800000)]:
 try:
  data=get(name,size)
  summary={"name":name,"type":type(data).__name__,"entries":len(data)}
  if isinstance(data,dict):
   summary["keys"]=list(data)[:30]
   for k,v in data.items():
    if isinstance(v,list):
     summary["list_field"]=k;summary["sample"]=str(v[:2])[:6500];break
  elif isinstance(data,list):
   summary["sample"]=str(data[:2])[:6500]
   ks=collections.Counter()
   formats=collections.Counter()
   for obj in data:
    if isinstance(obj,dict):
     ks.update(obj.keys())
     for attr in ("format","original_format","type","medium","rights","genre"):
      if attr in obj:formats.update((str(obj[attr])[:60],))
   summary["fields"]=ks.most_common(30);summary["format_values"]=formats.most_common(20)
  print("LOC_CURATED "+json.dumps(summary,ensure_ascii=False),flush=True)
 except Exception as e:print("LOC_CURATED_ERROR",name,str(e)[:300],flush=True)
