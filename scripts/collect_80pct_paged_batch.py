#!/usr/bin/env python3
"""Evidence-preserving paged batch of actual 1800+ flat-art image files.

This script does *not* pretend to acquire 259,200 images. It records
1800+ vs earlier creator dates, validates public downloadable flat artwork,
stores sample files, and refuses to count API results as downloaded files.
No login, no billing method, no paywall/DRM bypass.
"""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

OUT=Path("audit-80pct-batch")
IMAGES=OUT/"samples"
IMAGES.mkdir(parents=True, exist_ok=True)
CURRENT=2026
GOAL=259200
MODERN_GOAL=207360
EARLIER_GOAL=51840
assert MODERN_GOAL+EARLIER_GOAL==GOAL
AGENT="QuietArtGalleryGlobalArtAudit/1.1 (https://github.com/treesky0103-dot/quiet-art-gallery; research)"
MAX_DOWNLOAD=160
MAX_IMAGE_ATTEMPTS=500
ERA_SAMPLE_QUOTA={"1800-2026":128,"pre-1800":32}
MAX_FILE_BYTES=24*1024*1024
MIN_SHORT=1000
MIN_LONG=1400
ASPECT=1000/1600
MAXIMUM_CANDIDATE_RECORDS=3500
FIELDS=["source","id","title","artist","year_start","year_end","era","kind","rights","image_url","source_url","image_width","image_height","metadata_pass"]

def request(url, binary=False, timeout=28):
    req=Request(url,headers={"User-Agent":AGENT,"Accept":"*/*" if binary else "application/json"})
    with urlopen(req,timeout=timeout) as r:
        if r.status!=200:raise RuntimeError("HTTP "+str(r.status))
        if binary:
            blob=r.read(MAX_FILE_BYTES+1)
            if len(blob)>MAX_FILE_BYTES: raise ValueError("Exceeded 24MiB artwork cap")
            return blob
        return json.load(r)

def text(x):
    return str(x or "").strip()

def valid_year(y):
    if y is None or isinstance(y,bool):return None
    try:y=int(y)
    except (TypeError,ValueError):return None
    return y if -4000<=y<=CURRENT else None

def period(start,end):
    a=valid_year(start)
    b=valid_year(end)
    if a is None or b is None:return None
    if a>b:return None
    if a>=1800 and b<=CURRENT:return "1800-2026"
    if b<1800:return "pre-1800"
    return None  # Date ranges straddling 1800 cannot be counted toward either quota.

def good_kind(kind,medium=""):
    s=(text(kind)+" "+text(medium)).lower()
    deny=("photograph","sculpture","ceramic","vessel","textile","costume","jewelry","furniture",
          "installation","3d","video","film","postcard","manuscript","coin","book binding",
          "architectur","building","design object","artifact","album cover","poster for")
    if any(x in s for x in deny):return False
    yes=("painting","drawing","print","watercolor","watercolour","gouache",
         "etching","lithograph","woodcut","engraving","illustration",
         "works on paper","oil on canvas","oil on panel","ink on paper",
         "pastel on","acrylic on","silkscreen")
    return any(x in s for x in yes)

def image_fits(w,h):
    try:w,h=int(w),int(h)
    except (TypeError,ValueError):return False
    if w>=h or w<MIN_SHORT or h<MIN_LONG:return False
    ratio=(w/h)/ASPECT
    return min(ratio,1/ratio)>=0.75

def normalize(record):
    row={key:text(record.get(key)) for key in FIELDS}
    row["metadata_pass"]=bool(record.get("metadata_pass"))
    return row

def cleveland(era):
    # Official CMA docs: 'created_after', 'created_before', 'cc0', 'has_image', 'limit', 'skip'.
    args={"has_image":1,"limit":500,"skip":700,"created_before":1800 if era=="pre-1800" else CURRENT+1}
    if era=="1800-2026":args["created_after"]=1799
    url="https://openaccess-api.clevelandart.org/api/artworks/?"+urlencode(args)+"&cc0"
    data=request(url)
    records=[]
    for art in data.get("data",[]):
        st=art.get("creation_date_earliest")
        en=art.get("creation_date_latest")
        if st is None or en is None:continue
        when=period(st,en)
        if when!=era:continue
        kind=text(art.get("type"))
        med=text(art.get("technique"))
        if not good_kind(kind,med):continue
        if not art.get("share_license_status","").lower()=="cc0":continue
        images=art.get("images") or {}
        web=images.get("web") or {}
        display=images.get("print") or web
        original=images.get("full") or display
        image_url=(display.get("url") or web.get("url") or original.get("url") or "")
        if not image_url.startswith("https://"):continue
        image_dim=display
        records.append({"source":"Cleveland Museum of Art","id":art.get("id"),
            "title":art.get("title"),"artist":", ".join(x.get("description","") for x in (art.get("creators") or []) if isinstance(x,dict)),
            "year_start":st,"year_end":en,"era":when,"kind":kind,
            "rights":"CC0 (source metadata)","image_url":image_url,
            "source_url":art.get("url") or "", "image_width":image_dim.get("width"),
            "image_height":image_dim.get("height"),"metadata_pass":True})
    return records,{"reported_total_raw":(data.get("info") or {}).get("total"),"returned_records":len(data.get("data") or []),"request":url}

def artic(era):
    minimum=1800 if era=="1800-2026" else -4000
    maximum=CURRENT if era=="1800-2026" else 1799
    req={
      "resources":"artworks",
      "fields":["id","title","artist_title","date_start","date_end","date_display",
                "artwork_type_title","classification_title","medium_display","image_id",
                "is_public_domain","thumbnail","api_link","copyright_notice"],
      "query":{"bool":{"filter":[
         {"term":{"is_public_domain":True}},
         {"range":{"date_start":{"gte":minimum,"lte":maximum}}},
         {"range":{"date_end":{"gte":minimum,"lte":maximum}}},
         {"exists":{"field":"image_id"}}
       ]}},
      "limit":100,"page":7
    }
    url="https://api.artic.edu/api/v1/artworks/search?"+urlencode({"params":json.dumps(req,separators=(",",":"))})
    data=request(url)
    cfg=data.get("config") or {}
    iiif=(cfg.get("iiif_url") or "https://www.artic.edu/iiif/2").rstrip("/")
    records=[]
    for art in data.get("data") or []:
        when=period(art.get("date_start"),art.get("date_end"))
        if when!=era or art.get("is_public_domain") is not True:continue
        kind=text(art.get("artwork_type_title") or art.get("classification_title"))
        medium=text(art.get("medium_display"))
        if not good_kind(kind,medium):continue
        image_id=art.get("image_id")
        if not image_id:continue
        # For PD art, 1686px-wide IIIF file is allowed by the provider.
        image_url=iiif+"/"+quote(str(image_id),safe="")+"/full/1686,/0/default.jpg"
        records.append({"source":"Art Institute of Chicago","id":art.get("id"),
           "title":art.get("title"),"artist":art.get("artist_title"),"year_start":art.get("date_start"),
           "year_end":art.get("date_end"),"era":when,"kind":kind,
           "rights":"Public domain (source metadata)","image_url":image_url,
           "source_url":art.get("api_link"),"image_width":None,"image_height":None,"metadata_pass":True})
    return records,{"reported_total_raw":(data.get("pagination") or {}).get("total"),"returned_records":len(data.get("data") or []),"request":url}

def met(era):
    params={"q":"painting","medium":"Paintings","hasImages":"true",
            "dateBegin":1800 if era=="1800-2026" else 1,
            "dateEnd":CURRENT if era=="1800-2026" else 1799,
            "offset":700,"limit":80}
    url="https://collectionapi.metmuseum.org/public/collection/v1.1/search?"+urlencode(params)
    data=request(url)
    objects=data.get("objectIDs") or []
    records=[];tested=0;errors=0
    for oid in objects[:12]:
        try:
            art=request("https://collectionapi.metmuseum.org/public/collection/v1/objects/"+str(oid))
            tested+=1
        except Exception:
            errors+=1;continue
        when=period(art.get("objectBeginDate"),art.get("objectEndDate"))
        if when!=era or art.get("isPublicDomain") is not True:continue
        kind=text(art.get("classification"));medium=text(art.get("medium"))
        if not good_kind(kind,medium):continue
        image_url=text(art.get("primaryImage"))
        if not image_url.startswith("https://"):continue
        records.append({"source":"Metropolitan Museum of Art","id":oid,
          "title":art.get("title"),"artist":art.get("artistDisplayName"),
          "year_start":art.get("objectBeginDate"),"year_end":art.get("objectEndDate"),
          "era":when,"kind":kind or medium,"rights":"Public domain (source metadata)",
          "image_url":image_url,"source_url":art.get("objectURL"),
          "image_width":None,"image_height":None,"metadata_pass":True})
        time.sleep(.12)
    return records,{"reported_total_raw":data.get("total"),"returned_object_ids":len(objects),
                    "object_details_fetched":tested,"object_detail_errors":errors,"request":url}

def d_hash(image):
    from PIL import Image
    mono=image.convert("L").resize((9,8),Image.Resampling.LANCZOS)
    vals=list(mono.getdata())
    bits=0
    for y in range(8):
        for x in range(8):
            bits=(bits<<1)|int(vals[y*9+x]>vals[y*9+x+1])
    return f"{bits:016x}"

def download_verified(candidates):
    from PIL import Image
    by_source={}
    errors=[]
    seen_bytes=set();seen_phash=[]
    results=[]
    per_era={"1800-2026":0,"pre-1800":0}
    attempted=0
    for item in candidates:
        src=item["source"]
        if by_source.get(src,0)>=160 or len(results)>=MAX_DOWNLOAD:continue
        if item["era"] not in ERA_SAMPLE_QUOTA:continue
        if per_era[item["era"]]>=ERA_SAMPLE_QUOTA[item["era"]]:continue
        if len(results)>=MAX_DOWNLOAD or attempted>=MAX_IMAGE_ATTEMPTS:break
        attempted+=1
        try:
            blob=request(item["image_url"],binary=True,timeout=22)
            im=Image.open(io.BytesIO(blob))
            im.load()
            if im.format not in ("JPEG","PNG","WEBP"):raise ValueError("Not artwork image format")
            w,h=im.size
            if not image_fits(w,h):raise ValueError(f"Image {w}x{h} fails 75% portrait rule")
            sha=hashlib.sha256(blob).hexdigest()
            dh=d_hash(im)
            if sha in seen_bytes:raise ValueError("Byte duplicate")
            if any((int(dh,16)^int(old,16)).bit_count()<=5 for old in seen_phash):
                raise ValueError("Visually similar image detected")
            # Preserve validated source dimensions; cache portrait as a display-ready,
            # uncropped, optimized JPEG for 10GB tablets. Hash the actual saved bytes.
            im=im.convert("RGB")
            if im.height>2400:
                new_width=round(im.width*2400/im.height)
                im=im.resize((new_width,2400),Image.Resampling.LANCZOS)
            assert image_fits(*im.size), "Downsampled file fails display rule"
            encoded=io.BytesIO()
            im.save(encoded,format="JPEG",quality=84,optimize=True,progressive=True)
            saved=encoded.getvalue()
            output_hash=hashlib.sha256(saved).hexdigest()
            dest=IMAGES/(output_hash[:24]+".jpg")
            dest.write_bytes(saved)
            # Independently verify the bytes we actually persisted on disk.
            verification=Image.open(dest)
            verification.load()
            assert verification.format=="JPEG"
            assert image_fits(*verification.size)
            assert hashlib.sha256(dest.read_bytes()).hexdigest()==output_hash
            results.append({"source":src,"id":item["id"],"era":item["era"],
                "title":item["title"],"year_start":item["year_start"],
                "year_end":item["year_end"],"source_sha256":sha,
                "sha256":output_hash,"dhash":dh,"bytes":len(saved),
                "width":im.width,"height":im.height,"file":str(dest),
                "license":item["rights"],"source_url":item["source_url"],
                "original_width":w,"original_height":h})
            seen_bytes.add(sha);seen_phash.append(dh)
            by_source[src]=by_source.get(src,0)+1
            per_era[item["era"]]+=1
            print("VERIFIED "+json.dumps({"source":src,"era":item["era"],"width":w,"height":h,
                "sha256":sha[:16],"files":len(results)},ensure_ascii=False),flush=True)
        except Exception as e:
            if len(errors)<20:errors.append({"source":src,"id":item["id"],"error":str(e)[:100]})
    return results,errors

def test_unit():
    assert period(1800,1800)=="1800-2026"
    assert period(1799,1799)=="pre-1800"
    assert period(1799,1801) is None
    assert period(2027,2027) is None
    assert period(None,2010) is None
    assert good_kind("Painting","Oil on canvas")
    assert good_kind("Drawing","Ink")
    assert not good_kind("Sculpture","Bronze")
    assert not good_kind("Photograph","Gelatin silver")
    assert image_fits(1200,1800)
    assert not image_fits(1400,1000)
    assert not image_fits(400,800)
    assert not image_fits(1000,3000)
    assert GOAL==259200 and MODERN_GOAL/GOAL==0.8

def main():
    test_unit()
    sources=[("cleveland",cleveland),("artic",artic),("met",met)]
    candidates=[];steps=[]
    for era in ("1800-2026","pre-1800"):
        for name,fn in sources:
            try:
                rows,metadata=fn(era)
                candidates+=rows
                report={"source":name,"era":era,"metadata_candidates":len(rows),"error":None,**metadata}
            except Exception as e:
                report={"source":name,"era":era,"metadata_candidates":0,"error":repr(e)[:260]}
            steps.append(report)
            print("SOURCE "+json.dumps({k:v for k,v in report.items() if k!="request"},ensure_ascii=False),flush=True)
    # Per-source ID uniqueness, no evidence that similarly named cross-source works are distinct.
    ids=set();unique=[]
    for row in candidates[:MAXIMUM_CANDIDATE_RECORDS]:
        k=(row["source"],str(row["id"]))
        if k not in ids:unique.append(row);ids.add(k)
    verified,errors=download_verified(unique)
    with (OUT/"candidate_metadata_not_acquired.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
        for c in unique:w.writerow(normalize(c))
    with (OUT/"verified_downloaded_decoded.csv").open("w",encoding="utf-8",newline="") as f:
        if verified:
            w=csv.DictWriter(f,fieldnames=list(verified[0]));w.writeheader();w.writerows(verified)
    moderna=sum(x["era"]=="1800-2026" for x in verified)
    earlya=sum(x["era"]=="pre-1800" for x in verified)
    out={"target":{"all":GOAL,"modern_1800_to_2026":MODERN_GOAL,
                   "earlier_before_1800":EARLIER_GOAL,
                   "modern_percent":80},
         "actual_downloaded_decoded":{"all":len(verified),"modern":moderna,"earlier":earlya},
         "actual_90day_ready":False,
         "modern_shortfall":MODERN_GOAL-moderna,
         "earlier_shortfall":EARLIER_GOAL-earlya,
         "sources":steps,
         "metadata_candidates_not_acquired":len(unique),
         "download_errors_sample":errors,
         "limits":["Only page 7 / skip 700 was sampled; not entire museum collections.",
                   "Copyrighted and rights-uncertain images excluded from downloading.",
                   "No user tablet or production APK changed.",
                   "Year ranges crossing 1800 excluded rather than guessed.",
                   "Image hashes detect only exact and obvious perceptual duplicates.",
                   "Proof files saved to GitHub Actions artifacts, not to user's tablet."]}
    (OUT/"audit_report.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("AUDIT_FINAL "+json.dumps({k:out[k] for k in
       ("target","actual_downloaded_decoded","actual_90day_ready",
        "metadata_candidates_not_acquired","modern_shortfall","earlier_shortfall")},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
