#!/usr/bin/env python3
"""Verify real JPEGs from LOC official Free-to-Use and Reuse data pack.
Bounded to six artwork-genre samples. No metadata count is passed as image count.
"""
import io,json,re,urllib.request,collections,hashlib
from PIL import Image
BASE="https://data.labs.loc.gov/free-to-use/"
UA="QuietArtGalleryResearch/1.8.7 (six copyrighted-safe art imagery checks)"
def get(url,maxbytes=20000000):
 req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json,image/jpeg"})
 with urllib.request.urlopen(req,timeout=25) as r:
  b=r.read(maxbytes+1)
  if len(b)>maxbytes:raise ValueError("max bytes")
  return b,r.headers.get("Content-Type","")
meta=json.loads(get(BASE+"metadata.json")[0])
rows=json.loads(get(BASE+"manifest.json",maxbytes=800000)[0])
key={str(row[1]).replace("https://","http://"):row for row in rows["rows"]}
print("LOCMETADATA",len(meta),len(key),rows["cols"],flush=True)
art=re.compile(r"\b(?:paintings?|prints?|posters?|engravings?|etchings?|lithographs?|woodcuts?|drawings?|watercolo[u]?rs?|aquatints?)\b",re.I)
photo=re.compile(r"\b(?:photograph|photographic|negative|glass plate|photochrom|photomechanical|photoprint|maps?|plans?|measured drawing|blueprints?|books?|manuscripts?|newsprint|maps of|documentary)\b",re.I)
rights=re.compile(r"\b(?:public domain|free to use|no known restrictions|no known copyright|published without copyright)\b",re.I)
qualified=[]
for row in meta:
 m=" ".join(row.get("Medium",[]) or [])
 g=" ".join(row.get("Genre",[]) or [])
 rt=" ".join(row.get("Rights",[]) or [])
 if not art.search(m+" "+g) or photo.search(m+" "+g) or not rights.search(rt):continue
 man=key.get(str(row.get("Id","")).replace("https://","http://"))
 if not man or man[3]>6000000 or man[3]<90000:continue
 qualified.append((row,man))
print("LOCQUALIFIED",len(qualified),flush=True)
selected=[];seen=set()
for row,man in sorted(qualified,key=lambda pair:-pair[1][3]):
 theme=str(row.get("Set",[""])[0])
 if theme in seen:continue
 selected.append((row,man));seen.add(theme)
 if len(selected)>=8:break
passed=0
for i,(row,man) in enumerate(selected,1):
 url=BASE+"data/"+man[0]
 try:
  b,ct=get(url,6000000)
  with Image.open(io.BytesIO(b)) as im:
   im.load();w,h=im.size;fmt=im.format
  filled=min((w/h)/.62,.62/(w/h)) if h else 0
  ok=fmt=="JPEG" and min(w,h)>=1000 and max(w,h)>=1400 and h>w and filled>=.75
  passed+=ok
  print("LOC_ART_PIXEL",json.dumps({"index":i,"id":row.get("Id"),"title":str(row.get("Title"))[:90],
        "genre":str(row.get("Genre"))[:125],"medium":str(row.get("Medium"))[:130],
        "w":w,"h":h,"bytes":len(b),"fill":round(filled,3),"pass":ok,
        "sha256":hashlib.sha256(b).hexdigest() if ok else None},ensure_ascii=False),flush=True)
 except Exception as e:print("LOC_ART_PIXEL",json.dumps({"index":i,"error":str(e)[:130]}),flush=True)
print("LOC_SAMPLE_PASS",passed,"/",len(selected),flush=True)
