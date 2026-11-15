#!/usr/bin/env python3
"""Bounded pixel/rights verification for Princeton and public Quebec dataset."""
import urllib.request, json, io, re, hashlib, time
from PIL import Image
UA="QuietArtGalleryResearch/1.8.7 (single artwork rights and image feasibility)"
def fetch(url,limit=9000000):
 request=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json,image/jpeg,*/*;q=0.5"})
 with urllib.request.urlopen(request,timeout=22) as r:
  data=r.read(limit+1)
  return r.status,r.headers.get("Content-Type",""),data
def artwork(url,label):
 try:
  code,mime,data=fetch(url,limit=8*1024*1024)
  if len(data)>8*1024*1024:raise ValueError("max size")
  with Image.open(io.BytesIO(data)) as im:
   im.load();w,h=im.size;form=im.format
   fill=min(w/(h*.62),(h*.62)/w) if h else 0
   accepted=(form=="JPEG" and w>=1000 and h>=1400 and w<h and fill>=.75)
  print("PRINCETON_IMAGE",json.dumps({"label":label,"status":code,"mime":mime,"w":w,"h":h,"jpeg":form,"bytes":len(data),"fit":round(fill,3),"passes":accepted,"sha256":hashlib.sha256(data).hexdigest()},ensure_ascii=False),flush=True)
 except Exception as e:print("PRINCETON_IMAGE",json.dumps({"label":label,"error":str(e)[:170]}),flush=True)
sample="https://media.artmuseum.princeton.edu/iiif/3/collection/x1954-13"
artwork(sample+"/full/2000,/0/default.jpg","Degas Drawings, 1899 rights unrestricted")
artwork(sample+"/full/!1600,1600/0/default.jpg","Degas 1600-fit")
# Official Quebec open data is not yet accepted as a personal gallery supplier.
# Inspect only structure/rights/links, never download images that have no license.
q="https://www.donneesquebec.ca/recherche/dataset/6820a235-2658-4453-8a88-2d29618a4457/resource/3060f8cc-64f9-4853-b915-1c188bb825c1/download/oeuvres-mac-domaine-public-canada.json"
try:
 code,ct,b=fetch(q,9000000)
 print("QUEBEC_BYTES",len(b),"mime",ct,flush=True)
 if len(b)>9000000:raise ValueError("dataset exceeds 9 MB")
 j=json.loads(b)
 print("QUEBEC_DATASET",json.dumps({"shape":type(j).__name__,"count":len(j),"sample":str(j[:2] if isinstance(j,list) else list(j.items())[:1])[:4700]},ensure_ascii=False),flush=True)
except Exception as e:print("QUEBEC_DATASET_FAIL",type(e).__name__,str(e)[:250],flush=True)
