#!/usr/bin/env python3
import urllib.request,json
base="https://data.artmuseum.princeton.edu/"
ua={"User-Agent":"QuietArtGalleryResearch/1.8.7 (art object restrictions audit)"}
def get(path):
 with urllib.request.urlopen(urllib.request.Request(base+path,headers=ua),timeout=15) as r:return json.load(r)
ids=[9449,138583]
for idx in ids:
 try:
  x=get("objects/"+str(idx))
  out={k:x.get(k) for k in ["objectid","displaytitle","classification","datebegin","dateend","makers","restrictions","nowebuse","creditlinerepro","media","primaryimage"]}
  if isinstance(out.get("media"),list):
   out["media"]=[{k:v for k,v in m.items() if k in ("isprimary","mediatypeid","uri","restrictions","content","width","height")} for m in out["media"][:2]]
  if isinstance(out.get("makers"),list):
   out["makers"]=[{k:str(v)[:190] for k,v in mk.items() if k in ("displayname","displaydate","dateend","datebegin","maker","name","role")} for mk in out["makers"][:2]]
  print("PRINCETON_RIGHTS",json.dumps(out,ensure_ascii=False)[:7000],flush=True)
 except Exception as e:print("PRINCETON_ERROR",idx,str(e)[:150],flush=True)
