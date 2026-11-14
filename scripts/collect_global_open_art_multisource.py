#!/usr/bin/env python3
"""Multisource flat-art images beyond museum APIs: Commons, Openverse, US Library of Congress.

Search is deliberately broad; actual local file acquisition requires:
  * public accessible HTTPS URL from allowlisted art/CDN hosts
  * open/PD/CC0/CC-BY licensing metadata or repository open-use statement
  * no login, no age gate, no scraping, no access-control circumvention
  * JPEG/PNG/WEBP decode and uncropped >=1000x1400 with >=75% portrait screen fill
  * saved bytes SHA256 and title/original URL source identity uniqueness
  * no claim of pre-1800/1800+ if artwork creation year unknown.

Copyright-unknown and restricted search hits can be catalogued but not counted
as approved download records. SEARCH records are never counted as acquired JPEGs.
"""
from collections import Counter
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode,urlsplit
from PIL import Image,ImageOps
import csv,hashlib,io,ipaddress,json,os,re,socket,time
OUT=Path("audit-global-multisource-20261114")
JPG=OUT/"artworks"
JPG.mkdir(parents=True,exist_ok=True)
UA="QuietArtGallery/1.0 (public art archive verifier; https://github.com/treesky0103-dot/quiet-art-gallery)"
GOAL=60
MAX_DOWNLOAD_ATTEMPTS=125
MAX_IMAGE_BYTES=14*1024*1024
BLOCK=re.compile(r"(?:photograph of|photography|interior|museum room|gallery wall|framed|statue|sculpture|installation|exhibition view|3d render|photo of|collage of)",re.I)
OPEN_LICENSE={"cc0","pdm","pd","by","by-sa","cc-by","cc-by-sa"}
COMMONS_CATS=[
    "19th-century illustrations","20th-century illustrations",
    "21st-century illustrations","19th-century drawings",
    "20th-century drawings","19th-century prints","20th-century prints",
    "Japanese woodblock prints","Art Nouveau illustrations","Contemporary paintings"
]
OPENVERSE_TERMS=[
    "19th century botanical illustration","Japanese woodblock art print",
    "19th century portrait painting","19th century oil painting",
    "20th century abstract painting","original digital illustration",
    "watercolor painting artwork","art nouveau illustration",
    "vintage book illustration art","expressionist original artwork"
]
LOC_TERMS=[
    "watercolor drawing","woodcut print","lithograph",
    "illustration painting","poster art","fine art drawing"
]
ALLOWED_MEDIA_HOSTS={
    "upload.wikimedia.org","live.staticflickr.com","farm1.staticflickr.com",
    "farm2.staticflickr.com","farm3.staticflickr.com","farm4.staticflickr.com",
    "farm5.staticflickr.com","farm6.staticflickr.com",
    "farm7.staticflickr.com","farm8.staticflickr.com",
    "farm9.staticflickr.com","c1.staticflickr.com","c2.staticflickr.com",
    "tile.loc.gov","www.loc.gov","loc.gov","cdn.loc.gov",
    "iip.smk.dk","iip-thumb.smk.dk","images.metmuseum.org",
    "iiif.micr.io","ids.si.edu",
    "openaccess-cdn.clevelandart.org"
}
# Non-image source APIs must be exactly recognized; never fetch user-supplied arbitrary URIs.
ALLOWED_API={"api.openverse.org","commons.wikimedia.org","www.loc.gov"}

def check_https(url,api=False):
    p=urlsplit(str(url))
    if p.scheme!="https" or not p.hostname or p.username or p.password or p.port not in (None,443):
        raise ValueError("Unsafe scheme/authority")
    h=p.hostname.lower().rstrip(".")
    hosts=ALLOWED_API if api else ALLOWED_MEDIA_HOSTS
    if h not in hosts:raise ValueError("Not an approved public art source host: "+h)
    if re.match(r"^(?:[0-9.]+|\[)",h):raise ValueError("IP address prohibited")
    return str(url)

def request_json(url):
    check_https(url,api=True)
    req=Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
    with urlopen(req,timeout=27) as res:
        raw=res.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:raise ValueError("JSON larger than 4MiB")
    return json.loads(raw)

def image_blob(url):
    check_https(url)
    req=Request(url,headers={"User-Agent":UA,"Accept":"image/jpeg,image/png,image/webp"})
    with urlopen(req,timeout=27) as res:
        actual=urlsplit(res.geturl())
        if actual.scheme!="https" or actual.hostname not in ALLOWED_MEDIA_HOSTS:
            raise ValueError("Redirected to unknown media server")
        if res.status!=200:raise ValueError("Image HTTP status "+str(res.status))
        data=res.read(MAX_IMAGE_BYTES+1)
        if len(data)>MAX_IMAGE_BYTES:raise ValueError("Image exceeds bounded size")
        if res.headers.get("content-type","").split(";")[0].strip().lower() not in ("image/jpeg","image/png","image/webp","application/octet-stream"):
            raise ValueError("Nonimage content type")
    return data

def okay(w,h):
    try:w,h=int(w),int(h)
    except (ValueError,TypeError):return False
    if w<1000 or h<1400 or w>=h:return False
    return min((w/h)/.625,.625/(w/h))>=.75

def candidate(source,ident,title,image_url,license_code,work_url="",year_start=None,year_end=None):
    if not image_url or BLOCK.search(str(title)):return None
    if license_code not in OPEN_LICENSE:return None
    try:check_https(image_url)
    except (ValueError,TypeError):return None
    era="unknown"
    if year_start is not None and year_end is not None:
        try:
            a,b=int(year_start),int(year_end)
            if a<=b<=2026:era="1800plus" if a>=1800 else "older" if b<1800 else "unknown"
        except (ValueError,TypeError):pass
    return {"source":source,"id":str(ident),"title":str(title or "")[:220],
            "image_url":image_url,"work_url":work_url,
            "license":license_code,"year_start":year_start,"year_end":year_end,
            "era":era}

def from_openverse(term,page,stats):
    p={"q":term,"page":page,"page_size":40,"license":"cc0,pdm,by,by-sa","filter_dead":"true"}
    data=request_json("https://api.openverse.org/v1/images/?"+urlencode(p))
    found=data.get("results") or []
    stats["source_hits_openverse"]+=len(found)
    out=[]
    for obj in found:
        lic=str(obj.get("license") or "").lower()
        c=candidate("Openverse · "+str(obj.get("source") or "original"),
                    "ov:"+str(obj.get("id") or obj.get("url")),
                    obj.get("title") or "",obj.get("url") or "",
                    lic,obj.get("foreign_landing_url") or "")
        if c and okay(obj.get("width"),obj.get("height")):out.append(c)
    return out

def from_commons(cat,page,stats):
    q={"action":"query","generator":"search","gsrsearch":'deepcategory:"'+cat+'"',
       "gsrnamespace":6,"gsrlimit":40,"gsroffset":page*40,
       "prop":"imageinfo","iiprop":"url|size|mime|extmetadata","iiurlwidth":2100,
       "format":"json","formatversion":2}
    data=request_json("https://commons.wikimedia.org/w/api.php?"+urlencode(q))
    pages=((data.get("query") or {}).get("pages") or [])
    if not isinstance(pages,list):return []
    stats["source_hits_commons"]+=len(pages)
    output=[]
    for obj in pages:
        inf=((obj.get("imageinfo") or [{}])[0])
        if inf.get("mime") not in ("image/jpeg","image/png","image/webp"):continue
        meta=inf.get("extmetadata") or {}
        code=str((meta.get("LicenseShortName") or {}).get("value") or "").strip().lower()
        code=("cc0" if "cc0" in code or "public domain" in code else
              "pd" if code.startswith("pd") else
              "by-sa" if code.startswith("cc-by-sa") else
              "by" if code.startswith("cc-by") else "")
        im=inf.get("thumburl") or inf.get("url") or ""
        c=candidate("Wikimedia Commons · "+cat,str(obj.get("pageid")),
                    obj.get("title"),im,code,inf.get("descriptionurl") or "")
        if c and okay(inf.get("width"),inf.get("height")):output.append(c)
    return output

def parse_year_obj(v):
    if not v:return None,None
    dates=re.findall(r"(?<!\d)(1[5-9]\d\d|20[0-2]\d)(?!\d)",str(v))
    if not dates:return None,None
    nums=list(map(int,dates))
    return min(nums),max(nums)

def from_loc(term,page,stats):
    q={"fo":"json","q":term,"c":"50","sp":str(page),"at":"results,pagination"}
    data=request_json("https://www.loc.gov/photos/?"+urlencode(q))
    rows=data.get("results") or []
    stats["source_hits_loc"]+=len(rows)
    out=[]
    for row in rows:
        if not isinstance(row,dict):continue
        type_=" ".join(str(x) for x in (row.get("original_format") or []))
        if not re.search(r"\b(?:print|drawing|illustration|watercolor|watercolour|painting|poster|lithograph|etching)\b",type_,re.I):continue
        title=str(row.get("title") or "")
        rights=str(row.get("rights") or row.get("rights_information") or "").lower()
        # 'No known restrictions' is institution guidance, not a guarantee of PD worldwide;
        # treat other unknown as metadata only, not approved JPEG acquisition.
        if not any(t in rights for t in ("no known restrictions", "public domain", "no copyright")):continue
        images=row.get("image_url") or []
        if isinstance(images,str):images=[images]
        if not isinstance(images,list):continue
        imgs=[x for x in images if isinstance(x,str) and urlsplit(x).hostname in ALLOWED_MEDIA_HOSTS]
        if not imgs:continue
        img=imgs[-1]
        a,b=parse_year_obj(row.get("date") or row.get("created_published_date"))
        c=candidate("Library of Congress","loc:"+str(row.get("id") or ""),
                    title,img,"pd",row.get("id") or "",a,b)
        if c:out.append(c)
    return out

def save_one(item,state):
    raw=image_blob(item["image_url"])
    with Image.open(io.BytesIO(raw)) as orig:
        orig.load()
        if orig.format not in ("JPEG","PNG","WEBP"):return "format"
        if not okay(*orig.size):return "dimensions"
        pic=ImageOps.exif_transpose(orig).convert("RGB")
        if not okay(*pic.size):return "orientation"
        if pic.height>2400:
            pic=pic.resize((round(pic.width*2400/pic.height),2400),Image.Resampling.LANCZOS)
        assert okay(*pic.size)
        buff=io.BytesIO();pic.save(buff,"JPEG",quality=82,optimize=True,progressive=True)
        content=buff.getvalue()
    sha=hashlib.sha256(content).hexdigest()
    if sha in state["seen_sha"]:return "duplicate_hash"
    f=JPG/(sha[:24]+".jpg")
    f.write_bytes(content)
    with Image.open(f) as check:
        check.load()
        assert okay(*check.size)
        w,h=check.size
    assert hashlib.sha256(f.read_bytes()).hexdigest()==sha
    state["seen_sha"].add(sha)
    state["records"].append({**item,"sha256":sha,
        "source_sha256":hashlib.sha256(raw).hexdigest(),"file":str(f),
        "width":w,"height":h,"bytes":len(content)})
    return "saved"

def main():
    stats=Counter();attempts=0
    state={"seen_sha":set(),"records":[]}
    errors=[];candidates=[];seen_ids=set()
    blocked_api_providers=set()
    blocked_media_hosts=set()
    # Search many independent provider collections, not unlimited server scanning.
    tasks=([("commons",x,p) for x in COMMONS_CATS for p in (0,1)]
          +[("openverse",x,p) for x in OPENVERSE_TERMS for p in (1,2)]
          +[("loc",x,p) for x in LOC_TERMS for p in (1,2)])
    for kind,term,page in tasks:
        if kind in blocked_api_providers:
            stats["source_requests_safely_skipped_after_401_429"]+=1
            continue
        try:
            if kind=="commons": found=from_commons(term,page,stats)
            elif kind=="openverse": found=from_openverse(term,page,stats)
            else:found=from_loc(term,page,stats)
            stats["successful_source_requests"]+=1
            for obj in found:
                ident=(obj["source"],obj["id"])
                if ident in seen_ids:continue
                seen_ids.add(ident);candidates.append(obj)
        except Exception as e:
            stats["failed_source_requests"]+=1
            status=getattr(e,"code",None)
            if status in (401,429,503):
                blocked_api_providers.add(kind)
                stats["provider_access_paused_"+kind]+=1
            if len(errors)<35:errors.append({"kind":kind,"term":term,"page":page,"error":str(e)[:170]})
        time.sleep(.6)
    stats["qualified_candidate_records"]=len(candidates)
    # Distribute attempts across sources so a single library does not monopolize.
    by_source={"commons":[],"openverse":[],"loc":[]}
    for x in candidates:
        source=("commons" if x["source"].startswith("Wikimedia") else
                "openverse" if x["source"].startswith("Openverse") else "loc")
        by_source[source].append(x)
    schedule=[]
    length=max(len(v) for v in by_source.values()) if candidates else 0
    for k in range(length):
        for name in ("commons","openverse","loc"):
            if k<len(by_source[name]):schedule.append(by_source[name][k])
    attempts_seen=set()
    for item in schedule:
        if len(state["records"])>=GOAL or attempts>=MAX_DOWNLOAD_ATTEMPTS:break
        if item["image_url"] in attempts_seen:continue
        media_host=urlsplit(item["image_url"]).hostname
        if media_host in blocked_media_hosts:
            stats["media_downloads_skipped_after_429"]+=1
            continue
        attempts_seen.add(item["image_url"]);attempts+=1
        try:
            result=save_one(item,state)
            stats["image_"+result]+=1
            if result=="saved":
                print("GLOBAL_ACTUAL "+json.dumps({"n":len(state["records"]),
                  "source":item["source"],"era":item["era"],"bytes":state["records"][-1]["bytes"]},
                    ensure_ascii=False),flush=True)
        except Exception as e:
            stats["image_errors"]+=1
            if getattr(e,"code",None) in (429,503):
                blocked_media_hosts.add(media_host)
                stats["media_hosts_paused_due_to_rate_limit"]+=1
            if len(errors)<45:errors.append({"source":item["source"],
                "id":item["id"],"error":str(e)[:160]})
        time.sleep(.5)
    stats["actual_download_attempts"]=attempts
    counts=Counter(x["source"].split(" · ")[0] for x in state["records"])
    periods=Counter(x["era"] for x in state["records"])
    summary={"goal_90_day":259200,"new_sources":["Wikimedia Commons",
      "Openverse multi-origin art search","Library of Congress Prints/Drawings"],
      "source_request_count":len(tasks),"counters":dict(stats),
      "saved_actual_images":len(state["records"]),"by_source":dict(counts),
      "era_counts":dict(periods),"errors":errors,
      "actual_complete_259200":False,
      "limitations":[
       "Image bytes and pixel SHA256 actually checked; no cross-archive artwork identity proof.",
       "LoC no-known-restrictions is a US institutional rights statement, not worldwide PD assurance.",
       "Openverse or Commons source terms may describe reproductions of older paintings; unknown era stays unknown.",
       "Only allowlisted media hosts requested; private websites/premium archives not crawled.",
       "Archive files have limited GitHub Actions retention; not installed to Android tablet."
      ]}
    (OUT/"report.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    with (OUT/"verified_real_images.csv").open("w",newline="",encoding="utf-8") as f:
        fields=["source","id","title","image_url","work_url","license","year_start",
           "year_end","era","sha256","source_sha256","file","width","height","bytes"]
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(state["records"])
    print("GLOBAL_MULTISOURCE_FINAL "+json.dumps({
      "requests":len(tasks),"requests_ok":stats["successful_source_requests"],
      "metadata_candidates_not_acquired":len(candidates),
      "image_attempts":attempts,"actual_verified":len(state["records"]),
      "by_source":dict(counts),"eras":dict(periods),"all_259200_complete":False},
      ensure_ascii=False),flush=True)

if __name__=="__main__":main()
