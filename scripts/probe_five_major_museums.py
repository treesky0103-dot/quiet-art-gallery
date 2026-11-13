#!/usr/bin/env python3
"""Live metadata probe only; does not claim an APK or download artworks."""
import html
import json
import re
import sys
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
def fetch(cat):
    args = {
        "action": "query", "generator": "search",
        "gsrsearch": f'deepcategory:"{cat}"', "gsrnamespace": "6",
        "gsrlimit": "50", "gsroffset": "0", "prop": "imageinfo",
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
    ok=0
    for mid,category in CATEGORIES.items():
        try:
            data=fetch(category)
            if "error" in data:raise RuntimeError(str(data["error"])[:180])
            pages=(data.get("query") or {}).get("pages") or []
            images=[p.get("imageinfo",[None])[0] for p in pages if p.get("imageinfo")]
            candidates=[x for x in images if eligible(x)]
            print(json.dumps({"museum":mid,"category":category,"pages":len(pages),"images":len(images),
                "eligible_metadata":len(candidates),"first_pageid":pages[0].get("pageid") if pages else None},ensure_ascii=False))
            if pages:ok+=1
        except Exception as exc:
            print(json.dumps({"museum":mid,"error":str(exc)[:200]},ensure_ascii=False))
    print(f"Sources responding with image file search results: {ok}/5")
    return 0 if ok==5 else 1
if __name__=="__main__": sys.exit(main())
