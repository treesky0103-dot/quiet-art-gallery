(function () {
  'use strict';
  const C = window.GalleryCore;
  const CONFIG = Object.freeze({intervalMs: 30000, minPool: 28, targetPool: 180, maxQueue: 800, prefetch: 1, retryMs: 20000, pruneDays: 90, movementRetryMs: 5*60*1000, minimumPortraitFill:.75});
  const test = window.__GALLERY_TEST__ || null;
  const INTERVAL = test && test.intervalMs >= 100 ? test.intervalMs : CONFIG.intervalMs;
  const el = id => document.getElementById(id);
  const ui = {a:el('art-a'),b:el('art-b'), placeholder:el('placeholder'), status:el('main-status'),hud:el('hud'),
    caption:el('caption'),title:el('art-title'),meta:el('art-meta'),settings:el('settings'), backdrop:el('settings-backdrop'),
    pause:el('toggle-pause'),done:el('settings-done'),msg:el('setting-message')};
  const state = {
    db:null,pool:[],pendingKeys:new Set(), prepared:null,current:null,currentNode:ui.b,
    playing:true,busy:false,filling:null,preparing:null,timer:null,hideTimer:null,lastRendered:null,
    offlineReady:[],recentLoaded:[],recentDisplayed:new Set(),emergencyIndex:0,emergencySwaps:0,
    recentKeys:new Map(),visualHashes:new Map(),dedupBlocked:0,exhaustedTicks:0,
    lastSwapAt:0, nextDueAt:0,nativeClock:false,tickCount:0,
    cursors:{cleveland:{Painting:0,Drawing:0,Print:0},chicago:1,met:{'11':0,'9':0,'21':0,'6':0},asian:{},african:{},additional:{},smithsonian:{},modern:{},openverseModern:{}},
    sourceOrder:0,cmaType:0,metType:0,metIDs:[],metIndex:0, asianOrder:0, africanOrder:0, additionalOrder:0, smithsonianOrder:0, smithsonianCategoryOrder:0,
    modernOrder:0,modernCategoryIndex:0,modernOpenverseIndex:0,modernFetched:0,modernErrors:0,
    movementPages:{},lastMovementTry:{}, flipped:false, audit:null, auditing:false,
    failures:{cleveland:0,chicago:0,met:0,asian:0,african:0,additional:0,smithsonian:0,modern:0},backoff:{},
    stats:{slot:0,shown:0,portrait:0,other:0,modernShown:0,updatedAt:'',day:'',movementIndex:0},
    apiCalls:0,lastErr:'',sourceReady:[],lastTime:0
  };
  const sourceNames={cleveland:'클리블랜드',chicago:'시카고',met:'메트로폴리탄',asian:'아시아 박물관(공용 자료)',african:'아프리카 박물관(공용 자료)',additional:'세계 미술관 21곳(공용 자료)',smithsonian:'스미스소니언 미국미술관·국립아시아미술관(공개 회화)',modern:'현대 창작 · Openverse / 위키미디어'};
  function inform(message){ ui.status.textContent=message; ui.msg.textContent=message; }
  function wait(ms){return new Promise(r=>setTimeout(r,ms));}
  function openDB(){
    return new Promise((resolve,reject)=>{
      if(!window.indexedDB) return reject(new Error('IndexedDB 지원 없음'));
      const r=indexedDB.open('quiet-art-gallery-v1',1);
      r.onupgradeneeded=()=>{const db=r.result;const seen=db.createObjectStore('seen',{keyPath:'key'});seen.createIndex('when','when');db.createObjectStore('settings',{keyPath:'key'});};
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
  async function persist(){await dbPutMany('settings',[{key:'stats',value:state.stats},{key:'cursors',value:state.cursors}]);}
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
    // Reserve the next style quota slot synchronously BEFORE prefetch begins.
    // IndexedDB writes must not cause 65/35 scheduling drift.
    state.stats.slot++;state.stats.shown++;
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
    if(window.GalleryAndroid && /^offline\/fallback-(?:[0-9]|1[0-5])\.jpg$/.test(art.offlineAsset||'')){
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

  async function loadOfflineDeck(){
    if(!window.GalleryAndroid)return 0;
    try{
      const r=await fetch('https://appassets.gallery/offline-deck.json',{cache:'no-store'});
      if(!r.ok)throw Error('비상 작품 목록 없음');
      const items=await r.json();
      if(!Array.isArray(items)||items.length<2||items.length>16)throw Error('비상 작품 목록 형식 오류');
      const loaded=[];
      for(const art of items){
        if(!/^offline\/fallback-(?:[0-9]|1[0-5])\.jpg$/.test(art.offlineAsset||'')||
          !C.eligibleArt(art)||!C.metadataResolutionOkay(art))continue;
        art.movement=C.classifyMovement(art)||'additional';
        try{loaded.push(await loadImage(art));}catch(e){state.lastErr='비상 작품: '+e.message;}
      }
      state.offlineReady=loaded;
      return loaded.length;
    }catch(e){state.lastErr='비상 작품 준비: '+e.message;return 0;}
  }
  function normalizeBatch(kind,result){
    if(kind==='cleveland')return (Array.isArray(result.data)?result.data:[]).map(C.normalizeCleveland);
    if(kind==='chicago')return (Array.isArray(result.data)?result.data:[]).map(x=>C.normalizeChicago(x, result.config && result.config.iiif_url || 'https://www.artic.edu/iiif/2'));
    if(kind==='openverseModern')return C.normalizeModernOpenverse(result);
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
    if(kind==='cleveland'){
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
        const types=['Painting','Drawing','Print'];const t=types[(state.cmaType++)%3];let offset=state.cursors.cleveland[t]||0;
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
        const museum=C.ADDITIONAL_MUSEUMS[(state.additionalOrder++*8)%C.ADDITIONAL_MUSEUMS.length];
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
      state.failures[source]=(state.failures[source]||0)+1;
      state.backoff[source]=Date.now()+Math.min(10*60*1000,10000*Math.pow(2,state.failures[source]));
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
      if(Number(a.width)>0&&Number(a.height)>0&&
        !C.fillsPortraitScreen(a.width,a.height,innerWidth,innerHeight,CONFIG.minimumPortraitFill))continue;
      if(seenInMemory(a,null))continue;
      // Unknown/ambiguous style metadata cannot be silently labelled as a movement.
      a.movement=C.classifyMovement(a);
      if(!a.movement)continue;
      state.pool.push(a);state.pendingKeys.add(a.key);
    }
  }
  async function fillPool(target=CONFIG.targetPool){
    if(state.filling)return state.filling;
    state.filling=(async()=>{
      let attempts=0, progress=0;
      while(state.pool.length<target && attempts<14){
        const sources=['cleveland','chicago','met','asian','african','additional','additional','smithsonian','modern','modern'];
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
  async function takeCandidate(goal, movementId){
    // Preserve the verified school / portrait priority, but choose a high-
    // resolution artwork before a medium-resolution one within that group.
    // Unknown image metadata can still enter, but only after known high/medium.
    const order=[goal,'unknown',goal==='portrait'?'other':'portrait'];
    for(const orient of order){
      const eligible=state.pool.filter(a=>a.movement===movementId&&C.orientation(a)===orient);
      eligible.sort((a,b)=>C.qualityTier(b)-C.qualityTier(a));
      for(const a of eligible){
        const idx=state.pool.indexOf(a);if(idx<0)continue;
        if(await seenRecently(a)){
          state.pool.splice(idx,1);state.pendingKeys.delete(a.key);continue;
        }
        state.pool.splice(idx,1);state.pendingKeys.delete(a.key);return a;
      }
    }
    return null;
  }
  async function prepareNext(){
    if(state.prepared)return state.prepared;
    if(state.preparing)return state.preparing;
    state.preparing=(async()=>{
      const orientationGoal='portrait';
      if(!state.pool.length)await fillPool(CONFIG.minPool);
      // Seven evenly distributed modern-art goals per twenty normal displays.
      // A goal is intentionally not a false quota guarantee: when no genuine
      // CC0/public-domain new art exists, preserve classic rotation instead.
      const wantModern=C.targetModern(state.stats.slot);
      if(wantModern){
        if(!state.pool.some(a=>a.movement==='modern'))await fetchSource('modern');
        for(let attempt=0;attempt<12;attempt++){
          const art=await takeCandidate('portrait','modern');
          if(!art)break;
          try{
            const loaded=await loadImage(art);
            if(await seenRecently(art,loaded.visualHash)){state.dedupBlocked++;continue;}
            state.prepared=loaded;break;
          }catch(e){state.lastErr='현대 작품: '+e.message;}
        }
        if(state.prepared)return state.prepared;
      }
      const firstIdx=(Number(state.stats.movementIndex)||0)%C.MOVEMENTS.length;
      // One targeted lookup for the next movement. If unavailable, skip it
      // rather than inventing a label or breaking the 90-day embargo.
      const desired=C.MOVEMENTS[firstIdx].id==='modern'?'renaissance':C.MOVEMENTS[firstIdx].id;
      if(!state.pool.some(a=>a.movement===desired)){
        let calls=0;
        // Visit a few missing schools per retry so the app does not stall forever
        // when the first museum has no supported images for a given school.
        for(let step=0;step<C.MOVEMENTS.length && calls<3;step++){
          const id=C.MOVEMENTS[(firstIdx+step)%C.MOVEMENTS.length].id;
          if(id==='modern')continue;
          if(state.pool.some(a=>a.movement===id))break;
          if(Date.now()-(state.lastMovementTry[id]||0)<CONFIG.movementRetryMs)continue;
          calls++;
          await fetchForMovement(id);
          if(state.pool.some(a=>a.movement===id))break;
        }
      }
      for(let delta=0;delta<C.MOVEMENTS.length;delta++){
        const m=C.MOVEMENTS[(firstIdx+delta)%C.MOVEMENTS.length];
        if(m.id==='modern'||!state.pool.some(a=>a.movement===m.id))continue;
        let fallback=null;
        for(let attempt=0;attempt<15;attempt++){
          const art=await takeCandidate(orientationGoal,m.id);
          if(!art)break;
          try{
            const loaded=await loadImage(art);
            if(await seenRecently(art,loaded.visualHash)){state.dedupBlocked++;continue;}
            if(loaded.orient===orientationGoal){state.prepared=loaded;break;}
            if(!fallback)fallback=loaded;
            else addCandidates([loaded.art]);
          }catch(e){state.lastErr=`이미지: ${e.message}`;}
        }
        if(!state.prepared&&fallback)state.prepared=fallback;
        else if(state.prepared&&fallback)addCandidates([fallback.art]);
        if(state.prepared)break;
      }
      if(state.pool.length<CONFIG.minPool&&!state.filling)fillPool(CONFIG.targetPool).catch(()=>{});
      return state.prepared;
    })();
    try{return await state.preparing;}finally{state.preparing=null;}
  }
  async function restoreLastShown(){
    try{
      const saved=await dbGet('settings','lastArtwork');
      if(!saved||!C.eligibleArt(saved.value)||!C.metadataResolutionOkay(saved.value))return false;
      const last=await loadImage(saved.value);
      ui.a.src=last.src;ui.a.alt=last.art.title+' — '+last.art.artist;
      ui.a.classList.add('visible');ui.b.classList.remove('visible');
      state.current=last;state.currentNode=ui.a;
      ui.title.textContent=C.tidyLabel(last.art.title,'제목 미상');
      ui.meta.textContent=C.tidyLabel(last.art.artist,'작가 미상');
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
    markSeen(show); // Reserve identities before asynchronous disk writes.
    const target=state.currentNode===ui.a?ui.b:ui.a;
    target.alt=show.art.title+' — '+show.art.artist;
    target.src=show.src;
    target.classList.add('visible');
    state.currentNode.classList.remove('visible');
    ui.placeholder.hidden=true;
    state.currentNode=target;state.current=show;
    state.lastSwapAt=Date.now();
    ui.title.textContent=C.tidyLabel(show.art.title,'제목 미상');
    ui.meta.textContent=C.tidyLabel(show.art.artist,'작가 미상');
    const idx=C.MOVEMENTS.findIndex(m=>m.id===show.art.movement);
    state.stats.movementIndex=(Math.max(0,idx)+1)%C.MOVEMENTS.length;
    state.recentLoaded=[show,...state.recentLoaded.filter(x=>x.art.key!==show.art.key)].slice(0,8);
    state.recentDisplayed.add(show.art.key);
    if(emergency)state.emergencySwaps++;
    if(test&&test.onShow)test.onShow(show.art,show.orient,emergency);
    // Persist in the background: storage latency may not delay a visual transition.
    recordSeen(show).then(()=>
      dbPutMany('settings',[{key:'lastArtwork',value:show.art}])
    ).catch(e=>{
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
    const all=state.offlineReady;
    for(let offset=0;offset<all.length;offset++){
      const item=all[(state.emergencyIndex+offset)%all.length];
      if(item&&!seenInMemory(item.art,item.visualHash) &&
         (!state.current || state.current.art.key!==item.art.key)){
        state.emergencyIndex=(state.emergencyIndex+offset+1)%all.length;
        return item;
      }
    }
    return null; // HOLD current image when candidates run out.
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
    // This may take minutes; it NEVER blocks the next 30-second tick.
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
  // Android calls this from a main-thread Handler every 30,000ms, independent
  // of the API and loading promises.
  window.__galleryClockTick=()=>advanceSlide();
  window.__galleryForeground=()=>{if(state.playing)startClock();};
  function next(){
    advanceSlide();
    if(state.playing)startClock(); // manual skip resets the 30-second clock
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
        if(Number(a.width)>0&&Number(a.height)>0&&!C.fillsPortraitScreen(a.width,a.height,innerWidth,innerHeight,CONFIG.minimumPortraitFill))continue;
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

  function cacheStatus(){
    if(window.GalleryAndroid&&window.GalleryAndroid.cacheStats){
      try{const s=JSON.parse(window.GalleryAndroid.cacheStats());return `${C.prettyBytes(s.bytes||0)} / 100MB`;}catch(_){return '확인할 수 없음';}
    }
    return '브라우저 관리 (자동 캐시 제한 불가)';
  }
  function updateInfo(){
    el('seen-count').textContent=state.stats.shown.toLocaleString('ko-KR')+'점';
    if(el('modern-count'))el('modern-count').textContent=(Number(state.stats.modernShown)||0).toLocaleString('ko-KR')+'점 / '+state.stats.shown.toLocaleString('ko-KR')+'점';
    const count=state.stats.portrait+state.stats.other;
    el('ratio-count').textContent=count?`${Math.round(state.stats.portrait*100/count)}% 세로형`:'집계 전';
    el('cache-count').textContent=cacheStatus();
    if(el('dedup-count'))el('dedup-count').textContent=
      '중복 차단 '+state.dedupBlocked+'건 · 후보 부족 '+state.exhaustedTicks+'회';
    const backup=el('fallback-status');
    if(backup)backup.textContent=state.offlineReady.length+'점 준비 · 중복 없이 '+state.emergencySwaps+'회 사용';
    el('refresh-count').textContent=state.stats.updatedAt?new Date(state.stats.updatedAt).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',hour12:false}):'–';
    el('source-status').textContent=state.sourceReady.length?state.sourceReady.map(s=>sourceNames[s]).join(' · '):state.lastErr||'연결 대기';
    const m=C.MOVEMENTS[(Number(state.stats.movementIndex)||0)%C.MOVEMENTS.length];
    el('movement-status').textContent=state.current ? (C.MOVEMENTS.find(x=>x.id===state.current.art.movement)?.label||'미분류')+' → '+m.label : m.label+'부터 탐색';
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
  function showSettings(){ui.settings.hidden=false;ui.backdrop.hidden=false;clearTimeout(state.hideTimer);controlsFor(0);updateInfo();}
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
    el('audit-now').addEventListener('click',()=>runInventoryAudit().catch(e=>{ui.msg.textContent='조사 실패: '+String(e.message||e);state.auditing=false;el('audit-now').disabled=false;}));
    el('refresh-now').addEventListener('click',async()=>{
      ui.msg.textContent='새 목록 확인 중...';
      state.backoff={};try{await refreshForDay(true);await fillPool(CONFIG.targetPool);ui.msg.textContent=`작품 후보 ${state.pool.length}점을 확보했습니다.`;}
      catch(e){ui.msg.textContent='갱신 실패: '+e.message;}updateInfo();
    });
    el('free-space').addEventListener('click',()=>{
      if(window.GalleryAndroid&&window.GalleryAndroid.clearImageCache){
        const ok=window.GalleryAndroid.clearImageCache();ui.msg.textContent=ok?'저장된 이미지 캐시를 삭제했습니다. 감상 기록은 그대로입니다.':'캐시 정리에 실패했습니다.';
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
    document.addEventListener('visibilitychange',()=>{if(!document.hidden&&state.playing){startClock();refreshForDay().catch(()=>{});}});
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
      state.stats.modernShown=Number(state.stats.modernShown)||0;
      state.cursors.met=Object.assign({'11':0,'9':0,'21':0,'6':0},state.cursors.met||{});
      state.movementPages=(movements&&movements.value&&typeof movements.value==='object')?movements.value:{};
      state.audit=auditSaved&&auditSaved.value||null;
      state.flipped=!!(flip&&flip.value);
      applyRotation();
      if(!Number.isInteger(state.stats.movementIndex)||state.stats.movementIndex<0||state.stats.movementIndex>=C.MOVEMENTS.length)state.stats.movementIndex=0;
      // APK ships four true paintings. Load before starting the clock so a
      // transient outage or slow museum search cannot freeze a displayed work.
      await hydrateHistory();
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
    visualHashes:state.visualHashes.size,sourceCount:3+C.ASIAN_MUSEUMS.length+C.AFRICAN_MUSEUMS.length+C.ADDITIONAL_MUSEUMS.length+C.SMITHSONIAN_MUSEUMS.length,
    modernShown:state.stats.modernShown,modernFetched:state.modernFetched,modernPool:state.pool.filter(a=>a.modern).length,modernTargetNext:C.targetModern(state.stats.slot),
    lastSwapAt:state.lastSwapAt,tickCount:state.tickCount,emergencySwaps:state.emergencySwaps,
    offlineReady:state.offlineReady.length,nativeClock:state.nativeClock,nextDueAt:state.nextDueAt});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
