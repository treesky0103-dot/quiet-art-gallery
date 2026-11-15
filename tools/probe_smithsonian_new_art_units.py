#!/usr/bin/env python3
"""One shard per new Smithsonian art-focused museum; zero auth/payments.
Only read official public S3 CC0 metadata, not restricted Smithsonian images.
"""
import urllib.request,urllib.error,json,re,time,collections
HOST="https://smithsonian-open-access.s3-us-west-2.amazonaws.com/metadata/edan"
UA="QuietArtGalleryResearch/1.8.7 (CC0 museum art S3 public data audit)"
sources={"npg":"National Portrait Gallery","hmsg":"Hirshhorn Museum Sculpture Garden","nmafa":"National Museum of African Art","chndm":"Cooper Hewitt","fsg":"Freer Sackler"}
for unit,name in sources.items():
 u=f"{HOST}/{unit}/00.txt"
 try:
  req=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"text/plain,application/json"})
  with urllib.request.urlopen(req,timeout=30) as r:
   ct=r.headers.get("Content-Type","")
   size=r.headers.get("Content-Length","")
   b=r.read(11*1024*1024)
  if len(b)>=11*1024*1024:print("SMITHSONIAN",unit,"oversized shard",size,flush=True);continue
  rows=b.decode("utf-8","replace").splitlines()
  candidate=[];counts=collections.Counter(); keys=collections.Counter()
  for line in rows:
   try:j=json.loads(line)
   except Exception as e:counts["badjson"]+=1;continue
   keys.update(j.keys());counts["parsed"]+=1
   usage=(((j.get("content") or {}).get("descriptiveNonRepeating") or {}).get("metadata_usage") or {})
   if isinstance(usage,dict) and str(usage.get("access","")).upper()=="CC0":
    counts["CC0"]+=1
    content=j.get("content") or {}
    meta=(content.get("descriptiveNonRepeating") or {})
    online=(meta.get("online_media") or {})
    m=online.get("media") or []
    images=[x for x in m if (x.get("type") or "").lower() in ("images","image") and
       (x.get("usage") or {}).get("access")=="CC0" and
       str(x.get("content") or "").startswith("https://ids.si.edu/ids/")]
    if images:
     counts["CC0images"]+=1
     if len(candidate)<3:
      candidate.append({
        "id":j.get("id"),"title":str((content.get("descriptiveNonRepeating") or {}).get("title"))[:240],
        "media_first":str(images[0])[:1250],"content_keys":list(content)[:18],
        "physicalDescription":str((content.get("freetext") or {}).get("physicalDescription"))[:900],
        "indexed_object_type":(content.get("indexedStructured") or {}).get("object_type")})
  print("SMITHSONIAN",json.dumps({"unit":unit,"bytes":len(b),"file_head":b[:95].decode("utf-8","replace"),
    "type":ct,"expected_bytes":size,"lines":len(rows),"counts":counts,"top_keys":keys.most_common(15),"sample":candidate},ensure_ascii=False,default=str)[:7000],flush=True)
 except Exception as e:print("SMITHSONIAN_ERROR",unit,type(e).__name__,str(e)[:210],flush=True)
