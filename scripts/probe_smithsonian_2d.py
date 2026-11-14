#!/usr/bin/env python3
"""Independent Smithsonian CC0 2D art discovery with image provenance; no automatic counts."""
import json,re,time
from pathlib import Path
from urllib.request import Request,urlopen
OUT=Path("audit-smithsonian-2d")
OUT.mkdir(exist_ok=True)
UA="QuietArtGallery/1.0 (Smithsonian open access inspection; https://github.com/treesky0103-dot/quiet-art-gallery)"
BASE="https://smithsonian-open-access.s3-us-west-2.amazonaws.com/metadata/edan"
SHARDS=[("saam","00"),("saam","01"),("saam","02"),("chndm","00"),("chndm","01")]
def type_allowed(item):
    c=item.get("content") or {}
    free=c.get("freetext") or {}
    obj=" ".join(x.get("content","") for x in free.get("objectType",[]) if isinstance(x,dict)).lower()
    if any(x in obj for x in ("photograph","sculpture","pottery","ceramic","jewelry",
            "textile","decorative object","furniture","glass","installation","sound","video")):return False
    return any(x in obj for x in ("print","drawing","painting","engraving",
       "etching","woodcut","lithograph","watercolor","illustration","poster"))
def year_hint(item):
    c=item.get("content") or {}
    fields=(c.get("freetext") or {}).get("date") or []
    raw=" ".join(x.get("content","") for x in fields if isinstance(x,dict))
    m=re.findall(r"\b(?:1[0-9]{3}|20[012][0-9])\b",raw)
    if not m:return {"raw":raw[:100],"era":"unknown"}
    numbers=[int(x) for x in m]
    if min(numbers)>=1800 and max(numbers)<=2026:return {"raw":raw[:100],"era":"1800plus"}
    if max(numbers)<1800:return {"raw":raw[:100],"era":"earlier"}
    return {"raw":raw[:100],"era":"unknown"}
def main():
    out={"shards":[],"sample_art":[],"files_verified":0,"full_259200_complete":False}
    for unit,shard in SHARDS:
        url=f"{BASE}/{unit}/{shard}.txt"
        recordcount=0;qualified=0;media=0;sample=[]
        try:
            req=Request(url,headers={"User-Agent":UA})
            with urlopen(req,timeout=50) as resp:
                if resp.status!=200:raise RuntimeError("HTTP "+str(resp.status))
                # Bounded streaming so no huge files or unnecessary bandwidth.
                for line in resp:
                    recordcount+=1
                    if recordcount>5000:break
                    try:x=json.loads(line)
                    except json.JSONDecodeError:continue
                    if x.get("type")!="edanmdm":continue
                    c=x.get("content") or {}
                    access=((c.get("descriptiveNonRepeating") or {}).get("metadata_usage") or {}).get("access")
                    if access!="CC0" or not type_allowed(x):continue
                    qualified+=1
                    online=(c.get("descriptiveNonRepeating") or {}).get("online_media") or {}
                    elements=online.get("media") or []
                    image=[m for m in elements if str(m.get("type","")).lower()=="images" and (m.get("content") or m.get("idsId"))]
                    if image:media+=1
                    if len(sample)<4 and image:
                        sample.append({"source":unit,"record":x.get("id"),
                             "object":(c.get("descriptiveNonRepeating") or {}).get("title"),
                             "date":year_hint(x),
                             "media":image[:2],"metadata_usage":access,
                             "objectType":(c.get("freetext") or {}).get("objectType")})
            result={"unit":unit,"shard":shard,"sampled_records":recordcount,"cc0_2d_kind":qualified,
                    "cc0_2d_with_media":media,"error":None}
            out["sample_art"]+=sample
        except Exception as e:
            result={"unit":unit,"shard":shard,"sampled_records":recordcount,
                    "cc0_2d_kind":qualified,"cc0_2d_with_media":media,
                    "error":str(e)[:170]}
        out["shards"].append(result)
        print("SMITHSONIAN_SHARD "+json.dumps(result,ensure_ascii=False),flush=True)
        time.sleep(.35)
    (OUT/"first_art_metadata.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SMITHSONIAN_FINAL "+json.dumps({"shards":len(out["shards"]),
        "sample_art_found":len(out["sample_art"]),"real_images_downloaded":0},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
