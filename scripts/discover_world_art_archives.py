#!/usr/bin/env python3
"""Worldwide art-archive DISCOVERY, not completed image acquisition.

Sources: Wikimedia Commons category registry, Wikidata art museums with websites,
existing Quiet Art Gallery museum categories, and public archive API gateways.
This public-only, bounded tool records source provenance and verification status.
Do not claim "all museums" or count any catalogue entries as acquired images.
"""
import csv, hashlib, html, json, re, time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from audit_29_fields_90day import discover_repo_museum_categories, MUSEUMS

ROOT=Path("audit-global-archive-discovery")
ROOT.mkdir(exist_ok=True)
UA="QuietArtGalleryRegistry/1.0 (https://github.com/treesky0103-dot/quiet-art-gallery; academic open metadata audit)"
COMMONS="https://commons.wikimedia.org/w/api.php"
WIKIDATA="https://query.wikidata.org/sparql"
MAX_COMMONS_PER_PREFIX=1000
MAX_WIKIDATA=300

# Verified existence of the API documentation is NOT evidence of image rights or
# the availability of high-resolution images.
AGGREGATORS=[
 {"id":"commons","name":"Wikimedia Commons","url":"https://commons.wikimedia.org/w/api.php","kind":"federated","access":"no_key","status":"live_sampled","note":"Only per-file rights + image bytes qualify"},
 {"id":"wikidata","name":"Wikidata SPARQL","url":"https://query.wikidata.org/sparql","kind":"discovery","access":"no_key","status":"candidate_registry_only","note":"Institution records are not artwork files"},
 {"id":"met","name":"Metropolitan Museum of Art","url":"https://collectionapi.metmuseum.org/public/collection/v1","kind":"direct_museum_api","access":"no_key","status":"live_sampled","note":"isPublicDomain artwork flag required"},
 {"id":"cleveland","name":"Cleveland Museum of Art","url":"https://openaccess-api.clevelandart.org/api/artworks/","kind":"direct_museum_api","access":"no_key","status":"verified_image_sample","note":"CC0 share_license_status required"},
 {"id":"artic","name":"Art Institute of Chicago","url":"https://api.artic.edu/api/v1/artworks","kind":"direct_museum_api","access":"no_key","status":"live_sampled","note":"is_public_domain and image_id required"},
 {"id":"rijks","name":"Rijksmuseum Data Services","url":"https://data.rijksmuseum.nl/search/collection","kind":"direct_museum_api","access":"no_key","status":"live_search_only","note":"Linked Art identifiers must be resolved"},
 {"id":"getty","name":"Getty Museum Collection","url":"https://data.getty.edu/","kind":"direct_museum_api","access":"no_key_documentation","status":"docs_only","note":"Search API, rights and media need separate verification"},
 {"id":"vam","name":"Victoria and Albert Museum API","url":"https://api.vam.ac.uk/","kind":"direct_museum_api","access":"unknown","status":"docs_only","note":"Check actual terms and size"},
 {"id":"harvard","name":"Harvard Art Museums API","url":"https://harvardartmuseums.org/collections/api","kind":"direct_museum_api","access":"key_required_check_no_card","status":"docs_only","note":"Not connected, no key registered"},
 {"id":"smithsonian","name":"Smithsonian Open Access","url":"https://www.si.edu/openaccess/devtools","kind":"federated","access":"key_required_check_no_card","status":"docs_only","note":"Only CC0 media provided for eligible works"},
 {"id":"europeana","name":"Europeana","url":"https://api.europeana.eu/en","kind":"federated","access":"free_key_required","status":"docs_only","note":"Registration needed; rights differ per record"},
 {"id":"openverse","name":"Openverse","url":"https://api.openverse.org/v1/images/","kind":"federated","access":"no_key_low_volume","status":"existing_app_source","note":"Restrict source/license/artist/era"},
 {"id":"digitalnz","name":"DigitalNZ","url":"https://digitalnz.org/","kind":"federated","access":"key_required_check_no_card","status":"discovery_only","note":"Rights vary by supplying institution"},
 {"id":"loc","name":"Library of Congress","url":"https://www.loc.gov/apis/","kind":"federated","access":"no_key","status":"docs_only","note":"Most results not paintings; filter carefully"},
 {"id":"dpla","name":"Digital Public Library of America","url":"https://pro.dp.la/developers/api-codex","kind":"federated","access":"key_required_check_no_card","status":"docs_only","note":"Many image providers; no assumed download rights"},
 {"id":"parismusees","name":"Paris Musées Collections","url":"https://www.parismuseescollections.paris.fr/","kind":"museum_network","access":"not_verified","status":"discovery_only","note":"Metadata/image API not integrated"},
 {"id":"nationalgalleryuk","name":"National Gallery London","url":"https://www.nationalgallery.org.uk/paintings","kind":"direct_museum","access":"not_verified","status":"discovery_only","note":"Existing Commons category separately available"},
 {"id":"nga","name":"National Gallery of Art Washington","url":"https://www.nga.gov/open-access-policy.html","kind":"direct_museum","access":"no_key_downloads","status":"docs_only","note":"Public domain status and image dimensions to verify"},
 {"id":"smk","name":"Statens Museum for Kunst","url":"https://www.smk.dk/en/","kind":"direct_museum","access":"not_verified","status":"existing_commons_category","note":"Archive availability not proven by collection count"},
 {"id":"walters","name":"Walters Art Museum","url":"https://thewalters.org/","kind":"direct_museum","access":"not_verified","status":"existing_commons_category","note":"Existing Commons paintings category sampled"},
]

def api_json(url,accept="application/json",timeout=26):
    req=Request(url,headers={"User-Agent":UA,"Accept":accept})
    with urlopen(req,timeout=timeout) as r:
        if r.status!=200:raise RuntimeError("HTTP "+str(r.status))
        return json.load(r)

def discover_commons(prefix):
    records=[]
    cont=None
    loops=0
    while len(records)<MAX_COMMONS_PER_PREFIX and loops<3:
        args={"action":"query","list":"allcategories","acprefix":prefix,"aclimit":"500",
              "format":"json","formatversion":"2"}
        if cont:args["acfrom"]=cont
        body=api_json(COMMONS+"?"+urlencode(args))
        cats=((body.get("query") or {}).get("allcategories") or [])
        for a in cats:
            category=a.get("*") or a.get("category") or ""
            if not category:continue
            # Discovery only. Broad terms such as paintings in a room/city do not
            # become validated museum collections without further source checks.
            records.append(category)
        loops+=1
        next_=(body.get("continue") or {}).get("accontinue")
        if not next_ or len(records)>=MAX_COMMONS_PER_PREFIX:break
        cont=next_
        time.sleep(.35)
    return sorted(set(records)),loops

def discover_wikidata():
    query="""SELECT DISTINCT ?item ?itemLabel ?website ?countryLabel WHERE {
       ?item wdt:P31 wd:Q207694 .
       OPTIONAL { ?item wdt:P856 ?website . }
       OPTIONAL { ?item wdt:P17 ?country . }
       SERVICE wikibase:label { bd:serviceParam wikibase:language "en,ko". }
    } LIMIT 300"""
    body=api_json(WIKIDATA+"?"+urlencode({"query":query,"format":"json"}),
                  accept="application/sparql-results+json",timeout=40)
    rows=[]
    for x in (body.get("results") or {}).get("bindings") or []:
        def get(y):return ((x.get(y) or {}).get("value") or "").strip()
        uri=get("item")
        if not re.fullmatch(r"https?://www.wikidata.org/entity/Q\d+",uri):continue
        rows.append({"id":uri.rsplit("/",1)[-1],"name":get("itemLabel"),
                     "website":get("website"),"country":get("countryLabel"),
                     "source":"Wikidata","status":"discovered_unverified_images"})
    return rows

def main():
    existing,existing_total=discover_repo_museum_categories()
    for _,name in MUSEUMS:
        if not isinstance(name,str) or not name:raise RuntimeError("bad existing museum")
    corpus=[{"category":cat,"kind":kind,"status":"source_category_registered_not_all_images_verified"}
            for kind,ident,cat in existing]
    corpus+= [{"category":c,"kind":"existing_major_museum","status":"source_category_registered_not_all_images_verified"} for _,c in MUSEUMS]
    errors=[];prefix_sources=[]
    for prefix in ["Paintings in ","Paintings from ","Paintings at "]:
        try:
            results,pages=discover_commons(prefix)
            prefix_sources.append({"prefix":prefix,"discovered":len(results),"page_requests":pages})
            corpus.extend({"category":cat,"kind":"Wikimedia_allcategories",
                        "status":"discovered_unverified_images"} for cat in results)
        except Exception as e:
            errors.append({"provider":"Commons "+prefix,"error":str(e)[:190]})
        time.sleep(.4)
    unique={row["category"]:row for row in corpus}
    corpus=sorted(unique.values(),key=lambda x:x["category"])
    try:
        wikidata=discover_wikidata()
    except Exception as e:
        errors.append({"provider":"Wikidata SPARQL","error":str(e)[:190]})
        wikidata=[]
    with (ROOT/"candidate_commons_categories.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["category","kind","status"]);w.writeheader();w.writerows(corpus)
    with (ROOT/"candidate_wikidata_art_museums.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["id","name","website","country","source","status"]);w.writeheader();w.writerows(wikidata)
    (ROOT/"archive_provider_registry.json").write_text(json.dumps(AGGREGATORS,ensure_ascii=False,indent=2),encoding="utf-8")
    stats={
      "total_goal":259200,"goal_post1800":207360,"goal_other":51840,
      "guarantee_every_archive_in_world":False,
      "number_existing_source_categories":existing_total,
      "commons_category_queries":prefix_sources,
      "total_unique_commons_categories_discovered_or_registered":len(corpus),
      "wikidata_art_museum_records":len(wikidata),
      "archive_provider_adapters_or_gateways":len(AGGREGATORS),
      "provider_api_verified_downloaded_images_this_run":0,
      "actual_259200_images_acquired":False,
      "errors":errors,
      "limitations":[
         "Commons categories can represent regions/subjects, not just museums.",
         "Wikidata museum records cannot be counted as artworks or proven accessible archive endpoints.",
         "No private/paywalled archives, no guaranteed complete census of global archives.",
         "Only the 1800+/pre1800 artwork collector verifies image bytes and per-work metadata.",
         "Registered and discovered sources are not automatically live in installed Android v1.7.2."
      ]
    }
    (ROOT/"discovery_report.json").write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding="utf-8")
    print("DISCOVERY_FINAL "+json.dumps({
      k:stats[k] for k in ("total_goal","goal_post1800","goal_other",
            "number_existing_source_categories",
            "commons_category_queries",
            "total_unique_commons_categories_discovered_or_registered",
            "wikidata_art_museum_records","archive_provider_adapters_or_gateways",
            "actual_259200_images_acquired","errors")
    },ensure_ascii=False),flush=True)

if __name__=="__main__":main()
