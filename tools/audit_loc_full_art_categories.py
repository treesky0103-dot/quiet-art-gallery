#!/usr/bin/env python3
import json,re,urllib.request,collections,time
root="https://data.labs.loc.gov/free-to-use/"
def get(name,maxbytes):
 req=urllib.request.Request(root+name,headers={"User-Agent":"QuietArtGalleryResearch/1.8.7 (artwork-only audit)"})
 with urllib.request.urlopen(req,timeout=30) as r:
  data=r.read(maxbytes+1)
  if len(data)>maxbytes:raise Exception("oversize "+name)
  return json.loads(data)
meta=get("metadata.json",20000000)
manifest=get("manifest.json",900000)
print("FULL_SET",len(meta),len(manifest.get("rows",[])), "manifest_columns",manifest.get("cols"),flush=True)
print("MANIFEST_SAMPLE",json.dumps(manifest.get("rows",[])[:5],ensure_ascii=False)[:3500],flush=True)
for field in ("Genre","Medium","Original_format","Set","Mime_type","Rights"):
 c=collections.Counter()
 for row in meta:
  v=row.get(field,[])
  if not isinstance(v,list):v=[v]
  for i in v:
   if isinstance(i,str):c[i[:125]]+=1
 print("DISTRIBUTION",field,json.dumps(c.most_common(22),ensure_ascii=False)[:4200],flush=True)
patt=re.compile(r"\b(?:painting|poster|engraving|etching|lithograph|woodcut|woodblock|drawing|print|illustration|watercolor|gouache|screenprint|serigraph|aquatint|linocut|hand.colou?r|oil on canvas)\b",re.I)
bad=re.compile(r"(photograph|photographic|negative|glass plate|photo print|film|map|blueprint|plan of|manuscript|typescr|architectur|building|interior|newsprint|exhibition hall)",re.I)
safe=re.compile(r"public domain|free to use|no known restrictions|no known copyright|rights has expired",re.I)
found=[]
for row in meta:
 genre=" ".join(row.get("Genre",[]) if isinstance(row.get("Genre"),list) else [])
 medium=" ".join(row.get("Medium",[]) if isinstance(row.get("Medium"),list) else [])
 title=row.get("Title") or ""
 combined=genre+" "+medium+" "+title
 rights=" ".join(row.get("Rights",[]) if isinstance(row.get("Rights"),list) else [])
 if patt.search(combined) and not bad.search(genre+" "+medium) and safe.search(rights):
  found.append(row)
print("ART_LIKE",len(found),flush=True)
for row in found[:9]:
 print("ART_SAMPLE",json.dumps({k:row.get(k) for k in ("Id","Title","Genre","Medium","Preview_url","Set","Rights")},ensure_ascii=False)[:1050],flush=True)
