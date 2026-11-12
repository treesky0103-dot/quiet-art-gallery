#!/usr/bin/env python3
"""One-page sample of seven museum collections via Wikimedia Commons; no full coverage claims."""
import json,time,urllib.parse,urllib.request
SOURCES={
"rijks":("암스테르담 국립미술관","Paintings in the Rijksmuseum Amsterdam"),
"nga":("미국 국립미술관","Paintings in the National Gallery of Art (Washington, D.C.)"),
"getty":("게티 미술관","Paintings in The J. Paul Getty Museum"),
"smk":("덴마크 국립미술관","Paintings in Statens Museum for Kunst"),
"paris":("파리 시립미술관 연합(카르나발레 박물관)","Paintings in Musée Carnavalet"),
"london":("런던 내셔널갤러리","Paintings in the National Gallery, London"),
"walters":("월터스 미술관","Paintings in the Walters Art Museum")
}
for key,(label,category) in SOURCES.items():
 params={"action":"query","generator":"search","gsrsearch":'deepcategory:"'+category+'"',"gsrnamespace":"6","gsrlimit":"20","gsroffset":"0","prop":"imageinfo","iiprop":"url|size|mime|extmetadata","iiurlwidth":"2000","format":"json","formatversion":"2"}
 url="https://commons.wikimedia.org/w/api.php?"+urllib.parse.urlencode(params)
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"QuietArtGallery/1.6 (https://github.com/treesky0103-dot/quiet-art-gallery; personal art display)","Accept":"application/json"})
  with urllib.request.urlopen(req,timeout=22) as resp: data=json.load(resp)
  pages=(data.get("query") or {}).get("pages",[])
  ok=0;small=0
  examples=[]
  for p in pages:
   i=(p.get("imageinfo") or [{}])[0]
   lic=str(((i.get("extmetadata") or {}).get("LicenseShortName") or {}).get("value","")).lower().strip()
   if lic in ("public domain","pd","cc0","cc0 1.0","cc0 1.0 universal") and i.get("mime") in ("image/jpeg","image/png","image/webp"):
    if min(i.get("width") or 0,i.get("height") or 0)>=1200 and max(i.get("width") or 0,i.get("height") or 0)>=1600:ok+=1
    else:small+=1
   if len(examples)<2:examples.append(p.get("title","")[:85])
  print(json.dumps({"source":key,"category":category,"pages":len(pages),"highres_public_metadata":ok,"small_public":small,"examples":examples,"error":data.get("error")},ensure_ascii=False),flush=True)
 except Exception as e:print(json.dumps({"source":key,"error":str(e)[:180]},ensure_ascii=False),flush=True)
 time.sleep(.2)
