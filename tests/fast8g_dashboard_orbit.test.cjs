'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const read=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');

function dashboard(native){
 const app=read('web/app.js');
 const start=app.indexOf('  function nativeCacheStats(');
 const end=app.indexOf('  function updateInfo()',start);
 assert(start>0 && end>start,'Dashboard functions available');
 const ids=['cache-progress','cache-progress-fill','cache-photo-count','cache-volume','cache-percent','cache-apk-count','cache-detail','cache-unshown-count','cache-shown-count','cache-eligible-count','cache-available-days','cache-estimate-note'];
 const els=Object.fromEntries(ids.map(id=>[id,{textContent:'',style:{width:''},attrs:{},setAttribute(k,v){this.attrs[k]=v}}]));
 const state={cacheSnapshotAt:0,cacheSnapshot:null,offlineManifestCount:2692,collectorStopReason:'',downloadedKeys:new Set(['a','b']),offlineUnseenReady:120};
 const window=native?{GalleryAndroid:{cacheStats:()=>JSON.stringify(native)}}:{};
 const scope={state,window,el:id=>els[id],C:{prettyBytes:v=>String(v)},Date,Math,Number};
 vm.runInNewContext(app.slice(start,end)+'\nthis.dashboard={nativeCacheStats,renderCacheProgress};',scope);
 scope.dashboard.renderCacheProgress();
 return {els,state};
}

test('settings bar reports downloaded FILE count and true cache bytes, NOT artwork metadata counts',()=>{
 const gib=1024**3;
 const {els}=dashboard({bytes:2*gib,limitBytes:8*gib,imageFiles:3719,
    freeBytes:8*gib,reservedBytes:1.5*gib,purgedFiles:11,purgedBytes:4000000,unshownImageFiles:2800,shownCachedFiles:919});
 assert.equal(els['cache-photo-count'].textContent,'3,719점');
 assert.equal(els['cache-volume'].textContent,'2.00 / 8.00 GiB');
 assert.equal(els['cache-percent'].textContent,'25.0%');
 assert.equal(els['cache-progress'].attrs['aria-valuenow'],'25.0');
 assert.equal(els['cache-progress-fill'].style.width,'25.00%');
 assert.equal(els['cache-apk-count'].textContent,'2,692점');
 assert.equal(els['cache-unshown-count'].textContent,'2,800점');
 assert.equal(els['cache-shown-count'].textContent,'919점');
 assert.equal(els['cache-eligible-count'].textContent,'2점');
 assert.equal(els['cache-available-days'].textContent,'0일 2시간 이하');
});

test('settings bar does not invent 8GiB usage in browsers without native filesystem',()=>{
 const {els}=dashboard(null);
 assert.equal(els['cache-photo-count'].textContent,'태블릿에서 확인');
 assert.equal(els['cache-progress-fill'].style.width,'0%');
});

test('right-bottom ambient circle is visual only and respects reduced motion',()=>{
 const html=read('web/index.html'),css=read('web/style.css');
 assert.match(html,/id="ambient-orbit" class="ambient-orbit" aria-hidden="true"/);
 assert.match(css,/\.ambient-orbit\s*\{/);
 assert.match(css,/pointer-events:none/);
 assert.match(css,/@keyframes quiet-orbit-turn/);
 assert.match(css,/@media \(prefers-reduced-motion:reduce\)/);
 assert.match(html,/id="cache-progress"[^>]+role="progressbar"/);
});

test('8GiB-first downloader does not stop at 60 per 30 minutes or a 2000 per day ceiling',()=>{
 const app=read('web/app.js');
 const start=app.indexOf('  function collectorDelay(');
 const end=app.indexOf('  async function persistCollector()',start);
 assert(start>0&&end>start);
 const context={state:{collectorWindowStarted:0,collectorWindowSaved:0,collectorDayKey:'',collectorDaySaved:0},
    CONFIG:{collectorEveryMs:1800000,collectorTickMs:15000,collectorMaxPerTick:6}};
 vm.runInNewContext(app.slice(start,end)+'\nthis.quota=collectorQuota;',context);
 const now=Date.parse('2026-11-14T14:00:00Z');
 assert.equal(context.quota(now),6);
 context.state.collectorWindowSaved=600;context.state.collectorDaySaved=2000;
 assert.equal(context.quota(now+20*60000),6);
 assert.match(app,/await loadImage\(art\)/);
 assert.match(app,/await dbPutMany\('downloaded'/);
 assert.match(app,/limitBytes/);
 assert.match(app,/collectorMaxAttemptsPerTick:18/);
 assert.match(app,/collectorTickMs:15000/);
 assert.doesNotMatch(app,/collectorTargetPerWindow:\s*60/);
});
