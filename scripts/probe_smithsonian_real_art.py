#!/usr/bin/env python3
"""Verify Smithsonian SAAM/Cooper-Hewitt CC0 2-D art image files in bytes.

Creator dates/historical print dates need curation. Only explicit work-date >=1800
or <=1799 plus actual image bytes count as qualified.
"""
import io,hashlib,json,re,time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request,urlopen
from PIL import Image
OUT=Path("audit-smithsonian-actual")
SAMPLES=OUT/"samples"
SAMPLES.mkdir(parents=True,exist_ok=True)
AGENT="QuietArtGallery/1.0 (Smithsonian CC0 art verified imagery research; https://github.com/treesky0103-dot/quiet-art-gallery)"
BASE="https://smithsonian-open-access.s3-us-west-2.amazonaws.com/metadata/edan"
SHARDS=[("saam","00"),("saam","01"),("saam","02"),("chndm","00"),("chndm","01")]
MAX_FILES=12
def valid_screen(w,h):
    try:w=int(w);h=int(h)
    except (ValueError,TypeError):return False
    return w>=1000 and h>=1400 and w<h and min((w/h)/.625,.625/(w/h))>=.75
def type_ok(c):
    t=" ".join(x.get("content","") for x in ((c.get("freetext") or {}).get("objectType") or [])
               if isinstance(x,dict)).lower()
    if any(x in t for x in ("photograph","ceramic","furniture","sculpture",
       "textile","vessel","installation","video","glass","decorative object","poster for")):return False
    return any(x in t for x in ("painting","print","etching","drawing","watercolor",
                                "woodcut","engraving","illustration","lithograph","graphic arts"))
def explicit_date(c):
    values=[str(x.get("content") or "") for x in ((c.get("freetext") or {}).get("date") or []) if isinstance(x,dict)]
    if not values:return None
    value="; ".join(values)
    # Reject undated. If a source lists a publication date instead of creation
    # date, keep it as candidate rather than verified artwork-year evidence.
    if not value.strip() or re.search(r"\b(?:n\.d\.|undated|unknown|not dated)\b",value,re.I):return None
    years=[int(x) for x in re.findall(r"(?<!\d)(?:1[0-9]{3}|20[0-2][0-9])(?!\d)",value)]
    if not years:return None
    if re.search(r"\b(?:reprint|published|publication|reproduced|copy of)\b",value,re.I):return None
    lo,hi=min(years),max(years)
    era="1800-2026" if lo>=1800 and hi<=2026 else "pre-1800" if hi<=1799 else None
    if not era:return None
    return {"label":value[:120],"year_start":lo,"year_end":hi,"era":era}
def find_candidate(obj):
    if obj.get("type")!="edanmdm":return None
    c=obj.get("content") or {}
    dr=c.get("descriptiveNonRepeating") or {}
    if (dr.get("metadata_usage") or {}).get("access")!="CC0":return None
    if not type_ok(c):return None
    date=explicit_date(c)
    if not date:return None
    items=((dr.get("online_media") or {}).get("media") or [])
    for media in items:
        if media.get("type")!="Images" or (media.get("usage") or {}).get("access")!="CC0":continue
        if not valid_screen(media.get("width"),media.get("height")):continue
        identifier=str(media.get("idsId") or "")
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{3,140}",identifier):continue
        # Do not accept a different external host, JPEG rendition is from official IDS.
        u="https://ids.si.edu/ids/deliveryService?id="+quote(identifier,safe="")+"&max=2400"
        return {"id":obj.get("id"),"source_id":(dr.get("record_ID") or obj.get("url") or ""),
               "title":str((dr.get("title") or {}).get("content") or obj.get("title") or "")[:220],
               "source_url":dr.get("record_link") or "",
               "idsId":identifier,"image_url":u,"license":"CC0",
               "source_width":media.get("width"),"source_height":media.get("height"),
               "type":(c.get("freetext") or {}).get("objectType"),**date}
    return None
def download(url):
    r=Request(url,headers={"User-Agent":AGENT})
    with urlopen(r,timeout=28) as f:
        if f.status!=200:raise RuntimeError("Bad response: "+str(f.status))
        buf=f.read(16*1024*1024+1)
        if len(buf)>16*1024*1024:raise RuntimeError("File above 16 MiB")
        return buf
def main():
    result={"source":"Smithsonian Open Access SAAM/CHNDM",
      "shards":[],"candidates":0,"actual_downloaded":[],"errors":[],
      "completion_of_259200":False}
    candidates=[];seen_ids=set()
    for unit,num in SHARDS:
        url=f"{BASE}/{unit}/{num}.txt";total=0;qualified=0
        try:
            with urlopen(Request(url,headers={"User-Agent":AGENT}),timeout=45) as stream:
                for line in stream:
                    total+=1
                    if total>10000:break
                    try:obj=json.loads(line)
                    except (ValueError,TypeError):continue
                    art=find_candidate(obj)
                    if not art or art["source_id"] in seen_ids:continue
                    seen_ids.add(art["source_id"])
                    art["unit"]=unit
                    candidates.append(art)
                    qualified+=1
            err=None
        except Exception as e:
            err=str(e)[:210]
        result["shards"].append({"unit":unit,"part":num,"records_examined":total,
                                "metadata_qualified":qualified,"error":err})
        print("SMITHSONIAN_SOURCE "+json.dumps(result["shards"][-1],ensure_ascii=False),flush=True)
        time.sleep(.4)
    result["candidates"]=len(candidates)
    # Limit 6 images per era; this is not a full archive download.
    hashes=set()
    for period in ("1800-2026","pre-1800"):
        for art in (x for x in candidates if x["era"]==period):
            if len(result["actual_downloaded"])>=MAX_FILES:break
            if sum(x["era"]==period for x in result["actual_downloaded"])>=6:break
            try:
                raw=download(art["image_url"])
                im=Image.open(io.BytesIO(raw));im.load()
                if im.format not in ("JPEG","PNG","WEBP") or not valid_screen(*im.size):continue
                im=im.convert("RGB")
                if im.height>2400:im=im.resize((round(im.width*2400/im.height),2400),Image.Resampling.LANCZOS)
                b=io.BytesIO();im.save(b,"JPEG",quality=84,optimize=True)
                filebytes=b.getvalue();sha=hashlib.sha256(filebytes).hexdigest()
                if sha in hashes:continue
                dest=SAMPLES/(sha[:24]+".jpg")
                dest.write_bytes(filebytes)
                verify=Image.open(dest);verify.load()
                assert valid_screen(*verify.size)
                assert hashlib.sha256(dest.read_bytes()).hexdigest()==sha
                result["actual_downloaded"].append({**art,"sha256":sha,
                    "source_sha256":hashlib.sha256(raw).hexdigest(),
                    "width":verify.width,"height":verify.height,
                    "bytes":len(filebytes),"saved_file":str(dest)})
                hashes.add(sha)
                print("SMITHSONIAN_ACTUAL "+json.dumps({
                    "count":len(result["actual_downloaded"]),"era":period,
                    "sha256prefix":sha[:18],"bytes":len(filebytes)},ensure_ascii=False),flush=True)
            except Exception as e:
                if len(result["errors"])<30:result["errors"].append({"id":art["id"],"error":str(e)[:190]})
            time.sleep(.15)
    result["verified_byte_count"]=len(result["actual_downloaded"])
    result["verified_modern"]=sum(x["era"]=="1800-2026" for x in result["actual_downloaded"])
    result["verified_old"]=sum(x["era"]=="pre-1800" for x in result["actual_downloaded"])
    (OUT/"report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SMITHSONIAN_VERIFIED_FINAL "+json.dumps({
       "metadata_candidates":len(candidates),"file_bytes_verified":result["verified_byte_count"],
       "modern":result["verified_modern"],"old":result["verified_old"],
       "errors":result["errors"][:4],"complete":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
