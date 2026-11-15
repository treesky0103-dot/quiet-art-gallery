#!/usr/bin/env python3
"""Bounded public Smithsonian S3 sample verification for previously unused owning units.
Never count metadata hits as images; require record CC0, media CC0, flat art class,
portrait size, official IDS, then confirm pixel in separate audit.
"""
import urllib.request,urllib.error,json,re,collections,concurrent.futures
UNITS={"nmah":"American History Museum","nmaahc":"African American History Museum","acm":"Anacostia Museum","aaa":"Archives of American Art","eepa":"Eliot Elisofon Photo Archives","nmai":"American Indian Museum","nasm":"Air Space Museum","fsg":"Asian Art Freer Sackler","nmafa":"African Art Museum"}
SHARDS=("00","10","a0","f0")
UA="QuietArtGallery research/1.8.8 (open-data probe, bounded 1 shard per museum, no credential)"
RX=re.compile(r'^(?:paintings?|prints?|drawings?|watercolors?|watercolours?|posters?|graphic design|illustrations?|lithographs?|etchings?|engravings?|woodcuts?)$',re.I)
def run(k):
 unit,name=k;ret={"id":unit,"name":name,"tried":[]}
 for shard in SHARDS:
  url=f"https://smithsonian-open-access.s3-us-west-2.amazonaws.com/metadata/edan/{unit}/{shard}.txt"
  try:
   req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"text/plain"})
   with urllib.request.urlopen(req,timeout=15) as r:
    b=r.read(5*1024*1024+1);status=r.status
   if len(b)>5*1024*1024:
    ret["tried"].append({"shard":shard,"status":"too_large"});continue
   if len(b)<100:
    ret["tried"].append({"shard":shard,"status":"empty"});continue
   hits=[]; stats=collections.Counter()
   for line in b.splitlines()[:4000]:
    try:o=json.loads(line)
    except Exception:continue
    stats["records"]+=1
    c=o.get("content") or {}
    d=c.get("descriptiveNonRepeating") or {}
    if (d.get("metadata_usage") or {}).get("access")!="CC0":continue
    stats["record_cc0"]+=1
    kinds=(c.get("indexedStructured") or {}).get("object_type") or []
    if not any(RX.fullmatch(str(v)) for v in kinds):continue
    stats["flat_art"]+=1
    media=(d.get("online_media") or {}).get("media") or []
    for m in media:
     if str(m.get("type","")).lower()!="images" or (m.get("usage") or {}).get("access")!="CC0":continue
     uri=m.get("content") or ""
     imgid=m.get("idsId") or ""
     if not imgid or uri!=f"https://ids.si.edu/ids/deliveryService?id={imgid}":continue
     resources=m.get("resources") or []
     hires=next((x for x in resources if x.get("label")=="High-resolution JPEG"),{})
     w=int(hires.get("width") or 0);h=int(hires.get("height") or 0)
     stats["media_cc0"]+=1
     if w>=1000 and h>=1400 and h>w:
      stats["portrait_1000x1400"]+=1
      if len(hits)<4:hits.append({"title":(d.get("title") or {}).get("content","")[:150],"object_type":kinds,"idsId":imgid,"w":w,"h":h,"url":uri,"shard":shard})
   ret["tried"].append({"shard":shard,"size":len(b),"counts":dict(stats),"candidates":hits})
   if stats["portrait_1000x1400"]>=2:break
  except urllib.error.HTTPError as e:ret["tried"].append({"shard":shard,"status":e.code})
  except Exception as e:ret["tried"].append({"shard":shard,"error":str(e)[:120]})
 return ret
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
 results={r['id']:r for r in ex.map(run,UNITS.items())}
for k in UNITS:
 print("UNIT188",json.dumps(results[k],ensure_ascii=False)[:12000],flush=True)
