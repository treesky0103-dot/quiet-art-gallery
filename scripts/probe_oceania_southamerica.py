#!/usr/bin/env python3
"""Non-destructive, real-world Commons audit: Oceania and South America museums.
Only a collection with verified actual eligible images is a candidate.
"""
import concurrent.futures, json, urllib.parse, urllib.request, re, time, datetime
from pathlib import Path
sources={
 "oceania-ngv":("호주 빅토리아 국립미술관","Paintings in the National Gallery of Victoria"),
 "oceania-nsw":("호주 뉴사우스웨일스 미술관","Paintings in the Art Gallery of New South Wales"),
 "oceania-nga":("호주 국립미술관","Paintings in the National Gallery of Australia"),
 "oceania-south":("남호주 미술관","Paintings in the Art Gallery of South Australia"),
 "oceania-queensland":("퀸즐랜드 미술관","Paintings in the Queensland Art Gallery"),
 "oceania-auckland":("뉴질랜드 오클랜드 미술관","Paintings in the Auckland Art Gallery"),
 "oceania-tepapa":("뉴질랜드 테 파파 박물관","Paintings in the Museum of New Zealand Te Papa Tongarewa"),
 "oceania-dunedin":("뉴질랜드 더니든 미술관","Paintings in the Dunedin Public Art Gallery"),
 "latam-brasil":("브라질 국립미술관","Brazilian paintings in the Museu Nacional de Belas Artes"),
 "latam-argentina":("아르헨티나 국립미술관","Paintings in the Museo Nacional de Bellas Artes (Argentina)"),
 "latam-argentina2":("아르헨티나 국립미술관(자국 작품)","Argentinian paintings in the Museo Nacional de Bellas Artes (Argentina)"),
 "latam-chile":("칠레 국립미술관","Paintings in the Museo Nacional de Bellas Artes (Chile)"),
 "latam-peru":("페루 리마 미술관","Paintings in the Museo de Arte de Lima"),
 "latam-colombia":("콜롬비아 국립박물관","Paintings in the Museo Nacional de Colombia"),
 "latam-uruguay":("우루과이 국립시각예술박물관","Paintings in the Museo Nacional de Artes Visuales"),
 "latam-masp":("브라질 상파울루 미술관","Paintings in the São Paulo Museum of Art"),
 "latam-pinacoteca":("브라질 상파울루 피나코테카","Paintings in the Pinacoteca do Estado de São Paulo")
}
BLOCK=re.compile(r"gallery (?:interior|view|room)|museum (?:interior|hall|room)|exhibition (?:view|room|hall)|framed|statue|sculpture|installation|detail|verso|reverse",re.I)
PD={"public domain","pd","cc0","cc0 1.0","cc0 1.0 universal"}
def worker(entry):
 k,(name,cat)=entry
 out={"id":k,"name":name,"category":cat,"count":0,"raw":0,"valid":0,"portrait80_16_10":0,"examples":[],"error":None}
 for offset in (0,50):
  q=urllib.parse.urlencode({"action":"query","generator":"search","gsrsearch":'deepcategory:"'+cat+'"',
    "gsrnamespace":6,"gsrlimit":50,"gsroffset":offset,
    "prop":"imageinfo","iiprop":"url|size|mime|extmetadata","iiurlwidth":2000,
    "format":"json","formatversion":2})
  req=urllib.request.Request("https://commons.wikimedia.org/w/api.php?"+q,headers={
    "User-Agent":"QuietArtGallery/1.6.3 (https://github.com/treesky0103-dot/quiet-art-gallery; provenance audit)",
    "Accept":"application/json"})
  try:
   with urllib.request.urlopen(req,timeout=24) as resp:res=json.load(resp)
   if res.get("error"):raise ValueError(str(res["error"]))
   q=res.get("query") or {}
   pages=q.get("pages") or []
   if offset==0:out["count"]=(q.get("searchinfo") or {}).get("totalhits",None)
   out["raw"]+=len(pages)
   for p in pages:
    i=(p.get("imageinfo") or [{}])[0]
    meta=i.get("extmetadata") or {}
    lic=str((meta.get("LicenseShortName") or {}).get("value","")).lower().strip()
    if lic not in PD or i.get("mime") not in ("image/jpeg","image/png","image/webp") or BLOCK.search(str(p.get("title") or "")):continue
    w,h=int(i.get("width") or 0),int(i.get("height") or 0)
    if min(w,h)<1200 or max(w,h)<1600:continue
    out["valid"]+=1
    if h>w and min((w/h)/.625,.625/(w/h))>=.80:
     out["portrait80_16_10"]+=1
     if len(out["examples"])<3:out["examples"].append({"title":p.get("title"),"w":w,"h":h,"license":lic})
   if len(pages)<50:break
  except Exception as e:
   out["error"]=type(e).__name__+": "+str(e)[:170];break
 return out
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
 rows=list(ex.map(worker,sources.items()))
for r in rows:print(json.dumps(r,ensure_ascii=False),flush=True)
Path("oceania_southamerica_source_probe.json").write_text(json.dumps({"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"source_type":"Commons museum category only","rows":rows},ensure_ascii=False,indent=2),encoding="utf8")
