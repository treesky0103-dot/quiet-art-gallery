#!/usr/bin/env python3
"""Extend exactly verified 1511-asset APK with additional 2D museum art.

Searchable taxonomy and the 50 requested sites are separately registered, but
source-catalog registration does not prove artwork acquisition. Image ingestion
uses the Cleveland Museum of Art public CC0 API; pre-existing Commons/Openverse
search remains in WebView. Old 1511 ZIP JPEGs are copied unchanged. Each new
unique source must be downloaded, decoded, smart-portrait transformed, written,
reopened and SHA256 checked before counting or releasing the new APK.
"""
import collections,concurrent.futures,hashlib,io,json,re,time,zipfile
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from PIL import Image,ImageOps

from build_886_adapted_deck import smart_portrait

ROOT=Path("android-app/app/src/main/assets")
IMG=ROOT/"offline"
DECK=ROOT/"offline-deck.json"
PREVIOUS=Path("QuietArtGallery-Contemporary-Street-Graffiti-v176.apk")
PREVIOUS_SHA256="73c539f14ffef2eafa1608c86c1c2260f4277646153cfda75fcc1df00570df17"
MOVEMENTS=Path("data/requested_art_movements_20261114.json")
SOURCES=Path("data/50_requested_art_sources_20261114.json")
OUT=Path("build-global-movement-report.json")
MAX_ADDED=550
MAX_TOTAL=2700
MAX_BYTES=760*1024*1024
MAX_INPUT=16*1024*1024
UA="QuietArtGalleryOpenAccessArchive/1.8 (personal offline viewer; source attribution)"
IMG_HOST="openaccess-cdn.clevelandart.org"
API_HOST="openaccess-api.clevelandart.org"
Image.MAX_IMAGE_PIXELS=45_000_000

def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def file_sha(fp):
    h=hashlib.sha256()
    with fp.open('rb') as stream:
        for chunk in iter(lambda:stream.read(2*1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def fetch(url, maxbytes=MAX_INPUT, timeout=24):
    u=urlsplit(url)
    if u.scheme!='https' or u.hostname not in (IMG_HOST,API_HOST) or u.port not in (None,443) or u.username:
        raise ValueError("Not an authorized CMA source host")
    req=Request(url,headers={"User-Agent":UA,"Accept":"image/jpeg,image/png,image/webp,application/json"})
    with urlopen(req,timeout=timeout) as r:
        redirect=urlsplit(r.geturl())
        if redirect.hostname not in (IMG_HOST,API_HOST) or r.status!=200:
            raise ValueError("Unexpected image/metadata redirect or HTTP result")
        if r.headers.get('Content-Length') and int(r.headers['Content-Length'])>maxbytes:
            raise ValueError("Source exceeds size cap")
        blob=r.read(maxbytes+1)
        if len(blob)>maxbytes:raise ValueError("Source exceeds download cap")
        return blob

def restore_exact_source_apk():
    if not PREVIOUS.is_file() or file_sha(PREVIOUS)!=PREVIOUS_SHA256:
        raise RuntimeError("Published v1.7.6 source APK does not match immutable SHA256")
    IMG.mkdir(parents=True,exist_ok=True)
    for orphan in IMG.glob("pack-*.jpg"):orphan.unlink()
    with zipfile.ZipFile(PREVIOUS) as z:
        if z.testzip() is not None:raise IOError("Published APK CRC error")
        rows=json.loads(z.read("assets/offline-deck.json"))
        if len(rows)!=1511:raise AssertionError("Prior APK must have 1511 image files")
        types=collections.Counter(x.get('type') for x in rows)
        required={'Painting':886,'Photograph':600,'Animation Still':24,'Contemporary Art':1}
        if dict(types)!=required:raise AssertionError('Original artwork types changed '+str(types))
        for idx,art in enumerate(rows):
            name="offline/pack-%04d.jpg"%idx
            if art.get('offlineAsset')!=name:raise AssertionError("Original artwork file path altered")
            raw=z.read("assets/"+name)
            if sha_bytes(raw)!=art["derivedSHA256"]:
                raise AssertionError("Original published artwork SHA mismatch "+name)
            (ROOT/name).write_bytes(raw)
    print("VERIFIED_PREVIOUS_APK_1511_UNALTERED",dict(types),flush=True)
    return rows

def load_registry():
    catalog=json.loads(MOVEMENTS.read_text(encoding="utf-8"))
    sources=json.loads(SOURCES.read_text(encoding="utf-8"))
    terms=[m for g in catalog["groups"] for m in g["movements"]]
    assert catalog["entry_count"]==len(terms) and len(terms)>=375
    assert sources["requested_source_entries"]==50 and len(sources["entries"])==50
    assert sources["unique_source_names"]>=45
    aliases={}
    for m in terms:
        q=m.get('search_en')
        if q:
            key=q.casefold().strip()
            aliases.setdefault(key,[]).append(m['name_ko'])
    return catalog,sources,aliases

def year(d):
    try:
        n=int(d)
        return n if 0<n<=2026 else None
    except (TypeError,ValueError):return None

def candidate_sets():
    # Search 1800+ across visual type instead of just the first 100 museum
    # records. Official CC0 license is checked in every individual result.
    plans=[
      ("Painting",list(range(0,1400,100)),1799),
      ("Drawing",list(range(0,900,100)),1799),
      ("Print",list(range(0,1000,100)),1799),
      ("Photograph",list(range(500,1200,100)),1799)
    ]
    pools={k:[] for k,_,_ in plans}
    failed=[]
    for type_name,offsets,earliest in plans:
        for off in offsets:
            opts={'has_image':'1','type':type_name,'created_after':str(earliest),
                  'limit':'100','skip':str(off),'cc0':''}
            url='https://'+API_HOST+'/api/artworks/?'+urlencode(opts)
            try:
                raw=fetch(url,4*1024*1024,20)
                data=json.loads(raw)
                results=data.get('data') or []
            except Exception as e:
                failed.append(type_name+":"+str(off)+" "+str(e)[:85])
                print("MUSEUM_API_SKIP",type_name,off,type(e).__name__,flush=True)
                continue
            if not isinstance(results,list):continue
            count=0
            for doc in results:
                if not isinstance(doc,dict) or str(doc.get('share_license_status','')).casefold()!='cc0':continue
                real_type=str(doc.get('type') or '').casefold()
                if real_type!=type_name.casefold():continue
                img=(doc.get('images') or {}).get('print') or (doc.get('images') or {}).get('web') or {}
                image_url=str(img.get('url') or '')
                if urlsplit(image_url).hostname!=IMG_HOST:continue
                title=str(doc.get('title') or '').strip()
                if not title:continue
                ident=str(doc.get('id') or '')
                if not ident.isdigit():continue
                if re.search(r"\b(?:sculpture|furniture|glass vase|ceramic vessel|photo of museum interior)\b",title,re.I):continue
                creators=doc.get('creators') or []
                artist=", ".join(x.get('description','') for x in creators if isinstance(x,dict))[:140] or "작가 미상"
                styles=doc.get('style_titles') or []
                style=str(doc.get('style') or '')
                if isinstance(styles,list):
                    style_evidence=[x for x in styles if isinstance(x,str)]
                else:style_evidence=[]
                if style and style not in style_evidence:style_evidence.insert(0,style)
                pools[type_name].append({
                  'key':'cma:'+ident,'id':ident,'source':'Cleveland Museum of Art',
                  'url':image_url,'title':title[:180],'artist':artist,
                  'type':type_name,'rightsOK':True,'license':'CC0',
                  'yearStart':year(doc.get('creation_date_earliest')),
                  'yearEnd':year(doc.get('creation_date_latest')),
                  'style_evidence':style_evidence[:5],
                  'page':str(doc.get('url') or 'https://www.clevelandart.org/art/'+ident)
                });count+=1
            print("MUSEUM_METADATA",type_name,off,"rows",len(results),"eligible",count,flush=True)
            if len(results)<75:break
    print("MUSEUM_METADATA_TOTAL",str({k:len(v) for k,v in pools.items()}),"errors",len(failed),flush=True)
    return pools,failed

def encode_row(row):
    try:
        raw=fetch(row['url'],MAX_INPUT,28)
        source_sha=sha_bytes(raw)
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            if image.format not in ('JPEG','PNG','WEBP'):raise ValueError('Not a static image')
            width,height=ImageOps.exif_transpose(image).size
            jpeg,box,factor,original=smart_portrait(image)
        derived_sha=sha_bytes(jpeg)
        return {
          'key':row['key'],'source':row['source'],
          'title':row['title'],'artist':row['artist'],'image':'',
          'remoteImage':row['url'],'width':1000,'height':1667,
          'type':row['type'],'classification':row['type'],'medium':'',
          'rightsOK':True,'license':'CC0','yearStart':row['yearStart'],
          'yearEnd':row['yearEnd'],'date':str(row['yearStart'] or ''),
          'museumRegion':'bundled','offlineAsset':'',
          'sourceSHA256':source_sha,'derivedSHA256':derived_sha,
          'originalPixels':[width,height],'cropBox':list(box),
          'upscaleFactor':factor,'adaptType':'SMART_PORTRAIT_CROP',
          'metadataProvenance':'Official CMA CC0 type and source URL',
          'originalLandscape':bool(width>=height),
          'museumStyleEvidence':row['style_evidence'],
          'page':row['page']
        },jpeg,None
    except HTTPError as e:return None,None,f"{row['key']} HTTP {e.code}"
    except Exception as e:return None,None,f"{row['key']} {type(e).__name__} {str(e)[:105]}"

def add_museum_assets(rows,pools,aliases):
    before=len(rows)
    prior_key={x['key'] for x in rows}
    prior_raw={x['sourceSHA256'] for x in rows}
    prior_derived={x['derivedSHA256'] for x in rows}
    total=sum((ROOT/x['offlineAsset']).stat().st_size for x in rows)
    # Interleave media classes, allowing a broader range of art styles and
    # imagery rather than hundreds of photographs in a single source order.
    ordering=[]
    # Photo has 600 previous examples; prioritize painting and works on paper.
    weights=[('Painting',3),('Drawing',2),('Print',2),('Photograph',1)]
    indices=collections.Counter()
    while len(ordering)<sum(len(p) for p in pools.values()):
        advanced=False
        for k,weight in weights:
            for _ in range(weight):
                i=indices[k]
                if i<len(pools[k]):
                    row=pools[k][i];indices[k]+=1;ordering.append(row);advanced=True
        if not advanced:break
    ordering=[row for row in ordering if row['key'] not in prior_key]
    verified=collections.Counter()
    fail=[];matched=collections.Counter();landscape=collections.Counter();upscaled=collections.Counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        for index, (row,res) in enumerate(zip(ordering,pool.map(encode_row,ordering)),1):
            if len(rows)-before>=MAX_ADDED or len(rows)>=MAX_TOTAL:break
            art,blob,err=res
            if err:
                if len(fail)<65:fail.append(err)
                verified['failed']+=1
                continue
            if art['sourceSHA256'] in prior_raw or art['derivedSHA256'] in prior_derived:
                verified['deduplicated']+=1;continue
            if total+len(blob)>MAX_BYTES:
                print('ASSET_BYTE_LIMIT_REACHED',total,flush=True);break
            n=len(rows)
            name='offline/pack-%04d.jpg'%n
            fp=ROOT/name
            fp.write_bytes(blob)
            if file_sha(fp)!=art['derivedSHA256']:
                raise AssertionError('Copied file SHA does not match '+name)
            with Image.open(fp) as check:
                check.load()
                if check.size!=(1000,1667) or check.format!='JPEG':
                    raise AssertionError('Saved file failed decode '+name)
            art['offlineAsset']=name;art['image']='https://appassets.gallery/'+name
            rows.append(art);total+=len(blob);prior_raw.add(art['sourceSHA256']);prior_derived.add(art['derivedSHA256']);prior_key.add(art['key'])
            verified[art['type']]+=1
            landscape[art['type']]+=int(art['originalLandscape'])
            upscaled[art['type']]+=int(float(art['upscaleFactor'] or 1)>1.001)
            for term in art.get('museumStyleEvidence',[]):
                tag=term.casefold().strip()
                if tag in aliases:
                    for ko in aliases[tag]:matched[ko]+=1
            if (len(rows)-before)%50==0 or len(rows)==before+1:
                print('NEW_STYLE_IMAGES_REOPENED_SHA_VERIFIED',len(rows)-before,
                      "TOTAL",len(rows),"MEDIUMS",dict(verified),flush=True)
    if len(rows)<=before:raise RuntimeError("No actual new valid 2D artwork files")
    DECK.write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    return total,verified,landscape,upscaled,matched,fail

def main():
    movements,sources,aliases=load_registry()
    rows=restore_exact_source_apk()
    pools,query_errors=candidate_sets()
    total,verified,landscape,upscaled,matched,fail=add_museum_assets(rows,pools,aliases)
    new=sum(v for k,v in verified.items() if k not in ('failed','deduplicated'))
    if new<20:raise RuntimeError("Less than 20 actual new photographs/paintings/prints; reject unsupported release")
    result={
      'unchanged_previous_works':1511,
      'base_types':{'Painting':886,'Photograph':600,'Animation Still':24,'Contemporary Art':1},
      'actual_new_jpegs':new,'total_verified_jpegs':len(rows),
      'new_by_medium':{k:v for k,v in verified.items() if k not in ('failed','deduplicated')},
      'new_landscape_cropped':dict(landscape),'new_actually_upscaled':dict(upscaled),
      'bytes_all_embedded_jpegs':total,
      'download_or_quality_failures':int(verified['failed']),
      'duplicate_sources_or_images':int(verified['deduplicated']),
      'api_page_failures':query_errors[:45],'source_failures':fail[:55],
      'movement_registry_entries':movements['entry_count'],
      'movement_searches_with_known_english_terms':movements['english_query_terms'],
      'museum_style_tags_that_exactly_match_requested_english_movement_names':dict(matched),
      'movements_with_verified_museum_style_match':len(matched),
      'not_proven_all_movement_coverage':True,
      'requested_source_entries':sources['requested_source_entries'],
      'unique_requested_source_names':sources['unique_source_names'],
      'actual_request_list_source_apis_integrated':sources['automatic_search_integrations'],
      'requested_sources_not_auto_scraped':sources['reference_only_excluding_duplicates'],
      'new_embedded_artwork_provider':'Cleveland Museum of Art official CC0 image API',
      'sources_registered_not_same_as_ingested_files':True,
      'previous_release_apk_sha256':PREVIOUS_SHA256
    }
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('FULL_GLOBAL_ADDITIONAL_VERIFIED',json.dumps({k:v for k,v in result.items() if k not in ('api_page_failures','source_failures')},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
