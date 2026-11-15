#!/usr/bin/env python3
"""One low-volume read-only discovery request per prospective new source.
No image is downloaded or counted as an exhibit-ready artwork.
"""
import urllib.request,urllib.parse,json,ssl,time
from concurrent.futures import ThreadPoolExecutor,as_completed

ENDPOINTS={
 "loc":"https://www.loc.gov/photos/?fo=json&c=2&sp=1",
 "loc_print":"https://www.loc.gov/pictures/?fo=json",
 "loc_poster":"https://www.loc.gov/posters/?fo=json&c=2&sp=1",
 "loc_free":"https://www.loc.gov/free-to-use/?fo=json&c=2&sp=1",
 "wellcome":"https://api.wellcomecollection.org/catalogue/v2/images?query=illustration&locations.license=cc0,pdm&pageSize=3",
 "wellcome_pdm":"https://api.wellcomecollection.org/catalogue/v2/images?locations.license=pdm&pageSize=2",
 "wellcome_cc0":"https://api.wellcomecollection.org/catalogue/v2/images?locations.license=cc0&pageSize=2",
 "finna":"https://api.finna.fi/v1/search?lookfor=painting&limit=2&field%5B%5D=id&field%5B%5D=title&field%5B%5D=images&field%5B%5D=onlineUrls&field%5B%5D=usageRights&field%5B%5D=year&field%5B%5D=nonPresenterAuthors",
 "digitalcommonwealth":"https://www.digitalcommonwealth.org/search.json?q=painting&per_page=2",
 "digitalcommonwealth_item":"https://www.digitalcommonwealth.org/search/commonwealth:abcd12345.json",
 "digitalnz":"https://api.digitalnz.org/records/v3.json?text=painting&per_page=2",
 "digitalnz2":"https://api.digitalnz.org/v3/records.json?text=painting&per_page=2",
 "internetarchive":"https://archive.org/advancedsearch.php?q=mediatype%3Aimage+AND+licenseurl%3A%28%22creativecommons.org%2Fpublicdomain%22%29&fl%5B%5D=identifier&rows=2&page=1&output=json",
 "vam":"https://api.vam.ac.uk/v2/objects/search?q=watercolour&page_size=2",
 "vam2":"https://api.vam.ac.uk/v2/objects/search?q=painting&page_size=2",
 "sciencemuseum":"https://collection.sciencemuseumgroup.org.uk/search/objects?q=poster&format=json",
 "cooperhewitt":"https://api.cooperhewitt.org/?query=%7B%20__typename%20%7D",
 "gallica":"https://gallica.bnf.fr/SRU?version=1.2&operation=searchRetrieve&query=dc.title%3Dpaint&maximumRecords=2",
 "japansearch":"https://jpsearch.go.jp/rdf/sparql?query=SELECT%20%28COUNT%28%2A%29%20AS%20%3Fn%29%20WHERE%20%7B%20%3Fs%20%3Fp%20%3Fo%20%7D%20LIMIT%201&format=json",
}
def probe(name,url):
 t=time.monotonic()
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"QuietArtGallery research audit/1.0 (+public open-data API discovery; one request per host)","Accept":"application/json,application/ld+json,application/xml;q=0.7,*/*;q=0.2"})
  with urllib.request.urlopen(req,timeout=13,context=ssl.create_default_context()) as r:
   data=r.read(180000)
   status=r.status
   ct=r.headers.get("Content-Type","")
  out={"source":name,"status":status,"content_type":ct,"response_bytes_read":len(data),"truncated":len(data)==180000,"elapsed_s":round(time.monotonic()-t,1)}
  if "json" in ct or data.lstrip().startswith((b"{",b"[")):
   try:
    j=json.loads(data)
    out["top_keys"]=list(j)[:26] if isinstance(j,dict) else ["array",len(j)]
    for k in ("results","records","items","data","response","pagination","aggregations","totalItems","totalPages","total","hits","pages","facets"):
     v=j.get(k) if isinstance(j,dict) else None
     if isinstance(v,list):
      out["list_"+k+"_count"]=len(v)
      if v:out["sample_"+k+"_keys"]=list(v[0])[:35] if isinstance(v[0],dict) else str(type(v[0]))
      if v and isinstance(v[0],dict):
       sample=v[0]
       out["sample_subset"]={k:str(sample.get(k))[:650] for k in ("id","title","image","image_url","image_url_full","image_url_s","images","thumbnail","locations","source","rights","rights_advisory","license","date","created","creators","imageURL","imageId","attributes","links","_images","_primaryImageId","_primaryTitle","_primaryMaker") if k in sample}
     elif isinstance(v,dict):
      out[k+"_keys"]=list(v)[:20]
      if k=="data":
       out["data_subset"]={kk:(list(vv)[:7] if isinstance(vv,dict) else str(vv)[:100]) for kk,vv in v.items()}
   except Exception as e:out["json_error"]=str(e)[:160]
  else:out["body_preview"]=data[:160].decode("utf-8","replace")
  return out
 except Exception as e:
  return {"source":name,"error":str(e)[:220],"elapsed_s":round(time.monotonic()-t,1)}
with ThreadPoolExecutor(max_workers=5) as ex:
 tasks={ex.submit(probe,n,u):n for n,u in ENDPOINTS.items()}
 results={f.result()["source"]:f.result() for f in as_completed(tasks)}
for k in ENDPOINTS:
 print("PROBE "+json.dumps(results[k],ensure_ascii=False,sort_keys=True),flush=True)
