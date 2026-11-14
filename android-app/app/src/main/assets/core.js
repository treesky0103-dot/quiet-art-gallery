/* Artwork selection core. Zero external dependencies. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.GalleryCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const NINETY_DAYS_MS = 90 * 24 * 60 * 60 * 1000;
  // Minimum decoded image resolution. Never upscale a small original.
  const MIN_IMAGE_SHORT_SIDE = 1200; // preferred high-resolution tier (unchanged)
  const MIN_IMAGE_LONG_SIDE = 1600;
  const MIN_ACCEPTABLE_SHORT_SIDE = 1000; // medium-resolution fallback
  const MIN_ACCEPTABLE_LONG_SIDE = 1400;
  function highResolution(width,height){
    const w=Number(width),h=Number(height);
    return Number.isFinite(w)&&Number.isFinite(h)&&w>0&&h>0&&Math.min(w,h)>=MIN_IMAGE_SHORT_SIDE&&Math.max(w,h)>=MIN_IMAGE_LONG_SIDE;
  }
  function acceptableResolution(width,height){
    const w=Number(width),h=Number(height);
    return Number.isFinite(w)&&Number.isFinite(h)&&w>0&&h>0&&Math.min(w,h)>=MIN_ACCEPTABLE_SHORT_SIDE&&Math.max(w,h)>=MIN_ACCEPTABLE_LONG_SIDE;
  }
  function qualityTier(art){
    // Priority for known image dimensions: 2 high, 1 medium, 0 unknown/rejected.
    const w=Number(art&&art.width),h=Number(art&&art.height);
    return highResolution(w,h)?2:acceptableResolution(w,h)?1:0;
  }
  function metadataResolutionOkay(a){
    if(!a)return false;
    // On Android, the native image proxy can upscale eligible low-resolution
    // 2D art and make portrait smart crops. The actual decoded JPEG must still
    // pass strict 1000x1400/75%-fill validation before display.
    if(typeof window!=='undefined' && window.GalleryAndroid){
      const w=Number(a.width),h=Number(a.height);
      return !(w>0&&h>0) || (w>=380&&h>=630) || (w>=630&&h>=380);
    }
    // Commons source dimensions and Cleveland web rendition can be checked before download.
    if(a.museumRegion==='asia'||a.museumRegion==='africa'||a.museumRegion==='additional'||a.museumRegion==='modern'||a.source==='클리블랜드')return acceptableResolution(a.width,a.height);
    return true; // Other sources must pass the decoded-image check.
  }
  const BLOCKLIST = /(?:\bsculpture\b|\bceramic(?:s)?\b|\bpottery\b|\bfurniture\b|\btextile\b|\btapestry\b|\barmor\b|\barmour\b|\bweapon\b|\binstallation\b|\bstatue\b|\bvase\b|\bcoin\b|\bmedal\b|\bjewelry\b|\bjewellery\b|\barchitecture\b|\bdecorative art\b|\bframe(?:d)?\b|\bgallery view\b|\bexhibition view\b|\b3d\b|\bvideo\b|\bfilm\b|\bglass\b|\bcarpet\b|\bcostume\b|\bcarving\b|\brelief\b|\bbook cover\b)/i;
  const ALLOW_TYPES = /(?:painting|paintings|drawing|drawings|print|prints|watercolo[u]?r|etching|lithograph|woodblock|woodcut|illustration|photograph(?:y|s)?|photo print|animation still|animated film frame|contemporary art|street art|graffiti|stencil art|mural art|urban art|gouache|collage|pastel|ink on paper|oil on canvas|oil on panel|acrylic on|tempera on|aquatint|serigraph|screenprint|engraving)/i;
  function string(x) { return typeof x === 'string' ? x : ''; }
  function safeURL(url) {
    try {
      const u = new URL(url);
      if (u.protocol !== 'https:' || u.username || u.password || (u.port && u.port !== '443')) return false;
      const h = u.hostname.toLowerCase();
      // Only exact named, APK-embedded artworks may use the pseudo-local host.
      if(h === 'appassets.gallery')return /^\/offline\/pack-[0-9]{4}\.jpg$/.test(u.pathname) && !u.search && !u.hash;
      return h === 'upload.wikimedia.org' || h === 'images.metmuseum.org' || h === 'www.artic.edu' || h === 'artic.edu' || h === 'openaccess-cdn.clevelandart.org' || h.endsWith('.clevelandart.org');
    } catch (_) { return false; }
  }
  // Wikimedia Commons collection categories; not direct museum-operated APIs.
  const ASIAN_MUSEUMS = Object.freeze([
    {id:'korea', label:'국립중앙박물관', category:'Paintings in the National Museum of Korea'},
    {id:'tokyo', label:'도쿄국립박물관', category:'Japanese paintings in the Tokyo National Museum'},
    {id:'kyoto', label:'교토국립박물관', category:'Paintings in the Kyoto National Museum'},
    {id:'nara', label:'나라국립박물관', category:'Paintings in the Nara National Museum'},
    {id:'taipei', label:'타이완 국립고궁박물원', category:'Paintings in the National Palace Museum'}
  ]);
  // Paintings located in African museums, discovered through Wikimedia Commons
  // collection categories (not the institutions' own authenticated APIs).
  const AFRICAN_MUSEUMS = Object.freeze([
    {id:'iziko', label:'이지코 남아공 국립미술관', category:'Paintings in the South African National Gallery'},
    {id:'ethiopia', label:'에티오피아 국립박물관', category:'Paintings in the National Museum of Ethiopia'},
    {id:'zimbabwe', label:'짐바브웨 국립미술관', category:'Paintings in the National Gallery of Zimbabwe'},
    {id:'johannesburg', label:'요하네스버그 미술관', category:'Paintings by Paul Signac in the Johannesburg Art Gallery'}
  ]);
  // Additional museum-owned collections, discovered by Wikimedia Commons categories.
  // Paris Musées is represented by its member Musée Carnavalet, not the full network.
  const ADDITIONAL_MUSEUMS = Object.freeze([
    {id:'rijks',label:'암스테르담 국립미술관',category:'Paintings in the Rijksmuseum Amsterdam'},
    {id:'nga',label:'미국 국립미술관',category:'Paintings in the National Gallery of Art (Washington, D.C.)'},
    {id:'getty',label:'게티 미술관',category:'Paintings in The J. Paul Getty Museum'},
    {id:'smk',label:'덴마크 국립미술관',category:'Paintings in Statens Museum for Kunst'},
    {id:'paris',label:'파리 시립미술관 연합(카르나발레)',category:'Paintings in Musée Carnavalet'},
    {id:'london',label:'런던 내셔널갤러리',category:'Paintings in the National Gallery, London'},
    {id:'walters',label:'월터스 미술관',category:'Paintings in the Walters Art Museum'},
    {id:"ngv",label:"호주 빅토리아 국립미술관",category:"Paintings in the National Gallery of Victoria"},
    {id:"nsw",label:"호주 뉴사우스웨일스 미술관",category:"Paintings in the Art Gallery of New South Wales"},
    {id:"aus-nga",label:"호주 국립미술관",category:"Paintings in the National Gallery of Australia"},
    {id:"south-aus",label:"남호주 미술관",category:"Paintings in the Art Gallery of South Australia"},
    {id:"queensland",label:"호주 퀸즐랜드 미술관",category:"Paintings in the Queensland Art Gallery"},
    {id:"auckland",label:"뉴질랜드 오클랜드 미술관",category:"Paintings in the Auckland Art Gallery"},
    {id:"dunedin",label:"뉴질랜드 더니든 미술관",category:"Paintings in the Dunedin Public Art Gallery"},
    {id:"brasil-mnba",label:"브라질 국립미술관",category:"Brazilian paintings in the Museu Nacional de Belas Artes"},
    {id:"argentina-mnba",label:"아르헨티나 국립미술관",category:"Paintings in the Museo Nacional de Bellas Artes (Argentina)"},
    {id:"chile-mnba",label:"칠레 국립미술관",category:"Paintings in the Museo Nacional de Bellas Artes (Chile)"},
    {id:"peru-mali",label:"페루 리마 미술관",category:"Paintings in the Museo de Arte de Lima"},
    {id:"colombia-mnc",label:"콜롬비아 국립박물관",category:"Paintings in the Museo Nacional de Colombia"},
    {id:"uruguay-mnav",label:"우루과이 국립시각예술박물관",category:"Paintings in the Museo Nacional de Artes Visuales"},
    {id:"brasil-pina",label:"브라질 상파울루 피나코테카",category:"Paintings in the Pinacoteca do Estado de São Paulo"},
    {id:'louvre',label:'루브르 박물관',category:'Paintings in the Louvre'},
    {id:'orsay',label:'오르세 미술관',category:"Paintings in the Musée d'Orsay"},
    {id:'british',label:'대영박물관',category:'Prints in the British Museum',type:'Print'},
    {id:'prado',label:'프라도 미술관',category:'Paintings in the Museo del Prado'},
    {id:'hermitage',label:'에르미타시 박물관',category:'Paintings in the Hermitage'}
  ]);

  // Smithsonian collection images are discovered from the paintings-category
  // pages on Wikimedia Commons. These are NOT a direct Smithsonian EDAN API
  // integration. NMAA spans the Freer Gallery's Chinese, Japanese and Indian
  // painting collections; count the three categories as one museum.
  const SMITHSONIAN_MUSEUMS=Object.freeze([
    {id:'saam',label:'스미스소니언 미국미술관',
      museumRegion:'additional',
      categories:['Paintings in the Smithsonian American Art Museum']},
    {id:'nmaa',label:'스미스소니언 국립아시아미술관',
      museumRegion:'asia',
      categories:['Paintings from China in the Freer Gallery',
        'Paintings from Japan in the Freer Gallery of Art',
        'Paintings from India in the Freer Gallery of Art']}
  ]);

  // World-wide flat-art publication/category sources beyond museums.
  // All Wikimedia category names are discovery hints, not individual creation dates.
  // Sources include books, university libraries, prints and independent artists.
  const GLOBAL_OPEN_ART_CATEGORIES=Object.freeze([
    {id:'p19',label:'19세기 세계 회화',category:'19th-century paintings'},
    {id:'p20',label:'20세기 세계 회화',category:'20th-century paintings'},
    {id:'p21',label:'21세기 세계 회화',category:'21st-century paintings'},
    {id:'d19',label:'19세기 드로잉',category:'19th-century drawings'},
    {id:'d20',label:'20세기 드로잉',category:'20th-century drawings'},
    {id:'d21',label:'21세기 드로잉',category:'21st-century drawings'},
    {id:'r19',label:'19세기 판화',category:'19th-century prints',type:'Print'},
    {id:'r20',label:'20세기 판화',category:'20th-century prints',type:'Print'},
    {id:'r21',label:'21세기 판화',category:'21st-century prints',type:'Print'},
    {id:'illustrations19',label:'19세기 공개 삽화',category:'19th-century illustrations',type:'Illustration'},
    {id:'japanese-print',label:'일본 목판화',category:'Japanese woodblock prints',type:'Print'},
    {id:'independent',label:'공개 창작자 작품',category:'Paintings by Wikipedians'}
  ]);
  function normalizeGlobalCommons(data,categoryId){
    const found=GLOBAL_OPEN_ART_CATEGORIES.find(x=>x.id===categoryId);
    if(!found)return [];
    const pages=data&&data.query&&data.query.pages;
    return (Array.isArray(pages)?pages:[]).filter(page=>
       !COMMONS_SCENE_BLOCK.test(string(page&&page.title))&&
       !/\b(?:detail(?:ed)?|verso|back side|framed|gallery wall|photograph of|museum interior)\b/i.test(string(page&&page.title))
    ).map(page=>{
      const info=page&&Array.isArray(page.imageinfo)?page.imageinfo[0]:null;
      const meta=info&&info.extmetadata||{};
      const mime=string(info&&info.mime).toLowerCase();
      const title=string(page&&page.title).replace(/^File:/i,'').replace(/\.(?:jpg|jpeg|png|webp)$/i,'').replace(/_/g,' ');
      return {
        key:'commons:'+String(page&&page.pageid),source:'세계 공개 컬렉션 · '+found.label,
        title:wikimediaText(title)||'제목 미상',
        artist:wikimediaText(meta.Artist&&meta.Artist.value)||'작가 미상',
        image:string(info&&(info.thumburl||info.url)),
        width:Number(info&&info.width)||0,height:Number(info&&info.height)||0,
        type:found.type||'Painting',classification:found.type||'Painting',medium:'',
        description:'',license:wikimediaText(meta.LicenseShortName&&meta.LicenseShortName.value),
        rightsOK:commonsPublicDomain(meta)&&/^(?:image\/(?:jpeg|png|webp))$/.test(mime),
        museumRegion:'additional',verifiedCollectionCategory:false,style:'',styles:[],
        // A century-named category is NOT per-artwork reliable production-year evidence.
        date:'',yearStart:null,yearEnd:null,page:string(info&&info.descriptionurl)
      };
    });
  }

  // Mixed media category labels denote only the kind of work. Each image still
  // must pass rights, source, static MIME and pixel checks before exhibition.
  const MIXED_MEDIA_CATEGORIES=Object.freeze([
    {id:'photo-nature',category:'Nature photography',kind:'Photograph',label:'자연 사진'},
    {id:'photo-landscape',category:'Landscape photographs',kind:'Photograph',label:'풍경 사진'},
    {id:'photo-wildlife',category:'Wildlife photographs',kind:'Photograph',label:'야생동물 사진'},
    {id:'photo-street',category:'Street photography',kind:'Photograph',label:'거리 사진'},
    {id:'photo-portrait',category:'Portrait photographs',kind:'Photograph',label:'인물 사진'},
    {id:'photo-architecture',category:'Architectural photography',kind:'Photograph',label:'건축 사진'},
    {id:'photo-history',category:'Historical photographs',kind:'Photograph',label:'역사 사진'},
    {id:'illus-botanical',category:'Botanical illustrations',kind:'Illustration',label:'식물 삽화'},
    {id:'illus-science',category:'Scientific illustrations',kind:'Illustration',label:'과학 삽화'},
    {id:'illus-books',category:"Children's book illustrations",kind:'Illustration',label:'동화책 삽화'},
    {id:'animation-still',category:'Animation stills',kind:'Animation Still',label:'애니메이션 스틸'},
    {id:'contemporary-art',category:'Contemporary art',kind:'Contemporary Art',label:'컨템포러리 아트'},
    {id:'street-art',category:'Street art',kind:'Street Art',label:'스트리트 아트'},
    {id:'graffiti',category:'Graffiti',kind:'Graffiti',label:'그래피티'}
  ]);
  function normalizeMixedMediaCommons(data,categoryId){
    const found=MIXED_MEDIA_CATEGORIES.find(x=>x.id===categoryId);
    if(!found)return [];
    const pages=(data&&data.query&&data.query.pages)||[];
    if(!Array.isArray(pages))return [];
    return pages.filter(page=>
      !COMMONS_SCENE_BLOCK.test(string(page&&page.title)) &&
      !/\b(?:framed|exhibition view|museum interior|photo of gallery)\b/i.test(string(page&&page.title))
    ).map(page=>{
      const info=page&&Array.isArray(page.imageinfo)?page.imageinfo[0]:null;
      const meta=(info&&info.extmetadata)||{};
      const mime=string(info&&info.mime).toLowerCase();
      const filename=string(page&&page.title).replace(/^File:/i,'').replace(/\.(?:jpg|jpeg|png|webp)$/i,'').replace(/_/g,' ');
      return {
        key:'commons:'+String(page&&page.pageid),
        source:'공개 이미지 아카이브 · '+found.label,
        title:wikimediaText(filename)||'제목 미상',
        artist:wikimediaText(meta.Artist&&meta.Artist.value)||'작가 미상',
        image:string(info&&(info.thumburl||info.url)),
        width:Number(info&&info.width)||0,height:Number(info&&info.height)||0,
        type:found.kind,classification:found.kind,medium:'',
        description:'',license:wikimediaText(meta.LicenseShortName&&meta.LicenseShortName.value),
        rightsOK:commonsPublicDomain(meta)&&/^image\/(?:jpeg|png|webp)$/.test(mime),
        museumRegion:'mixedMedia',mediaKind:found.kind,
        style:'',styles:[],date:'',yearStart:null,yearEnd:null,
        page:string(info&&info.descriptionurl)
      };
    });
  }
  function shuffledCopy(items,rng=Math.random){
    const result=Array.isArray(items)?items.slice():[];
    for(let i=result.length-1;i>0;i--){
      const v=Number(rng());
      const r=Number.isFinite(v)?Math.min(Math.max(v,0),.999999999):.5;
      const j=Math.floor(r*(i+1));
      [result[i],result[j]]=[result[j],result[i]];
    }
    return result;
  }
  function artworkYearLabel(art){
    if(!art)return '연도 미상';
    const valid=x=>x!==undefined&&x!==null&&x!==''&&Number.isInteger(Number(x))&&
      Number(x)>=0&&Number(x)<=RECENT_YEAR_MAX;
    const a=art.yearStart,b=art.yearEnd;
    if(valid(a)&&valid(b)){
      if(Number(a)>Number(b))return '연도 미상';
      return Number(a)===Number(b)?String(Number(a)):String(Number(a))+'–'+String(Number(b));
    }
    if(valid(a))return String(Number(a));
    if(valid(b))return String(Number(b));
    const date=string(art.date).trim();
    return /^(?:c(?:irca)?\.?\s*)?(?:1\d{3}|20[0-2]\d)$/.test(date)?date:'연도 미상';
  }

  // "Modern" is a verified category with explicit year evidence or original
  // digital-art title, NOT a broad keyword search of historic reproductions.
  const MODERN_CATEGORIES = Object.freeze([
    {id:'2020s',label:'2020년대 회화',category:'2020s paintings'},
    {id:'2010s',label:'2010년대 회화',category:'2010s paintings'},
    {id:'contemporary',label:'현대 회화',category:'Contemporary paintings'},
    {id:'creator',label:'창작자 직접 공개 회화',category:'Paintings by Wikipedians'},
    {id:'century',label:'21세기 회화',category:'21st-century paintings'}
  ]);
  const MODERN_OPENVERSE_TERMS = Object.freeze([
    'digital painting','digital illustration','abstract digital artwork'
  ]);
  const MODERN_TITLE_BLOCK = /(?:photograph(?:y)?|photo of|portrait of visitors|exhibition|gallery view|museum interior|sculpture|statue|installation|poster for|album cover|book cover|screenshot|game screen|t-shirt|logo|wallpaper|sample scan|reproduction|recreated|copy after|printed in|image from page|manuscript of|circa 1[0-9]{3}|circa 19[0-8][0-9])/i;
  function modernYear(title,metaDate){
    const years=[...(string(title)+' '+string(metaDate)).matchAll(/\b20(?:0\d|1\d|2[0-6])\b/g)]
      .map(m=>Number(m[0]));
    return years.length?Math.max(...years):0;
  }
  function modernTitleEligible(title,metaDate){
    const t=string(title);
    if(MODERN_TITLE_BLOCK.test(t))return false;
    if(/\b(?:1[0-9]{3}|19[0-8][0-9])\b/.test(t))return false;
    return modernYear(t,metaDate)>=2000;
  }
  function normalizeModernCommons(data,categoryId){
    if(!MODERN_CATEGORIES.some(c=>c.id===categoryId))return [];
    const pages=data&&data.query&&data.query.pages;
    return (Array.isArray(pages)?pages:[]).map(page=>{
      const info=page&&Array.isArray(page.imageinfo)?page.imageinfo[0]:null;
      const meta=info&&info.extmetadata||{};
      const title=string(page&&page.title).replace(/^File:/i,'').replace(/\.(?:jpg|jpeg|png|webp)$/i,'').replace(/_/g,' ');
      const originalDate=wikimediaText(meta.DateTimeOriginal&&meta.DateTimeOriginal.value);
      const maker=wikimediaText(meta.Artist&&meta.Artist.value);
      const modern=modernTitleEligible(title,originalDate);
      return {
        key:'commons:'+String(page&&page.pageid),
        source:'위키미디어 현대 창작',title:wikimediaText(title)||'제목 미상',
        artist:maker||'작가 미상',image:string(info&&(info.thumburl||info.url)),
        width:Number(info&&info.width)||0,height:Number(info&&info.height)||0,
        type:'Painting',classification:'Painting',medium:'',
        description:'',license:wikimediaText(meta.LicenseShortName&&meta.LicenseShortName.value),
        rightsOK:modern&&commonsPublicDomain(meta)&&/^(?:image\/(?:jpeg|png|webp))$/.test(string(info&&info.mime).toLowerCase()),
        museumRegion:'modern',modern,modernEvidence:modern?'year-title':'',
        verifiedCollectionCategory:true,style:'Contemporary Art',styles:[],
        date:originalDate||String(modernYear(title,'')),page:string(info&&info.descriptionurl)
      };
    }).filter(a=>a.modern&&a.rightsOK);
  }
  function normalizeModernOpenverse(data){
    const results=data&&data.results;
    return (Array.isArray(results)?results:[]).map(item=>{
      const title=string(item&&item.title).replace(/<[^>]*>/g,' ').trim();
      const src=string(item&&item.url);
      const license=string(item&&item.license).toLowerCase();
      const directArt=/\b(?:digital painting|digital illustration|original digital artwork)\b/i.test(title);
      const reject=MODERN_TITLE_BLOCK.test(title)||/\b(?:1[0-9]{3}|19[0-9]{2})\b/.test(title);
      const sourceOK=item&&item.source==='wikimedia'&&safeURL(src)&&new URL(src).hostname==='upload.wikimedia.org';
      const rightsOK=directArt&&!reject&&sourceOK&&['cc0','pdm'].includes(license)&&!item.watermarked;
      return {
        key:'openverse:'+string(item&&item.id), source:'Openverse · 위키미디어',
        title:wikimediaText(title)||'제목 미상',
        artist:wikimediaText(item&&item.creator)||'작가 미상',
        image:src,width:Number(item&&item.width)||0,height:Number(item&&item.height)||0,
        type:/illustration/i.test(title)?'Illustration':'Painting',classification:'',medium:'',
        description:'',license,rightsOK, museumRegion:'modern',modern:rightsOK,
        modernEvidence:rightsOK?'original-digital-title':'',
        verifiedCollectionCategory:false,style:'Contemporary Art',styles:[],
        date:'',page:string(item&&item.foreign_landing_url)
      };
    }).filter(a=>a.modern&&a.rightsOK);
  }
  // Retained as a legacy helper. The 1800+ gallery uses targetPost1800,
  // not "modern digital art" as a proxy for artwork creation dates.
  function targetModern(slot){
    return ((Math.max(0,Math.floor(slot))*7+3)%20)<7;
  }
  const MODERN_THRESHOLD_YEAR=1800;
  const RECENT_YEAR_MAX=2026;
  function artworkEra(a){
    if(!a)return 'unknown';
    // Museum numerical creation dates take precedence over words in an art title.
    // A range crossing the 1800 boundary is unknown, rather than guessed.
    let start=a.yearStart, end=a.yearEnd;
    const isYear=v=>v!==null&&v!==undefined&&v!==''&&Number.isInteger(Number(v))
       &&Number(v)>=-4000&&Number(v)<=RECENT_YEAR_MAX;
    if(isYear(start)&&isYear(end)){
      start=Number(start);end=Number(end);
      if(start>end)return 'unknown';
      return start>=MODERN_THRESHOLD_YEAR?'post1800':
        end<MODERN_THRESHOLD_YEAR?'pre1800':'unknown';
    }
    // Explicitly identified original contemporary artwork with trustworthy metadata,
    // not a photograph of a work made before 1800.
    if(a.modern===true && a.rightsOK===true &&
       ['year-title','original-digital-title'].includes(a.modernEvidence))return 'post1800';
    // Commons file upload dates and museum accession years are NOT artwork dates.
    return 'unknown';
  }
  // Four post-1800 goals and one older/unclassified goal per five displays.
  // This is a demand/scheduling target; missing eligible files can reduce
  // the ACTUAL share, which must be measured separately.
  function targetPost1800(slot){
    const n=Number(slot);
    return Number.isFinite(n) && (Math.max(0,Math.floor(n))%5)<4;
  }
  function eraQuota90Days(){
    return Object.freeze({total:259200,post1800:207360,remainder:51840});
  }

  // 14 verified Oceania/South America Commons categories appended to the original seven.
  // Existing metadata licensing rules also apply to all new sources.
  // Conservative exclusions for exhibition-room, 3-D-object and framed photography filenames.
  const COMMONS_SCENE_BLOCK = /(?:gallery (?:interior|view|room)|museum (?:interior|hall|room)|exhibition (?:view|room|hall)|on (?:the )?wall|framed (?:painting|art)|sculpture|statue|installation|museum building|art gallery building|visitor|tour group|gallery entrance)/i;
  function wikimediaText(v) {
    return string(v).replace(/<[^>]*>/g,' ').replace(/&amp;/g,'&')
      .replace(/&#(?:x([0-9a-f]+)|([0-9]+));/gi, (all,h,d)=>{
        const cp=parseInt(h||d, h?16:10);
        return cp>31&&cp<=0x10ffff?String.fromCodePoint(cp):' ';
      }).replace(/&(?:nbsp|quot|lt|gt|#39);/gi,' ').replace(/\s+/g,' ').trim().slice(0,160);
  }
  function commonsPublicDomain(meta) {
    const short=wikimediaText(meta && meta.LicenseShortName && meta.LicenseShortName.value).toLowerCase();
    const license=wikimediaText(meta && meta.License && meta.License.value).toLowerCase();
    return /^(?:public domain|pd|cc0(?: 1\.0)?|cc0 1\.0 universal)$/.test(short) ||
      /^(?:pd|cc0)$/.test(license);
  }
  function normalizeAsianCommons(data, museumId) {
    const museum=ASIAN_MUSEUMS.find(m=>m.id===museumId);
    if(!museum)return [];
    const pages=data&&data.query&&data.query.pages;
    return (Array.isArray(pages)?pages:[]).map(page=>{
      const info=page&&Array.isArray(page.imageinfo)?page.imageinfo[0]:null;
      const metadata=info&&info.extmetadata||{};
      const mime=string(info&&info.mime).toLowerCase();
      const title=string(page&&page.title).replace(/^File:/i,'').replace(/\.(?:jpg|jpeg|png|webp)$/i,'').replace(/_/g,' ');
      return {
        key:'commons:'+String(page&&page.pageid),source:museum.label,
        title:wikimediaText(title)||'제목 미상',
        artist:wikimediaText(metadata.Artist&&metadata.Artist.value)||'작가 미상',
        image:string(info&&(info.thumburl||info.url)),
        width:Number(info&&info.width)||0,height:Number(info&&info.height)||0,
        type:'Painting',classification:'Painting',medium:'',
        description:'',license:wikimediaText(metadata.LicenseShortName&&metadata.LicenseShortName.value),
        rightsOK:commonsPublicDomain(metadata)&&/^(?:image\/(?:jpeg|png|webp))$/.test(mime),
        museumRegion:'asia',verifiedCollectionCategory:true,style:'',styles:[],date:'',
        page:string(info&&info.descriptionurl)
      };
    });
  }
  function normalizeAfricanCommons(data, museumId) {
    const museum=AFRICAN_MUSEUMS.find(m=>m.id===museumId);
    if(!museum)return [];
    const pages=data&&data.query&&data.query.pages;
    return (Array.isArray(pages)?pages:[]).filter(page=>!COMMONS_SCENE_BLOCK.test(string(page&&page.title))).map(page=>{
      const info=page&&Array.isArray(page.imageinfo)?page.imageinfo[0]:null;
      const metadata=info&&info.extmetadata||{};
      const mime=string(info&&info.mime).toLowerCase();
      const title=string(page&&page.title).replace(/^File:/i,'').replace(/\.(?:jpg|jpeg|png|webp)$/i,'').replace(/_/g,' ');
      return {
        key:'commons:'+String(page&&page.pageid),source:museum.label,
        title:wikimediaText(title)||'제목 미상',
        artist:wikimediaText(metadata.Artist&&metadata.Artist.value)||'작가 미상',
        image:string(info&&(info.thumburl||info.url)),
        width:Number(info&&info.width)||0,height:Number(info&&info.height)||0,
        type:'Painting',classification:'Painting',medium:'',
        description:'',license:wikimediaText(metadata.LicenseShortName&&metadata.LicenseShortName.value),
        rightsOK:commonsPublicDomain(metadata)&&/^(?:image\/(?:jpeg|png|webp))$/.test(mime),
        museumRegion:'africa',verifiedCollectionCategory:true,style:'',styles:[],date:'',
        page:string(info&&info.descriptionurl)
      };
    });
  }
  function normalizeAdditionalCommons(data, museumId) {
    const museum=ADDITIONAL_MUSEUMS.find(m=>m.id===museumId);
    if(!museum)return [];
    const pages=data&&data.query&&data.query.pages;
    return (Array.isArray(pages)?pages:[]).filter(page=>!COMMONS_SCENE_BLOCK.test(string(page&&page.title))&&!/\b(?:detail(?:ed)?|verso|back side|frame|gallery wall|portrait of visitors)\b/i.test(string(page&&page.title))).map(page=>{
      const info=page&&Array.isArray(page.imageinfo)?page.imageinfo[0]:null;
      const metadata=info&&info.extmetadata||{};
      const mime=string(info&&info.mime).toLowerCase();
      const title=string(page&&page.title).replace(/^File:/i,'').replace(/\.(?:jpg|jpeg|png|webp)$/i,'').replace(/_/g,' ');
      return {
        key:'commons:'+String(page&&page.pageid),source:museum.label,
        title:wikimediaText(title)||'제목 미상',
        artist:wikimediaText(metadata.Artist&&metadata.Artist.value)||'작가 미상',
        image:string(info&&(info.thumburl||info.url)),
        width:Number(info&&info.width)||0,height:Number(info&&info.height)||0,
        type:museum.type||'Painting',classification:museum.type||'Painting',medium:'',
        description:'',license:wikimediaText(metadata.LicenseShortName&&metadata.LicenseShortName.value),
        rightsOK:commonsPublicDomain(metadata)&&/^(?:image\/(?:jpeg|png|webp))$/.test(mime),
        museumRegion:'additional',verifiedCollectionCategory:true,style:'',styles:[],date:'',
        page:string(info&&info.descriptionurl)
      };
    });
  }
  function normalizeSmithsonianCommons(data,museumId){
    const museum=SMITHSONIAN_MUSEUMS.find(m=>m.id===museumId);
    if(!museum)return [];
    const pages=data&&data.query&&data.query.pages;
    const blocked=/\b(?:detail(?:ed)?|verso|back side|frame|gallery wall|portrait of visitors|original photograph|interior shot)\b/i;
    return (Array.isArray(pages)?pages:[])
      .filter(page=>!COMMONS_SCENE_BLOCK.test(string(page&&page.title))&&!blocked.test(string(page&&page.title)))
      .map(page=>{
        const info=page&&Array.isArray(page.imageinfo)?page.imageinfo[0]:null;
        const metadata=info&&info.extmetadata||{};
        const mime=string(info&&info.mime).toLowerCase();
        const title=string(page&&page.title).replace(/^File:/i,'').replace(/\.(?:jpg|jpeg|png|webp)$/i,'').replace(/_/g,' ');
        return {
          key:'commons:'+String(page&&page.pageid),source:museum.label,
          title:wikimediaText(title)||'제목 미상',
          artist:wikimediaText(metadata.Artist&&metadata.Artist.value)||'작가 미상',
          image:string(info&&(info.thumburl||info.url)),
          width:Number(info&&info.width)||0,height:Number(info&&info.height)||0,
          type:'Painting',classification:'Painting',medium:'',
          description:'',license:wikimediaText(metadata.LicenseShortName&&metadata.LicenseShortName.value),
          rightsOK:commonsPublicDomain(metadata)&&/^(?:image\/(?:jpeg|png|webp))$/.test(mime),
          museumRegion:museum.museumRegion,verifiedCollectionCategory:true,style:'',styles:[],date:'',
          page:string(info&&info.descriptionurl)
        };
      });
  }
  function fingerprint(a) {
    const norm = value => string(value).normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '').slice(0, 95);
    const title = norm(a.title), artist = norm(a.artist);
    return title.length >= 4 && artist.length >= 3 ? `fp:${title}:${artist}` : null;
  }
  // 'contain' occupies this fraction of a portrait display. Does not crop artwork.
  function portraitScreenFill(w,h,viewportW,viewportH){
    w=Number(w);h=Number(h);viewportW=Number(viewportW);viewportH=Number(viewportH);
    if(!(w>0&&h>0&&viewportW>0&&viewportH>0)||w>=h)return 0;
    const artRatio=w/h,screenRatio=Math.min(viewportW,viewportH)/Math.max(viewportW,viewportH);
    return Math.min(artRatio/screenRatio,screenRatio/artRatio);
  }
  function fillsPortraitScreen(w,h,vw,vh,threshold=.75){
    return portraitScreenFill(w,h,vw,vh)+1e-8>=threshold;
  }
  // Multiple museum records can point to one original Commons file.
  // Normalize URLs of Commons thumbnails and IIIF renditions before 90d lookup.
  function imageIdentity(a){
    const src=string(a&&a.image);
    try{
      const u=new URL(src);
      if(!safeURL(src))return null;
      let p=decodeURIComponent(u.pathname).replace(/\/thumb\/(?=[0-9a-f]\/)/i,'/');
      if(u.hostname==='upload.wikimedia.org')p=p.replace(/\/(?:\d+px-[^\/]+)$/i,'');
      if(u.hostname==='www.artic.edu'||u.hostname==='artic.edu')p=p.replace(/\/full\/[^/]+\/0\/default\.jpg$/i,'');
      return 'url:'+u.hostname.toLowerCase()+p.normalize('NFKC').toLowerCase().slice(0,225);
    }catch(_){return null;}
  }
  function identityKeys(a){
    if(!a)return [];
    const keys=[a.key,fingerprint(a),imageIdentity(a)];
    return [...new Set(keys.filter(x=>typeof x==='string'&&x.length>0&&x.length<=270))];
  }
  function hashDistance(a,b){
    if(!/^[0-9a-f]{16}$/.test(a||'')||!/^[0-9a-f]{16}$/.test(b||''))return 64;
    let n=0;
    for(let i=0;i<16;i++){
      let v=parseInt(a[i],16)^parseInt(b[i],16);
      while(v){n++;v&=v-1;}
    }
    return n;
  }
  function orientation(a) {
    const w = Number(a.width), h = Number(a.height);
    if (w > 0 && h > 0) return h > w * 1.02 ? 'portrait' : 'other';
    return 'unknown';
  }
  // EXACTLY seven portrait goals per 10 slots (orientation is a target, not a false guarantee).
  function targetOrientation(slot) { return ((Math.max(0, Math.floor(slot)) % 10) < 7) ? 'portrait' : 'other'; }
  function kstRenewalDay(epoch) {
    // KST midnight 10:00 boundary = 01:00 UTC. Use UTC-1h day-shift.
    return new Date(epoch - 60 * 60 * 1000).toISOString().slice(0, 10);
  }
  function canReshow(previous, now = Date.now()) {
    if (!Number.isFinite(previous)) return true;
    // Clock rolled back: never bypass a 90-day embargo.
    return now >= previous && now - previous >= NINETY_DAYS_MS;
  }
  function eligibleArt(a) {
    if (!a || !a.key || /:(?:undefined|null|NaN)$/.test(a.key) || !a.image || !safeURL(a.image) || !a.rightsOK) return false;
    const t = string(a.type).trim();
    const medium = string(a.medium).trim();
    const classification = string(a.classification).trim();
    const visualClass = [t, classification, medium].filter(Boolean).join(' | ');
    // Type (or known metadata) must explicitly identify a 2D visual work.
    if (!visualClass || !ALLOW_TYPES.test(visualClass)) return false;
    if (BLOCKLIST.test(visualClass)) return false;
    // Reject obvious photo-of-gallery or framed-object metadata; titles can refer to a painted frame,
    // so do not reject artwork titles for merely mentioning a frame.
    if (BLOCKLIST.test(string(a.description).slice(0, 160)) || /\b(?:photograph of (?:painting|sculpture|gallery)|photo of gallery)\b/i.test(string(a.description).slice(0,160))) return false;
    if (/\b(?:unknown|unverified|copyrighted|restricted)\b/i.test(string(a.license))) return false;
    return true;
  }
  function normalizeCleveland(item) {
    // CMA web rendition is only 900 px: use the CC0 print (3400 px) image when available.
    const img = item && item.images && (item.images.print || item.images.web);
    const creator = item && item.creators && item.creators[0];
    return {
      key: `cma:${item && item.id}`,
      source: '클리블랜드', title: string(item && item.title) || '제목 미상',
      artist: string(creator && creator.description) || '작가 미상',
      image: string(img && img.url),
      width: Number(img && img.width) || 0, height: Number(img && img.height) || 0,
      type: string(item && item.type), medium: string(item && item.technique),
      classification: string(item && item.type),
      description: '', license: string(item && item.share_license_status),
      rightsOK: (item && item.share_license_status) === 'CC0',
      style: string(item && item.style), styles: Array.isArray(item && item.style_titles) ? item.style_titles : [],
      date: string(item && item.creation_date),
      yearStart:item && item.creation_date_earliest, yearEnd:item && item.creation_date_latest,
      page: string(item && item.url)
    };
  }
  function normalizeChicago(item, iiifBase) {
    const imgid = string(item && item.image_id);
    const base = string(iiifBase).replace(/\/$/, '');
    // image_id comes from museum metadata; path may only contain safe token characters.
    const image = imgid && /^[a-zA-Z0-9_-]{15,100}$/.test(imgid) && /^https:\/\/www\.artic\.edu\/iiif\/2$/i.test(base)
      ? `${base}/${imgid}/full/2000,/0/default.jpg` : '';
    return {
      key: `aic:${item && item.id}`,
      source: '시카고', title: string(item && item.title) || '제목 미상',
      artist: string(item && item.artist_title) || '작가 미상',
      image,
      width: Number(item && item.thumbnail && item.thumbnail.width) || 0,
      height: Number(item && item.thumbnail && item.thumbnail.height) || 0,
      type: string(item && item.artwork_type_title),
      medium: string(item && item.medium_display), classification: string(item && item.artwork_type_title),
      description: '', license: 'Public domain',
      rightsOK: !!(item && item.is_public_domain),
      style: string(item && item.style_title), styles: Array.isArray(item && item.style_titles) ? item.style_titles : [],
      date: string(item && item.date_display),
      yearStart:item && item.date_start, yearEnd:item && item.date_end,
      page: item && Number.isInteger(item.id) ? `https://www.artic.edu/artworks/${item.id}` : ''
    };
  }
  function normalizeMet(item) {
    return {
      key: `met:${item && item.objectID}`,
      source: '메트로폴리탄', title: string(item && item.title) || '제목 미상',
      artist: string(item && item.artistDisplayName) || '작가 미상',
      image: string(item && (item.primaryImage || item.primaryImageSmall)),
      width: 0, height: 0,
      type: string(item && item.objectName), medium: string(item && item.medium),
      classification: string(item && item.classification),
      description: '', license: 'CC0',
      rightsOK: !!(item && item.isPublicDomain),
      style: string(item && item.period), styles: [], date: string(item && item.objectDate),
      yearStart:item && item.objectBeginDate, yearEnd:item && item.objectEndDate,
      department: string(item && item.department), page: string(item && item.objectURL)
    };
  }
  function pickCandidate(candidates, goal, seen, now) {
    function available(a) {
      if (!eligibleArt(a)) return false;
      const s = seen.get(a.key), fp = fingerprint(a), f = fp ? seen.get(fp) : null;
      return canReshow(s, now) && canReshow(f, now);
    }
    const exact = candidates.findIndex(a => available(a) && orientation(a) === goal);
    if (exact >= 0) return exact;
    const unknown = candidates.findIndex(a => available(a) && orientation(a) === 'unknown');
    if (unknown >= 0) return unknown;
    return candidates.findIndex(available);
  }

  // Art-history rotation: styles from museum metadata win; curated makers provide
  // a conservative fallback. No movement is inferred from the work's date alone.
  const MOVEMENTS = Object.freeze([
    {id:'renaissance', label:'르네상스', en:'Renaissance'},
    {id:'baroque', label:'바로크', en:'Baroque'},
    {id:'rococo', label:'로코코', en:'Rococo'},
    {id:'neoclassicism', label:'신고전주의', en:'Neoclassicism'},
    {id:'romanticism', label:'낭만주의', en:'Romanticism'},
    {id:'realism', label:'사실주의', en:'Realism'},
    {id:'impressionism', label:'인상주의', en:'Impressionism'},
    {id:'post-impressionism', label:'후기인상주의', en:'Post-Impressionism'},
    {id:'expressionism', label:'표현주의', en:'Expressionism'},
    {id:'cubism', label:'입체주의', en:'Cubism'},
    {id:'surrealism', label:'초현실주의', en:'Surrealism'},
    {id:'abstract', label:'추상미술', en:'Abstract Art'},
    {id:'contemporary', label:'현대미술', en:'Contemporary Art'},
    {id:'asian', label:'아시아 회화', en:'Asian painting'},
    {id:'african', label:'아프리카 소장 회화', en:'Paintings from African museum collections'},
    {id:'additional',label:'세계 미술관 소장 회화',en:'Museum painting collections worldwide'},
    {id:'modern',label:'현대 디지털 아트·회화',en:'Modern original flat artwork'}
  ]);
  const STYLE_RULES = [
    ['post-impressionism',/\bpost[\s-]*impressionis(?:m|t)\b/i],
    ['neoclassicism',/\bneo[\s-]*classic(?:ism|al)\b/i],
    ['renaissance',/\b(?:renaissance|early renaissance|high renaissance)\b/i],
    ['baroque',/\bbaroque\b/i],
    ['rococo',/\brococo\b/i],
    ['romanticism',/\bromantic(?:ism|ist)\b/i],
    ['realism',/\b(?:realism|realist|social realism)\b/i],
    ['impressionism',/\bimpressionis(?:m|t)\b/i],
    ['expressionism',/\b(?:expressionism|expressionist|die br[üu]cke|der blaue reiter)\b/i],
    ['cubism',/\bcubis(?:m|t)\b/i],
    ['surrealism',/\bsurreal(?:ism|ist)\b/i],
    ['abstract',/\b(?:abstract(?:ion| art| painting| expressionism)?|non[\s-]*objective art|geometric abstraction|suprematism|constructivism|color field)\b/i],
    ['contemporary',/\b(?:contemporary art|contemporary painting|conceptual painting|21st century art)\b/i]
  ];
  // Avoid makers whose work spans several schools (e.g. Picasso, Dali, Manet).
  // Cross-school artists must be classified using explicit museum style tags.
  const MAKER_RULES = [
    ['renaissance',['sandro botticelli','leonardo da vinci','michelangelo buonarroti','raphael sanzio','raffaello sanzio','titian','tiziano vecellio','albrecht dürer','albrecht durer','jan van eyck','hans holbein','piero della francesca','andrea mantegna','giovanni bellini','hieronymus bosch','giorgione']],
    ['baroque',['caravaggio','rembrandt van rijn','peter paul rubens','diego velázquez','diego velazquez','artemisia gentileschi','johannes vermeer','frans hals','anthony van dyck','guido reni','claude lorrain','nicolas poussin','pietro da cortona']],
    ['rococo',['jean-antoine watteau','antoine watteau','françois boucher','francois boucher','jean-honoré fragonard','jean-honore fragonard','giovanni battista tiepolo','thomas gainsborough','rosalba carriera']],
    ['neoclassicism',['jacques-louis david','jean-auguste-dominique ingres','antonio canova','angelica kauffman','anton raphael mengs','elisabeth vigée le brun','elisabeth vigee le brun','joseph-marie vien','benjamin west']],
    ['romanticism',['caspar david friedrich','eugène delacroix','eugene delacroix','théodore géricault','theodore gericault','j. m. w. turner','john constable','william blake','francisco de goya','henry fuseli','thomas cole']],
    ['realism',['gustave courbet','jean-françois millet','jean-francois millet','honoré daumier','honore daumier','rosa bonheur','ivan shishkin','ilya repin','winslow homer','thomas eakins']],
    ['impressionism',['claude monet','pierre-auguste renoir','alfred sisley','camille pissarro','berthe morisot','mary cassatt','gustave caillebotte','frédéric bazille','frederic bazille']],
    ['post-impressionism',['vincent van gogh','paul cézanne','paul cezanne','paul gauguin','georges seurat','paul signac','henri de toulouse-lautrec','émile bernard','emile bernard','henri-edmond cross']],
    ['expressionism',['edvard munch','ernst ludwig kirchner','egon schiele','emil nolde','karl schmidt-rottluff','erich heckel','oskar kokoschka','franz marc','august macke','käthe kollwitz','kathe kollwitz']],
    ['cubism',['juan gris','georges braque','fernand léger','fernand leger','jean metzinger','albert gleizes','robert delaunay','sonia delaunay']],
    ['surrealism',['rené magritte','rene magritte','max ernst','joan miró','joan miro','yves tanguy','leonora carrington','dorothea tanning','remedios varo','paul delvaux']],
    ['abstract',['wassily kandinsky','piet mondrian','kazimir malevich','hilma af klint','mark rothko','barnett newman','agnes martin','jackson pollock','helen frankenthaler','lyubov popova','el lissitzky','frank stella']],
    ['contemporary',['yoshitomo nara','takashi murakami','yayoi kusama','kerry james marshall','julie mehretu','cecil y brown','kehinde wiley','amy sherald','mark bradford','mickalene thomas']]
  ];
  function tidyLabel(text, fallback) {
    const t=string(text).replace(/[\uFFFD\u25A0-\u25FF\uE000-\uF8FF]/g,'').replace(/[\u0000-\u001f\u007f]/g,' ').replace(/\s+/g,' ').trim();
    return t && /[\p{L}\p{N}]/u.test(t) ? t.slice(0,160) : fallback;
  }
  function classifyMovement(a) {
    if(!a)return null;
    if(a.museumRegion==='modern' && a.modern===true && a.rightsOK)return 'modern';
    if(a.museumRegion==='asia' && a.verifiedCollectionCategory === true && a.rightsOK)return 'asian';
    if(a.museumRegion==='africa' && a.verifiedCollectionCategory === true && a.rightsOK)return 'african';
    if(a.source==='메트로폴리탄' && a.department==='Asian Art' && a.rightsOK)return 'asian';
    const styles = [string(a.style), ...(Array.isArray(a.styles)?a.styles.filter(x=>typeof x==='string'):[])].join(' | ');
    // Only curator-provided style fields can justify classifications such as cubism
    // for artists who worked in several movements.
    for(const [id,pattern] of STYLE_RULES) if(pattern.test(styles))return id;
    const artist=string(a.artist).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
    if(/\b(?:after|follower of|school of|workshop of|in the style of|copy after)\b/i.test(artist))return null;
    for(const [id,names] of MAKER_RULES)for(const name of names){
      const n=name.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
      const at=artist.indexOf(n);
      if(at>=0 && (at===0 || !/[a-z]/.test(artist[at-1])) &&
         (at+n.length===artist.length || !/[a-z]/.test(artist[at+n.length])))return id;
    }
    if(a.museumRegion==='additional' && a.verifiedCollectionCategory===true && a.rightsOK)return 'additional';
    return null;
  }
  function nextAvailableMovementIndex(start, has) {
    for(let i=0;i<MOVEMENTS.length;i++){
      const idx=(start+i)%MOVEMENTS.length;
      if(has(MOVEMENTS[idx].id))return idx;
    }
    return -1;
  }

  function prettyBytes(bytes) {
    const v = Number(bytes) || 0;
    return v < 1024 * 1024 ? `${(v / 1024).toFixed(0)}KB` : `${(v / (1024 * 1024)).toFixed(1)}MB`;
  }
  return { NINETY_DAYS_MS, MIN_IMAGE_SHORT_SIDE, MIN_IMAGE_LONG_SIDE, MIN_ACCEPTABLE_SHORT_SIDE, MIN_ACCEPTABLE_LONG_SIDE, highResolution, acceptableResolution, qualityTier, metadataResolutionOkay, safeURL, eligibleArt, fingerprint, orientation, targetOrientation,
    kstRenewalDay, canReshow, normalizeCleveland, normalizeChicago, normalizeMet, normalizeAsianCommons, ASIAN_MUSEUMS, normalizeAfricanCommons, AFRICAN_MUSEUMS, normalizeAdditionalCommons, ADDITIONAL_MUSEUMS, SMITHSONIAN_MUSEUMS, normalizeSmithsonianCommons, commonsPublicDomain,
    pickCandidate, prettyBytes, MOVEMENTS, classifyMovement, nextAvailableMovementIndex, tidyLabel,
    MODERN_CATEGORIES,MODERN_OPENVERSE_TERMS,normalizeModernCommons,normalizeModernOpenverse,targetModern,
    artworkEra,targetPost1800,eraQuota90Days,MODERN_THRESHOLD_YEAR,
    GLOBAL_OPEN_ART_CATEGORIES,normalizeGlobalCommons,MIXED_MEDIA_CATEGORIES,normalizeMixedMediaCommons,shuffledCopy,artworkYearLabel,
    portraitScreenFill, fillsPortraitScreen, imageIdentity, identityKeys, hashDistance };
});
