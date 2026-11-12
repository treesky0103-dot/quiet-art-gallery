#!/usr/bin/env python3
"""Non-exhaustive, metadata-only Wikimedia Commons audit of 4 African museum painting collections."""
import datetime
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

SOURCES = {
    "iziko": ("이지코 남아공 국립미술관", "Paintings in the South African National Gallery"),
    "ethiopia": ("에티오피아 국립박물관", "Paintings in the National Museum of Ethiopia"),
    "zimbabwe": ("짐바브웨 국립미술관", "Paintings in the National Gallery of Zimbabwe"),
    "johannesburg": ("요하네스버그 미술관", "Paintings by Paul Signac in the Johannesburg Art Gallery"),
}
BAD = re.compile(r"gallery (?:interior|view|room)|museum (?:interior|hall|room)|exhibition (?:view|room|hall)|on (?:the )?wall|framed (?:painting|art)|sculpture|statue|installation|museum building|art gallery building|visitor|tour group|gallery entrance", re.I)
PD = {"public domain", "pd", "cc0", "cc0 1.0", "cc0 1.0 universal"}

def audit_one(name, category):
    params = {
      "action": "query", "generator": "search",
      "gsrsearch": 'deepcategory:"'+category+'"',
      "gsrnamespace": "6", "gsrlimit": "50", "gsroffset": "0",
      "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
      "iiurlwidth": "2000", "format": "json", "formatversion": "2"
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent":"QuietArtGallery/1.5 (https://github.com/treesky0103-dot/quiet-art-gallery; metadata-only audit)", "Accept":"application/json"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        obj=json.load(resp)
    pages=(obj.get("query") or {}).get("pages") or []
    status={"museum":name,"category":category,"pages_scanned":len(pages),
            "rights_2d_file_candidates":0,"size_metadata_pass":0,
            "actual_image_decoded":0,"known_small":0,"rejected_other":0,
            "sample_only":True,"exhaustive":False}
    for p in pages:
        images=p.get("imageinfo") or []
        if not images: status["rejected_other"]+=1; continue
        info=images[0];meta=info.get("extmetadata") or {}
        rights=str((meta.get("LicenseShortName") or {}).get("value","")).strip().lower()
        mime=info.get("mime")
        title=str(p.get("title",""))
        if rights not in PD or mime not in ("image/jpeg","image/png","image/webp") or BAD.search(title):
            status["rejected_other"]+=1; continue
        status["rights_2d_file_candidates"]+=1
        w=int(info.get("width") or 0);h=int(info.get("height") or 0)
        if min(w,h)>=1200 and max(w,h)>=1600: status["size_metadata_pass"]+=1
        else: status["known_small"]+=1
    return status

def main():
    results={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "disclaimer":"Metadata sample only, not the total playable artworks in each museum. Frame/photo image inspection not performed.",
             "sources":[]}
    for i,(k,(label,cat)) in enumerate(SOURCES.items()):
        try:
            row=audit_one(label,cat)
        except Exception as e:
            row={"museum":label,"category":cat,"error":f"{type(e).__name__}: {str(e)[:120]}","sample_only":True}
        print(k,json.dumps(row,ensure_ascii=False),flush=True)
        results["sources"].append(row)
        time.sleep(.3)
    Path("africa_audit_sample.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__ == "__main__":main()
