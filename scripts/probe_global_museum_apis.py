#!/usr/bin/env python3
"""Public-only, no-auth probe for new global museum data and image gateways.

NOT a verified-image acquisition run; discovered metadata is reported separately.
No login, fees, paid services, CC claims, fake counts or image download.
"""
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from pathlib import Path
import json, time, re, xml.etree.ElementTree as ET
OUT=Path("audit-global-direct-apis")
OUT.mkdir(exist_ok=True)
UA="QuietArtGallery/1.0 (public collections research; https://github.com/treesky0103-dot/quiet-art-gallery)"
SOURCES=[
 ("SMK_open_search","https://api.smk.dk/api/v1/art/search/?"+urlencode({
      "keys":"*","filters":"[has_image:true],[public_domain:true]","offset":"0","rows":"3"}),"json"),
 ("SMK_simple_search","https://api.smk.dk/api/v1/art/search/?"+urlencode({
      "keys":"*","offset":"0","rows":"3"}),"json"),
 ("Smithsonian_SAAM_index","https://smithsonian-open-access.s3-us-west-2.amazonaws.com/metadata/edan/saam/index.txt","text"),
 ("Smithsonian_SAAM_00","https://smithsonian-open-access.s3-us-west-2.amazonaws.com/metadata/edan/saam/00.txt","ndjson"),
 ("Smithsonian_CHNDM_00","https://smithsonian-open-access.s3-us-west-2.amazonaws.com/metadata/edan/chndm/00.txt","ndjson"),
 ("Yale_British_Art_OAI","https://harvester-bl.britishart.yale.edu/oaicatmuseum/OAIHandler?verb=Identify","xml"),
 ("Yale_British_Art_OAI2","https://harvester-bl.britishart.yale.edu/oaicatmuseum/?verb=Identify","xml"),
 ("Rijksmuseum_OAI","https://data.rijksmuseum.nl/oai?verb=Identify","xml"),
 ("Getty_API_docs","https://data.getty.edu/","text"),
]
CAP=450000
def sample(url,kind):
    req=Request(url,headers={"User-Agent":UA,"Accept":"application/json,application/xml,text/plain,*/*"})
    with urlopen(req,timeout=24) as f:
        data=f.read(CAP)
        status=f.status
        typ=f.headers.get("content-type","")
    raw=data.decode("utf-8",errors="replace")
    output={"http_status":status,"content_type":typ,"sample_size_bytes":len(data)}
    if kind=="json":
        x=json.loads(raw)
        output["top_keys"]=list(x)[:25] if isinstance(x,dict) else []
        output["total_count_hint"]=x.get("found") or x.get("count") or x.get("total") if isinstance(x,dict) else None
        arr=x.get("items") or x.get("data") or x.get("results") or x.get("artworks") or [] if isinstance(x,dict) else []
        if isinstance(arr,dict):arr=list(arr.values())
        output["item_count"]=len(arr)
        output["first_2_items"]=arr[:2] if isinstance(arr,list) else []
    elif kind=="ndjson":
        firstline=raw.splitlines()[0] if raw.splitlines() else ""
        if len(firstline)<250000:
            x=json.loads(firstline)
            output["first_record"]=x
        output["partial_line_count"]=len(raw.splitlines())
    elif kind=="xml":
        root=ET.fromstring(raw)
        output["root_name"]=root.tag
        output["root_children"]=[x.tag for x in root][:12]
        output["head_xml"]=raw[:2800]
    else:
        output["head_text"]=raw[:4000]
    return output
def main():
    result={"date":"2026-11-14","intended":len(SOURCES),
           "results":[],"images_downloaded":0,
           "actual_259200_acquired":False}
    for name,url,kind in SOURCES:
        try:
            payload=sample(url,kind)
            status="ok"
            error=None
        except Exception as e:
            payload={}
            status="error"
            error=str(e)[:280]
        item={"source":name,"url":url,"kind":kind,"status":status,"error":error,
              "probe":payload}
        result["results"].append(item)
        print("SOURCE_PROBE "+json.dumps({"source":name,"status":status,
            "error":error,"fields":payload.get("top_keys"),"count_hint":payload.get("total_count_hint"),
            "kind":kind},ensure_ascii=False),flush=True)
        time.sleep(.5)
    (OUT/"source_probes.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SOURCE_PROBES_FINAL "+json.dumps({"attempts":len(SOURCES),
        "success":sum(x["status"]=="ok" for x in result["results"]),
        "downloaded_images":0,"complete":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
