#!/usr/bin/env python3
"""Conservative, bounded live checks of institutions not among the 135 prior entries.
Discover only. Never count metadata as gallery-ready image.
"""
import json,time,urllib.request,urllib.parse,urllib.error
from concurrent.futures import ThreadPoolExecutor,as_completed

ENDPOINTS={
 "princeton_draw":"https://data.artmuseum.princeton.edu/objects/9449",
 "princeton_older":"https://data.artmuseum.princeton.edu/objects/32221",
 "princeton_page":"https://data.artmuseum.princeton.edu/objects?department=Prints%20and%20Drawings&size=4&from=0",
 "princeton_query":"https://data.artmuseum.princeton.edu/search?q=painting&type=artobjects&size=3",
 "yale_lux":"https://lux.collections.yale.edu/api/search/item?q=%7B%22text%22%3A%22watercolor%22%7D&pageLength=3",
 "yale_lux_estimate":"https://lux.collections.yale.edu/api/search-estimate/item?q=%7B%22text%22%3A%22painting%22%7D",
 "yale_lux_basic":"https://lux.collections.yale.edu/api/search/item?q=%7B%22text%22%3A%22painting%22%7D&pageLength=2",
 "whitney":"https://whitney.org/api/artworks?q%5Bclassification_eq%5D=Paintings&page=1",
 "nationalmuseum_sweden":"https://api.nationalmuseum.se/",
 "kulturarvsdata_sweden":"https://kulturarvsdata.se/ksamsok/api",
 "k_samsok":"https://kulturarvsdata.se/ksamsok/api?method=search&query=painting&hitsPerPage=2",
 "birmingham_museum_uk":"https://images.birminghammuseums.org.uk/",
 "birmingham_museum_us":"https://www.artsbma.org/collection/",
 "princeton_download_rights":"https://artmuseum.princeton.edu/art/collections/objects/9449"
}
def probe(name,url):
 t=time.monotonic()
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"QuietArtGallery local art collector research/1.0 (noncommercial; 1-2 requests per institution)","Accept":"application/json,application/ld+json,application/xml;q=0.7,*/*;q=0.2"})
  with urllib.request.urlopen(req,timeout=16) as r:
   b=r.read(550000);ct=r.headers.get('Content-Type','');status=r.status
  out={"id":name,"http":status,"content_type":ct,"bytes":len(b),"elapsed_s":round(time.monotonic()-t,2)}
  try:
   j=json.loads(b)
   if isinstance(j,dict):
    out["keys"]=list(j)[:35]
    if name.startswith('princeton_') and name not in ('princeton_page','princeton_query'):
     out["fields"]={k:j.get(k) for k in ('objectid','displaytitle','classification','department','datebegin','dateend','maker','displaymaker','hasimage','nowebuse','restrictions','creditlinerepro','copyright','publicdomain','media','primaryimage') if k in j}
     if isinstance(out["fields"].get("media"),list):
      out["fields"]["media"]=out["fields"]["media"][:3]
    if name=='princeton_page':
     out["array_summaries"]={k:{"len":len(v),"first":str(v[0])[:600]} for k,v in j.items() if isinstance(v,list) and v}
    if name=='princeton_query':
     out["hits"]={k:str(v)[:400] for k,v in j.get('hits',{}).items()}
    if name.startswith('yale_lux'):
     out["data"]=str(j)[:1400]
    if name=='whitney':
     out["data"]=str(j)[:1600]
   elif isinstance(j,list):
    out["list_count"]=len(j);out["first"]=str(j[0])[:900] if j else ''
  except Exception as e:out["first_chars"]=b[:240].decode('utf-8','replace')
  return out
 except urllib.error.HTTPError as e:
  return {"id":name,"http":e.code,"error":str(e)[:140],"elapsed_s":round(time.monotonic()-t,2)}
 except Exception as e:return {"id":name,"error":str(e)[:140],"elapsed_s":round(time.monotonic()-t,2)}
with ThreadPoolExecutor(max_workers=4) as ex:
 tasks={ex.submit(probe,k,v):k for k,v in ENDPOINTS.items()}
 results={f.result()['id']:f.result() for f in as_completed(tasks)}
for k in ENDPOINTS:
 print('PROBE187 '+json.dumps(results[k],ensure_ascii=False,sort_keys=True)[:4300],flush=True)
