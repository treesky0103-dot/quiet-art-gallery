(function () {
  'use strict';
  const C = window.GalleryCore;
  const CONFIG = Object.freeze({intervalMs: 30000, minPool: 22, targetPool: 140, maxQueue: 500, prefetch: 1, retryMs: 20000, pruneDays: 90, movementRetryMs: 5*60*1000});
  const test = window.__GALLERY_TEST__ || null;
  const INTERVAL = test && test.intervalMs >= 100 ? test.intervalMs : CONFIG.intervalMs;
  const el = id => document.getElementById(id);
  const ui = {a:el('art-a'),b:el('art-b'), placeholder:el('placeholder'), status:el('main-status'),hud:el('hud'),
    caption:el('caption'),title:el('art-title'),meta:el('art-meta'),settings:el('settings'), backdrop:el('settings-backdrop'),
    pause:el('toggle-pause'),done:el('settings-done'),msg:el('setting-message')};
  const state = {
    db:null,pool:[],pendingKeys:new Set(), prepared:null,current:null,currentNode:ui.b,
    playing:true,busy:false,filling:null,preparing:null,timer:null,hideTimer:null,lastRendered:null,
    cursors:{cleveland:{Painting:0,Drawing:0,Print:0},chicago:1,met:{'11':0,'9':0,'21':0,'6':0},asian:{},african:{},additional:{}},
    sourceOrder:0,cmaType:0,metType:0,metIDs:[],metIndex:0, asianOrder:0, africanOrder:0, additionalOrder:0, movementPages:{},lastMovementTry:{}, flipped:false, audit:null, auditing:false,
    failures:{cleveland:0,chicago:0,met:0,asian:0,african:0,additional:0},backoff:{},
    stats:{slot:0,shown:0,portrait:0,other:0,updatedAt:'',day:'',movementIndex:0},
    apiCalls:0,lastErr:'',sourceReady:[],lastTime:0
  };
  const sourceNames={cleveland:'클리블랜드',chicago:'시카고',met:'메트로폴리탄',asian:'아시아 박물관(공용 자료)',african:'아프리카 박물관(공용 자료)',additional:'유럽·미국 미술관 7곳(공용 자료)'};
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
  async function seenRecently(art){
    const now=Date.now();
    const exact=await dbGet('seen',art.key);
    if(exact&&!C.canReshow(exact.when,now))return true;
    const fp=C.fingerprint(art);
    if(fp){const near=await dbGet('seen',fp); if(near&&!C.canReshow(near.when,now))return true;}
    return false;
  }
  async function recordSeen(art,orient){
    const when=Date.now();
    const values=[{key:art.key,when}];const fp=C.fingerprint(art);if(fp)values.push({key:fp,when});
    await dbPutMany('seen',values);
    state.stats.slot+=1; state.stats.shown+=1;
    state.stats[orient==='portrait'?'portrait':'other']+=1;
    await persist();
  }
  function imageURL(art){
    if(!C.safeURL(art.image))return '';
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
    if(!C.highResolution(img.naturalWidth,img.naturalHeight))throw new Error('저해상도 또는 소형 이미지 제외');
    return {art,src,width:img.naturalWidth,height:img.naturalHeight,orient:img.naturalHeight>img.naturalWidth*1.02?'portrait':'other'};
  }
  function normalizeBatch(kind,result){
    if(kind==='cleveland')return (Array.isArray(result.data)?result.data:[]).map(C.normalizeCleveland);
    if(kind==='chicago')return (Array.isArray(result.data)?result.data:[]).map(x=>C.normalizeChicago(x, result.config && result.config.iiif_url || 'https://www.artic.edu/iiif/2'));
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
        const museum=C.ADDITIONAL_MUSEUMS[state.additionalOrder++%C.ADDITIONAL_MUSEUMS.length];
        const offset=Number(state.cursors.additional[museum.id])||0;
        const res=await request('additionalCommons',museum.id+':'+offset);
        addCandidates(C.normalizeAdditionalCommons(res,museum.id).filter(C.eligibleArt));
        const rows=Array.isArray(res.query&&res.query.pages)?res.query.pages.length:0;
        const total=Number(res.query&&res.query.searchinfo&&res.query.searchinfo.totalhits)||0;
        state.cursors.additional[museum.id]=(rows===0||rows<50||offset>=100000||(total&&offset+50>=total))?0:offset+50;
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
      while(state.pool.length<target && attempts<12){
        const source=['cleveland','chicago','met','asian','african','additional'][state.sourceOrder++%6];
        attempts++;
        progress+=await fetchSource(source);
        if(test&&typeof test.afterFetch==='function')test.afterFetch(source);
        if(state.pool.length>=target)break;
        if(attempts>=6&&!progress)break;
      }
      if(state.pool.length===0&&state.lastErr) inform('새 작품을 가져오지 못했습니다. 네트워크를 확인해 주세요.');
      return state.pool.length;
    })();
    try{return await state.filling;}finally{state.filling=null; updateInfo();}
  }
  async function takeCandidate(goal, movementId){
    // Only choose from the next verified school; orientation remains a target.
    const order=[goal,'unknown',goal==='portrait'?'other':'portrait'];
    for(const orient of order){
      for(let i=0;i<state.pool.length;i++){
        const a=state.pool[i];
        if(a.movement!==movementId||C.orientation(a)!==orient)continue;
        if(await seenRecently(a)){
          state.pool.splice(i,1);state.pendingKeys.delete(a.key);i--;continue;
        }
        state.pool.splice(i,1);state.pendingKeys.delete(a.key);return a;
      }
    }
    return null;
  }
  async function prepareNext(){
    if(state.prepared)return state.prepared;
    if(state.preparing)return state.preparing;
    state.preparing=(async()=>{
      const orientationGoal=C.targetOrientation(state.stats.slot);
      if(!state.pool.length)await fillPool(CONFIG.minPool);
      const firstIdx=(Number(state.stats.movementIndex)||0)%C.MOVEMENTS.length;
      // One targeted lookup for the next movement. If unavailable, skip it
      // rather than inventing a label or breaking the 90-day embargo.
      const desired=C.MOVEMENTS[firstIdx].id;
      if(!state.pool.some(a=>a.movement===desired)){
        let calls=0;
        // Visit a few missing schools per retry so the app does not stall forever
        // when the first museum has no supported images for a given school.
        for(let step=0;step<C.MOVEMENTS.length && calls<3;step++){
          const id=C.MOVEMENTS[(firstIdx+step)%C.MOVEMENTS.length].id;
          if(state.pool.some(a=>a.movement===id))break;
          if(Date.now()-(state.lastMovementTry[id]||0)<CONFIG.movementRetryMs)continue;
          calls++;
          await fetchForMovement(id);
          if(state.pool.some(a=>a.movement===id))break;
        }
      }
      for(let delta=0;delta<C.MOVEMENTS.length;delta++){
        const m=C.MOVEMENTS[(firstIdx+delta)%C.MOVEMENTS.length];
        if(!state.pool.some(a=>a.movement===m.id))continue;
        let fallback=null;
        for(let attempt=0;attempt<15;attempt++){
          const art=await takeCandidate(orientationGoal,m.id);
          if(!art)break;
          try{
            const loaded=await loadImage(art);
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
  async function next(){
    if(state.busy)return;state.busy=true;
    let retry=false;
    clearTimeout(state.timer);
    try{
      const show=await prepareNext();
      if(!show){
        if(!state.current)inform('전시할 작품을 찾고 있습니다. 네트워크나 공급원 상태를 확인해 주세요.');
        else inform('90일 제한을 지키며 새로운 작품을 찾는 중입니다.');
        retry=true;
        return;
      }
      if(await seenRecently(show.art)){
        state.prepared=null;retry=true;
        inform('90일 중복 방지 기록과 대조하여 다음 작품을 찾는 중입니다.');
        return;
      }
      const target=state.currentNode===ui.a?ui.b:ui.a;
      target.alt=show.art.title+' — '+show.art.artist;
      target.src=show.src;
      target.classList.add('visible');state.currentNode.classList.remove('visible');
      ui.placeholder.hidden=true;
      state.currentNode=target;state.current=show;state.prepared=null;
      ui.title.textContent=C.tidyLabel(show.art.title,'제목 미상');
      ui.meta.textContent=C.tidyLabel(show.art.artist,'작가 미상');
      state.stats.movementIndex=(C.MOVEMENTS.findIndex(m=>m.id===show.art.movement)+1)%C.MOVEMENTS.length;
      try{await recordSeen(show.art,show.orient);await dbPutMany('settings',[{key:'lastArtwork',value:show.art}]);}catch(e){
        state.playing=false;inform('감상 기록 저장에 실패했습니다. 90일 중복 방지를 위해 재생을 중단했습니다.');
        controlsFor(0);return;
      }
      if(test&&test.onShow)test.onShow(show.art,show.orient);
      updateInfo();
    }catch(e){state.lastErr=e.message;inform('작품 전환 오류: '+e.message);}
    finally{
      state.busy=false;
      if(state.playing)state.timer=setTimeout(next,retry?CONFIG.retryMs:INTERVAL);
      if(state.playing&&!retry)prepareNext().catch(()=>{});
    }
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
        const verifiedSize=(a.museumRegion==='asia'||a.museumRegion==='africa'||a.museumRegion==='additional'||a.source==='클리블랜드');
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
    const count=state.stats.portrait+state.stats.other;
    el('ratio-count').textContent=count?`${Math.round(state.stats.portrait*100/count)}% 세로형`:'집계 전';
    el('cache-count').textContent=cacheStatus();
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
  async function setFlip(enabled){
    state.flipped=!!enabled;
    document.body.classList.toggle('upside-down',state.flipped);
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
      if(typeof key!=='string'||key.length>270||!(/^(?:cma|aic|met):[1-9][0-9]{0,12}$|^fp:[^\s]{4,270}$/u.test(key))||
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
    state.pool=state.pool.filter(a=>C.eligibleArt(a));
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
    el('rotate-180').addEventListener('click',()=>setFlip(!state.flipped).catch(e=>{ui.msg.textContent='화면 방향 저장 실패: '+e.message;}));
    el('close-settings').addEventListener('click',closeSettings);
    el('settings-done').addEventListener('click',closeSettings);
    ui.backdrop.addEventListener('click',closeSettings);
    el('next').addEventListener('click',()=>{if(state.busy)return;state.prepared=null;next();controlsFor();});
    el('toggle-pause').addEventListener('click',()=>{
      state.playing=!state.playing;clearTimeout(state.timer);
      if(state.playing)state.timer=setTimeout(next,INTERVAL);
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
    document.addEventListener('visibilitychange',()=>{if(!document.hidden&&state.playing){clearTimeout(state.timer);state.timer=setTimeout(next,INTERVAL);refreshForDay().catch(()=>{});}});
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
      state.cursors.met=Object.assign({'11':0,'9':0,'21':0,'6':0},state.cursors.met||{});
      state.movementPages=(movements&&movements.value&&typeof movements.value==='object')?movements.value:{};
      state.audit=auditSaved&&auditSaved.value||null;
      state.flipped=!!(flip&&flip.value);
      document.body.classList.toggle('upside-down',state.flipped);
      if(!Number.isInteger(state.stats.movementIndex)||state.stats.movementIndex<0||state.stats.movementIndex>=C.MOVEMENTS.length)state.stats.movementIndex=0;
      await restoreLastShown();
      await refreshForDay();
      await fillPool(CONFIG.minPool);
      await next();
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
    flipped:state.flipped,caption:[ui.title.textContent,ui.meta.textContent]});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
