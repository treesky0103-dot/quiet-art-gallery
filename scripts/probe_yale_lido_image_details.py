#!/usr/bin/env python3
"""Check actual LIDO art/image/rights fields from Yale Centre for British Art via public OAI.
No image catalog counts are called acquired image bytes; source metadata only.
"""
import collections,json,re,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from xml.etree import ElementTree as ET
OUT=Path("audit-yale-lido-image-links")
OUT.mkdir(exist_ok=True)
BASE="https://harvester-bl.britishart.yale.edu/oaicatmuseum/OAIHandler"
UA="QuietArtGalleryYaleResearch/1.0 (public records; https://github.com/treesky0103-dot/quiet-art-gallery)"
NS={"o":"http://www.openarchives.org/OAI/2.0/","l":"http://www.lido-schema.org"}
IDS=[1000,10001,10002,10003,10006,10007,10010,10011,10012,10013]
def query(oid):
    q=urlencode({"verb":"GetRecord","identifier":f"oai:tms.ycba.yale.edu:{oid}","metadataPrefix":"lido"})
    req=Request(BASE+"?"+q,headers={"User-Agent":UA,"Accept":"application/xml"})
    with urlopen(req,timeout=35) as r:
        if r.status!=200:raise RuntimeError("HTTP "+str(r.status))
        b=r.read(3*1024*1024+1)
        if len(b)>3*1024*1024:raise RuntimeError("Yale LIDO XML 3 MB cap")
    return ET.fromstring(b)
def fields(node,tag,limit=12):
    arr=[]
    for x in node.findall(".//l:"+tag,NS):
        text=" ".join("".join(x.itertext()).split())
        if text and text not in arr:arr.append(text[:400])
        if len(arr)>=limit:break
    return arr
def links(root):
    ans=[]
    for row in root.findall(".//l:resourceSet",NS):
        ids=fields(row,"resourceID",4)
        urls=fields(row,"linkResource",4)
        rights=fields(row,"rightsType",6)+fields(row,"creditLine",4)
        resType=fields(row,"term",6)
        if urls or ids:
            ans.append({"ids":ids,"urls":urls,"rights":rights,"type":resType})
        if len(ans)>=12:break
    return ans
def main():
    report={"provider":"Yale Center for British Art LIDO OAI open metadata",
      "sample_ids":IDS,"records":[],"errors":[],"actual_image_files_downloaded":0,
      "artwork_259200_complete":False}
    for oid in IDS:
        try:
            root=query(oid)
            errors=fields(root,"error",5)
            row={"id":oid,"errors":errors,
                 "work_type":fields(root,"term",15),
                 "record_title":fields(root,"appellationValue",4),
                 "earliest_dates":fields(root,"earliestDate",12),
                 "latest_dates":fields(root,"latestDate",12),
                 "display_dates":fields(root,"displayDate",8),
                 "rights_terms":fields(root,"rightsType",10),
                 "images":links(root)}
            report["records"].append(row)
            print("YALE_LIDO_SAMPLE "+json.dumps({"id":oid,"titles":row["record_title"][:1],
               "date":row["display_dates"][:1],
               "resources":len(row["images"]),"links":sum(len(x["urls"]) for x in row["images"]),
               "rights":row["rights_terms"][:3]},ensure_ascii=False),flush=True)
        except Exception as e:
            report["errors"].append({"id":oid,"error":str(e)[:220]})
        time.sleep(.5)
    (OUT/"sample_lido_image_rights.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("YALE_LIDO_FINAL "+json.dumps({"records_retrieved":len(report["records"]),
      "errors":report["errors"],"image_file_count":0},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
