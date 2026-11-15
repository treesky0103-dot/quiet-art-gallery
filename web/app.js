(function () {
  'use strict';
  const C = window.GalleryCore;
  const CONFIG = Object.freeze({intervalMs: 60000, minPool: 28, targetPool: 350, maxQueue: 7200, prefetch: 1, retryMs: 20000, pruneDays: 90, movementRetryMs: 5*60*1000, minimumPortraitFill:.75, collectorEveryMs:1800000, collectorTickMs:15000, collectorMaxPerTick:6, collectorMaxAttemptsPerTick:18, savedCandidateLimit:1000});
  const test = window.__GALLERY_TEST__ || null;
  const INTERVAL = test && test.intervalMs >= 100 ? test.intervalMs : CONFIG.intervalMs;
  const el = id => document.getElementById(id);
  const ui = {a:el('art-a'),b:el('art-b'), placeholder:el('placeholder'), status:el('main-status'),hud:el('hud'),
    caption:el('caption'),title:el('art-title'),meta:el('art-meta'),settings:el('settings'), backdrop:el('settings-backdrop'),
    pause:el('toggle-pause'),done:el('settings-done'),msg:el('setting-message')};
  const state = {
    collectorStopReason:'', offlineManifestCount:0, cacheSnapshot:null, cacheSnapshotAt:0,
    downloadedKeys:new Set(),downloadedVisualHashes:new Map(),downloadedURLs:new Set(),
    inflightVisualHashes:new Map(),offlineUnseenReady:0,inventoryUpdatedAt:0,networkOnline:true,collectorRejectedKeys:new Set(),
    db:null,pool:[],pendingKeys:new Set(), prepared:null,current:null,currentNode:ui.b,
    playing:true,busy:false,filling:null,preparing:null,timer:null,hideTimer:null,lastRendered:null,
    offlineReady:[],recentLoaded:[],recentDisplayed:new Set(),emergencyIndex:0,emergencySwaps:0,
    recentKeys:new Map(),visualHashes:new Map(),dedupBlocked:0,exhaustedTicks:0,
    lastSwapAt:0, nextDueAt:0,nativeClock:false,tickCount:0,
    cursors:{cleveland:{Painting:0,Drawing:0,Print:0,Photograph:0},chicago:1,met:{'11':0,'9':0,'21':0,'6':0},asian:{},african:{},additional:{},smithsonian:{},modern:{},openverseModern:{},media:{},movement:{},wellcome:{},princeton:{},smithsonianNpgShard:0,smithsonianChndmShard:0,smithsonianNmaahcShard:0,smithsonianFsgShard:0},
    sourceOrder:0,cmaType:0,metType:0,metIDs:[],metIndex:0, asianOrder:0, africanOrder:0, additionalOrder:0, smithsonianOrder:0, smithsonianCategoryOrder:0,globalCategoryIndex:0,wellcomeIndex:0,princetonIndex:0,
    modernOrder:0,modernCategoryIndex:0,modernOpenverseIndex:0,mediaCategoryIndex:0,movementTermIndex:0,movementQueries:[],modernFetched:0,modernErrors:0, collectorRunning:false,collectorLastAt:0,collectorSuccess:0,collectorErrors:0,collectorTimer:null,prefetchedKeys:new Set(),collectorWindowStarted:0,collectorWindowSaved:0,collectorDayKey:'',collectorDaySaved:0,collectorLastIndexAt:0,collectorRetry:{},collectorThrottled:0,
    movementPages:{},lastMovementTry:{}, flipped:false, audit:null, auditing:false,
    failures:{global:0,cleveland:0,chicago:0,met:0,asian:0,african:0,additional:0,smithsonian:0,modern:0,media:0,movement:0,wellcome:0,princeton:0,smNpg:0,smChndm:0,smNmaahc:0,smFsg:0},backoff:{},
    stats:{slot:0,shown:0,portrait:0,other:0,modernShown:0,post1800Shown:0,updatedAt:'',day:'',movementIndex:0},
    apiCalls:0,lastErr:'',sourceReady:[],lastTime:0
  };
  const sourceNames={global:'세계 공개 아카이브',cleveland:'클리블랜드',chicago:'시카고',met:'메트로폴리탄',asian:'아시아 박물관(공용 자료)',african:'아프리카 박물관(공용 자료)',additional:'세계 미술관(공용 자료)',smithsonian:'스미스소니언 미국미술관·국립아시아미술관(공개 회화)',modern:'현대 창작 · Openverse / 위키미디어',media:'사진·일러스트·애니메이션 스틸(공개 아카이브)',movement:'전 세계 사조·화파 (검증된 정지 이미지)',wellcome:'웰컴 컬렉션(PDM 직접 API)',princeton:'프린스턴 대학교 미술관(퍼블릭 도메인 IIIF)',smNpg:'스미스소니언 국립초상화미술관(직접 CC0)',smChndm:'쿠퍼 휴잇 디자인 박물관(직접 CC0)',smNmaahc:'국립아프리카계미국인역사문화박물관(직접 CC0)',smFsg:'스미스소니언 국립아시아미술관(직접 CC0)'};
  function inform(message){ ui.status.textContent=message; ui.msg.textContent=message; }
  function wait(ms){return new Promise(r=>setTimeout(r,ms));}
  function openDB(){
    return new Promise((resolve,reject)=>{
      if(!window.indexedDB) return reject(new Error('IndexedDB 지원 없음'));
      const r=indexedDB.open('quiet-art-gallery-v1',2);
      r.onupgradeneeded=()=>{const db=r.result;
        if(!db.objectStoreNames.contains('seen')){const seen=db.createObjectStore('seen',{keyPath:'key'});seen.createIndex('when','when');}
        if(!db.objectStoreNames.contains('settings'))db.createObjectStore('settings',{keyPath:'key'});
        // Unshown, fully downloaded images survive closing and reopening the app.
        if(!db.objectStoreNames.contains('downloaded'))db.createObjectStore('downloaded',{keyPath:'key'});
      };
      r.onsuccess=()=>resolve(r.result); r.onerror=()=>reject(r.error||new Error('DB 연결 실패'));
    });
  }
  function dbGet(store,key){return new Promise((resolve,reject)=>{
    const t=state.db.transaction(store,'readonly'),r=t.objectStore(store).get(key);
    r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);
  });}
  function dbPutMany(store,entries){return new Promise((resolve,reject)=>{
    const t=state.db.transaction(store,'readwrite'),s=t.objectStore(store);
    for(const entry of entries)s.put(entry);
    t.oncomplete=resolve;t.onerror=()=>reject(t.error);t.onabort=()=>reject(t.error);
  });}
  function dbDelete(store,key){return new Promise((resolve,reject)=>{
    const tx=state.db.transaction(store,'readwrite');
    tx.objectStore(store).delete(key);
    tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
  });}
  function dbClear(store){return new Promise((resolve,reject)=>{
    const tx=state.db.transaction(store,'readwrite');
    tx.objectStore(store).clear();
    tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
  });}
  async function persist(){await dbPutMany('settings',[{key:'stats',value:state.stats},{key:'cursors',value:state.cursors},{key:'globalCategoryIndex',value:state.globalCategoryIndex}]);}
  function rowKeys(art,hash){
    const keys=C.identityKeys(art);
    if(hash)keys.push('vis:'+hash);
    return [...new Set(keys)];
  }
  function visuallySeen(hash,now=Date.now()){
    if(!hash)return false;
    for(const [prior,when] of state.visualHashes)
      if(!C.canReshow(when,now)&&C.hashDistance(hash,prior)<=2)return true;
    return false;
  }
  function seenInMemory(art,hash){
    const now=Date.now();
    if(rowKeys(art,hash).some(k=>
      state.recentKeys.has(k)&&!C.canReshow(state.recentKeys.get(k),now)))return true;
    return visuallySeen(hash,now);
  }
  async function hydrateHistory(){
    if(!state.db)return;
    state.recentKeys.clear();state.visualHashes.clear();
    await new Promise((resolve,reject)=>{
      const tx=state.db.transaction('seen','readonly'),cursor=tx.objectStore('seen').openCursor();
      cursor.onsuccess=()=>{
        const c=cursor.result;if(!c)return;
        const when=Number(c.value&&c.value.when),key=String(c.key);
        if(Number.isFinite(when)&&!C.canReshow(when,Date.now())){
          state.recentKeys.set(key,when);
          if(/^vis:[0-9a-f]{16}$/.test(key))state.visualHashes.set(key.slice(4),when);
        }
        c.continue();
      };
      tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
    });
  }
  async function seenRecently(art,hash){
    if(seenInMemory(art,hash))return true;
    const now=Date.now();
    for(const key of rowKeys(art,hash)){
      const entry=await dbGet('seen',key);
      if(entry&&!C.canReshow(entry.when,now)){
        state.recentKeys.set(key,entry.when);
        if(key.startsWith('vis:'))state.visualHashes.set(key.slice(4),entry.when);
        return true;
      }
    }
    return visuallySeen(hash,now);
  }
  function markSeen(show){
    const when=Date.now();
    for(const key of rowKeys(show.art,show.visualHash)){
      state.recentKeys.set(key,when);
      if(key.startsWith('vis:'))state.visualHashes.set(key.slice(4),when);
    }
    // Reserve the next 1800+ quota slot synchronously BEFORE prefetch begins.
    // IndexedDB writes must not cause 80/20 scheduling drift.
    state.stats.slot++;state.stats.shown++;
    if(C.artworkEra(show.art)==='post1800')state.stats.post1800Shown=(Number(state.stats.post1800Shown)||0)+1;
    if(show.art.modern===true)state.stats.modernShown=(Number(state.stats.modernShown)||0)+1;
    state.stats[show.orient==='portrait'?'portrait':'other']++;
  }
  async function recordSeen(show){
    const when=Date.now();
    await dbPutMany('seen',rowKeys(show.art,show.visualHash).map(key=>({key,when})));
    await persist();
  }
  function visualHash(img){
    try{
      const c=document.createElement('canvas');c.width=9;c.height=8;
      const g=c.getContext('2d',{willReadFrequently:true});if(!g)return null;
      g.drawImage(img,0,0,9,8);
      const px=g.getImageData(0,0,9,8).data;
      const l=[];let low=255,high=0;
      for(let i=0;i<px.length;i+=4){
        const v=Math.round(.299*px[i]+.587*px[i+1]+.114*px[i+2]);
        l.push(v);low=Math.min(low,v);high=Math.max(high,v);
      }
      if(high-low<18)return null; // Flat synthetic image does not support a perceptual hash.
      let hex='',bits=0,n=0;
      for(let y=0;y<8;y++)for(let x=0;x<8;x++){
        bits=(bits<<1)|(l[y*9+x]>l[y*9+x+1]?1:0);
        if(++n===4){hex+=bits.toString(16);bits=0;n=0;}
      }
      return hex;
    }catch(_){return null;} // Cross-origin browser images retain URL/title protections.
  }
  function imageURL(art){
    if(!C.safeURL(art.image))return '';
    // Strict offline-asset whitelist; runtime JSON cannot inject arbitrary asset paths.
    if(window.GalleryAndroid && /^(?:offline\/fallback-(?:[0-9]|1[0-5])|offline\/pack-[0-9]{4})\.jpg$/.test(art.offlineAsset||'')){
      return 'https://appassets.gallery/'+art.offlineAsset;
    }
    if(window.GalleryAndroid) return 'https://appassets.gallery/art-image?u='+encodeURIComponent(art.image);
    return art.image;
  }
  async function loadImage(art){
    const src=imageURL(art);
    if(!src)throw new Error('이미지 주소 검증 실패');
    const img=new Image();img.decoding='async';
    img.referrerPolicy='no-referrer';
    await new Promise((resolve,reject)=>{
      let finished=false;
      const timeout=setTimeout(()=>{if(finished)return;finished=true;img.src='';reject(new Error('이미지 로딩 시간 초과'));},17000);
      img.onload=()=>{if(finished)return;finished=true;clearTimeout(timeout);resolve();};
      img.onerror=()=>{if(finished)return;finished=true;clearTimeout(timeout);reject(new Error('이미지 파일 로드 실패'));};
      img.src=src;
    });
    if(!C.acceptableResolution(img.naturalWidth,img.naturalHeight))throw new Error('최소 중화질 미달 (짧은 변 1000px·긴 변 1400px)');
    if(!C.fillsPortraitScreen(img.naturalWidth,img.naturalHeight,innerWidth,innerHeight,CONFIG.minimumPortraitFill))
      throw new Error('세로 화면 75% 미만 작품 제외');
    return {art,src,width:img.naturalWidth,height:img.naturalHeight,orient:'portrait',visualHash:visualHash(img)};
  }

  async function loadMovementCatalog(){
    try{
      const r=await fetch('https://appassets.gallery/art-movements.json',{cache:'no-store'});
      if(!r.ok)throw Error('movement catalog not yet served');
      const catalog=await r.json();
      const items=(catalog.groups||[]).flatMap(x=>Array.isArray(x.movements)?x.movements:[])
          .filter(x=>x&&typeof x.name_ko==='string'&&(typeof x.search_en==='string'||x.search_en===null));
      if(items.length!==catalog.entry_count||items.length<375)throw Error('Movement count mismatch');
      state.movementQueries=items;
      return items.length;
    }catch(e){
      state.movementQueries=[];
      state.lastErr='사조별 상세 검색 목록: '+String(e.message||e);
      return 0; // Non-blocking. Existing 1511+ still artworks remain playable.
    }
  }

  async function loadOfflineDeck(){
    if(!window.GalleryAndroid)return 0;
    try{
      const r=await fetch('https://appassets.gallery/offline-deck.json',{cache:'no-store'});
      if(!r.ok)throw Error('비상 작품 목록 없음');
      const items=await r.json();
      if(Array.isArray(items))state.offlineManifestCount=items.length;
      if(!Array.isArray(items)||items.length<2||items.length>2700)throw Error('내장 작품 목록 형식 오류');
      const all=C.shuffledCopy(items.filter(art=>
        /^(?:offline\/fallback-(?:[0-9]|1[0-5])|offline\/pack-[0-9]{4})\.jpg$/.test(art.offlineAsset||'') &&
        C.eligibleArt(art) && C.metadataResolutionOkay(art)));
      state.offlineUnseenReady=all.filter(a=>!state.recentKeys.has(a.key)).length;
      const loaded=[];
      // Load an initial dozen. Pace later decoding in small batches so
      // background prefetch does not starve low-memory tablets.
      for(const art of all.slice(0,12)){
        art.movement=C.classifyMovement(art)||'additional';
        try{loaded.push(await loadImage(art));}catch(e){state.lastErr='내장 작품: '+e.message;}
      }
      state.offlineReady=loaded;
      let index=12;
      async function preloadMore(){
        for(let k=0;k<4 && index<all.length;k++,index++){
          const art=all[index];
          art.movement=C.classifyMovement(art)||'additional';
          try{state.offlineReady.push(await loadImage(art));}
          catch(e){state.lastErr='내장 작품 점검: '+e.message;}
        }
        if(index<all.length)setTimeout(()=>preloadMore().catch(()=>{}),2000);
        else updateInfo();
      }
      if(index<all.length)setTimeout(()=>preloadMore().catch(()=>{}),2000);
      return loaded.length;
    }catch(e){state.lastErr='비상 작품 준비: '+e.message;return 0;}
  }
  function normalizeBatch(kind,result){
    if(kind==='cleveland')return (Array.isArray(result.data)?result.data:[]).map(C.normalizeCleveland);
    if(kind==='chicago')return (Array.isArray(result.data)?result.data:[]).map(x=>C.normalizeChicago(x, result.config && result.config.iiif_url || 'https://www.artic.edu/iiif/2'));
    if(kind==='openverseModern')return C.normalizeModernOpenverse(result);
    if(kind==='wellcome')return (Array.isArray(result.results)?result.results:[]).map(C.normalizeWellcome).filter(Boolean);
    if(kind==='smithsonianShard')return (Array.isArray(result.results)?result.results:[]).filter(C.eligibleArt);
    return [];
  }
  let requestNum=0;
  const androidRequests=new Map();
  window.__galleryResolve=(reqId,success,data)=>{
    const entry=androidRequests.get(String(reqId));if(!entry)return;
    androidRequests.delete(String(reqId));clearTimeout(entry.timeout);
    if(success){try{entry.resolve(JSON.parse(data));}catch(e){entry.reject(e);}}
    else entry.reject(new Error(String(data).slice(0,160)));
  };
  async function request(kind,param){
    state.apiCalls++;
    if(test&&typeof test.request==='function')return test.request(kind,param);
    if(window.GalleryAndroid&&typeof window.GalleryAndroid.requestJson==='function'){
      const id=String(++requestNum);
      return new Promise((resolve,reject)=>{
        const timeout=setTimeout(()=>{androidRequests.delete(id);reject(new Error('응답 시간 초과'));},22000);
        androidRequests.set(id,{resolve,reject,timeout});
        try{window.GalleryAndroid.requestJson(kind,String(param),id);}catch(e){clearTimeout(timeout);androidRequests.delete(id);reject(e);}
      });
    }
    let url='';
    if(kind==='smithsonianShard'){
      // Android's native bridge fetches a fixed public S3 NDJSON shard and
      // returns only image-specific CC0 2D object records.
      throw Error('Smithsonian direct S3 artwork collection is Android-only');
    }else if(kind==='cleveland'){
      const [type,offset]=String(param).split(':');
      url=`https://openaccess-api.clevelandart.org/api/artworks/?cc0&has_image=1&type=${encodeURIComponent(type)}&limit=100&skip=${Number(offset)||0}`;
    }else if(kind==='chicago'||kind==='chicagoMovement'){
      let page=Math.max(1,parseInt(param,10)||1);
      const isMovement=kind==='chicagoMovement';
      const movement=isMovement?C.MOVEMENTS.find(m=>m.id===String(param).split(':')[0]):null;
      if(isMovement&&!movement)throw Error('허용되지 않은 사조');
      if(isMovement){
        const pieces=String(param).split(':');
        if(pieces.length!==2)throw Error('사조 페이지 오류');
        page=Math.max(1,parseInt(pieces[1],10)||1);
      }
      const params={query:{bool:{filter:[{term:{is_public_domain:true}},{exists:{field:'image_id'}}]}},page,limit:100,fields:['id','title','artist_title','image_id','is_public_domain','artwork_type_title','medium_display','thumbnail','style_title','style_titles','date_display','date_start']};
      if(isMovement)params.query.bool.must=[{multi_match:{query:movement.en,fields:['style_title^5','style_titles^4','term_titles^2','artist_title','title']}}];
      url=`https://api.artic.edu/api/v1/artworks/search?params=${encodeURIComponent(JSON.stringify(params))}`;
    }else if(kind==='globalCommons'){
      const parts=String(param).split(':');
      const cat=C.GLOBAL_OPEN_ART_CATEGORIES.find(x=>x.id===parts[0]);
      const offset=Number(parts[1]);
      if(parts.length!==2||!cat||!Number.isInteger(offset)||offset<0||offset>100000)
        throw Error('공개 미술 소스 검색 조건 오류');
      const qs=new URLSearchParams({action:'query',generator:'search',
        gsrsearch:'deepcategory:"'+cat.category+'"',gsrnamespace:'6',
        gsrlimit:'50',gsroffset:String(offset),prop:'imageinfo',
        iiprop:'url|size|mime|extmetadata',iiurlwidth:'2000',format:'json',formatversion:'2',origin:'*'});
      url='https://commons.wikimedia.org/w/api.php?'+qs.toString();
    }else if(kind==='movementCommons'){
      const parts=String(param).split(':');
      const idx=Number(parts[0]),offset=Number(parts[1]);
      const school=state.movementQueries[idx];
      if(parts.length!==2||!school||!Number.isInteger(idx)||
         !Number.isInteger(offset)||offset<0||offset>2500)throw Error('사조 검색 범위 오류');
      const phrase=(school.search_en||school.name_ko).trim();
      const q=phrase+' painting drawing illustration photograph';
      const qs=new URLSearchParams({action:'query',generator:'search',
        gsrsearch:q,gsrnamespace:'6',gsrlimit:'25',gsroffset:String(offset),
        prop:'imageinfo',iiprop:'url|size|mime|extmetadata',iiurlwidth:'2000',
        format:'json',formatversion:'2',origin:'*'});
      url='https://commons.wikimedia.org/w/api.php?'+qs.toString();
    }else if(kind==='mediaCommons'){
      const parts=String(param).split(':');
      const cat=C.MIXED_MEDIA_CATEGORIES.find(x=>x.id===parts[0]);
      const offset=Number(parts[1]);
      if(parts.length!==2||!cat||!Number.isInteger(offset)||offset<0||offset>100000)
        throw Error('복합 매체 검색 조건 오류');
      const qs=new URLSearchParams({action:'query',generator:'search',
        gsrsearch:'deepcategory:"'+cat.category+'"',gsrnamespace:'6',
        gsrlimit:'50',gsroffset:String(offset),prop:'imageinfo',
        iiprop:'url|size|mime|extmetadata',iiurlwidth:'2000',format:'json',formatversion:'2',origin:'*'});
      url='https://commons.wikimedia.org/w/api.php?'+qs.toString();
    }else if(kind==='asianCommons'||kind==='africanCommons'||kind==='additionalCommons'){
      const [museumId, offsetText]=String(param).split(':');
      const museums=kind==='africanCommons'?C.AFRICAN_MUSEUMS:kind==='additionalCommons'?C.ADDITIONAL_MUSEUMS:C.ASIAN_MUSEUMS;
      const museum=museums.find(m=>m.id===museumId);
      const offset=Number(offsetText);
      if(!museum||!Number.isInteger(offset)||offset<0||offset>100000)throw Error('박물관 소장품 조회 범위 오류');
      const query='deepcategory:"'+museum.category+'"';
      const qs=new URLSearchParams({action:'query',generator:'search',gsrsearch:query,
        gsrnamespace:'6',gsrlimit:'50',gsroffset:String(offset),prop:'imageinfo',
        iiprop:'url|size|mime|extmetadata',iiurlwidth:'2000',format:'json',formatversion:'2',origin:'*'});
      url='https://commons.wikimedia.org/w/api.php?'+qs.toString();
    }else if(kind==='smithsonianCommons'){
      const [museumId,catText,offsetText]=String(param).split(':');
      const museum=C.SMITHSONIAN_MUSEUMS.find(m=>m.id===museumId);
      const idx=Number(catText),offset=Number(offsetText);
      if(!museum||!Number.isInteger(idx)||idx<0||idx>=museum.categories.length||
         !Number.isInteger(offset)||offset<0||offset>100000)throw Error('스미스소니언 작품 검색 조건 오류');
      const qs=new URLSearchParams({action:'query',generator:'search',
        gsrsearch:'deepcategory:"'+museum.categories[idx]+'"',gsrnamespace:'6',
        gsrlimit:'50',gsroffset:String(offset),prop:'imageinfo',
        iiprop:'url|size|mime|extmetadata',iiurlwidth:'2000',format:'json',
        formatversion:'2',origin:'*'});
      url='https://commons.wikimedia.org/w/api.php?'+qs.toString();
    }else if(kind==='modernCommons'){
      const [id,offsetText]=String(param).split(':');
      const cat=C.MODERN_CATEGORIES.find(c=>c.id===id);
      const offset=Number(offsetText);
      if(!cat||!Number.isInteger(offset)||offset<0||offset>100000)throw Error('현대작품 검색 범위 오류');
      const qs=new URLSearchParams({action:'query',generator:'search',
        gsrsearch:'deepcategory:"'+cat.category+'"',gsrnamespace:'6',
        gsrlimit:'50',gsroffset:String(offset),prop:'imageinfo',
        iiprop:'url|size|mime|extmetadata',iiurlwidth:'2000',format:'json',
        formatversion:'2',origin:'*'});
      url='https://commons.wikimedia.org/w/api.php?'+qs.toString();
    }else if(kind==='princetonSearch'){
      const parts=String(param).split(':'),idx=Number(parts[0]),offset=Number(parts[1]);
      if(parts.length!==2||!Number.isInteger(idx)||idx<0||idx>=C.PRINCETON_TERMS.length||
          !Number.isInteger(offset)||offset<0||offset>3000||offset%20)
        throw Error('프린스턴 검색 범위 오류');
      url='https://data.artmuseum.princeton.edu/search?'+new URLSearchParams({
        q:C.PRINCETON_TERMS[idx],type:'artobjects',size:'20',from:String(offset)
      });
    }else if(kind==='princetonObject'){
      const n=Number(param);
      if(!Number.isInteger(n)||n<1||n>9999999)throw Error('프린스턴 작품 ID 오류');
      url='https://data.artmuseum.princeton.edu/objects/'+n;
    }else if(kind==='wellcome'){
      const parts=String(param).split(':');
      const ix=Number(parts[0]),page=Number(parts[1]);
      if(parts.length!==2||!Number.isInteger(ix)||ix<0||ix>=C.WELLCOME_TERMS.length||
         !Number.isInteger(page)||page<1||page>250)
        throw Error('Wellcome 공개 이미지 검색 인자 오류');
      const qs=new URLSearchParams({query:C.WELLCOME_TERMS[ix],
        'locations.license':'pdm','include':'source.genres,source.contributors',
        page:String(page),pageSize:'50'});
      url='https://api.wellcomecollection.org/catalogue/v2/images?'+qs.toString();
    }else if(kind==='openverseModern'){
      const [termIndexText,pageText]=String(param).split(':');
      const termIndex=Number(termIndexText),page=Number(pageText);
      if(!Number.isInteger(termIndex)||termIndex<0||termIndex>=C.MODERN_OPENVERSE_TERMS.length
         ||!Number.isInteger(page)||page<1||page>4)throw Error('Openverse 검색 범위 오류');
      const qs=new URLSearchParams({q:C.MODERN_OPENVERSE_TERMS[termIndex],
        license:'cc0,pdm',source:'wikimedia',page:String(page),page_size:'20'});
      url='https://api.openverse.org/v1/images/?'+qs.toString();
    }else if(kind==='metSearch'){
      const [dept,offset]=String(param).split(':');
      if(!['11','9','21','6'].includes(dept))throw Error('부서 ID 오류');
      url=`https://collectionapi.metmuseum.org/public/collection/v1.1/search?hasImages=true&departmentId=${dept}&limit=100&offset=${Number(offset)||0}`;
    }else if(kind==='metObject'){
      const n=Number(param);if(!Number.isInteger(n)||n<1)throw Error('잘못된 작품 ID');
      url=`https://collectionapi.metmuseum.org/public/collection/v1/objects/${n}`;
    }else throw Error('허용되지 않은 API');
    const ac=new AbortController();const tm=setTimeout(()=>ac.abort(),15000);
    try{const response=await fetch(url,{signal:ac.signal,mode:'cors',cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)throw Error('HTTP '+response.status);
      const data=await response.json();return data;
    }finally{clearTimeout(tm);}
  }
  function sourceIsAllowed(source){return Date.now()>=(state.backoff[source]||0);}
  async function fetchSource(source){
    if(!sourceIsAllowed(source))return 0;
    const before=state.pool.length;
    try{
      if(source==='cleveland'){
        const types=['Painting','Drawing','Print','Photograph'];const t=types[(state.cmaType++)%types.length];let offset=state.cursors.cleveland[t]||0;
        const res=await request('cleveland',t+':'+offset);
        const total=Number(res.info&&res.info.total)||0;
        const arr=normalizeBatch(source,res).filter(C.eligibleArt);
        addCandidates(arr);
        state.cursors.cleveland[t]=total && offset+100>=total?0:offset+100;
      }else if(source==='chicago'){
        const page=state.cursors.chicago||1;
        const res=await request('chicago',page);
        addCandidates(normalizeBatch(source,res).filter(C.eligibleArt));
        const totalPages=Number(res.pagination&&res.pagination.total_pages)||999999;
        state.cursors.chicago=page>=totalPages?1:page+1;
      }else if(source==='global'){
        const category=C.GLOBAL_OPEN_ART_CATEGORIES[state.globalCategoryIndex++%C.GLOBAL_OPEN_ART_CATEGORIES.length];
        const offset=Number(state.cursors.global&&state.cursors.global[category.id])||0;
        const response=await request('globalCommons',category.id+':'+offset);
        addCandidates(C.normalizeGlobalCommons(response,category.id).filter(C.eligibleArt));
        const received=Array.isArray(response.query&&response.query.pages)?response.query.pages.length:0;
        const total=Number(response.query&&response.query.searchinfo&&response.query.searchinfo.totalhits)||0;
        state.cursors.global=state.cursors.global||{};
        state.cursors.global[category.id]=(received===0||received<50||offset>=100000||(total&&offset+50>=total))?0:offset+50;
      }else if(source==='movement'){
        if(!state.movementQueries.length)return 0;
        const idx=state.movementTermIndex++%state.movementQueries.length;
        const school=state.movementQueries[idx];
        const key=String(idx);
        const offset=Number(state.cursors.movement&&state.cursors.movement[key])||0;
        const res=await request('movementCommons',idx+':'+offset);
        const candidates=C.normalizeMovementCommons(res,school).filter(C.eligibleArt);
        addCandidates(candidates);
        const count=Array.isArray(res.query&&res.query.pages)?res.query.pages.length:0;
        state.cursors.movement[key]=(count<25||offset>=2500)?0:offset+25;
      }else if(source==='media'){
        const category=C.MIXED_MEDIA_CATEGORIES[state.mediaCategoryIndex++%C.MIXED_MEDIA_CATEGORIES.length];
        const offset=Number(state.cursors.media&&state.cursors.media[category.id])||0;
        const res=await request('mediaCommons',category.id+':'+offset);
        addCandidates(C.normalizeMixedMediaCommons(res,category.id).filter(C.eligibleArt));
        const count=Array.isArray(res.query&&res.query.pages)?res.query.pages.length:0;
        state.cursors.media[category.id]=(count===0||count<50||offset>=100000)?0:offset+50;
      }else if(source==='asian'){
        const museum=C.ASIAN_MUSEUMS[state.asianOrder++%C.ASIAN_MUSEUMS.length];
        const offset=Number(state.cursors.asian[museum.id])||0;
        const res=await request('asianCommons',museum.id+':'+offset);
        const normalized=C.normalizeAsianCommons(res,museum.id).filter(C.eligibleArt);
        addCandidates(normalized);
        const rows=Array.isArray(res.query&&res.query.pages)?res.query.pages.length:0;
        const total=Number(res.query&&res.query.searchinfo&&res.query.searchinfo.totalhits)||0;
        state.cursors.asian[museum.id]=(rows===0||rows<50||offset>=100000||(total&&offset+50>=total))?0:offset+50;
      }else if(source==='african'){
        const museum=C.AFRICAN_MUSEUMS[state.africanOrder++%C.AFRICAN_MUSEUMS.length];
        const offset=Number(state.cursors.african[museum.id])||0;
        const res=await request('africanCommons',museum.id+':'+offset);
        addCandidates(C.normalizeAfricanCommons(res,museum.id).filter(C.eligibleArt));
        const rows=Array.isArray(res.query&&res.query.pages)?res.query.pages.length:0;
        const total=Number(res.query&&res.query.searchinfo&&res.query.searchinfo.totalhits)||0;
        state.cursors.african[museum.id]=(rows===0||rows<50||offset>=100000||(total&&offset+50>=total))?0:offset+50;
      }else if(source==='additional'){
        const museum=C.ADDITIONAL_MUSEUMS[(state.additionalOrder++*11)%C.ADDITIONAL_MUSEUMS.length];
        const offset=Number(state.cursors.additional[museum.id])||0;
        const res=await request('additionalCommons',museum.id+':'+offset);
        addCandidates(C.normalizeAdditionalCommons(res,museum.id).filter(C.eligibleArt));
        const rows=Array.isArray(res.query&&res.query.pages)?res.query.pages.length:0;
        const total=Number(res.query&&res.query.searchinfo&&res.query.searchinfo.totalhits)||0;
        state.cursors.additional[museum.id]=(rows===0||rows<50||offset>=100000||(total&&offset+50>=total))?0:offset+50;
      }else if(source==='smithsonian'){
        const museum=C.SMITHSONIAN_MUSEUMS[state.smithsonianOrder++%C.SMITHSONIAN_MUSEUMS.length];
        const idx=museum.id==='nmaa' ? state.smithsonianCategoryOrder++%museum.categories.length:0;
        const cursorKey=museum.id+':'+idx,offset=Number(state.cursors.smithsonian[cursorKey])||0;
        const res=await request('smithsonianCommons',museum.id+':'+idx+':'+offset);
        const items=C.normalizeSmithsonianCommons(res,museum.id).filter(C.eligibleArt);
        addCandidates(items);
        const rows=Array.isArray(res.query&&res.query.pages)?res.query.pages.length:0;
        const total=Number(res.query&&res.query.searchinfo&&res.query.searchinfo.totalhits)||0;
        state.cursors.smithsonian[cursorKey]=(rows===0||rows<50||offset>=100000||(total&&offset+50>=total))?0:offset+50;
      }else if(source==='modern'){
        const mode=state.modernOrder++%3;
        if(mode!==2){
          const category=C.MODERN_CATEGORIES[state.modernCategoryIndex++%C.MODERN_CATEGORIES.length];
          const offset=Number(state.cursors.modern[category.id])||0;
          const res=await request('modernCommons',category.id+':'+offset);
          const items=C.normalizeModernCommons(res,category.id);
          addCandidates(items);
          state.modernFetched+=items.length;
          const rows=Array.isArray(res.query&&res.query.pages)?res.query.pages.length:0;
          state.cursors.modern[category.id]=(rows===0||rows<50||offset>=100000)?0:offset+50;
        }else{
          const idx=state.modernOpenverseIndex++%C.MODERN_OPENVERSE_TERMS.length;
          const page=Number(state.cursors.openverseModern[idx])||1;
          const res=await request('openverseModern',idx+':'+page);
          const items=C.normalizeModernOpenverse(res);
          addCandidates(items);
          state.modernFetched+=items.length;
          state.cursors.openverseModern[idx]=(Array.isArray(res.results)&&res.results.length===20&&page<4)?page+1:1;
        }
      }else if(source==='smNpg'||source==='smChndm'||source==='smNmaahc'||source==='smFsg'){
        if(!window.GalleryAndroid)return 0;
        const isNpg=source==='smNpg';
        const cursorKey=isNpg?'smithsonianNpgShard':
          source==='smChndm'?'smithsonianChndmShard':
          source==='smNmaahc'?'smithsonianNmaahcShard':'smithsonianFsgShard';
        const shard=Number(state.cursors[cursorKey])||0;
        const kind=isNpg?'npg':source==='smChndm'?'chndm':source==='smNmaahc'?'nmaahc':'fsg';
        const res=await request('smithsonianShard',kind+':'+shard);
        addCandidates(normalizeBatch('smithsonianShard',res));
        state.cursors[cursorKey]=(shard+1)%256;
      }else if(source==='princeton'){
        const index=state.princetonIndex++%C.PRINCETON_TERMS.length;
        const offset=Number(state.cursors.princeton[index])||0;
        const page=await request('princetonSearch',index+':'+offset);
        const hits=page&&page.hits&&Array.isArray(page.hits.hits)?page.hits.hits:[];
        let checked=0;
        for(const hit of hits){
          if(checked>=5||state.pool.length-before>=10)break;
          const id=Number(hit&&hit._id);
          if(!Number.isInteger(id)||id<1||id>9999999)continue;
          checked++;
          try{
            const record=await request('princetonObject',String(id));
            const art=C.normalizePrinceton(record);
            if(art)addCandidates([art]);
          }catch(_){/* isolated artwork failure; no rights bypass */}
        }
        state.cursors.princeton[index]=hits.length<20||offset>=3000?0:offset+20;
      }else if(source==='wellcome'){
        const index=state.wellcomeIndex++%C.WELLCOME_TERMS.length;
        const page=Number(state.cursors.wellcome&&state.cursors.wellcome[index])||1;
        const result=await request('wellcome',index+':'+page);
        const arts=normalizeBatch('wellcome',result);
        addCandidates(arts);
        const pages=Math.min(250,Number(result.totalPages)||1);
        state.cursors.wellcome[index]=(page>=pages||!Array.isArray(result.results)||!result.results.length)?1:page+1;
      }else if(source==='met'){
        const departments=['11','9','21','6'];const m=departments[(state.metType++)%3];
        if(!state.metIDs.length||state.metIndex>=state.metIDs.length){
          const off=state.cursors.met[m]||0;
          const res=await request('metSearch',m+':'+off);
          state.metIDs=Array.isArray(res.objectIDs)?res.objectIDs:[];state.metIndex=0;
          state.cursors.met[m]=off+100<Math.min(Number(res.total)||0,10000)?off+100:0;
        }
        let reads=0;
        while(state.metIndex<state.metIDs.length&&reads<14&&state.pool.length-before<20){
          const id=state.metIDs[state.metIndex++];reads++;
          try{const res=await request('metObject',id);const art=C.normalizeMet(res);
            if(C.eligibleArt(art))addCandidates([art]);
          }catch(_){/* A single missing object is normal; continue. */}
          if(!test)await wait(120);
        }
      }
      state.failures[source]=0;state.backoff[source]=0;
      if(!state.sourceReady.includes(source))state.sourceReady.push(source);
      await persist();
      return state.pool.length-before;
    }catch(e){
      state.failures[source]=Math.min(10,(state.failures[source]||0)+1);
      const info=collectorErrorInfo(e);
      state.backoff[source]=Date.now()+collectorDelay(info.status,state.failures[source],info.retryMs);
      if(info.status===429)state.collectorThrottled++;
      state.lastErr=`${sourceNames[source]}: ${e.message}`;
      return 0;
    }
  }
  async function fetchForMovement(movementId){
    const movement=C.MOVEMENTS.find(m=>m.id===movementId);
    if(!movement)return 0;
    if(movementId==='asian')return sourceIsAllowed('asian')?fetchSource('asian'):0;
    if(movementId==='african')return sourceIsAllowed('african')?fetchSource('african'):0;
    if(movementId==='additional')return sourceIsAllowed('additional')?fetchSource('additional'):0;
    if(movementId==='modern')return sourceIsAllowed('modern')?fetchSource('modern'):0;
    if(!sourceIsAllowed('chicago'))return 0;
    const last=state.lastMovementTry[movementId]||0;
    if(Date.now()-last<CONFIG.movementRetryMs)return 0;
    state.lastMovementTry[movementId]=Date.now();
    const page=state.movementPages[movementId]||1;
    try{
      const res=await request('chicagoMovement',`${movementId}:${page}`);
      const arr=normalizeBatch('chicago',res).filter(C.eligibleArt);
      const before=state.pool.length;
      addCandidates(arr);
      const pages=Number(res.pagination&&res.pagination.total_pages)||1;
      state.movementPages[movementId]=page>=pages?1:page+1;
      await dbPutMany('settings',[{key:'movementPages',value:state.movementPages}]);
      if(!state.sourceReady.includes('chicago'))state.sourceReady.push('chicago');
      return state.pool.length-before;
    }catch(e){state.lastErr=`시카고(${movement.label}): ${e.message}`;return 0;}
  }
  function addCandidates(items){
    for(const a of items){
      if(state.pool.length>=CONFIG.maxQueue)break;
      if(!C.eligibleArt(a)||!C.metadataResolutionOkay(a)||state.pendingKeys.has(a.key))continue;
      if(!window.GalleryAndroid && Number(a.width)>0&&Number(a.height)>0&&
        !C.fillsPortraitScreen(a.width,a.height,innerWidth,innerHeight,CONFIG.minimumPortraitFill))continue;
      if(seenInMemory(a,null))continue;
      // Art history schools are optional; a work is not rejected for lacking one.
      // Never mislabel an unclassified painting as a specific art movement.
      a.movement=C.classifyMovement(a)||'unclassified';
      a.era=C.artworkEra(a);
      state.pool.push(a);state.pendingKeys.add(a.key);
    }
  }
  async function fillPool(target=CONFIG.targetPool){
    if(state.filling)return state.filling;
    state.filling=(async()=>{
      let attempts=0, progress=0;
      while(state.pool.length<target && attempts<14){
        // Give year-dated museum APIs greater weight than undated Commons filenames.
        const sources=['movement','smNpg','media','cleveland','princeton','wellcome','chicago','media','smChndm','smNmaahc','met','cleveland','global','chicago','smNpg','princeton','wellcome','smFsg','asian','media','african','additional','movement','global','additional','smithsonian','modern','smNmaahc','smFsg'];
        const source=sources[state.sourceOrder++%sources.length];
        attempts++;
        progress+=await fetchSource(source);
        if(test&&typeof test.afterFetch==='function')test.afterFetch(source);
        if(state.pool.length>=target)break;
        if(attempts>=9&&!progress)break;
      }
      if(state.pool.length===0&&state.lastErr) inform('새 작품을 가져오지 못했습니다. 네트워크를 확인해 주세요.');
      return state.pool.length;
    })();
    try{return await state.filling;}finally{state.filling=null; updateInfo();}
  }
  // No daily or 30-minute image quota: collect toward the 8GiB device cache.
  // Per-pass limits protect tablet responsiveness and respect HTTP 429/503 backoff.
  // The one-minute slideshow remains independent from the collector.
  function collectorDelay(status,attempt,retryMs=0){
    const n=Math.max(1,Math.min(10,Number(attempt)||1));
    const base=status===429?1800000:status===503?480000:45000;
    const cap=status===429?86400000:status===503?14400000:2700000;
    return Math.max(Math.min(cap,base*Math.pow(2,n-1)),Math.min(86400000,Math.max(0,Number(retryMs)||0)));
  }
  function collectorErrorInfo(err){
    const message=String(err&&err.message||err||'');
    const status=message.match(/\bHTTP\s*(429|503|500|502|403)\b/i);
    const retry=message.match(/\bRetry-After:\s*(\d+)\b/i);
    return {status:status?Number(status[1]):0,retryMs:retry?Math.min(86400000,Number(retry[1])*1000):0};
  }
  function collectorQuota(now=Date.now()){
    if(!Number.isFinite(state.collectorWindowStarted)||state.collectorWindowStarted<1||
        now<state.collectorWindowStarted||now-state.collectorWindowStarted>=CONFIG.collectorEveryMs){
      state.collectorWindowStarted=now;state.collectorWindowSaved=0;
    }
    const today=new Date(now+9*60*60*1000).toISOString().slice(0,10);
    if(state.collectorDayKey!==today){state.collectorDayKey=today;state.collectorDaySaved=0;}
    // Pump limit, not a cap on 30-minute or daily actual downloads.
    return CONFIG.collectorMaxPerTick;
  }
  async function persistCollector(){
    const now=Date.now();
    state.collectorRetry=Object.fromEntries(Object.entries(state.collectorRetry)
      .filter(([key,item])=>key.length<220&&item&&Number.isFinite(item.nextAt)&&item.nextAt>now-86400000)
      .sort((a,b)=>a[1].nextAt-b[1].nextAt).slice(0,500));
    await dbPutMany('settings',[{key:'collectorV2State',value:{
      windowStarted:state.collectorWindowStarted,windowDownloaded:state.collectorWindowSaved,
      dayKey:state.collectorDayKey,dayDownloaded:state.collectorDaySaved,
      totalDownloaded:state.collectorSuccess,totalErrors:state.collectorErrors,
      sourceBackoff:state.backoff,sourceFailures:state.failures,
      retry:state.collectorRetry,ready:[...state.prefetchedKeys].slice(-1000),
      lastIndexAt:state.collectorLastIndexAt,throttled:state.collectorThrottled
    }}]);
  }
  async function restoreCollector(){
    try{
      const row=await dbGet('settings','collectorV2State'),saved=row&&row.value;
      if(!saved||typeof saved!=='object')return;
      const nonnegative=x=>Number.isFinite(Number(x))&&Number(x)>0?Number(x):0;
      state.collectorWindowStarted=nonnegative(saved.windowStarted);
      state.collectorWindowSaved=nonnegative(saved.windowDownloaded);
      state.collectorDayKey=typeof saved.dayKey==='string'?saved.dayKey:'';
      state.collectorDaySaved=nonnegative(saved.dayDownloaded);
      state.collectorSuccess=nonnegative(saved.totalDownloaded);
      state.collectorErrors=nonnegative(saved.totalErrors);
      state.collectorThrottled=nonnegative(saved.throttled);
      state.collectorLastIndexAt=nonnegative(saved.lastIndexAt);
      if(saved.retry&&typeof saved.retry==='object'&&!Array.isArray(saved.retry))
        state.collectorRetry=Object.fromEntries(Object.entries(saved.retry).filter(([key,item])=>
          key.length<220&&item&&Number.isFinite(Number(item.nextAt))&&
          Number(item.nextAt)>Date.now()-86400000).slice(0,500));
      if(Array.isArray(saved.ready))
        state.prefetchedKeys=new Set(saved.ready.filter(key=>typeof key==='string'&&key.length<220).slice(-1000));
      if(saved.sourceBackoff&&typeof saved.sourceBackoff==='object'&&!Array.isArray(saved.sourceBackoff))
        state.backoff=Object.fromEntries(Object.entries(saved.sourceBackoff).filter(([key,until])=>
          Object.prototype.hasOwnProperty.call(sourceNames,key)&&Number.isFinite(Number(until))&&
          Number(until)>Date.now()));
      if(saved.sourceFailures&&typeof saved.sourceFailures==='object'&&!Array.isArray(saved.sourceFailures))
        for(const key of Object.keys(sourceNames))state.failures[key]=Math.max(0,Math.min(10,Number(saved.sourceFailures[key])||0));
    }catch(e){state.lastErr='수집 대기열 복원 실패: '+String(e.message||e);}
  }
  async function collectorPump(){
    if(state.collectorRunning||!state.db||document.hidden||!state.networkOnline)return;
    const now=Date.now();
    if(state.collectorLastAt&&now-state.collectorLastAt<CONFIG.collectorTickMs-3000)return;
    state.collectorRunning=true;state.collectorLastAt=now;
    try{
      const quota=collectorQuota(now);
      // Read the actual tablet cache, not metadata, search results or APK counts.
      const storage=nativeCacheStats();
      if(storage){
        const bytes=Math.max(0,Number(storage.bytes)||0);
        const limit=Number(storage.limitBytes)||8*1024**3;
        const free=Number(storage.freeBytes)||0;
        const reserve=Number(storage.reservedBytes)||1536*1024**2;
        const displayed=Number(storage.displayedCacheEntries)||0;
        if(bytes+8*1024*1024>=limit&&displayed===0){
          state.collectorStopReason='8GiB 한도 근접 · 미전시 파일 보호';
          return;
        }
        if(free<reserve+8*1024*1024&&displayed===0){
          state.collectorStopReason='기기 여유 저장 공간 부족';
          return;
        }
      }
      state.collectorStopReason='';
      let ready=state.pool.filter(a=>!state.prefetchedKeys.has(a.key)&&!state.downloadedKeys.has(a.key)&&!state.collectorRejectedKeys.has(a.key)&&!state.downloadedKeys.has(a.key)&&!state.collectorRejectedKeys.has(a.key)&&
        !seenInMemory(a,null)&&!(state.collectorRetry[a.key]&&state.collectorRetry[a.key].nextAt>now));
      // Keep archived downloaded candidates on disk while allowing discovery
      // to continue if the 7200-item in-memory queue becomes entirely staged.
      if(ready.length<Math.max(12,quota*4)&&state.pool.length>=CONFIG.maxQueue){
        const park=new Set(state.pool.filter(a=>state.prefetchedKeys.has(a.key))
          .slice(0,600).map(a=>a.key));
        if(park.size){
          state.pool=state.pool.filter(a=>!park.has(a.key));
          for(const key of park)state.pendingKeys.delete(key);
        }
      }
      if(ready.length<Math.max(12,quota*4)&&state.pool.length<CONFIG.maxQueue&&
         (!state.collectorLastIndexAt||now-state.collectorLastIndexAt>CONFIG.collectorTickMs-3000)){
        state.collectorLastIndexAt=now;
        await fillPool(Math.min(CONFIG.maxQueue,Math.max(CONFIG.targetPool,state.pool.length+80)));
        ready=state.pool.filter(a=>!state.prefetchedKeys.has(a.key)&&
          !seenInMemory(a,null)&&!(state.collectorRetry[a.key]&&state.collectorRetry[a.key].nextAt>Date.now()));
      }
      if(!state.prepared&&!state.preparing&&state.pool.length)await prepareNext();
      // JS requests overlap across independent URLs, but Android allows only
      // three simultaneous native transfers and serializes same-URL writes.
      // No bypass of source cooldowns, Retry-After or the 1.5GiB free reserve.
      let downloaded=0,attempted=0,queueIndex=0,active=0;
      const candidates=C.shuffledCopy(ready);
      async function collectOne(art){
        if(state.downloadedKeys.has(art.key)||state.collectorRejectedKeys.has(art.key)||
           state.prefetchedKeys.has(art.key)||seenInMemory(art,null))return;
        const old=state.collectorRetry[art.key];
        if(old&&old.nextAt>Date.now())return;
        attempted++;
        let reserved=false;
        try{
          const already=await dbGet('downloaded',art.key);
          if(already){
            state.downloadedKeys.add(art.key);
            state.prefetchedKeys.add(art.key);
            return;
          }
          if(state.downloadedURLs.has(art.image)){
            state.collectorRejectedKeys.add(art.key);
            state.dedupBlocked++;
            return;
          }
          const loaded=await loadImage(art);
          if(!cachedArtworkExists(art))throw Error('실제 캐시 파일이 저장되지 않음');
          if((await seenRecently(art,loaded.visualHash))||
             similarDownloadedImage(loaded.visualHash,art.key)){
            state.collectorRejectedKeys.add(art.key);
            state.dedupBlocked++;
            if(!state.downloadedURLs.has(art.image))discardRejectedArtwork(art);
            return;
          }
          if(loaded.visualHash){
            state.inflightVisualHashes.set(art.key,loaded.visualHash);
            reserved=true;
          }
          await dbPutMany('downloaded',[{key:art.key,art,visualHash:loaded.visualHash,when:Date.now()}]);
          state.downloadedKeys.add(art.key);
          state.downloadedURLs.add(art.image);
          if(loaded.visualHash)state.downloadedVisualHashes.set(art.key,loaded.visualHash);
          state.prefetchedKeys.add(art.key);
          delete state.collectorRetry[art.key];
          downloaded++;state.collectorSuccess++;state.collectorWindowSaved++;state.collectorDaySaved++;
        }catch(e){
          const info=collectorErrorInfo(e),attempts=Math.min(10,Number(old&&old.attempts||0)+1);
          state.collectorRetry[art.key]={
            attempts,nextAt:Date.now()+collectorDelay(info.status,attempts,info.retryMs),
            network:info.status===0
          };
          state.collectorErrors++;
          if(info.status===429)state.collectorThrottled++;
          state.lastErr='수집 재시도 대기: '+String(e&&e.message||e);
        }finally{
          if(reserved)state.inflightVisualHashes.delete(art.key);
        }
      }
      async function worker(){
        while(queueIndex<candidates.length &&
              downloaded+active<quota&&attempted<CONFIG.collectorMaxAttemptsPerTick){
          const idx=queueIndex++;
          active++;
          try{await collectOne(candidates[idx]);}
          finally{active--;}
        }
      }
      await Promise.all(Array.from({length:Math.min(3,candidates.length)},()=>worker()));
      if(state.collectorRejectedKeys.size>6000)
        state.collectorRejectedKeys=new Set([...state.collectorRejectedKeys].slice(-3000));
      if(state.prefetchedKeys.size>1500){
        const live=new Set(state.pool.map(a=>a.key));
        state.prefetchedKeys=new Set([...state.prefetchedKeys].filter(k=>live.has(k)).slice(-1000));
      }
      const unready=state.pool.filter(a=>!state.prefetchedKeys.has(a.key)&&!state.downloadedKeys.has(a.key));
      const staged=state.pool.filter(a=>state.prefetchedKeys.has(a.key));
      await dbPutMany('settings',[{key:'candidatePool',value:
        unready.slice(0,Math.min(800,CONFIG.savedCandidateLimit))
        .concat(staged.slice(-200)).slice(0,CONFIG.savedCandidateLimit)}]);
      await persistCollector();await persist();
    }catch(e){state.collectorErrors++;state.lastErr='수집 대기열 오류: '+String(e.message||e);}
    finally{state.collectorRunning=false;state.cacheSnapshotAt=0;updateInfo();}
  }
  function startContinuousCollector(){
    if(state.collectorTimer)clearInterval(state.collectorTimer);
    state.collectorTimer=setInterval(()=>{collectorPump().catch(()=>{});},CONFIG.collectorTickMs);
    collectorPump().catch(()=>{});
  }
  // Read at most a small page of saved unshown artworks, so 8GiB of downloads
  // need not become a single giant settings record or startup JS array.
  function cachedArtworkExists(art){
    if(!window.GalleryAndroid||typeof window.GalleryAndroid.cachedArtworkExists!=='function')return true;
    try{return !!window.GalleryAndroid.cachedArtworkExists(art.image);}
    catch(_){return false;}
  }
  function discardRejectedArtwork(art){
    if(!window.GalleryAndroid||typeof window.GalleryAndroid.discardUnshownDuplicate!=='function')return;
    try{window.GalleryAndroid.discardUnshownDuplicate(art.image);}catch(_){}
  }
  function similarDownloadedImage(hash,key){
    if(!hash)return false;
    for(const [priorKey,priorHash] of state.downloadedVisualHashes){
      if(priorKey!==key&&priorHash&&C.hashDistance(hash,priorHash)<=2)return true;
    }
    for(const [priorKey,priorHash] of state.inflightVisualHashes){
      if(priorKey!==key&&priorHash&&C.hashDistance(hash,priorHash)<=2)return true;
    }
    for(const item of state.offlineReady){
      if(item.visualHash&&C.hashDistance(hash,item.visualHash)<=2)return true;
    }
    return false;
  }
  async function hydrateDownloadedIndex(){
    if(!state.db||!state.db.objectStoreNames.contains('downloaded'))return 0;
    state.downloadedKeys.clear();state.downloadedVisualHashes.clear();state.downloadedURLs.clear();
    return new Promise((resolve,reject)=>{
      let count=0;
      const tx=state.db.transaction('downloaded','readonly'),req=tx.objectStore('downloaded').openCursor();
      req.onsuccess=()=>{
        const cursor=req.result;if(!cursor)return;
        const row=cursor.value,art=row&&row.art;
        if(art&&typeof art.key==='string'&&C.eligibleArt(art)){
          state.downloadedKeys.add(art.key);
          if(row.visualHash&&/^[0-9a-f]{16}$/.test(row.visualHash))
            state.downloadedVisualHashes.set(art.key,row.visualHash);
          if(typeof art.image==='string')state.downloadedURLs.add(art.image);
          count++;
        }
        cursor.continue();
      };
      tx.oncomplete=()=>resolve(count);
      tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
    });
  }
  async function restoreDownloadedInventory(limit=300){
    if(!state.db||!state.db.objectStoreNames.contains('downloaded'))return 0;
    return new Promise((resolve,reject)=>{
      let added=0;const staleKeys=[];
      const tx=state.db.transaction('downloaded','readonly');
      const req=tx.objectStore('downloaded').openCursor();
      req.onsuccess=()=>{
        const cursor=req.result;
        if(!cursor||added>=limit||state.pool.length>=CONFIG.maxQueue)return;
        const art=cursor.value&&cursor.value.art;
        const exists=art&&cachedArtworkExists(art);
        if(art&&!exists){
          state.downloadedKeys.delete(art.key);
          state.downloadedVisualHashes.delete(art.key);
          state.downloadedURLs.delete(art.image);
          staleKeys.push(art.key);
        }
        if(art&&exists&&C.eligibleArt(art)&&C.metadataResolutionOkay(art)&&
           !seenInMemory(art,null)&&!state.pendingKeys.has(art.key)){
          state.pendingKeys.add(art.key);state.pool.push(art);
          state.prefetchedKeys.add(art.key);
          added++;
        }
        cursor.continue();
      };
      tx.oncomplete=()=>{
        Promise.all(staleKeys.map(key=>dbDelete('downloaded',key))).then(
          ()=>resolve(added),reject);
      };
      tx.onerror=()=>reject(tx.error);
      tx.onabort=()=>reject(tx.error);
    });
  }
  async function restoreCandidatePool(){
    try{
      const saved=await dbGet('settings','candidatePool');
      if(!saved||!Array.isArray(saved.value))return 0;
      for(const art of saved.value.slice(0,CONFIG.savedCandidateLimit)){
        if(!C.eligibleArt(art)||!C.metadataResolutionOkay(art)||seenInMemory(art,null))continue;
        if(state.pendingKeys.has(art.key))continue;
        state.pendingKeys.add(art.key);state.pool.push(art);
      }
      return state.pool.length;
    }catch(_){return 0;}
  }
  async function takeEraCandidate(era){
    // Strictly separate known dates from unknown: no guess based on upload date.
    // Random across all media types, no fixed category order.
    const eligible=C.shuffledCopy(state.pool.filter(a=>C.artworkEra(a)===era));
    for(const a of eligible){
      const idx=state.pool.indexOf(a);
      if(idx<0)continue;
      if(await seenRecently(a)){state.pool.splice(idx,1);state.pendingKeys.delete(a.key);continue;}
      state.pool.splice(idx,1);state.pendingKeys.delete(a.key);
      try{
        const loaded=await loadImage(a);
        if(loaded.orient!=='portrait'){
          // Reject for the unchanged portrait-only, 75%-fill display rule.
          continue;
        }
        if(await seenRecently(a,loaded.visualHash)){state.dedupBlocked++;continue;}
        return loaded;
      }catch(e){state.lastErr='작품 이미지: '+e.message;}
    }
    return null;
  }
  async function prepareNext(){
    if(state.prepared)return state.prepared;
    if(state.preparing)return state.preparing;
    state.preparing=(async()=>{
      if(state.pool.length<CONFIG.minPool)await restoreDownloadedInventory(300);
      if(!state.pool.length)await fillPool(CONFIG.minPool);
      const requestedPost1800=C.targetPost1800(state.stats.slot);
      const first=requestedPost1800?'post1800':'pre1800';
      if(!state.pool.some(a=>C.artworkEra(a)===first)){
        // Museum APIs provide explicit production-year ranges; Commons file
        // upload dates cannot prove artwork age.
        const order=requestedPost1800?['cleveland','chicago','met','modern']:
          ['cleveland','chicago','met','additional'];
        for(let n=0;n<2;n++){
          const source=order[n];
          if(!sourceIsAllowed(source))continue;
          await fetchSource(source);
          if(state.pool.some(a=>C.artworkEra(a)===first))break;
        }
      }
      // Target 4/5 post-1800; if the required era has no eligible new image,
      // fall back without blocking the screen and show the actual achieved share.
      const order=requestedPost1800?
        ['post1800','pre1800','unknown']:
        ['pre1800','unknown','post1800'];
      for(const era of order){
        state.prepared=await takeEraCandidate(era);
        if(state.prepared)break;
      }
      if(state.pool.length<CONFIG.minPool&&!state.filling)
        fillPool(CONFIG.targetPool).catch(()=>{});
      return state.prepared;
    })();
    try{return await state.preparing;}finally{state.preparing=null;}
  }
  function tellNativeArtworkWasActuallyDisplayed(art){
    if(!window.GalleryAndroid||
       typeof window.GalleryAndroid.markArtworkDisplayed!=='function')return;
    // Bundled APK images are not the 8GiB downloaded-image cache.
    // Passing an empty string unpins the last downloaded image.
    const url=art&&!art.offlineAsset&&C.safeURL(art.image)?art.image:'';
    try{window.GalleryAndroid.markArtworkDisplayed(url);}
    catch(e){state.lastErr='전시 이력(캐시 정리용) 기록 실패: '+String(e.message||e);}
  }
  async function restoreLastShown(){
    try{
      const saved=await dbGet('settings','lastArtwork');
      if(!saved||!C.eligibleArt(saved.value)||!C.metadataResolutionOkay(saved.value))return false;
      const last=await loadImage(saved.value);
      ui.a.src=last.src;ui.a.alt=last.art.title+' — '+last.art.artist;
      ui.a.classList.add('visible');ui.b.classList.remove('visible');
      state.current=last;state.currentNode=ui.a;
      tellNativeArtworkWasActuallyDisplayed(last.art);
      ui.title.textContent=C.tidyLabel(last.art.title,'제목 미상');
      ui.meta.textContent=C.tidyLabel(last.art.artist,'작가 미상')+' · '+C.artworkYearLabel(last.art);
      ui.placeholder.hidden=true;
      return true;
    }catch(_){return false;}
  }
  function controlsFor(ms=7500){
    ui.hud.classList.add('active');
    clearTimeout(state.hideTimer);
    if(ms>0)state.hideTimer=setTimeout(()=>{
      if(!ui.settings.hidden)return;
      ui.hud.classList.remove('active');
    },ms);
  }

  // Rendering is intentionally synchronous and never waits for API/network/image
  // requests. The tick is driven independently by the native Android clock.
  function displayLoaded(show,emergency=false){
    if(!show || (state.current&&state.current.art.key===show.art.key))return false;
    if(seenInMemory(show.art,show.visualHash)){state.dedupBlocked++;return false;}
    // Atomic native journal is committed BEFORE on-screen display. A crash
    // between the render and IndexedDB's async commit cannot repeat the art.
    if(window.GalleryAndroid&&typeof window.GalleryAndroid.claimArtworkKeys==='function'){
      let claimed=false;
      try{claimed=!!window.GalleryAndroid.claimArtworkKeys(
        JSON.stringify(rowKeys(show.art,show.visualHash)));}catch(_){}
      if(!claimed){
        state.dedupBlocked++;state.lastErr='기기 전시 기록 저장 실패 또는 최근 90일 작품';
        return false;
      }
    }
    markSeen(show); // Reserve identities before asynchronous disk writes.
    const target=state.currentNode===ui.a?ui.b:ui.a;
    target.alt=show.art.title+' — '+show.art.artist;
    target.src=show.src;
    target.classList.add('visible');
    state.currentNode.classList.remove('visible');
    ui.placeholder.hidden=true;
    state.currentNode=target;state.current=show;
    tellNativeArtworkWasActuallyDisplayed(show.art);
    state.lastSwapAt=Date.now();
    ui.title.textContent=C.tidyLabel(show.art.title,'제목 미상');
    ui.meta.textContent=C.tidyLabel(show.art.artist,'작가 미상')+' · '+C.artworkYearLabel(show.art);
    // No mandatory 17-movement rotation: only the evidence-based era quota.
    state.recentLoaded=[show,...state.recentLoaded.filter(x=>x.art.key!==show.art.key)].slice(0,8);
    state.recentDisplayed.add(show.art.key);
    if(emergency)state.emergencySwaps++;
    if(show.art.offlineAsset)state.offlineUnseenReady=Math.max(0,state.offlineUnseenReady-1);
    if(test&&test.onShow)test.onShow(show.art,show.orient,emergency);
    // Persist in the background: storage latency may not delay a visual transition.
    recordSeen(show).then(async()=>{
      await dbDelete('downloaded',show.art.key);
      state.downloadedKeys.delete(show.art.key);
      state.downloadedVisualHashes.delete(show.art.key);
      state.downloadedURLs.delete(show.art.image);
      await dbPutMany('settings',[{key:'lastArtwork',value:show.art}]);
    }).catch(e=>{
      state.lastErr='감상 기록 저장 실패: '+String(e.message||e);
      // Keep the artwork clock running, but disclose that 90-day records
      // may be incomplete until storage recovers.
    });
    updateInfo();
    return true;
  }
  function emergencyChoice(){
    // Previously v1.6.2 repeatedly cycled four bundled paintings.
    // The 90-day embargo now includes every bundled painting.
    const all=state.offlineReady.filter(item=>item &&
      !seenInMemory(item.art,item.visualHash) &&
      (!state.current || state.current.art.key!==item.art.key));
    if(!all.length)return null; // HOLD current image; no 90-day repeat.
    return all[Math.floor(Math.random()*all.length)];
  }
  function advanceSlide(){
    if(!state.playing)return;
    state.tickCount++;
    let shown=false;
    if(state.prepared){
      const candidate=state.prepared;
      state.prepared=null;
      if(!state.recentDisplayed.has(candidate.art.key)){
        shown=displayLoaded(candidate,false);
      }
    }
    if(!shown){
      const emergency=emergencyChoice();
      if(emergency)shown=displayLoaded(emergency,true);
    }
    if(!shown){
      state.exhaustedTicks++;
      state.lastErr='최근 90일 내 보지 않은 새 그림을 준비 중입니다. 중복 재생하지 않습니다.';
    }
    // This may take minutes; it NEVER blocks the next one-minute tick.
    prepareNext().catch(e=>{state.lastErr='다음 그림 준비: '+e.message;});
  }
  function stopClock(){
    clearTimeout(state.timer);state.timer=null;
    if(state.nativeClock && window.GalleryAndroid &&
       typeof window.GalleryAndroid.stopArtworkClock==='function'){
      window.GalleryAndroid.stopArtworkClock();
    }
    state.nativeClock=false;
  }
  function armBrowserClock(){
    if(!state.playing)return;
    state.timer=setTimeout(()=>{
      if(!state.playing)return;
      state.nextDueAt+=INTERVAL;
      if(state.nextDueAt<=Date.now())state.nextDueAt=Date.now()+INTERVAL;
      advanceSlide();
      armBrowserClock();
    },Math.max(0,state.nextDueAt-Date.now()));
  }
  function startClock(){
    stopClock();
    if(!state.playing)return;
    state.nextDueAt=Date.now()+INTERVAL;
    if(!test&&window.GalleryAndroid &&
       typeof window.GalleryAndroid.startArtworkClock==='function'){
      state.nativeClock=true;
      window.GalleryAndroid.startArtworkClock(CONFIG.intervalMs);
    }else armBrowserClock();
  }
  // Android calls this from a main-thread Handler every 60,000ms, independent
  // of the API and loading promises.
  window.__galleryClockTick=()=>advanceSlide();
  window.__galleryForeground=()=>{if(state.playing)startClock();};
  function next(){
    advanceSlide();
    if(state.playing)startClock(); // manual skip resets the one-minute clock
  }
  async function pruneExpired(){
    const cutoff=Date.now()-C.NINETY_DAYS_MS;
    return new Promise((resolve,reject)=>{
      const tx=state.db.transaction('seen','readwrite'),s=tx.objectStore('seen'),cursor=s.index('when').openCursor(IDBKeyRange.upperBound(cutoff,true));
      cursor.onsuccess=()=>{const c=cursor.result;if(!c)return;
        if(Number.isFinite(c.value.when)&&c.value.when<cutoff)c.delete();c.continue();
      };
      tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);
    });
  }
  async function refreshForDay(force=false){
    const today=C.kstRenewalDay(Date.now());
    if(force||state.stats.day!==today){
      state.stats.day=today;state.stats.updatedAt=new Date().toISOString();
      await pruneExpired();await persist();
      fillPool(CONFIG.targetPool).catch(()=>{});
      updateInfo();
    }
  }

  // Audit is deliberately a limited, metadata-only sample, NOT an inventory of
  // all works at all museums or a promise of playable high-resolution images.
  function renderAudit(){
    const a=state.audit;
    const node=el('audit-summary');if(!node)return;
    if(!a){node.textContent='조사 전 · 전체 수 미확인';return;}
    const parts=[
      '최근 조사 '+new Date(a.at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}),
      '조회한 메타데이터 '+a.raw.toLocaleString('ko-KR')+'건',
      '권리·평면 작품 필터 통과 '+a.eligible.toLocaleString('ko-KR')+'건',
      '원본/제공 이미지 크기 사전 확인 통과 '+a.resolutionChecked.toLocaleString('ko-KR')+'건',
      '실제 픽셀 확인 필요 '+a.pixelUnknown.toLocaleString('ko-KR')+'건',
      '표본 내 고유 후보 '+a.unique.toLocaleString('ko-KR')+'건',
      '검사 실패 공급원 '+a.failed+'개',
      '※ 조회 범위의 잠정 후보이며 전체 작품 수·재생 보장 수가 아닙니다.'
    ];
    for(const r of a.details)parts.push(r.name+': '+(r.error?'오류 '+r.error:(r.unique+'점 후보 / '+r.raw+'건 조회')));
    node.textContent=parts.join('\n');
  }
  async function runInventoryAudit(){
    if(state.auditing)return;
    state.auditing=true;el('audit-now').disabled=true;
    const reports=new Map(),unique=new Set(),fingerprints=new Set();
    const out={at:new Date().toISOString(),raw:0,eligible:0,resolutionChecked:0,pixelUnknown:0,unique:0,failed:0,details:[]};
    const get=name=>{
      if(!reports.has(name))reports.set(name,{name,raw:0,eligible:0,resolutionChecked:0,pixelUnknown:0,unique:0,error:''});
      return reports.get(name);
    };
    const evaluate=(name,raw,normalized)=>{
      const rec=get(name);rec.raw+=raw;out.raw+=raw;
      for(const a of normalized){
        if(!C.eligibleArt(a))continue;
        rec.eligible++;out.eligible++;
        if(!C.metadataResolutionOkay(a))continue;
        if(!window.GalleryAndroid && Number(a.width)>0&&Number(a.height)>0&&!C.fillsPortraitScreen(a.width,a.height,innerWidth,innerHeight,CONFIG.minimumPortraitFill))continue;
        const verifiedSize=(a.museumRegion==='asia'||a.museumRegion==='africa'||a.museumRegion==='additional'||a.museumRegion==='modern'||a.source==='클리블랜드');
        if(verifiedSize){rec.resolutionChecked++;out.resolutionChecked++;}
        else {rec.pixelUnknown++;out.pixelUnknown++;}
        if(unique.has(a.key))continue;
        const fp=C.fingerprint(a);
        if(fp&&fingerprints.has(fp))continue;
        unique.add(a.key);if(fp)fingerprints.add(fp);
        rec.unique++;out.unique++;
      }
    };
    const perform=async(name,kind,param,extract)=>{
      const rec=get(name);
      el('audit-summary').textContent='표본 조사 중: '+name+'\n진행한 조회 '+out.raw+'건';
      try{const raw=await request(kind,param);
        const result=extract(raw);
        evaluate(name,result.count,result.items);
      }catch(e){rec.error=String(e.message||e).slice(0,90);out.failed++;}
      if(!test)await wait(220);
    };
    try{
      for(const t of ['Painting','Drawing','Print']){
        await perform('클리블랜드','cleveland',t+':0',r=>({count:Array.isArray(r.data)?r.data.length:0,items:normalizeBatch('cleveland',r)}));
      }
      await perform('시카고','chicago','1',r=>({count:Array.isArray(r.data)?r.data.length:0,items:normalizeBatch('chicago',r)}));
      let metIDs=[];
      await perform('메트로폴리탄','metSearch','11:0',r=>{metIDs=Array.isArray(r.objectIDs)?r.objectIDs.slice(0,8):[];return {count:0,items:[]};});
      for(const id of metIDs)await perform('메트로폴리탄','metObject',String(id),r=>({count:1,items:[C.normalizeMet(r)]}));
      for(const m of C.ASIAN_MUSEUMS)
        await perform(m.label,'asianCommons',m.id+':0',r=>({count:Array.isArray(r.query&&r.query.pages)?r.query.pages.length:0,items:C.normalizeAsianCommons(r,m.id)}));
      for(const m of C.AFRICAN_MUSEUMS)
        await perform(m.label,'africanCommons',m.id+':0',r=>({count:Array.isArray(r.query&&r.query.pages)?r.query.pages.length:0,items:C.normalizeAfricanCommons(r,m.id)}));
      for(const m of C.ADDITIONAL_MUSEUMS)
        await perform(m.label,'additionalCommons',m.id+':0',r=>({count:Array.isArray(r.query&&r.query.pages)?r.query.pages.length:0,items:C.normalizeAdditionalCommons(r,m.id)}));
      for(const m of C.SMITHSONIAN_MUSEUMS)for(let idx=0;idx<m.categories.length;idx++)
        await perform(m.label+' · '+(m.id==='nmaa'?['중국','일본','인도'][idx]:'미국 회화'),
          'smithsonianCommons',m.id+':'+idx+':0',
          r=>({count:Array.isArray(r.query&&r.query.pages)?r.query.pages.length:0,items:C.normalizeSmithsonianCommons(r,m.id)}));
      for(const m of C.MODERN_CATEGORIES)
        await perform('현대: '+m.label,'modernCommons',m.id+':0',r=>({count:Array.isArray(r.query&&r.query.pages)?r.query.pages.length:0,items:C.normalizeModernCommons(r,m.id)}));
      for(let idx=0;idx<C.MODERN_OPENVERSE_TERMS.length;idx++)
        await perform('Openverse: '+C.MODERN_OPENVERSE_TERMS[idx],'openverseModern',idx+':1',
          r=>({count:Array.isArray(r.results)?r.results.length:0,items:C.normalizeModernOpenverse(r)}));
      out.details=[...reports.values()];
      state.audit=out;
      try{await dbPutMany('settings',[{key:'inventoryAudit',value:out}]);}
      catch(e){ui.msg.textContent='조사 결과 저장 실패: '+String(e.message||e);}
      renderAudit();
    }finally{state.auditing=false;el('audit-now').disabled=false;}
  }

  function nativeCacheStats(force=false){
    if(!window.GalleryAndroid||typeof window.GalleryAndroid.cacheStats!=='function')return null;
    if(!force&&state.cacheSnapshot&&Date.now()-state.cacheSnapshotAt<10000)return state.cacheSnapshot;
    try{
      const data=JSON.parse(window.GalleryAndroid.cacheStats());
      if(!data||!Number.isFinite(Number(data.limitBytes))||Number(data.limitBytes)<=0)return null;
      state.cacheSnapshot=data;
      state.cacheSnapshotAt=Date.now();
      return data;
    }catch(_){return null;}
  }
  function cacheStatus(){
    const s=nativeCacheStats();
    if(!s)return '태블릿에서만 저장량 확인 가능';
    return `${C.prettyBytes(s.bytes||0)} / 8GiB · 실제 저장 ${Number(s.imageFiles||0).toLocaleString('ko-KR')}점 · 전시 후 삭제 ${Number(s.purgedFiles||0)}점 (${C.prettyBytes(s.purgedBytes||0)})`;
  }
  function renderCacheProgress(){
    const s=nativeCacheStats();
    const bar=el('cache-progress'),fill=el('cache-progress-fill');
    if(!bar||!fill)return;
    if(!s){
      el('cache-photo-count').textContent='태블릿에서 확인';
      for(const id of ['cache-unshown-count','cache-shown-count','cache-eligible-count','cache-available-days'])
        if(el(id))el(id).textContent='태블릿에서 확인';
      el('cache-volume').textContent='기기 연결 후 표시';
      el('cache-percent').textContent='—';
      el('cache-detail').textContent='실제 저장된 다운로드 이미지 파일만 집계합니다.';
      bar.setAttribute('aria-valuenow','0');
      fill.style.width='0%';
      return;
    }
    const limit=Number(s.limitBytes)||8*1024**3;
    const bytes=Math.max(0,Number(s.bytes)||0);
    const count=Math.max(0,Number(s.imageFiles)||0);
    const pct=Math.min(100,Math.max(0,100*bytes/limit));
    const gib=n=>(n/1024**3).toFixed(2);
    el('cache-photo-count').textContent=count.toLocaleString('ko-KR')+'점';
    el('cache-volume').textContent=gib(bytes)+' / '+gib(limit)+' GiB';
    el('cache-percent').textContent=pct.toFixed(1)+'%';
    el('cache-apk-count').textContent=state.offlineManifestCount.toLocaleString('ko-KR')+'점';
    const unseenFiles=Math.max(0,Number(s.unshownImageFiles)||0);
    const shownFiles=Math.max(0,Number(s.shownCachedFiles)||0);
    // Index entries were individually checked for decoding and eligibility;
    // native files exclude entries already displayed. The lower count is used.
    // This is a maximum planning estimate, NOT a 90-day uptime guarantee.
    const eligibleDownloaded=Math.min(unseenFiles,state.downloadedKeys.size);
    const possible=eligibleDownloaded+state.offlineUnseenReady;
    const days=Math.floor(possible/1440),hours=Math.floor((possible%1440)/60);
    el('cache-unshown-count').textContent=unseenFiles.toLocaleString('ko-KR')+'점';
    el('cache-shown-count').textContent=shownFiles.toLocaleString('ko-KR')+'점';
    el('cache-eligible-count').textContent=eligibleDownloaded.toLocaleString('ko-KR')+'점';
    el('cache-available-days').textContent=days+'일 '+hours+'시간 이하';
    el('cache-estimate-note').textContent=
      '이미지 중복·화질·권리 검증과 실제 기기 상태에 따라 예상 기간이 단축될 수 있습니다. '+
      '내장 미전시 후보 '+state.offlineUnseenReady.toLocaleString('ko-KR')+'점 포함 · 1분당 1점 기준';
    const free=Math.max(0,Number(s.freeBytes)||0);
    const reserve=Math.max(0,Number(s.reservedBytes)||0);
    const limited=free<reserve+8*1024*1024;
    el('cache-detail').textContent=state.collectorStopReason||
      (limited?'기기 여유 공간 보호 기준에 도달했습니다.':
      '태블릿에 실제 저장된 이미지 파일 기준 · 미전시 이미지 보호');
    bar.setAttribute('aria-valuenow',pct.toFixed(1));
    fill.style.width=pct.toFixed(2)+'%';
  }
  function updateInfo(){
    el('seen-count').textContent=state.stats.shown.toLocaleString('ko-KR')+'점';
    if(el('modern-count')){
      const count=Number(state.stats.post1800Shown)||0;
      const shown=Number(state.stats.shown)||0;
      el('modern-count').textContent=count.toLocaleString('ko-KR')+' / '+
        shown.toLocaleString('ko-KR')+'점 ('+(shown?((100*count/shown).toFixed(1)):'0.0')+'%)';
    }
    const count=state.stats.portrait+state.stats.other;
    el('ratio-count').textContent=count?`${Math.round(state.stats.portrait*100/count)}% 세로형`:'집계 전';
    el('cache-count').textContent=cacheStatus();
    renderCacheProgress();
    if(el('collector-status'))el('collector-status').textContent=
      (document.hidden?'화면 비활성':'화면 활성 · 8GiB 우선 수집')+
      ' · 최근 30분 '+state.collectorWindowSaved+
      '점 · 오늘 '+state.collectorDaySaved+'점 · 누적 '+state.collectorSuccess+
      '점 · 실패 '+state.collectorErrors+'회 · 제한 '+state.collectorThrottled+'회';
    if(el('dedup-count'))el('dedup-count').textContent=
      '중복 차단 '+state.dedupBlocked+'건 · 후보 부족 '+state.exhaustedTicks+'회';
    const backup=el('fallback-status');
    if(backup)backup.textContent=state.offlineReady.length+'점 준비 · 중복 없이 '+state.emergencySwaps+'회 사용';
    el('refresh-count').textContent=state.stats.updatedAt?new Date(state.stats.updatedAt).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',hour12:false}):'–';
    el('source-status').textContent=state.sourceReady.length?state.sourceReady.map(s=>sourceNames[s]).join(' · '):state.lastErr||'연결 대기';
    const nextEra=C.targetPost1800(state.stats.slot)?'1800년 이후':'1800년 이전 우선';
    const currentEra=state.current?C.artworkEra(state.current.art):'unknown';
    el('movement-status').textContent=(currentEra==='post1800'?'1800년 이후':
      currentEra==='pre1800'?'1800년 이전':'제작 연대 미상')+' → '+nextEra;
    el('rotation-status').textContent=state.flipped?'180° 회전 중':'기본 방향';
    renderAudit();
    el('rotate-180').textContent=state.flipped?'기본 방향으로 되돌리기':'화면 180° 회전';
    el('toggle-pause').textContent=state.playing?'Ⅱ':'▶';
    el('toggle-pause').setAttribute('aria-label',state.playing?'일시정지':'재생');
  }
  // Android rotates its actual WebView to avoid CSS fixed-layer issues.
  function applyRotation(){
    const native=window.GalleryAndroid && typeof window.GalleryAndroid.setDisplayRotation==='function';
    document.body.classList.toggle('native-rotation',!!native);
    document.body.classList.toggle('upside-down',state.flipped);
    if(native)window.GalleryAndroid.setDisplayRotation(state.flipped);
  }
  async function setFlip(enabled){
    state.flipped=!!enabled;
    applyRotation();
    if(state.db)await dbPutMany('settings',[{key:'flipped',value:state.flipped}]);
    updateInfo();
  }
  function showSettings(){ui.settings.hidden=false;ui.backdrop.hidden=false;clearTimeout(state.hideTimer);controlsFor(0);state.cacheSnapshotAt=0;updateInfo();}
  function closeSettings(){ui.settings.hidden=true;ui.backdrop.hidden=true;controlsFor(2500);}
  function exportHistory(){
    const native=window.GalleryAndroid&&typeof window.GalleryAndroid.beginHistoryExport==='function';
    const rows=native?[]:['key,shown_at'];
    let total=0,failed=false;
    if(native){try{window.GalleryAndroid.beginHistoryExport();window.GalleryAndroid.appendHistoryExport('key,shown_at\r\n');}catch(e){ui.msg.textContent='백업 시작 실패';return;}}
    const tx=state.db.transaction('seen','readonly');const req=tx.objectStore('seen').openCursor();
    const flush=()=>{
      if(!rows.length)return true;
      const output=rows.join('\r\n')+'\r\n';rows.length=0;
      return window.GalleryAndroid.appendHistoryExport(output);
    };
    req.onsuccess=()=>{const c=req.result;
      if(c){
        rows.push(JSON.stringify(c.key)+','+new Date(c.value.when).toISOString());total++;
        if(native&&rows.length>=500&&!flush())failed=true;
        if(failed){ui.msg.textContent='감상 기록 백업 처리 실패';return;}
        c.continue();return;
      }
      if(native){
        if(!flush()){ui.msg.textContent='감상 기록 백업 저장 실패';return;}
        window.GalleryAndroid.finishHistoryExport();
        ui.msg.textContent=`감상 기록 ${total.toLocaleString('ko-KR')}건을 내보냅니다. 저장 위치를 선택하세요.`;
      }else{
        const blob=new Blob(['\ufeff'+rows.join('\r\n')],{type:'text/csv;charset=utf-8'});
        const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;
        a.download=`gallery-history-${C.kstRenewalDay(Date.now())}.csv`;document.body.appendChild(a);a.click();a.remove();
        setTimeout(()=>URL.revokeObjectURL(url),30000);
        ui.msg.textContent=`감상 기록 ${total.toLocaleString('ko-KR')}건 백업 파일을 만들었습니다.`;
      }
    };
    req.onerror=()=>{ui.msg.textContent='감상 기록 내보내기 실패';};
  }

  // History backup survives APK reinstallation, including GitHub Actions debug-signing changes.
  // Import is deliberately limited to previously exported ID + timestamp records only.
  function parseHistoryCsv(csv, now=Date.now()){
    if(typeof csv!=='string'||csv.length>128*1024*1024)throw new Error('CSV 파일은 128MB 이하여야 합니다.');
    const lines=csv.replace(/^\ufeff/,'').split(/\r?\n/);
    if(lines.shift()?.trim()!=='key,shown_at')throw new Error('이 앱에서 만든 감상 기록 CSV만 복원할 수 있습니다.');
    const valid=new Map();let skipped=0;
    for(const line of lines){
      if(!line.trim())continue;
      const comma=line.lastIndexOf(',');
      if(comma<1){skipped++;continue;}
      let key;
      try{key=JSON.parse(line.slice(0,comma));}catch(_){skipped++;continue;}
      const date=line.slice(comma+1).trim();
      const when=Date.parse(date);
      if(typeof key!=='string'||key.length>270||!(/^(?:cma|aic|met):[1-9][0-9]{0,12}$|^commons:[1-9][0-9]{0,14}$|^openverse:[0-9a-f-]{8,40}$|^fp:[^\s]{4,270}$|^url:[^\s]{4,266}$|^vis:[0-9a-f]{16}$/u.test(key))||
         !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(date)||
         !Number.isFinite(when)||when>now||now-when>C.NINETY_DAYS_MS){skipped++;continue;}
      valid.set(key,Math.max(valid.get(key)||0,when));
    }
    return {entries:[...valid].map(([key,when])=>({key,when})),skipped};
  }
  async function importHistoryCsv(csv){
    if(!state.db)throw new Error('감상 기록 데이터베이스가 준비되지 않았습니다.');
    const parsed=parseHistoryCsv(csv);
    if(!parsed.entries.length)throw new Error('복원 가능한 최근 90일 기록이 없습니다.');
    let imported=0;
    for(let i=0;i<parsed.entries.length;i+=500){
      const batch=parsed.entries.slice(i,i+500);
      await new Promise((resolve,reject)=>{
        const tx=state.db.transaction('seen','readwrite'), store=tx.objectStore('seen');
        for(const entry of batch){
          const r=store.get(entry.key);
          r.onsuccess=()=>{if(!r.result||r.result.when<entry.when)store.put(entry);};
        }
        tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
      });
      imported+=batch.length;
      if(i%5000===0)ui.msg.textContent=`감상 기록 복원 중: ${imported.toLocaleString('ko-KR')}건`;
    }
    // Newly restored history might invalidate an already-prefetched image.
    // Do not disturb the image currently on screen, but force the next selection through the database.
    state.prepared=null;
    await hydrateHistory();
    state.pool=state.pool.filter(a=>C.eligibleArt(a)&&!seenInMemory(a,null));
    ui.msg.textContent=`감상 기록 ${imported.toLocaleString('ko-KR')}건 복원 완료 · 건너뜀 ${parsed.skipped.toLocaleString('ko-KR')}건`;
    return {imported, skipped:parsed.skipped};
  }
  async function historyImportFromNative(){
    try{
      const r=await fetch('https://appassets.gallery/import-history',{cache:'no-store'});
      if(!r.ok)throw new Error('선택한 CSV를 읽을 수 없습니다.');
      const csv=await r.text();await importHistoryCsv(csv);
    }catch(e){ui.msg.textContent='복원 실패: '+e.message;}
  }
  window.__galleryImportReady=historyImportFromNative;
  window.__galleryImportError=(error)=>{ui.msg.textContent='복원 실패: '+String(error).slice(0,150);};
  // This hook performs the same validation on both browser files and native CSVs.
  if(test)window.__galleryTestImportCsv=importHistoryCsv;

  function wire(){
    el('viewer').addEventListener('click',()=>controlsFor());
    el('open-settings').addEventListener('click',showSettings);
    el('rotate-180').addEventListener('click',async()=>{
      try{await setFlip(!state.flipped);}
      catch(e){ui.msg.textContent='화면 방향 저장 실패: '+e.message;}
      finally{closeSettings();}
    });
    el('close-settings').addEventListener('click',closeSettings);
    el('settings-done').addEventListener('click',closeSettings);
    ui.backdrop.addEventListener('click',closeSettings);
    el('next').addEventListener('click',()=>{next();controlsFor();});
    el('toggle-pause').addEventListener('click',()=>{
      state.playing=!state.playing;
      if(state.playing)startClock();else stopClock();
      updateInfo();controlsFor();
    });
    const catalogBox=el('catalog-result');
    el('show-movements').addEventListener('click',async()=>{
      el('source-catalog-links').hidden=true;
      try{
        const r=await fetch('https://appassets.gallery/art-movements.json');
        if(!r.ok)throw Error('데이터를 읽을 수 없습니다.');
        const j=await r.json();
        const body=(j.groups||[]).map(g=>'['+g.region+' · '+g.section+']\n'+
          g.movements.map(m=>'• '+m.name_ko+(m.search_en?' ('+m.search_en+')':'')).join('\n')).join('\n\n');
        catalogBox.textContent='검색 분류 '+j.entry_count+'개 등록 · 실제 작품 확보량과 별개\n\n'+body;
        catalogBox.hidden=false;
      }catch(e){catalogBox.textContent='사조 목록 오류: '+e.message;catalogBox.hidden=false;}
    });
    el('show-providers').addEventListener('click',async()=>{
      const panel=el('source-catalog-links');
      panel.replaceChildren();
      catalogBox.hidden=true;
      try{
        const r=await fetch('https://appassets.gallery/art-sources-85.json');
        if(!r.ok)throw Error('데이터를 읽을 수 없습니다.');
        const j=await r.json();
        if(j.entries_total!==85||!Array.isArray(j.entries)||j.entries.length!==85)
          throw Error('85개 공급원 목록 내용이 손상됐습니다.');
        const lead=document.createElement('p');
        lead.textContent='총 85곳: 직접 미술관 API 3곳 · Wikimedia Commons 검색 37곳 · 공식 사이트 열람 45곳. 45곳은 자동 이미지 수집 연동이 아닙니다. 공식 주소가 확인되지 않은 2곳은 열 수 없습니다.';
        panel.appendChild(lead);
        for(const item of j.entries){
          const btn=document.createElement('button');
          btn.className='wide-btn';
          const mode=item.status==='official_api'?'[직접 수집 API]':
             item.status==='commons_category'?'[Commons 분류 검색]':'[공식 사이트 열람]';
          btn.textContent=item.number+'. '+item.name+' '+mode+(item.link?'':' (주소 미확인)');
          btn.disabled=!item.link;
          btn.addEventListener('click',()=>{
            if(!item.link)return;
            if(window.GalleryAndroid&&typeof window.GalleryAndroid.openRegisteredSource==='function'){
              window.GalleryAndroid.openRegisteredSource(item.number-1);
            }else{
              const link=new URL(item.link);
              if(link.protocol==='https:')window.open(link.href,'_blank','noopener,noreferrer');
            }
          });
          panel.appendChild(btn);
        }
        panel.hidden=false;
      }catch(e){
        catalogBox.textContent='공급원 목록 오류: '+String(e.message||e);
        catalogBox.hidden=false;panel.hidden=true;
      }
    });
    el('show-new50').addEventListener('click',async()=>{
      const panel=el('new50-audit-panel');
      panel.hidden=false;panel.textContent='공급원 검토 대장을 읽는 중입니다.';
      try{
        const path=window.GalleryAndroid?'https://appassets.gallery/new50-provider-audit.json':'./new50-provider-audit.json';
        const res=await fetch(path,{cache:'no-store'});
        if(!res.ok)throw Error('공급원 검토 대장 열기 실패');
        const report=await res.json();
        if(report.reviewed_candidates!==50||!Array.isArray(report.items)||report.items.length!==50)
          throw Error('신규 50곳 감사 파일 형식 오류');
        const lines=report.items.map(x=>x.index+'. '+x.name+' ['+
          (x.enabled_in_apk?'자동 수집 코드 연결':'연동 보류')+'] · '+x.assessment.replace(/_/g,' '));
        const linked=report.items.filter(x=>x.enabled_in_apk).length;
        panel.textContent='기존 85곳 외 50곳 검토\n자동 수집 코드 연결 '+linked+
          '곳: Wellcome · Cooper Hewitt\n연동 보류 '+(50-linked)+'곳\n'+
          '별도 추가 발견 Princeton·Smithsonian NPG 2곳은 아래 검증 결과에서 확인\n'+
          '※ 자동 수집의 실제 일일 성공량과 90일 운영은 실기기 미검증\n\n'+lines.join('\n');
      }catch(e){panel.textContent='신규 공급원 검토 목록 확인 실패: '+String(e&&e.message||e);}
    });
    el('show-v187').addEventListener('click',async()=>{
      const panel=el('v187-audit-panel');
      panel.hidden=false;panel.textContent='새로운 공급원 실물 검증을 불러오는 중입니다.';
      try{
        const path=window.GalleryAndroid?'https://appassets.gallery/v187-verified-sources.json':'./v187-verified-sources.json';
        const response=await fetch(path,{cache:'no-store'});
        if(!response.ok)throw Error('실측 공급원 파일 없음');
        const audit=await response.json();
        if(audit.reviewed_new_units!==3||audit.new_institutions.length!==3)throw Error('검증 자료 형식 오류');
        const lines=audit.new_institutions.map(x=>{
          const imgs=x.pixels_verified||[];
          return '• '+x.name+' ['+x.status+']\n'+
            '  실제 JPEG 검사 '+imgs.length+'건 · '+
            imgs.map(i=>i.width+'×'+i.height).join(', ')+'\n'+
            '  '+x.conditions;
        });
        panel.textContent='독립 추가 확인 2곳: Princeton University Art Museum / Smithsonian NPG\n'+
          '이전 50곳 중 실측 승격 1곳: Smithsonian Cooper Hewitt\n'+
          '총 신규 연결: Wellcome 포함 4개 직접 수집 경로\n'+
          '※ 아래 검사는 CI 네트워크에서의 표본이며 태블릿의 장시간 운용을 증명하지 않습니다.\n\n'+
          lines.join('\n\n')+'\n\n보류 기록\n'+
          audit.excluded_or_deferred.map(x=>'• '+x.name+': '+x.reason).join('\n');
      }catch(e){panel.textContent='검증 결과 조회 실패: '+String(e&&e.message||e);}
    });
    el('audit-now').addEventListener('click',()=>runInventoryAudit().catch(e=>{ui.msg.textContent='조사 실패: '+String(e.message||e);state.auditing=false;el('audit-now').disabled=false;}));
    el('refresh-now').addEventListener('click',async()=>{
      ui.msg.textContent='새 목록 확인 중...';
      // Manual refresh must not bypass a provider's 429/Retry-After cooldown.
      state.backoff=Object.fromEntries(Object.entries(state.backoff).filter(([source,until])=>Number(until)>Date.now()));
      try{await refreshForDay(true);await fillPool(CONFIG.targetPool);ui.msg.textContent=`작품 후보 ${state.pool.length}점을 확보했습니다.`;}
      catch(e){ui.msg.textContent='갱신 실패: '+e.message;}updateInfo();
    });
    el('free-space').addEventListener('click',async()=>{
      if(window.GalleryAndroid&&window.GalleryAndroid.clearImageCache){
        const ok=window.GalleryAndroid.clearImageCache();
        if(ok){
          state.cacheSnapshotAt=0;
          try{
            await dbClear('downloaded');
            state.prefetchedKeys.clear();state.downloadedKeys.clear();
            state.downloadedVisualHashes.clear();state.downloadedURLs.clear();
          }
          catch(e){state.lastErr='캐시 목록 정리 실패: '+String(e.message||e);}
        }
        ui.msg.textContent=ok?'이미지 캐시와 다운로드 목록을 삭제했습니다. 90일 감상 기록은 보존됩니다.':'캐시 정리에 실패했습니다.';
      }else{ui.msg.textContent='웹 브라우저의 이미지 HTTP 캐시는 사이트에서 직접 지울 수 없습니다. 안드로이드 APK에서는 자동 정리됩니다.';}
      updateInfo();
    });
    el('export-history').addEventListener('click',exportHistory);
    el('import-history').addEventListener('click',()=>{
      if(window.GalleryAndroid&&typeof window.GalleryAndroid.pickHistoryImport==='function'){
        window.GalleryAndroid.pickHistoryImport();
      }else el('history-file').click();
    });
    el('history-file').addEventListener('change',async(e)=>{
      const file=e.target.files&&e.target.files[0];
      if(!file)return;
      try{
        if(file.size>128*1024*1024)throw new Error('CSV 파일은 128MB 이하여야 합니다.');
        const csv=await file.text();await importHistoryCsv(csv);
      }catch(err){ui.msg.textContent='복원 실패: '+err.message;}
      e.target.value='';
    });
    document.addEventListener('keydown',e=>{if(e.key==='Escape')closeSettings(); if(e.key==='ArrowRight'&&ui.settings.hidden)next(); if(e.key===' '&&ui.settings.hidden){e.preventDefault();el('toggle-pause').click();}});
    document.addEventListener('visibilitychange',()=>{if(!document.hidden){if(state.playing)startClock();refreshForDay().catch(()=>{});collectorPump().catch(()=>{});}});
    window.addEventListener('offline',()=>{
      state.networkOnline=false;
      state.collectorStopReason='인터넷 연결 없음 · 저장된 작품으로 계속 전시';
      updateInfo();
    });
    window.addEventListener('online',()=>{
      state.networkOnline=true;state.collectorLastAt=0;
      // Retry connection failures, never shorten a provider's 429/503 cooldown.
      state.collectorRetry=Object.fromEntries(Object.entries(state.collectorRetry)
        .filter(([_,entry])=>!entry.network));
      state.collectorStopReason='';
      if(!document.hidden){fillPool(CONFIG.targetPool).catch(()=>{});collectorPump().catch(()=>{});}
      updateInfo();
    });
  }
  async function init(){
    wire();
    try{
      state.db=await openDB();
      const [a,b,flip,movements,auditSaved]=await Promise.all([dbGet('settings','stats'),dbGet('settings','cursors'),dbGet('settings','flipped'),dbGet('settings','movementPages'),dbGet('settings','inventoryAudit')]);
      if(a&&a.value){state.stats=Object.assign(state.stats,a.value);}
      if(b&&b.value){state.cursors=Object.assign(state.cursors,b.value);}
      state.cursors.asian=state.cursors.asian||{};
      state.cursors.african=state.cursors.african||{};
      state.cursors.additional=state.cursors.additional||{};
      state.cursors.smithsonian=state.cursors.smithsonian||{};
      state.cursors.modern=state.cursors.modern||{};
      state.cursors.openverseModern=state.cursors.openverseModern||{};
      state.cursors.media=state.cursors.media||{};
      state.cursors.movement=state.cursors.movement||{};
      state.cursors.wellcome=state.cursors.wellcome||{};
      state.cursors.princeton=state.cursors.princeton||{};
      state.cursors.smithsonianNpgShard=Math.max(0,Math.min(255,Number(state.cursors.smithsonianNpgShard)||0));
      state.cursors.smithsonianChndmShard=Math.max(0,Math.min(255,Number(state.cursors.smithsonianChndmShard)||0));
      state.cursors.global=state.cursors.global||{};
      const gIndex=await dbGet('settings','globalCategoryIndex');
      state.globalCategoryIndex=Number.isInteger(gIndex&&gIndex.value)?Math.max(0,gIndex.value):0;
      state.stats.modernShown=Number(state.stats.modernShown)||0;
      state.cursors.met=Object.assign({'11':0,'9':0,'21':0,'6':0},state.cursors.met||{});
      state.movementPages=(movements&&movements.value&&typeof movements.value==='object')?movements.value:{};
      state.audit=auditSaved&&auditSaved.value||null;
      state.flipped=!!(flip&&flip.value);
      applyRotation();
      if(!Number.isInteger(state.stats.movementIndex)||state.stats.movementIndex<0||state.stats.movementIndex>=C.MOVEMENTS.length)state.stats.movementIndex=0;
      // APK ships four true paintings. Load before starting the clock so a
      // transient outage or slow museum search cannot freeze a displayed work.
      await loadMovementCatalog();
      await restoreCollector();
      await hydrateHistory();
      await hydrateDownloadedIndex();
      await restoreCandidatePool();
      await restoreDownloadedInventory(300);
      await loadOfflineDeck();
      const firstUnseen=state.offlineReady.find(x=>!seenInMemory(x.art,x.visualHash));
      if(firstUnseen){
        displayLoaded(firstUnseen,true);
      }else{
        await restoreLastShown();
        if(!state.current){
          await fillPool(CONFIG.minPool);
          await prepareNext();
          if(state.prepared){const first=state.prepared;state.prepared=null;displayLoaded(first);}
        }
      }
      startClock();
      refreshForDay().catch(()=>{});
      prepareNext().catch(()=>{});
      setInterval(()=>refreshForDay().catch(()=>{}),60*1000);
      setInterval(updateInfo,30000);
      startContinuousCollector();
      if('serviceWorker' in navigator && !window.GalleryAndroid && location.protocol==='https:'){
        navigator.serviceWorker.register('./sw.js').catch(()=>{});
      }
      if('wakeLock' in navigator&&!window.GalleryAndroid){
        const keepAwake=async()=>{try{await navigator.wakeLock.request('screen');}catch(_){}};
        keepAwake();document.addEventListener('visibilitychange',()=>{if(!document.hidden)keepAwake();});
      }
    }catch(e){inform('초기화 실패: '+e.message+' · 저장 공간 또는 브라우저 설정을 확인하세요.');ui.placeholder.hidden=false;}
    updateInfo();
  }
  // Read-only diagnostics for local automated verification.
  window.__galleryDiagnostic=()=>({shown:state.stats.shown,slot:state.stats.slot,portrait:state.stats.portrait,
    other:state.stats.other,pool:state.pool.length,current:state.current&&state.current.art.key,
    prepared:state.prepared&&state.prepared.art.key,errors:state.lastErr,sourceReady:state.sourceReady,
    apiCalls:state.apiCalls,day:state.stats.day,playing:state.playing,
    movementIndex:state.stats.movementIndex,movement:state.current&&state.current.art.movement,
    flipped:state.flipped,caption:[ui.title.textContent,ui.meta.textContent],
    dedupBlocked:state.dedupBlocked,exhaustedTicks:state.exhaustedTicks,recentKeys:state.recentKeys.size,
    visualHashes:state.visualHashes.size,sourceCount:3+C.ASIAN_MUSEUMS.length+C.AFRICAN_MUSEUMS.length+C.ADDITIONAL_MUSEUMS.length+C.SMITHSONIAN_MUSEUMS.length+C.GLOBAL_OPEN_ART_CATEGORIES.length,
    collector:{running:state.collectorRunning,lastAt:state.collectorLastAt,validatedPrefetch:state.collectorSuccess,errors:state.collectorErrors,categoryIndex:state.globalCategoryIndex,windowDownloaded:state.collectorWindowSaved,windowGoal:null,dayDownloaded:state.collectorDaySaved,throttled:state.collectorThrottled,retryEntries:Object.keys(state.collectorRetry).length,stopReason:state.collectorStopReason,cacheStats:nativeCacheStats()},
    modernShown:state.stats.modernShown,modernFetched:state.modernFetched,modernPool:state.pool.filter(a=>a.modern).length,modernTargetNext:C.targetModern(state.stats.slot),
    lastSwapAt:state.lastSwapAt,tickCount:state.tickCount,emergencySwaps:state.emergencySwaps,
    offlineReady:state.offlineReady.length,nativeClock:state.nativeClock,nextDueAt:state.nextDueAt});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
