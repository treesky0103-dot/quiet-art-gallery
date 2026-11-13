#!/usr/bin/env python3
"""Evidence-first, bounded global-source audit for Quiet Art Gallery.
This is NOT a 259,200-image download and does not claim 90-day readiness.
Only confirmed downloaded, decoded and correctly licensed files may be called acquired.
"""
import concurrent.futures
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

DAYS=90
DAILY=2880
CYCLE=29
TOTAL=DAYS*DAILY
TARGET={str(i+1):TOTAL//CYCLE+(1 if i<TOTAL%CYCLE else 0) for i in range(CYCLE)}
USER_AGENT="QuietArtGalleryResearch/1.0 (metadata proof-of-concept; https://github.com/treesky0103-dot/quiet-art-gallery)"
MOVEMENTS=[
 ("renaissance","르네상스","Renaissance paintings"),
 ("baroque","바로크","Baroque paintings"),
 ("rococo","로코코","Rococo paintings"),
 ("neoclassicism","신고전주의","Neoclassical paintings"),
 ("romanticism","낭만주의","Romantic paintings"),
 ("realism","사실주의","Realist paintings"),
 ("impressionism","인상주의","Impressionist paintings"),
 ("post-impressionism","후기인상주의","Post-Impressionist paintings"),
 ("expressionism","표현주의","Expressionist paintings"),
 ("cubism","입체주의","Cubist paintings"),
 ("surrealism","초현실주의","Surrealist paintings"),
 ("abstract","추상미술","Abstract paintings"),
 ("contemporary","현대미술","Contemporary paintings"),
 ("asian","아시아 회화","Asian paintings"),
 ("african","아프리카 미술관 소장 회화","Paintings in African museums"),
 ("additional","세계 미술관 소장 회화","Paintings in museums"),
 ("modern","현대 디지털 아트·회화","Digital paintings"),
]
SPECIAL=[
 ("pulitzer","퓰리처상 수상 사진","photo",8),
 ("wpp","월드 프레스 포토","photo",3),
 ("sony","소니 월드 포토그래피 어워즈","photo",1),
 ("wildlife","올해의 야생동물 사진가","photo",1),
 ("prix","프리 픽테","photo",0),
 ("leica","라이카 오스카 바르낙 어워드","photo",2),
 ("magnum","매그넘 포토스","photo",0),
 ("ghibli","스튜디오 지브리","animation",100),
 ("nfaj","일본 국립영화아카이브","animation",3),
 ("pixar","픽사","animation",1),
 ("disney","월트 디즈니 애니메이션 스튜디오","animation",3),
 ("looney","루니 툰","animation",1),
]
MUSEUMS=[
 ("louvre","Paintings in the Louvre"),
 ("orsay","Paintings in the Musée d'Orsay"),
 ("british","Prints in the British Museum"),
 ("prado","Paintings in the Museo del Prado"),
 ("hermitage","Paintings in the Hermitage"),
]
# Official sources provide additional discovery options, not validated eligible counts.
OFFICIAL=[
 ("met","https://collectionapi.metmuseum.org/public/collection/v1.1/search?hasImages=true&q=painting&limit=1","total"),
 ("cleveland","https://openaccess-api.clevelandart.org/api/artworks/?limit=1&has_image=1&cc0=1","info.total"),
 ("chicago","https://api.artic.edu/api/v1/artworks?limit=1&fields=id,image_id,is_public_domain","pagination.total"),
 ("rijks","https://data.rijksmuseum.nl/search/collection?type=painting","unknown"),
]
OUT=Path("audit-global-90day")
OUT.mkdir(exist_ok=True)

def get(url, attempts=2, timeout=22):
    last=None
    for i in range(attempts):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status!=200: raise RuntimeError("HTTP "+str(r.status))
                return json.load(r)
        except Exception as e:
            last=e
            if i+1<attempts:time.sleep(1.0)
    raise last

def commons(category):
    base="https://commons.wikimedia.org/w/api.php?"
    data=get(base+urllib.parse.urlencode({
        "action":"query","generator":"search",
        "gsrsearch":'deepcategory:"'+category+'"',"gsrnamespace":"6","gsrlimit":"50",
        "prop":"imageinfo","iiprop":"size|mime|extmetadata|url",
        "iiurlwidth":"1600","format":"json","formatversion":"2"
    }))
    if "error" in data:raise RuntimeError(str(data["error"]))
    pages=(data.get("query") or {}).get("pages") or []
    eligible=[]
    for p in pages:
        info=(p.get("imageinfo") or [None])[0]
        if not info or info.get("mime","").lower() not in ("image/jpeg","image/png","image/webp"):continue
        meta=info.get("extmetadata") or {}
        short=re.sub("<[^>]*>","",html.unescape((meta.get("LicenseShortName") or {}).get("value",""))).strip().lower()
        license_code=re.sub("<[^>]*>","",html.unescape((meta.get("License") or {}).get("value",""))).strip().lower()
        if not (short in ("public domain","pd","cc0","cc0 1.0","cc0 1.0 universal") or license_code in ("pd","cc0")):continue
        w,h=info.get("width",0),info.get("height",0)
        if not w or not h or min(w,h)<1000 or max(w,h)<1400 or w>=h:continue
        ratio=(w/h)/(1000/1600)
        if min(ratio,1/ratio)<.75:continue
        image_url=info.get("thumburl") or info.get("url") or ""
        if not image_url.startswith("https://upload.wikimedia.org/"):continue
        eligible.append({"pageid":p.get("pageid"),"title":p.get("title"),"url":image_url,
                         "width":w,"height":h,"license":short or license_code})
    try:
        count=get(base+urllib.parse.urlencode({
            "action":"query","list":"search","srsearch":'deepcategory:"'+category+'"',
            "srnamespace":"6","srlimit":"1","srinfo":"totalhits","format":"json",
            "formatversion":"2"
        }))
        total_hits=(count.get("query") or {}).get("searchinfo",{}).get("totalhits")
    except Exception as e:
        total_hits=None
    return {"category":category,"first_page_files":len(pages),
            "first_page_eligible_metadata":len(eligible),
            "index_hits_unverified":total_hits,
            "sample_candidates":eligible}

def audit_task(x):
    kind,key,category=x
    try:
        d=commons(category)
        row={"kind":kind,"id":key,**d,"error":None}
    except Exception as e:
        row={"kind":kind,"id":key,"category":category,"error":str(e)[:220],
             "first_page_files":0,"first_page_eligible_metadata":0,
             "index_hits_unverified":None,"sample_candidates":[]}
    print(json.dumps({k:v for k,v in row.items() if k!="sample_candidates"},ensure_ascii=False),flush=True)
    return row

def official_probe(x):
    key,url,field=x
    try:
        data=get(url,attempts=1,timeout=18)
        value=data
        if field!="unknown":
            for token in field.split("."):value=value[token]
        else:value=None
        result={"id":key,"response_success":True,"returned_total_unverified":value,
                "count_scope":"API query only, NOT verified portrait CC0 art"}
    except Exception as e:
        result={"id":key,"response_success":False,"error":str(e)[:200]}
    print("OFFICIAL "+json.dumps(result,ensure_ascii=False),flush=True)
    return result

def download_sample(rows):
    try:from PIL import Image
    except ImportError:return {"verified_image_files":0,"errors":["Pillow unavailable"]}
    verified=[];errors=[]
    # Three pilot files maximum. Download bytes, decode, measure, hash; never conflate with metadata.
    for row in rows:
        if len(verified)>=3:break
        if row["kind"] not in ("movement","museum"):continue
        for item in row.get("sample_candidates",[]):
            try:
                req=urllib.request.Request(item["url"],headers={"User-Agent":USER_AGENT})
                with urllib.request.urlopen(req,timeout=25) as response:
                    blob=response.read(12*1024*1024+1)
                if len(blob)>12*1024*1024:raise ValueError("image exceeds 12MiB test cap")
                im=Image.open(io.BytesIO(blob))
                im.load()
                w,h=im.size
                if w>=h or w<1000 or h<1400:raise ValueError("downloaded resolution/portrait mismatch")
                aspect=(w/h)/(.625)
                if min(aspect,1/aspect)<.75:raise ValueError("portrait fill below 75%")
                ext=".png" if im.format=="PNG" else ".webp" if im.format=="WEBP" else ".jpg"
                dest=OUT/("verified_"+str(len(verified)+1)+ext)
                dest.write_bytes(blob)
                verified.append({"kind":row["kind"],"id":row["id"],"file":str(dest),
                                 "width":w,"height":h,"size_bytes":len(blob),
                                 "sha256":hashlib.sha256(blob).hexdigest(),
                                 "source_page_id":item["pageid"],"license":item["license"]})
                break
            except Exception as e:errors.append(str(e)[:100])
    return {"verified_image_files":len(verified),"files":verified,"errors":errors[:10]}

def main():
    assert len(MOVEMENTS)==17 and len(SPECIAL)==12
    assert len(TARGET)==29 and sum(TARGET.values())==TOTAL
    tasks=[("movement",key,cat) for key,label,cat in MOVEMENTS]+[("museum",key,cat) for key,cat in MUSEUMS]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        rows=list(pool.map(audit_task,tasks))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        official=list(pool.map(official_probe,OFFICIAL))
    samples=download_sample(rows)
    thirtyday=[];summary=[]
    for i in range(29):
        required=TARGET[str(i+1)]
        if i<17:
            key,label,cat=MOVEMENTS[i]
            matched=next(x for x in rows if x["kind"]=="movement" and x["id"]==key)
            sample_count=matched["first_page_eligible_metadata"]
            # Metadata-sample count is NOT acquired.
            acquired=0
            known=sample_count
            source_type="Wikimedia Commons category metadata (non-exhaustive)"
        else:
            key,label,kind,registered=SPECIAL[i-17]
            acquired=0;known=registered
            source_type="legacy candidate URL count, not downloaded/decoded"
        summary.append({"slot":i+1,"id":key,"label":label,"required_unique_90d":required,
             "known_candidates_non_verified":known,"acquired_verified":acquired,
             "gap_min_without_future_collection":required,"evidence":source_type})
    # The only acquired files are the at-most-three explicit decoded sample files.
    results={"required_90day":TOTAL,"categories":29,
         "all_29_ready":False,"actual_verified_downloads":samples["verified_image_files"],
         "note":"No 259200-image catalog was built. Metadata samples and object record totals are not images.",
         "slots":summary,"commons_samples":rows,"official_api_probes":official,
         "downloaded_sample_proof":samples}
    (OUT/"global_29_readiness.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"29_categories.csv").write_text(
        "slot,id,label,required_unique_90d,known_candidates_non_verified,acquired_verified\n"+
        "".join(f"{x['slot']},{x['id']},{x['label']},{x['required_unique_90d']},{x['known_candidates_non_verified']},{x['acquired_verified']}\n" for x in summary),
        encoding="utf-8")
    print("AUDIT_FINAL "+json.dumps({"required_90day":TOTAL,"categories":29,
        "all_29_ready":False,"actual_verified_downloads":samples["verified_image_files"],
        "commons_metadata_eligible_sample_total":sum(x["first_page_eligible_metadata"] for x in rows if x["kind"]=="movement"),
        "registered_photo_animation_candidates":sum(x[3] for x in SPECIAL)},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
