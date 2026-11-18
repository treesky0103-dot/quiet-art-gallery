#!/usr/bin/env python3
"""Live metadata probe only; does not claim an APK or download artworks."""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request

CATEGORIES = {
    "louvre": "Paintings in the Louvre",
    "orsay": "Paintings in the Musée d'Orsay",
    "british": "Prints in the British Museum",
    "prado": "Paintings in the Museo del Prado",
    "hermitage": "Paintings in the Hermitage",
}
USER_AGENT = "QuietArtGallerySourceProbe/1.0 (+https://github.com/treesky0103-dot/quiet-art-gallery)"
def fetch(cat, offset=0):
    args = {
        "action": "query", "generator": "search",
        "gsrsearch": f'deepcategory:"{cat}"', "gsrnamespace": "6",
        "gsrlimit": "50", "gsroffset": str(offset), "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "2000",
        "format": "json", "formatversion": "2",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(args)
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json"
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200: raise RuntimeError(f"HTTP {response.status}")
        return json.load(response)
def eligible(info):
    if not info or info.get("mime", "").lower() not in ("image/jpeg","image/png","image/webp"): return False
    meta = info.get("extmetadata") or {}
    licence = re.sub("<[^>]*>", "", html.unescape((meta.get("LicenseShortName") or {}).get("value", ""))).strip().lower()
    lic = re.sub("<[^>]*>", "", html.unescape((meta.get("License") or {}).get("value", ""))).strip().lower()
    if not (licence in ("public domain", "pd", "cc0", "cc0 1.0", "cc0 1.0 universal") or lic in ("pd","cc0")):
        return False
    w,h=info.get("width",0),info.get("height",0)
    if min(w,h)<1000 or max(w,h)<1400 or w>=h:return False
    screen_ratio=1000/1600
    fill=min((w/h)/screen_ratio,screen_ratio/(w/h))
    return fill>=.75 and info.get("thumburl",info.get("url","")).startswith("https://upload.wikimedia.org/")
def main():
    # Bounded sample: twenty result pages per museum, never a full catalog count.
    sample_limit=1000
    ok=0
    for mid,category in CATEGORIES.items():
        pages_seen=set()
        qualifying=set()
        errors=[]
        requests=0
        for offset in range(0,sample_limit,50):
            try:
                data=fetch(category, offset)
                requests+=1
                if "error" in data:raise RuntimeError(str(data["error"])[:180])
                pages=(data.get("query") or {}).get("pages") or []
                if not pages:break
                for p in pages:
                    pid=p.get("pageid")
                    if pid in pages_seen:continue
                    pages_seen.add(pid)
                    info=(p.get("imageinfo") or [None])[0]
                    if eligible(info):qualifying.add(pid)
                if len(pages)<50:break
                time.sleep(.18)
            except Exception as exc:
                errors.append({"offset":offset,"error":str(exc)[:120]})
                break
        row={"museum":mid,"sampled_unique_files":len(pages_seen),
             "eligible_metadata":len(qualifying),"requests":requests,
             "errors":errors,"full_collection_count":"NOT_MEASURED"}
        print(json.dumps(row,ensure_ascii=False),flush=True)
        if len(pages_seen)>0:ok+=1
    print(f"Sources responding with image file search results: {ok}/5",flush=True)
    return 0 if ok==5 else 1
if __name__=="__main__": sys.exit(main())
