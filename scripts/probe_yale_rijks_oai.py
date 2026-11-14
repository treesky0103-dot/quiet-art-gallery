#!/usr/bin/env python3
"""Keyless Yale and Rijks OAI harvesting interface inspection (not acquired files)."""
import json,time,xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen

OUT=Path("audit-yale-rijks-oai")
OUT.mkdir(exist_ok=True)
UA="QuietArtGalleryPublicDataAudit/1.0 (https://github.com/treesky0103-dot/quiet-art-gallery)"
URLS={
 "Yale_Center_for_British_Art":"https://harvester-bl.britishart.yale.edu/oaicatmuseum/OAIHandler",
 "Rijksmuseum":"https://data.rijksmuseum.nl/oai"
}
NS={"o":"http://www.openarchives.org/OAI/2.0/"}
def request(base,verb,**kw):
    url=base+"?"+urlencode({"verb":verb,**kw})
    req=Request(url,headers={"User-Agent":UA,"Accept":"application/xml,text/xml"})
    with urlopen(req,timeout=42) as resp:
        body=resp.read(3*1024*1024+1)
        if len(body)>3*1024*1024:raise RuntimeError("XML response too large")
        if resp.status!=200:raise RuntimeError("HTTP "+str(resp.status))
    root=ET.fromstring(body)
    return root,url
def formats(base):
    root,_=request(base,"ListMetadataFormats")
    return [n.findtext("o:metadataPrefix",default="",namespaces=NS) for n in root.findall(".//o:metadataFormat",NS)]
def count_records(root,ns):
    data={}
    data["record_count_first_response"]=len(root.findall(".//o:record",ns))
    data["identifiers"]=len(root.findall(".//o:header",ns))
    data["resumption_token_present"]=bool(root.findtext(".//o:resumptionToken",default="",namespaces=ns))
    d=ET.tostring(root.find(".//o:record",ns),encoding="unicode")
    if root.find(".//o:record",ns) is not None else ""
    data["first_record_excerpt"]=d[:2600]
    data["error_entries"]=len(root.findall(".//o:error",ns))
    return data
def main():
    report={"sources":[],"actual_image_downloads":0,"complete_259200":False}
    for name,url in URLS.items():
        row={"name":name,"url":url}
        try:
            available=formats(url)
            row["formats"]=available
            preferred=next((x for x in ("lido","oai_lido","oai_dc","edm") if x in available),None)
            if preferred:
                root,request_url=request(url,"ListRecords",metadataPrefix=preferred)
                row.update(count_records(root,NS))
                row["first_records_url"]=request_url
                row["used_prefix"]=preferred
            else:row["error"]="No recognized harvest format"
        except Exception as e:
            row["error"]=str(e)[:220]
        report["sources"].append(row)
        print("OAI_SOURCE "+json.dumps({k:v for k,v in row.items() if k!="first_record_excerpt"},ensure_ascii=False),flush=True)
        time.sleep(.4)
    (OUT/"oai_formats_and_first_artwork.xml.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("OAI_FINAL "+json.dumps({"sources":len(report["sources"]),"downloaded_files":0,"complete":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
