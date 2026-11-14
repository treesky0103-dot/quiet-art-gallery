#!/usr/bin/env python3
"""Rijksmuseum public Search API -> keyless OAI-DC rights/date/type -> IIIF decoded file trial.

Does NOT imply that every Dutch museum print is open or portrait, nor that a
found search index count is a verified image file. Maximum 125 object details,
14 actual image downloads, none paywalled or with forbidden licenses.
"""
import hashlib,io,json,re,time,xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode,quote,urlsplit
from urllib.request import Request,urlopen
from PIL import Image
OUT=Path("audit-rijks-actual-2d")
IMAGES=OUT/"samples";IMAGES.mkdir(parents=True,exist_ok=True)
SEARCH="https://data.rijksmuseum.nl/search/collection"
OAI="https://data.rijksmuseum.nl/oai"
UA="QuietArtGalleryArtProof/1.0 (Rijks public open data; https://github.com/treesky0103-dot/quiet-art-gallery)"
OAI_NS={"o":"http://www.openarchives.org/OAI/2.0/","dc":"http://purl.org/dc/elements/1.1/"}
TARGETS=[("print","18??"),("drawing","18??"),("print","19??"),("drawing","19??"),
         ("painting","18??"),("print","17??"),("drawing","17??"),("painting","17??")]
MAX_DETAILS=125
MAX_IMAGES=14
PAUSE=.20

def fetch(url,binary=False,timeout=29,cap=None):
    req=Request(url,headers={"User-Agent":UA,"Accept":"application/json,application/xml,image/jpeg,*/*"})
    with urlopen(req,timeout=timeout) as f:
        if f.status!=200:raise RuntimeError("HTTP "+str(f.status))
        blob=f.read((cap or (20*1024*1024 if binary else 3*1024*1024))+1)
        if len(blob)>(cap or (20*1024*1024 if binary else 3*1024*1024)):raise RuntimeError("Response over cap")
        return blob if binary else blob

def query_index(kind,century):
    url=SEARCH+"?"+urlencode({"type":kind,"creationDate":century,"imageAvailable":"true"})
    data=json.loads(fetch(url))
    ids=[]
    for x in data.get("orderedItems") or []:
        uri=x.get("id") or x.get("@id") or ""
        if re.fullmatch(r"https://id\.rijksmuseum\.nl/[0-9]+",uri):
            ids.append(uri)
    return ids,{"type":kind,"century":century,
        "reported_search_hits_not_images":(data.get("partOf") or {}).get("totalItems"),
        "first_page_ids":len(ids),"request":url}

def parse_record(uri):
    xml=fetch(OAI+"?"+urlencode({"verb":"GetRecord","identifier":uri,"metadataPrefix":"oai_dc"}))
    root=ET.fromstring(xml)
    ns=OAI_NS
    records=root.findall(".//o:record",ns)
    if not records:raise RuntimeError("No OAI record")
    node=records[0]
    vals=lambda tag:[(x.text or "").strip() for x in node.findall(".//dc:"+tag,ns) if (x.text or "").strip()]
    rights=vals("rights")
    joined_rights=" ".join(rights).lower()
    if not any(x in joined_rights for x in ("creativecommons.org/publicdomain/mark/",
         "creativecommons.org/publicdomain/zero/","rightsstatements.org/vocab/noc-")):
        return None,"nonpublic_rights"
    labels=" ".join(vals("type")).lower()
    if not any(x in labels for x in ("schilderij","tekening","prent","painting","drawing","print")):
        return None,"nonflat_object"
    if any(x in labels for x in ("fotografie","photograph","sculptuur","sculpture","installatie","film")):
        return None,"nonflat_object"
    dates=vals("date")
    if not dates:return None,"undated"
    # The OAI dc:date specifically refers to object creation date. Reject sources
    # with multiple-century straddles or ambiguous ranges; never use ingestion dates.
    numbers=[]
    for label in dates:
        numbers.extend(int(y) for y in re.findall(r"(?<![0-9])(?:1[5-9][0-9]{2}|20[0-2][0-9])(?![0-9])",label))
    if not numbers:return None,"unparsable_year"
    lo,hi=min(numbers),max(numbers)
    era="1800-2026" if lo>=1800 and hi<=2026 else "pre-1800" if hi<1800 else None
    if era is None:return None,"year_straddles_1800"
    image_urls=[x for x in vals("relation") if x.startswith("https://iiif.micr.io/")]
    if not image_urls:return None,"missing_official_iiif"
    return {"object_id":uri,"title":(vals("title") or [""])[0],
      "year_start":lo,"year_end":hi,"era":era,"type":labels,
      "rights":rights[:6],"relation_image":image_urls[0],"date_raw":dates[:4]},None

def good_portrait(w,h):
    try:w,h=int(w),int(h)
    except (ValueError,TypeError):return False
    return w>=1000 and h>=1400 and w<h and min((w/h)/.625,.625/(w/h))>=.75

def get_image(art):
    raw=art["relation_image"]
    parent=raw.split("?",1)[0].split("/full/",1)[0].removesuffix("/info.json").rstrip("/")
    if urlsplit(parent).hostname!="iiif.micr.io":raise ValueError("Non-Rijks source")
    info=json.loads(fetch(parent+"/info.json",cap=256*1024))
    w,h=info.get("width"),info.get("height")
    if not good_portrait(w,h):raise ValueError("Metadata image resolution/orientation")
    url=parent+"/full/!2400,2400/0/default.jpg"
    blob=fetch(url,binary=True,cap=20*1024*1024,timeout=40)
    with Image.open(io.BytesIO(blob)) as original:
        original.load()
        if original.format not in ("JPEG","PNG","WEBP") or not good_portrait(*original.size):
            raise ValueError("Actual image resolution/orientation")
        img=original.convert("RGB")
        if img.height>2400:
            img=img.resize((round(img.width*2400/img.height),2400),Image.Resampling.LANCZOS)
    buf=io.BytesIO();img.save(buf,"JPEG",quality=84,optimize=True)
    saved=buf.getvalue();sha=hashlib.sha256(saved).hexdigest()
    dest=IMAGES/(sha[:24]+".jpg")
    dest.write_bytes(saved)
    reopened=Image.open(dest);reopened.load()
    assert good_portrait(*reopened.size)
    assert hashlib.sha256(dest.read_bytes()).hexdigest()==sha
    return {"saved_file":str(dest),"sha256":sha,"source_sha256":hashlib.sha256(blob).hexdigest(),
       "saved_width":reopened.width,"saved_height":reopened.height,"saved_bytes":len(saved),
       "source_image_url":url}

def main():
    result={"source":"Rijksmuseum public official data / OAI + IIIF","queries":[],
      "object_details_examined":0,"eligible_object_metadata":0,
      "errors":[],"rejects":{},"actual_downloaded":[],"all_259200_verified":False}
    discovered=[];seen_uris=set()
    for kind,century in TARGETS:
        try:
            ids,report=query_index(kind,century)
            result["queries"].append({**report,"error":None})
            for uri in ids:
                if uri not in seen_uris:
                    discovered.append(uri);seen_uris.add(uri)
        except Exception as e:
            result["queries"].append({"type":kind,"century":century,"error":str(e)[:200]})
        time.sleep(.4)
    seen_sha=set()
    actual_era={"1800-2026":0,"pre-1800":0}
    for uri in discovered:
        if result["object_details_examined"]>=MAX_DETAILS:break
        if len(result["actual_downloaded"])>=MAX_IMAGES:break
        try:
            art,reason=parse_record(uri)
            result["object_details_examined"]+=1
            if reason:
                result["rejects"][reason]=result["rejects"].get(reason,0)+1;continue
            result["eligible_object_metadata"]+=1
            if actual_era[art["era"]]>=7:continue
            try:
                image=get_image(art)
                if image["sha256"] in seen_sha:
                    result["rejects"]["identical_byte_hash"] = result["rejects"].get("identical_byte_hash",0)+1
                    continue
                seen_sha.add(image["sha256"])
                actual_era[art["era"]]+=1
                result["actual_downloaded"].append({**art,**image,
                        "license":"Official OAI public-domain mark / CC0"})
                print("RIJKS_ACTUAL "+json.dumps({"files":len(result["actual_downloaded"]),
                         "era":art["era"],"object":art["object_id"],"bytes":image["saved_bytes"]},
                         ensure_ascii=False),flush=True)
            except Exception as e:
                result["rejects"]["image_"+str(e)[:50]]=result["rejects"].get("image_"+str(e)[:50],0)+1
        except Exception as e:
            if len(result["errors"])<20:result["errors"].append({"id":uri,"error":str(e)[:200]})
        time.sleep(PAUSE)
    result["actual_downloaded_count"]=len(result["actual_downloaded"])
    result["year_qualified_modern"]=actual_era["1800-2026"]
    result["year_qualified_old"]=actual_era["pre-1800"]
    (OUT/"report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("RIJKS_FINAL "+json.dumps({"queried":len(result["queries"]),
        "details_examined":result["object_details_examined"],
        "metadata_eligible":result["eligible_object_metadata"],
        "actual_verified_images":result["actual_downloaded_count"],
        "modern":result["year_qualified_modern"],"older":result["year_qualified_old"],
        "rejects":result["rejects"],"errors":result["errors"][:3],
        "all_259200_verified":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
