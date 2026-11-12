(function () {
  'use strict';
  const C = window.GalleryCore;
  const CONFIG = Object.freeze({intervalMs: 30000, minPool: 22, targetPool: 140, maxQueue: 500, prefetch: 1, retryMs: 20000, pruneDays: 90});
  const test = window.__GALLERY_TEST__ || null;
  const INTERVAL = test && test.intervalMs >= 100 ? test.intervalMs : CONFIG.intervalMs;
  const el = id => document.getElementById(id);
  const ui = {a:el('art-a'),b:el('art-b'), placeholder:el('placeholder'), status:el('main-status'),hud:el('hud'),
    caption:el('caption'),title:el('art-title'),meta:el('art-meta'),settings:el('settings'), backdrop:el('settings-backdrop'),
    pause:el('toggle-pause'),done:el('settings-done'),msg:el('setting-message')};
  const state = {
    db:null,pool:[],pendingKeys:new Set(), prepared:null,current:null,currentNode:ui.b,
    playing:true,busy:false,filling:null,preparing:null,timer:null,hideTimer:null,lastRendered:null,
    cursors:{cleveland:{Painting:0,Drawing:0,Print:0},chicago:1,met:{'11':0,'9':0,'21':0}},
    sourceOrder:0,cmaType:0,metType:0,metIDs:[],metIndex:0,
    failures:{cleveland:0,chicago:0,met:0},backoff:{},
    stats:{slot:0,shown:0,portrait:0,other:0,updatedAt:'',day:''},
    apiCalls:0,lastErr:'',sourceReady:[],lastTime:0
  };
  const sourceNames={cleveland:'클리블랜드',chicago:'시카고',met:'메트로폴리탄'};
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
    if(img.naturalWidth<260||img.naturalHeight<260)throw new Error('이미지 해상도 부족');
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
    }else if(kind==='chicago'){
      const page=Math.max(1,parseInt(param,10)||1);
      const params={query:{bool:{filter:[{term:{is_public_domain:true}},{exists:{field:'image_id'}}]}},page,limit:100,fields:['id','title','artist_title','image_id','is_public_domain','artwork_type_title','medium_display','thumbnail']};
      url=`https://api.artic.edu/api/v1/artworks/search?params=${encodeURIComponent(JSON.stringify(params))}`;
    }else if(kind==='metSearch'){
      const [dept,offset]=String(param).split(':');
      if(!['11','9','21'].includes(dept))throw Error('부서 ID 오류');
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
      }else if(source==='met'){
        const departments=['11','9','21'];const m=departments[(state.metType++)%3];
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
  function addCandidates(items){
    for(const a of items){
      if(state.pool.length>=CONFIG.maxQueue)break;
      if(!C.eligibleArt(a)||state.pendingKeys.has(a.key))continue;
      state.pool.push(a);state.pendingKeys.add(a.key);
    }
  }
  async function fillPool(target=CONFIG.targetPool){
    if(state.filling)return state.filling;
    state.filling=(async()=>{
      let attempts=0, progress=0;
      while(state.pool.length<target && attempts<6){
        const source=['cleveland','chicago','met'][state.sourceOrder++%3];
        attempts++;
        progress+=await fetchSource(source);
        if(test&&typeof test.afterFetch==='function')test.afterFetch(source);
        if(state.pool.length>=target)break;
        if(attempts>=3&&!progress)break;
      }
      if(state.pool.length===0&&state.lastErr) inform('새 작품을 가져오지 못했습니다. 네트워크를 확인해 주세요.');
      return state.pool.length;
    })();
    try{return await state.filling;}finally{state.filling=null; updateInfo();}
  }
  async function takeCandidate(goal){
    // Prefer tagged orientations. Unknown orientations are verified when image is decoded.
    const order=[goal,'unknown',goal==='portrait'?'other':'portrait'];
    for(const orient of order){
      for(let i=0;i<state.pool.length;i++){
        const a=state.pool[i];
        if(C.orientation(a)!==orient)continue;
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
    const target=C.targetOrientation(state.stats.slot);
    if(!state.pool.length)await fillPool(CONFIG.minPool);
    let fallback=null;
    for(let j=0;j<15;j++){
      if(!state.pool.length){await fillPool(CONFIG.minPool);if(!state.pool.length)break;}
      const art=await takeCandidate(target);
      if(!art)break;
      try{
        const loaded=await loadImage(art);
        if(loaded.orient===target){state.prepared=loaded;break;}
        if(!fallback)fallback=loaded;
        else addCandidates([loaded.art]);
      }catch(e){state.lastErr=`이미지: ${e.message}`;}
    }
    if(!state.prepared&&fallback)state.prepared=fallback;
    else if(state.prepared&&fallback)addCandidates([fallback.art]);
    if(state.pool.length<CONFIG.minPool&&!state.filling)fillPool(CONFIG.targetPool).catch(()=>{});
    return state.prepared;
    })();
    try{return await state.preparing;}finally{state.preparing=null;}
  }
  async function restoreLastShown(){
    try{
      const saved=await dbGet('settings','lastArtwork');
      if(!saved||!C.eligibleArt(saved.value))return false;
      const last=await loadImage(saved.value);
      ui.a.src=last.src;ui.a.alt=last.art.title+' — '+last.art.artist;
      ui.a.classList.add('visible');ui.b.classList.remove('visible');
      state.current=last;state.currentNode=ui.a;
      ui.title.textContent=last.art.title;
      ui.meta.textContent=last.art.artist+' · '+last.art.source+' · 이전에 전시한 작품';
      ui.placeholder.hidden=true;
      return true;
    }catch(_){return false;}
  }
  function controlsFor(ms=7500){
    ui.hud.classList.add('active');ui.caption.classList.add('active');
    clearTimeout(state.hideTimer);
    if(ms>0)state.hideTimer=setTimeout(()=>{
      if(!ui.settings.hidden)return;
      ui.hud.classList.remove('active');ui.caption.classList.remove('active');
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
      ui.title.textContent=show.art.title;
      ui.meta.textContent=show.art.artist+' · '+show.art.source+' · '+(show.orient==='portrait'?'세로형':'가로·정사각형');
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
    el('toggle-pause').textContent=state.playing?'Ⅱ':'▶';
    el('toggle-pause').setAttribute('aria-label',state.playing?'일시정지':'재생');
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
    el('close-settings').addEventListener('click',closeSettings);
    el('settings-done').addEventListener('click',closeSettings);
    ui.backdrop.addEventListener('click',closeSettings);
    el('next').addEventListener('click',()=>{if(state.busy)return;state.prepared=null;next();controlsFor();});
    el('toggle-pause').addEventListener('click',()=>{
      state.playing=!state.playing;clearTimeout(state.timer);
      if(state.playing)state.timer=setTimeout(next,INTERVAL);
      updateInfo();controlsFor();
    });
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
      const [a,b]=await Promise.all([dbGet('settings','stats'),dbGet('settings','cursors')]);
      if(a&&a.value){state.stats=Object.assign(state.stats,a.value);}
      if(b&&b.value){state.cursors=Object.assign(state.cursors,b.value);}
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
    apiCalls:state.apiCalls,day:state.stats.day,playing:state.playing});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
