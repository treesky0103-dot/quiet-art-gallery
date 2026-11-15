#!/usr/bin/env python3
import urllib.request,urllib.parse,json,ssl,time
def grab(url, maxbytes=500000):
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"QuietArtGalleryResearch/1.0 (public open art personal display)","Accept":"application/json,*/*"})
  with urllib.request.urlopen(req,timeout=13) as r:
   payload=r.read(maxbytes);code=r.status;ct=r.headers.get("Content-Type","")
  j=json.loads(payload)
  return {"http":code,"type":ct,"json":j}
 except Exception as e:return {"error":str(e)[:160]}
def show(label,url,cb):
 d=grab(url)
 if "json" not in d:print(label,json.dumps(d));return
 try:out=cb(d["json"]);print(label,json.dumps(out,ensure_ascii=False,default=str)[:6000])
 except Exception as e:print(label,json.dumps({"parse_error":str(e)})[:700])
show("LOC", "https://www.loc.gov/photos/?fo=json&c=3&sp=2",
 lambda x:[{k:row.get(k) for k in ("id","title","image_url","online_format","original_format","rights","rights_advisory","access_restricted","digitized","date","description","resources","reproductions")}for row in x.get("results",[])[:2]])
show("WELLCOME", "https://api.wellcomecollection.org/catalogue/v2/images?locations.license=pdm&pageSize=3",
 lambda x:[{k:row.get(k) for k in ("id","source","locations","aspectRatio")} for row in x.get("results",[])[:2]])
show("DC", "https://www.digitalcommonwealth.org/search.json?q=painting&per_page=2",
 lambda x:[{"id":row.get("id"),"attributes":{k:v for k,v in row.get("attributes",{}).items()if any(s in k.lower() for s in ["rights","thumbnail","image","genre","date","type","title","iiif","creator","url","license","url","digital"])},"links":row.get("links")}for row in x.get("data",[])[:2]])
show("VAM", "https://api.vam.ac.uk/v2/museumobject/O34799",
 lambda x:{"keys":list(x),"record":{k:v for k,v in x.get("record",{}).items()if any(s in k.lower() for s in ["rights","copyright","image","type","maker","title","date","medium","category","object"])}})
show("DIGITALNZ","https://api.digitalnz.org/v3/records.json?text=painting&per_page=2",
 lambda x:{"keys":list(x),"search":x.get("search",{})})
show("LOC_ITEM","https://www.loc.gov/item/2010651951/?fo=json",
 lambda x:{"keys":list(x),"item":{k:v for k,v in x.get("item",{}).items()if any(s in k.lower() for s in ["rights","image","format","date","title","medium","resources"])},"resources":x.get("resources",[])[:1]})
