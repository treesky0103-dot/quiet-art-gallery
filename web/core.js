/* Artwork selection core. Zero external dependencies. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.GalleryCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const NINETY_DAYS_MS = 90 * 24 * 60 * 60 * 1000;
  // Minimum decoded image resolution. Never upscale a small original.
  const MIN_IMAGE_SHORT_SIDE = 1200;
  const MIN_IMAGE_LONG_SIDE = 1600;
  function highResolution(width,height){
    const w=Number(width),h=Number(height);
    return Number.isFinite(w)&&Number.isFinite(h)&&w>0&&h>0&&Math.min(w,h)>=MIN_IMAGE_SHORT_SIDE&&Math.max(w,h)>=MIN_IMAGE_LONG_SIDE;
  }
  function metadataResolutionOkay(a){
    if(!a)return false;
    // Commons source dimensions and Cleveland web rendition can be checked before download.
    if(a.museumRegion==='asia'||a.museumRegion==='africa'||a.museumRegion==='additional'||a.source==='클리블랜드')return highResolution(a.width,a.height);
    return true; // Other sources must pass the decoded-image check.
  }
  const BLOCKLIST = /(?:\bsculpture\b|\bceramic(?:s)?\b|\bpottery\b|\bfurniture\b|\btextile\b|\btapestry\b|\barmor\b|\barmour\b|\bweapon\b|\bphotograph(?:y)?\b|\binstallation\b|\bstatue\b|\bvase\b|\bcoin\b|\bmedal\b|\bjewelry\b|\bjewellery\b|\barchitecture\b|\bdecorative art\b|\bframe(?:d)?\b|\bgallery view\b|\bexhibition view\b|\b3d\b|\bvideo\b|\bfilm\b|\bglass\b|\bcarpet\b|\bcostume\b|\bcarving\b|\brelief\b|\bbook cover\b)/i;
  const ALLOW_TYPES = /(?:painting|paintings|drawing|drawings|print|prints|watercolo[u]?r|etching|lithograph|woodblock|woodcut|illustration|gouache|collage|pastel|ink on paper|oil on canvas|oil on panel|acrylic on|tempera on|aquatint|serigraph|screenprint|engraving)/i;
  function string(x) { return typeof x === 'string' ? x : ''; }
  function safeURL(url) {
    try {
      const u = new URL(url);
      if (u.protocol !== 'https:' || u.username || u.password || (u.port && u.port !== '443')) return false;
      const h = u.hostname.toLowerCase();
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
    {id:"brasil-pina",label:"브라질 상파울루 피나코테카",category:"Paintings in the Pinacoteca do Estado de São Paulo"}
  ]);
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
        type:'Painting',classification:'Painting',medium:'',
        description:'',license:wikimediaText(metadata.LicenseShortName&&metadata.LicenseShortName.value),
        rightsOK:commonsPublicDomain(metadata)&&/^(?:image\/(?:jpeg|png|webp))$/.test(mime),
        museumRegion:'additional',verifiedCollectionCategory:true,style:'',styles:[],date:'',
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
  function fillsPortraitScreen(w,h,vw,vh,threshold=.80){
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
    if (BLOCKLIST.test(string(a.description).slice(0, 160))) return false;
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
      date: string(item && item.creation_date), page: string(item && item.url)
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
      date: string(item && item.date_display), page: item && Number.isInteger(item.id) ? `https://www.artic.edu/artworks/${item.id}` : ''
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
    {id:'additional',label:'세계 미술관 소장 회화',en:'Museum painting collections worldwide'}
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
  return { NINETY_DAYS_MS, MIN_IMAGE_SHORT_SIDE, MIN_IMAGE_LONG_SIDE, highResolution, metadataResolutionOkay, safeURL, eligibleArt, fingerprint, orientation, targetOrientation,
    kstRenewalDay, canReshow, normalizeCleveland, normalizeChicago, normalizeMet, normalizeAsianCommons, ASIAN_MUSEUMS, normalizeAfricanCommons, AFRICAN_MUSEUMS, normalizeAdditionalCommons, ADDITIONAL_MUSEUMS, commonsPublicDomain,
    pickCandidate, prettyBytes, MOVEMENTS, classifyMovement, nextAvailableMovementIndex, tidyLabel,
    portraitScreenFill, fillsPortraitScreen, imageIdentity, identityKeys, hashDistance };
});
