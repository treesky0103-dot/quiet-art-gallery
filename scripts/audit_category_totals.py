#!/usr/bin/env python3
"""Fetch search-index hit counts from Wikimedia Commons for 16 existing gallery categories.

Counts are raw search records, not distinct legally eligible, 2D, high-res images.
They may be bounded by Wikimedia search engine limits and include duplicates.
"""
import concurrent.futures, json,urllib.parse,urllib.request
from pathlib import Path
sources=[
 ('asia-korea','Paintings in the National Museum of Korea'),('asia-tokyo','Japanese paintings in the Tokyo National Museum'),
 ('asia-kyoto','Paintings in the Kyoto National Museum'),('asia-nara','Paintings in the Nara National Museum'),
 ('asia-taipei','Paintings in the National Palace Museum'),
 ('africa-iziko','Paintings in the South African National Gallery'),
 ('africa-ethiopia','Paintings in the National Museum of Ethiopia'),
 ('africa-zimbabwe','Paintings in the National Gallery of Zimbabwe'),
 ('africa-johannesburg','Paintings by Paul Signac in the Johannesburg Art Gallery'),
 ('europe-rijks','Paintings in the Rijksmuseum Amsterdam'),
 ('us-nga','Paintings in the National Gallery of Art (Washington, D.C.)'),
 ('us-getty','Paintings in The J. Paul Getty Museum'),
 ('europe-smk','Paintings in Statens Museum for Kunst'),
 ('europe-paris','Paintings in Musée Carnavalet'),
 ('europe-london','Paintings in the National Gallery, London'),
 ('us-walters','Paintings in the Walters Art Museum')
]
def probe(it):
 name,cat=it
 q=urllib.parse.urlencode({"action":"query","list":"search","srsearch":'deepcategory:"'+cat+'"',
  "srnamespace":"6","srlimit":"1","format":"json","formatversion":"2"})
 req=urllib.request.Request("https://commons.wikimedia.org/w/api.php?"+q,headers={
  "User-Agent":"QuietArtGalleryCandidateTotals/1 (https://github.com/treesky0103-dot/quiet-art-gallery; counts only)",
  "Accept":"application/json"})
 try:
  with urllib.request.urlopen(req,timeout=25) as x:data=json.load(x)
  return {"source":name,"total_hits":(data.get("query") or {}).get("searchinfo",{}).get("totalhits"),
   "error":data.get("error"),"sample_one":len((data.get("query") or {}).get("search") or [])}
 except Exception as e:return {"source":name,"error":repr(e)[:180]}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:rows=list(ex.map(probe,sources))
for row in rows:print(json.dumps(row,ensure_ascii=False),flush=True)
Path("portrait_source_totals_20261113.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
