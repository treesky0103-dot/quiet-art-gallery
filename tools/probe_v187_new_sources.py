#!/usr/bin/env python3
"""Bounded real HTTP audit of *new* keyless candidate institutions.
Never bypass 403/429 or collect images without rights validation.
Each source gets at most one short metadata request. No authentication or paid services.
"""
import urllib.request, urllib.parse, json, concurrent.futures, time, re, hashlib
UA="QuietArtGalleryResearch/1.8.7 (personal non-commercial flat-art gallery; contact repository)"
probes={
 "princeton_search":"https://data.artmuseum.princeton.edu/search?q=watercolor&type=artobjects&size=3&from=0",
 "princeton_object":"https://data.artmuseum.princeton.edu/objects/9449",
 "princeton_list":"https://data.artmuseum.princeton.edu/objects?department=Prints%20and%20Drawings&size=2&from=0",
 "princeton_iiif_info":"https://media.artmuseum.princeton.edu/iiif/3/collection/x1954-13/info.json",
 "yale_lux":"https://lux.collections.yale.edu/api/search/object?q=%7B%22text%22%3A%22watercolor%22%7D",
 "yale_lux_sample":"https://lux.collections.yale.edu/api/search/object?q=%7B%22AND%22%3A%5B%7B%22hasDigitalImage%22%3A1%7D%2C%7B%22text%22%3A%22painting%22%7D%5D%7D",
 "quebec_mac":"https://www.donneesquebec.ca/recherche/dataset/6820a235-2658-4453-8a88-2d29618a4457/resource/3060f8cc-64f9-4853-b915-1c188bb825c1/download/oeuvres-mac-domaine-public-canada.json",
 "birmingham_wp":"https://www.artsbma.org/wp-json/wp/v2/search?search=painting&per_page=2",
 "cooperhewwitt_graphql":"https://api.cooperhewitt.org/?query=%7B%20__typename%20%7D",
 "national_library_scotland":"https://data.nls.uk/api/",
 "canadian_libraries":"https://www.canadiana.ca/iiif/presentation/v2/collection.json",
 "usc_public_art":"https://digitalcollections.library.gsu.edu/api/search?query=painting"
}
MAX=160000
def audit(pair):
 n,u=pair;beg=time.monotonic()
 try:
  req=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"application/json,application/ld+json,application/xml;q=0.9,*/*;q=0.3"})
  with urllib.request.urlopen(req, timeout=13) as r:
   ct=r.headers.get("Content-Type","")
   data=r.read(MAX+1)
   status=r.status
  obj={"name":n,"http":status,"content_type":ct,"bytes_read":len(data),"truncated":len(data)>MAX}
  try:
   j=json.loads(data)
   if isinstance(j,dict):
    obj["keys"]=list(j)[:38]
    for field in ("hits","results","items","objects","data","records","media","primaryimage","images","classification","restrictions","nowebuse","creditlinerepro","datebegin","dateend","hasimage","objectnumber","displaytitle","displaymaker","uri","total","numberOfItems","orderedItems","id","@id"):
     v=j.get(field)
     if v is not None:
      if isinstance(v,dict):obj[field+"_keys"]=list(v)[:14]
      elif isinstance(v,list):obj[field+"_len"]=len(v);obj[field+"_first"]=str(v[0])[:420] if v else ""
      else:obj[field]=str(v)[:280]
    for fld in ("_source","hits","results","items","objects","data","records"):
     v=j.get(fld)
     if isinstance(v,dict) and "hits" in v: v=v["hits"]
     if isinstance(v,list) and v and isinstance(v[0],dict):
      obj["record_keys"]=list(v[0])[:40]
      obj["record_subset"]={k:str(v[0].get(k))[:140] for k in ("objectid","id","_id","displaytitle","classification","nowebuse","restrictions","primaryimage","uri","medium","creditlinerepro","copyright","rights","license") if k in v[0]}
      break
   elif isinstance(j,list):
    obj["list_len"]=len(j)
    obj["first_keys"]=list(j[0])[:45] if j and isinstance(j[0],dict) else []
  except Exception as e:
   obj["preview"]=data[:155].decode("utf8","replace")
   obj["parse_error"]=str(e)[:95]
  obj["elapsed_s"]=round(time.monotonic()-beg,2)
  return obj
 except Exception as e:return {"name":n,"error":str(e)[:175],"elapsed_s":round(time.monotonic()-beg,2)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
 results={q["name"]:q for q in ex.map(audit,probes.items())}
for n in probes:print("SOURCE_V187 "+json.dumps(results[n],sort_keys=True,ensure_ascii=False),flush=True)
