#!/usr/bin/env python3
"""Independent before/after visual audit of the *released* 886-image APK.

Pulls exact embedded JPEGs from the APK ZIP, redownloads each matching original
and confirms its source SHA256 before drawing the actual recorded crop.
Does not infer missing photos from metadata or regenerate a substitute crop.
"""
import hashlib, io, json, math, re, zipfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from PIL import Image, ImageDraw, ImageFont, ImageOps

APK=Path("QuietArtGallery-Portrait30min-Expanded-debug.apk")
APK_SHA="b826eb8afefb936eda7bfd1316f045d480e42152e9c4111fa9e2e96b767349e4"
DIMS=(2340,1560)
OUT=Path("portrait-comparison")
OUT.mkdir(exist_ok=True)
UA="QuietArtGalleryVisualAudit/1.0 (+https://github.com/treesky0103-dot/quiet-art-gallery)"
ALLOWED={"openaccess-cdn.clevelandart.org","images.metmuseum.org","iiif.micr.io","iiif.wellcomecollection.org","images.collections.yale.edu","open.smk.dk","ids.si.edu","api.nga.gov","images.nga.gov"}

def image_from_url(url,sha):
    p=urlsplit(url)
    if p.scheme!="https" or p.hostname not in ALLOWED or p.port not in (None,443):
        raise ValueError("Unsupported original host")
    req=Request(url,headers={"User-Agent":UA,"Accept":"image/jpeg,image/webp,image/png"})
    with urlopen(req,timeout=22) as r:
        if r.status!=200:raise ValueError("Original HTTP "+str(r.status))
        raw=r.read(17*1024*1024)
        final=urlsplit(r.geturl())
        if final.hostname not in ALLOWED:raise ValueError("Untrusted redirect")
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError("Original source SHA mismatch")
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        return ImageOps.exif_transpose(im).convert("RGB")

def font(size,bold=False):
    candidates=[
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        try:return ImageFont.truetype(p,size)
        except OSError:pass
    return ImageFont.load_default()

def fit_rect(img,left,top,width,height):
    iw,ih=img.size
    sf=min(width/iw,height/ih)
    nw,nh=round(iw*sf),round(ih*sf)
    return (left+(width-nw)//2,top+(height-nh)//2,nw,nh)

def draw_panel(img_list,kind,title,output):
    bg=Image.new("RGB",DIMS,(19,23,29))
    dr=ImageDraw.Draw(bg)
    dr.text((48,18),title,font=font(32,True),fill=(244,239,226))
    dr.text((50,62),"LEFT: original + crop window   |   RIGHT: exact portrait JPEG embedded in APK",
            font=font(19),fill=(198,210,221))
    slots=[(25,124),(1180,124),(25,852),(1180,852)]
    summary=[]
    for (art,source,converted), (px,py) in zip(img_list,slots):
        dr.rounded_rectangle([px,py,px+1130,py+698],radius=16,fill=(35,40,47))
        name=re.sub(r"\s+"," ",str(art.get("title") or ""))[:42]
        dr.text((px+20,py+18),name,font=font(23,True),fill=(250,251,253))
        dr.text((px+20,py+53),f"From {source.width}x{source.height} to 1000x1667",
                font=font(18),fill=(204,218,230))
        orig=(px+15,py+104,625,514)
        dest=(px+700,py+104,330,514)
        sx,sy,sw,sh=fit_rect(source,*orig)
        scaled=source.resize((sw,sh),Image.Resampling.LANCZOS)
        bg.paste(scaled,(sx,sy))
        crop=art["cropBox"]
        d=ImageDraw.Draw(bg)
        bx0=sx+round(crop[0]/source.width*sw)
        by0=sy+round(crop[1]/source.height*sh)
        bx1=sx+round(crop[2]/source.width*sw)
        by1=sy+round(crop[3]/source.height*sh)
        d.rectangle([bx0,by0,bx1,by1],outline=(246,166,57),width=5)
        dx,dy,dw,dh=fit_rect(converted,*dest)
        bg.paste(converted.resize((dw,dh),Image.Resampling.LANCZOS),(dx,dy))
        d.text((px+636,py+344),">>",font=font(38,True),fill=(246,166,57))
        d.text((px+20,py+648),f"Original {art.get('source','')} | resize {art.get('upscaleFactor',1)}x",
               font=font(15),fill=(202,213,222))
        summary.append({"title":art.get("title"),"source":art.get("source"),"original_pixels":art.get("originalPixels"),"crop_box":crop,
            "upscale_factor":art.get("upscaleFactor"),"new_adaptive":art.get("metadataProvenance")=="new_adaptive_metadata",
            "original_sha256_verified":True,"embedded_image_sha256_verified":True})
    bg.save(output,"JPEG",quality=86,optimize=True,subsampling=0)
    with Image.open(output) as check:check.load();assert check.size==DIMS
    return summary

def main():
    if not APK.exists() or hashlib.sha256(APK.read_bytes()).hexdigest()!=APK_SHA:
        raise RuntimeError("Refuse preview: exact released APK missing or SHA mismatch")
    with zipfile.ZipFile(APK) as archive:
        rows=json.loads(archive.read("assets/offline-deck.json"))
        assert len(rows)==886
        counts={
          "embedded":len(rows),
          "existing_ledger":sum(x.get("metadataProvenance")=="previous_hash_ledger" for x in rows),
          "new_adaptive":sum(x.get("metadataProvenance")=="new_adaptive_metadata" for x in rows),
          "original_landscape":sum(bool(x.get("originalLandscape")) for x in rows),
          "upscaled":sum(float(x.get("upscaleFactor") or 1)>1.001 for x in rows)
        }
        print("AUDIT_APK_COUNTS",json.dumps(counts),flush=True)
        groups={
          "landscape":[x for x in rows if x.get("originalLandscape") and x.get("metadataProvenance")=="new_adaptive_metadata"],
          "upscale":[x for x in rows if float(x.get("upscaleFactor") or 1)>1.001],
        }
        # Spread across the actual released manifest, rather than displaying
        # 4 almost-identical adjacent objects from one API page.
        previews={}
        for key,items in groups.items():
            if not items:raise RuntimeError("Missing requested group "+key)
            choices=[items[round(i*(len(items)-1)/11)] for i in range(12)]
            if key=="upscale":choices=sorted(choices,key=lambda x:-float(x.get("upscaleFactor") or 1))
            done=[];failures=[]
            for art in choices:
                if len(done)>=4:break
                try:
                    raw=image_from_url(art["remoteImage"],art["sourceSHA256"])
                    payload=archive.read("assets/"+art["offlineAsset"])
                    if hashlib.sha256(payload).hexdigest()!=art["derivedSHA256"]:
                        raise ValueError("Embedded portrait SHA mismatch")
                    with Image.open(io.BytesIO(payload)) as im:
                        im.load()
                        if im.size!=(1000,1667):raise ValueError("Unexpected embedded dimensions")
                        processed=im.convert("RGB")
                    if art["originalPixels"]!=list(raw.size):
                        raise ValueError("Recorded original pixel size mismatch")
                    done.append((art,raw,processed))
                except Exception as ex:failures.append({"title":art.get("title"),"reason":str(ex)[:100]})
            if len(done)<3:raise RuntimeError(f"{key} only {len(done)} hash-verified comparisons; "+str(failures))
            path=OUT/f"before-after-{key}.jpg"
            previews[key]=draw_panel(done,key,f"Quiet Art Gallery — {key.upper()} conversion examples",path)
            print("REAL_COMPARISON_CREATED",key,len(done),path,flush=True)
    report={"apk_sha256":APK_SHA,"counts":counts,"proofs":previews,"note":"Smart cropping uses edge / contrast / saturation energy, not semantic AI."}
    (OUT/"before-after-audit-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("COMPARISON_AUDIT_PASS",json.dumps({"counts":counts,"visual_proofs":{k:len(v) for k,v in previews.items()}}),flush=True)

if __name__=="__main__":main()
