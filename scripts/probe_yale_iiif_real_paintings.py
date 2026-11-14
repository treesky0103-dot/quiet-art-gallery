#!/usr/bin/env python3
"""Yale Center for British Art CC0 IIIF source->artwork exact production date->decoded portrait JPEG proof.

Do not mistake artist lifespan/exhibitions for production date, nor LIDO records
or IIIF manifests for actual downloaded images. 10 IDs only for bounded trial.
"""
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,urlopen
from xml.etree import ElementTree as ET
from PIL import Image
import hashlib,io,json,re,time
ROOT=Path("audit-yale-actual-2d")
SAMPLES=ROOT/"samples"
SAMPLES.mkdir(parents=True,exist_ok=True)
OAI="https://harvester-bl.britishart.yale.edu/oaicatmuseum/OAIHandler"
UA="QuietArtGalleryPublicArt/1.0 (public Yale IIIF research; https://github.com/treesky0103-dot/quiet-art-gallery)"
NS={"o":"http://www.openarchives.org/OAI/2.0/","l":"http://www.lido-schema.org"}
IDS=[1000,10001,10002,10003,10006,10007,10010,10011,10012,10013,10020,10021,10022,10023,10024,10025,10026,10027]
MAX_VERIFIED=12
def download(url,limit,timeout=35):
    domain=urlsplit(url).hostname
    if domain not in ("harvester-bl.britishart.yale.edu","manifests.collections.yale.edu",
                      "images.collections.yale.edu","images.ycba.yale.edu",
                      "iiif.collections.yale.edu"):
        raise ValueError("Unexpected Yale image host: "+str(domain))
    req=Request(url,headers={"User-Agent":UA,"Accept":"*/*"})
    with urlopen(req,timeout=timeout) as resp:
        if resp.status!=200:raise RuntimeError("HTTP "+str(resp.status))
        data=resp.read(limit+1)
        if len(data)>limit:raise RuntimeError("Exceeded per-file bytes")
        return data
def text(elem):
    if elem is None:return ""
    return " ".join("".join(elem.itertext()).split()).strip()
def elems(node,path):
    return node.findall(path,NS)
def year_production(root):
    years=[]
    for event in elems(root,".//l:eventSet/l:event"):
        kind=" ".join(text(x).lower() for x in elems(event,".//l:eventType/l:term"))
        if not ("production" in kind or "creation" in kind):continue
        lo=[text(x) for x in elems(event,".//l:eventDate/l:date/l:earliestDate")]
        hi=[text(x) for x in elems(event,".//l:eventDate/l:date/l:latestDate")]
        disp=[text(x) for x in elems(event,".//l:eventDate/l:displayDate")]
        def yr(v):
            v=str(v or "").strip()
            m=re.match(r"^(1[0-9]{3}|20[012][0-9])(?:$|[-\s])",v)
            return int(m.group(1)) if m else None
        if lo and hi:
            a=yr(lo[0]);b=yr(hi[0])
        else:
            a=b=yr(disp[0]) if disp else None
        if a is not None and b is not None and a<=b<=2026:years.append((a,b))
    if not years:return None
    a=min(x[0] for x in years);b=max(x[1] for x in years)
    if a>=1800:return {"era":"1800-2026","year_start":a,"year_end":b}
    if b<1800:return {"era":"pre-1800","year_start":a,"year_end":b}
    return None
def is_flat(root):
    terms=[text(x).lower() for x in elems(root,".//l:objectWorkType/l:term")]
    labels=" ".join(terms)
    if any(s in labels for s in ("photograph","sculpture","ceramic","glass","furniture","textile","coin")):return False
    return any(s in labels for s in ("painting","drawing","print","engraving","etching",
                                    "lithograph","watercolor","watercolour"))
def get_iiif_url(root):
    vals=[text(x) for x in elems(root,".//l:resourceSet//l:linkResource")]
    for v in vals:
        if v.startswith("https://manifests.collections.yale.edu/"):
            return v
    return None
def licensed(root):
    t=" ".join(text(x).lower() for x in elems(root,".//l:rightsType"))
    return ("public domain" in t and "creativecommons.org/publicdomain/zero/1.0" in t)
def year_info(x):
    man= x.get("sequences") or []
    for seq in man:
        for canvas in seq.get("canvases") or []:
            for img in canvas.get("images") or []:
                resource=img.get("resource") or {}
                svc=resource.get("service") or {}
                if isinstance(svc,list):svc=svc[0] if svc else {}
                url=svc.get("@id") or svc.get("id") or ""
                if url:
                    return url,canvas.get("width"),canvas.get("height")
    for canvas in x.get("items") or []:
        for ann in canvas.get("items") or []:
            for page in ann.get("items") or []:
                body=page.get("body") or {}
                svc=body.get("service") or []
                if isinstance(svc,dict):svc=[svc]
                for one in svc:
                    url=one.get("id") or one.get("@id")
                    if url:return url,canvas.get("width"),canvas.get("height")
    return None,None,None
def fits(w,h):
    try:w,h=int(w),int(h)
    except (ValueError,TypeError):return False
    return w>=1000 and h>=1400 and w<h and min((w/h)/.625,.625/(w/h))>=.75
def main():
    result={"actual_downloaded":[],"source_ids":IDS,"metadata_eligible":0,"skipped":[],"errors":[],
            "is_259200_acquired":False}
    seen_sha=set();per_era={"1800-2026":0,"pre-1800":0}
    for obj in IDS:
        if len(result["actual_downloaded"])>=MAX_VERIFIED:break
        try:
            u=OAI+"?"+urlencode({"verb":"GetRecord","identifier":f"oai:tms.ycba.yale.edu:{obj}","metadataPrefix":"lido"})
            root=ET.fromstring(download(u,4*1024*1024))
            if not licensed(root) or not is_flat(root):
                result["skipped"].append({"id":obj,"reason":"not_CC0_or_flat"});continue
            era=year_production(root)
            if era is None:
                result["skipped"].append({"id":obj,"reason":"no_unambiguous_production_year"});continue
            if per_era[era["era"]]>=6:continue
            manifest_url=get_iiif_url(root)
            if not manifest_url:
                result["skipped"].append({"id":obj,"reason":"missing_image_manifest"});continue
            result["metadata_eligible"]+=1
            manifest=json.loads(download(manifest_url,2*1024*1024))
            service,w,h=year_info(manifest)
            if not service or not fits(w,h):
                result["skipped"].append({"id":obj,"reason":"IIIF_manifest_missing_portrait_dimensions","dim":[w,h]});continue
            service=service.split("?",1)[0].removesuffix("/info.json").rstrip("/")
            uri=service+"/full/!2400,2400/0/default.jpg"
            original=download(uri,20*1024*1024)
            im=Image.open(io.BytesIO(original));im.load()
            if im.format not in ("JPEG","PNG","WEBP") or not fits(*im.size):
                result["skipped"].append({"id":obj,"reason":"actual_image_dims_failed","dimensions":im.size});continue
            im=im.convert("RGB")
            if im.height>2400:im=im.resize((round(im.width*2400/im.height),2400),Image.Resampling.LANCZOS)
            buf=io.BytesIO();im.save(buf,"JPEG",quality=84,optimize=True)
            blob=buf.getvalue();sha=hashlib.sha256(blob).hexdigest()
            if sha in seen_sha:continue
            file=SAMPLES/(sha[:24]+".jpg");file.write_bytes(blob)
            check=Image.open(file);check.load()
            assert fits(*check.size)
            assert hashlib.sha256(file.read_bytes()).hexdigest()==sha
            seen_sha.add(sha);per_era[era["era"]]+=1
            result["actual_downloaded"].append({
              "source":"Yale Center for British Art","artwork_id":obj,
              **era,"title":text(root.find(".//l:titleSet/l:appellationValue",NS)),
              "license":"Public Domain / CC0 from Yale LIDO",
              "manifest_url":manifest_url,"image_url":uri,
              "saved_file":str(file),"saved_sha256":sha,
              "source_sha256":hashlib.sha256(original).hexdigest(),
              "width":im.width,"height":im.height,"bytes":len(blob)})
            print("YALE_BYTE_VERIFIED "+json.dumps({"id":obj,"era":era["era"],
                "files":len(result["actual_downloaded"]),"bytes":len(blob)},ensure_ascii=False),flush=True)
        except Exception as e:
            if len(result["errors"])<30:result["errors"].append({"id":obj,"reason":str(e)[:220]})
        time.sleep(.35)
    result["real_files_verified"]=len(result["actual_downloaded"])
    (ROOT/"report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("YALE_FINAL "+json.dumps({"eligible_metadata":result["metadata_eligible"],
      "real_files_verified":result["real_files_verified"],
      "by_era":per_era,"skipped_count":len(result["skipped"]),"errors":result["errors"][:5],
      "completed_259200":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
