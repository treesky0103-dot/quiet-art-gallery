#!/usr/bin/env python3
"""Comparison ONLY: 3 verified public-domain paintings per screen-fill band.
Create two real-resolution exports of the SAME 6 artworks for meaningful
HD vs medium comparison (12 previews). No production code is modified.
"""
import base64, concurrent.futures, datetime, html, io, json, math, random, re, textwrap, urllib.parse, urllib.request
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps

OUT=Path("comparison");OUT.mkdir(exist_ok=True)
USER_AGENT="QuietArtGallery/Compare-20261113 (https://github.com/treesky0103-dot/quiet-art-gallery; 6 copyrighted-safe artworks)"
CATEGORIES=[
 ("Rijksmuseum","Paintings in the Rijksmuseum Amsterdam"),
 ("NGV Australia","Paintings in the National Gallery of Victoria"),
 ("National Gallery London","Paintings in the National Gallery, London"),
 ("National Gallery Washington","Paintings in the National Gallery of Art (Washington, D.C.)"),
 ("Getty","Paintings in The J. Paul Getty Museum"),
 ("NSW Australia","Paintings in the Art Gallery of New South Wales"),
 ("Art Gallery South Australia","Paintings in the Art Gallery of South Australia"),
 ("Argentina Fine Arts","Paintings in the Museo Nacional de Bellas Artes (Argentina)"),
 ("Chile Fine Arts","Paintings in the Museo Nacional de Bellas Artes (Chile)"),
 ("SMK Denmark","Paintings in Statens Museum for Kunst"),
 ("Walters Art Museum","Paintings in the Walters Art Museum"),
 ("National Gallery Australia","Paintings in the National Gallery of Australia"),
 ("Museo Arte Lima","Paintings in the Museo de Arte de Lima"),
 ("Pinacoteca Brazil","Paintings in the Pinacoteca do Estado de São Paulo"),
 ("Auckland Art Gallery","Paintings in the Auckland Art Gallery"),
 ("Dunedin Art Gallery","Paintings in the Dunedin Public Art Gallery"),
 ("2020s contemporary paintings","2020s paintings"),
 ("Contemporary paintings","Contemporary paintings"),
]
BAD=re.compile(r"(?i)(?:sculpture|statue|installation|interior|exhibition|gallery view|museum hall|framed|frame|detail|reverse|verso|galleries|photograph|old photo|portrait of visitors|reproduction|poster|manuscript|engraved object|coin|stamp|architecture|building)")
ALLOWED={"public domain","pd","cc0","cc0 1.0","cc0 1.0 universal"}
def fetch(url,maxbytes=8_000_000,timeout=25):
 req=urllib.request.Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/json,image/jpeg,image/png"})
 with urllib.request.urlopen(req,timeout=timeout) as r:
  data=r.read(maxbytes+1)
  if len(data)>maxbytes:raise ValueError("Oversize download")
  return data
def meta_one(arg):
 name,cat=arg;out=[]
 try:
  for offset in (0,50,100):
   query={"action":"query","generator":"search","gsrsearch":'deepcategory:"'+cat+'"',
   "gsrnamespace":"6","gsrlimit":"50","gsroffset":str(offset),
   "prop":"imageinfo","iiprop":"url|size|mime|extmetadata","iiurlwidth":"1600",
   "format":"json","formatversion":"2"}
   url="https://commons.wikimedia.org/w/api.php?"+urllib.parse.urlencode(query)
   j=json.loads(fetch(url,8_000_000,28))
   pages=(j.get("query") or {}).get("pages") or []
   for p in pages:
    info=(p.get("imageinfo") or [None])[0]
    if not info:continue
    title=str(p.get("title") or "")
    if BAD.search(title):continue
    meta=info.get("extmetadata") or {}
    lic=str((meta.get("LicenseShortName") or {}).get("value") or "").lower().strip()
    if lic not in ALLOWED or info.get("mime") not in ("image/jpeg","image/png"):continue
    w,h=int(info.get("width") or 0),int(info.get("height") or 0)
    if not(w>=1500 and h>=1700 and h>w):continue
    ratio=w/h
    fill=min(ratio/.625,.625/ratio)
    if not(.75<=fill<.8 or .84<=fill<=.95):continue
    thumb=info.get("thumburl") or info.get("url")
    if not thumb:continue
    u=urllib.parse.urlparse(thumb)
    if u.scheme!="https" or u.hostname not in ("upload.wikimedia.org","thumb.wikimedia.org"):continue
    artist=re.sub("<[^>]+>"," ",str((meta.get("Artist") or {}).get("value") or ""))
    artist=html.unescape(re.sub(r"\s+"," ",artist)).strip()[:60]
    desc=info.get("descriptionurl") or ("https://commons.wikimedia.org/wiki/"+urllib.parse.quote(title.replace(" ","_")))
    out.append({"id":p.get("pageid"),"source":name,"title":title.removeprefix("File:").rsplit(".",1)[0].replace("_"," ")[:160],
      "artist":artist,"license":lic,"thumb":thumb,"description":desc,
      "source_w":w,"source_h":h,"fill":fill,"ratio":ratio,
      "band":"80" if fill>=.8 else "75"})
   if len(pages)<50:break
 except Exception as e:
  print("SOURCE_ERROR",name,str(e)[:90],flush=True)
 print("SOURCE",name,"eligible",len(out),"80",sum(x["band"]=="80" for x in out),
   "75",sum(x["band"]=="75" for x in out),flush=True)
 return out
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
 groups=list(ex.map(meta_one,CATEGORIES))
candidates=[x for group in groups for x in group]
random.Random(4206).shuffle(candidates)
picked=[]
for band in ("80","75"):
 used_sources=set()
 matches=[x for x in candidates if x["band"]==band]
 matches.sort(key=lambda x:(-x["fill"] if band=="80" else abs(x["fill"]-.77),-min(x["source_w"],x["source_h"])))
 tries=0
 for entry in matches:
  if sum(x["band"]==band for x in picked)>=3:break
  if entry["source"] in used_sources:continue
  if entry["id"] in {x["id"] for x in picked}:continue
  try:
   data=fetch(entry["thumb"],14_000_000,28)
   im=Image.open(io.BytesIO(data));im.load()
   if im.mode not in ("RGB","RGBA"):im=im.convert("RGB")
   else:im=im.convert("RGB")
   r=im.width/im.height
   if abs(r-entry["ratio"])>.022:continue
   hiw=max(1230,math.ceil(1710*r))
   if im.width <hiw or im.height<1710:continue
   entry["loaded_w"]=im.width;entry["loaded_h"]=im.height
   entry["_image"]=im
   picked.append(entry);used_sources.add(entry["source"])
   print("PICK",band,entry["id"],entry["title"][:50],"meta",entry["source_w"],entry["source_h"],
         "actual",im.width,im.height,"fill",round(entry["fill"],4),flush=True)
  except Exception as e:
   tries+=1
   if tries<15:print("SKIP",entry["id"],str(e)[:85],flush=True)
  if tries>30:break
 if sum(x["band"]==band for x in picked)<3:raise RuntimeError("Not enough real high-resolution eligible artworks in band "+band)
def image_jpeg(im,width,quality):
 h=round(im.height*width/im.width)
 cropped=im.resize((width,h),Image.Resampling.LANCZOS)
 b=io.BytesIO();cropped.save(b,"JPEG",quality=quality,subsampling=0,optimize=True)
 return b.getvalue(),(width,h)
items=[]
for group in ("80","75"):
 examples=[x for x in picked if x["band"]==group][:3]
 for quality in ("high","medium"):
  for n,entry in enumerate(examples,1):
   im=entry["_image"];ratio=im.width/im.height
   target=max(1230,math.ceil(1710*ratio)) if quality=="high" else max(1010,math.ceil(1420*ratio))
   assert target <im.width and (quality=="high" or target<1200)
   data,(w,h)=image_jpeg(im,target,93 if quality=="high" else 79)
   assert (min(w,h)>=1200 and max(w,h)>=1600) if quality=="high" else (min(w,h)>=1000 and max(w,h)>=1400 and min(w,h)<1200)
   fname=f"{group}_{quality}_{n}.jpg"
   (OUT/fname).write_bytes(data)
   items.append({k:v for k,v in entry.items() if k!="_image"}|{"band":group,"quality":quality,"file":fname,"export_w":w,"export_h":h,"bytes":len(data)})
OUT.joinpath("source_data.json").write_text(json.dumps({"viewport":"16:10 portrait","mode":"same three artworks for high and medium per threshold","artworks":items},ensure_ascii=False,indent=2),encoding="utf8")
fontpath="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
ft=ImageFont.truetype(fontpath,30);fb=ImageFont.truetype(fontpath,18);small=ImageFont.truetype(fontpath,14)
W,H=460,810;TOP=80
sheet=Image.new("RGB",(3*W,4*(H+TOP)+32),(245,244,239));d=ImageDraw.Draw(sheet)
group_labels=[("80","high","80%+  HIGH QUALITY"),("80","medium","80%+  MEDIUM QUALITY"),("75","high","75-80%  HIGH QUALITY"),("75","medium","75-80%  MEDIUM QUALITY")]
for gi,(band,qual,label) in enumerate(group_labels):
 y=gi*(H+TOP)+10
 d.rounded_rectangle((12,y,1368,y+56),radius=10,fill=(25,33,42))
 d.text((30,y+11),label,font=ft,fill=(255,255,255))
 for idx,item in enumerate([it for it in items if it["band"]==band and it["quality"]==qual]):
  x=idx*W
  d.rounded_rectangle((x+8,y+66,x+W-8,y+TOP+H-12),radius=10,fill=(255,255,255))
  # 16:10 portrait screen 400x640 pixels. Contain, never crop.
  wx,wy=x+30,y+100;vw,vh=400,640
  d.rectangle((wx-1,wy-1,wx+vw+1,wy+vh+1),fill=(10,11,13))
  im=Image.open(OUT/item["file"]).convert("RGB")
  scale=min(vw/im.width,vh/im.height)
  dst=im.resize((max(1,round(im.width*scale)),max(1,round(im.height*scale))),Image.Resampling.LANCZOS)
  sheet.paste(dst,(wx+(vw-dst.width)//2,wy+(vh-dst.height)//2))
  title=item["title"][:39]+("..." if len(item["title"])>39 else "")
  d.text((wx,wy+vh+13),title,font=fb,fill=(23,24,28))
  d.text((wx,wy+vh+38),f'{item["export_w"]}x{item["export_h"]} px | {item["fill"]*100:.1f}% screen',font=small,fill=(79,87,90))
sheet.save(OUT/"comparison_12_panels.png",optimize=True)
# HTML retains the original individual high/medium files and allows full pixel zoom
html_items=[]
for it in items:
 b64=base64.b64encode((OUT/it["file"]).read_bytes()).decode("ascii")
 html_items.append({**it,"data":"data:image/jpeg;base64,"+b64})
JS=json.dumps(html_items,ensure_ascii=False).replace("</","<\\/")
template="""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>고요한 미술관 — 화질과 화면 채움 비교</title>
<style>body{margin:0;background:#ecebe6;color:#19252b;font-family:Arial,"Noto Sans KR",sans-serif}main{max-width:1240px;margin:auto;padding:25px}h1{font-size:24px}p{line-height:1.7}section{margin:32px 0}section h2{background:#243540;color:white;padding:13px 18px;border-radius:8px;font-size:19px}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.card{background:white;padding:14px;border-radius:12px;box-shadow:0 2px 10px #0001}.screen{background:#111218;aspect-ratio:10/16;display:flex;align-items:center;justify-content:center;border-radius:5px;overflow:hidden;cursor:zoom-in}.screen img{width:100%;height:100%;object-fit:contain}
.name{margin:12px 0 3px;overflow-wrap:anywhere;font-size:13px;font-weight:bold}.sub{font-size:12px;color:#58656b;line-height:1.5}.sub a{color:#225a85}
#modal{position:fixed;inset:0;background:#000e;display:none;align-items:center;justify-content:center;z-index:9;padding:1rem}#modal img{max-width:95vw;max-height:95vh;object-fit:contain}#close{position:fixed;top:15px;right:18px;background:#fff;padding:8px;border:0;border-radius:5px;font-size:20px}
.notice{background:white;border-radius:9px;padding:13px 20px}small{color:#64727b}@media(max-width:750px){main{padding:12px}.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.card{padding:7px}h1{font-size:21px}section h2{font-size:16px}}@media(max-width:430px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}</style></head>
<body><main><h1>고요한 미술관 · 화면 채움과 화질 비교</h1><div class="notice">
<p>기준: 세로 16:10 태블릿 · 그림 자르기 없음 · 원본 6점을 각각 두 화질로 내보낸 총 12개 화면. <b>80% 이상</b>과 <b>75~80% 미만</b>의 차이를 비교할 수 있습니다.</p>
<p><b>고화질:</b> 짧은 변 1,200px / 긴 변 1,600px 이상. <b>중화질:</b> 짧은 변 1,000px / 긴 변 1,400px 이상이되 고화질 기준 미달. 같은 작품을 다른 해상도로 출력했습니다. 모든 이미지 클릭 시 크게 볼 수 있습니다.</p>
<small>각 작품은 Wikimedia Commons에 표시된 Public domain 또는 CC0 원본을 사용했습니다. 파일명·제작자·라이선스는 아래 링크로 확인할 수 있습니다. 이는 태블릿 전시 조건을 시각적으로 비교하기 위한 예시이며 실제 앱 공급원 전체의 작품 수 추정이 아닙니다.</small></div><div id="sections"></div></main>
<div id="modal" onclick="this.style.display='none'"><button id="close" aria-label="닫기">×</button><img id="enlarged" alt=""></div>
<script>const rows=__ROWS__;const groups=[['80','high','① 80% 이상 · 고화질'],['80','medium','② 80% 이상 · 중화질'],['75','high','③ 75~80% 미만 · 고화질'],['75','medium','④ 75~80% 미만 · 중화질']];
const root=document.getElementById('sections');for(const [band,quality,label] of groups){const s=document.createElement('section');s.innerHTML='<h2>'+label+'</h2>';const g=document.createElement('div');g.className='grid';
 for(const x of rows.filter(r=>r.band===band&&r.quality===quality)){const c=document.createElement('article');c.className='card';
 const pic=document.createElement('div');pic.className='screen';const img=document.createElement('img');img.src=x.data;img.alt=x.title;pic.appendChild(img);pic.onclick=()=>{document.getElementById('enlarged').src=x.data;document.getElementById('modal').style.display='flex';};
 const t=document.createElement('div');t.className='name';t.textContent=x.title;const b=document.createElement('div');b.className='sub';b.textContent=x.export_w+'×'+x.export_h+'px · 화면 '+(x.fill*100).toFixed(1)+'% · '+x.source+' · '+x.license;
 const a=document.createElement('a');a.href=x.description;a.target='_blank';a.rel='noopener noreferrer';a.textContent='작품 원본·라이선스 확인';const p=document.createElement('div');p.className='sub';p.append(a);
 c.append(pic,t,b,p);g.appendChild(c);}s.appendChild(g);root.appendChild(s);}document.addEventListener('keydown',e=>{if(e.key==='Escape')document.getElementById('modal').style.display='none';});</script></body></html>"""
(OUT/"comparison_interactive.html").write_text(template.replace("__ROWS__",JS),encoding="utf-8")
print("COMPLETE",json.dumps({"artworks":len(picked),"panels":len(items),"sizes":[{"title":x["title"],"band":x["band"],"fill":round(x["fill"],4),"size":str(x["export_w"])+"x"+str(x["export_h"])} for x in items]},ensure_ascii=False),flush=True)
