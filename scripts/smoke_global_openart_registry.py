#!/usr/bin/env python3
"""Bounded live registry smoke-check for twelve worldwide open Commons categories.

Records provider hits and rights metadata only. No image files downloaded.
A Wikimedia category does not prove independent museums or creation years.
"""
import json,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
CATS=[
 ("p19","19th-century paintings"),("p20","20th-century paintings"),
 ("p21","21st-century paintings"),("d19","19th-century drawings"),
 ("d20","20th-century drawings"),("d21","21st-century drawings"),
 ("r19","19th-century prints"),("r20","20th-century prints"),
 ("r21","21st-century prints"),
 ("british-library","Illustrations from the British Library"),
 ("japanese-print","Japanese woodblock prints"),
 ("independent","Paintings by Wikipedians")]
REPORT=Path("audit-global-openart-registry")
REPORT.mkdir(exist_ok=True)
def probe(cid,cat):
    p={"action":"query","generator":"search","gsrsearch":'deepcategory:"'+cat+'"',
       "gsrnamespace":6,"gsrlimit":20,"gsroffset":0,
       "prop":"imageinfo","iiprop":"url|size|mime|extmetadata",
       "iiurlwidth":2000,"format":"json","formatversion":2}
    req=Request("https://commons.wikimedia.org/w/api.php?"+urlencode(p),
                headers={"User-Agent":"QuietArtGallery/1.0 (global art source validation; https://github.com/treesky0103-dot/quiet-art-gallery)",
                         "Accept":"application/json"})
    with urlopen(req,timeout=35) as f:
        data=json.load(f)
    pages=(data.get("query") or {}).get("pages") or []
    total=(data.get("query") or {}).get("searchinfo",{}).get("totalhits")
    if not isinstance(pages,list):raise ValueError("Unexpected Commons page structure")
    status={"id":cid,"category":cat,"returned_image_records":len(pages),
        "search_hits_unverified":total,"image_file_downloads":0}
    with_meta=0
    for page in pages:
        info=(page.get("imageinfo") or [{}])[0]
        if info.get("url") and info.get("width") and info.get("height"):
            with_meta+=1
    status["records_with_image_metadata"]=with_meta
    return status
def main():
    items=[]
    for cid,cat in CATS:
        try:r=probe(cid,cat);r["error"]=None
        except Exception as e:r={"id":cid,"category":cat,"returned_image_records":0,
             "records_with_image_metadata":0,"image_file_downloads":0,
             "error":str(e)[:230]}
        items.append(r)
        print("REGISTRY_SOURCE "+json.dumps(r,ensure_ascii=False),flush=True)
        time.sleep(1.1)
    j={"registered":len(CATS),"tested":len(items),"results":items,
       "sum_metadata_only":sum(i["records_with_image_metadata"] for i in items),
       "actually_downloaded_and_decoded":0,
       "all_servers_connected":False,"target_artwork_count_complete":False,
       "note":"Each item is a Wikimedia Commons public category, not an individually connected remote server."}
    (REPORT/"registry_smoke.json").write_text(json.dumps(j,ensure_ascii=False,indent=2),encoding="utf-8")
    print("REGISTRY_SMOKE_FINAL "+json.dumps({k:j[k] for k in
      ("registered","tested","sum_metadata_only","actually_downloaded_and_decoded",
       "all_servers_connected")},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
