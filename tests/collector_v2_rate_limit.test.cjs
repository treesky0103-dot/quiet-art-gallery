'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');

function policy(){
 const s=read('web/app.js');
 const a=s.indexOf('  function collectorDelay('),b=s.indexOf('  async function persistCollector(){',a);
 assert.ok(a>0&&b>a);
 const state={collectorWindowStarted:0,collectorWindowSaved:0,collectorDayKey:'',collectorDaySaved:0};
 const CONFIG={collectorEveryMs:1800000,collectorTickMs:60000,
   collectorTargetPerWindow:60,collectorMaxPerTick:4};
 const box={state,CONFIG};
 vm.runInNewContext(s.slice(a,b)+'\nthis.policy={collectorDelay,collectorErrorInfo,collectorQuota};',box);
 return {state,CONFIG,...box.policy};
}

test('adaptive quota is 2/min when 60 images are required per 30-minute window',()=>{
 const x=policy(),now=Date.parse('2026-11-14T14:00:00Z');
 assert.equal(x.collectorQuota(now),2);
 assert.equal(x.state.collectorDayKey,'2026-11-14','KST calendar day is used');
 x.state.collectorWindowSaved=10;
 assert.equal(x.collectorQuota(now+5*60000),2);
 x.state.collectorWindowSaved=55;
 assert.equal(x.collectorQuota(now+29*60000),4,'late backlog is bounded at four per tick');
 x.state.collectorWindowSaved=60;
 assert.equal(x.collectorQuota(now+29*60000),0);
 assert.equal(x.collectorQuota(now+30*60000),2,'next 30-minute window resets only its quota');
 assert.equal(x.state.collectorWindowSaved,0);
});

test('rate limits use strict source cooldown, exponential backoff and server Retry-After',()=>{
 const x=policy();
 assert.equal(x.collectorDelay(429,1),1800000);
 assert.equal(x.collectorDelay(429,2),3600000);
 assert.equal(x.collectorDelay(429,20),86400000);
 assert.ok(x.collectorDelay(503,1)>=480000);
 assert.ok(x.collectorDelay(0,1)>=45000);
 const err=x.collectorErrorInfo(new Error('HTTP 429 Retry-After:7200'));
 assert.equal(err.status,429);
 assert.equal(err.retryMs,7200000);
 assert.equal(x.collectorDelay(err.status,1,err.retryMs),7200000);
});

test('source backoff survives restart and manual refresh cannot bypass it',()=>{
 const s=read('web/app.js'),java=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(s,/collectorV2State/);
 assert.match(s,/async function restoreCollector/);
 assert.match(s,/async function persistCollector/);
 assert.match(s,/state\.backoff=Object\.fromEntries\(Object\.entries\(state\.backoff\)\.filter/);
 assert.match(s,/state\.failures\[source\]=Math\.min\(10/);
 assert.match(s,/state\.backoff\[source\]=Date\.now\(\)\+collectorDelay/);
 assert.match(java,/HOST_WAIT_UNTIL=new ConcurrentHashMap/);
 assert.match(java,/DateTimeFormatter\.RFC_1123_DATE_TIME/);
 assert.match(java,/recordHostThrottle\(conn,code\)/);
 assert.match(java,/recordHostThrottle\(con,httpStatus\)/);
});

test('disks preserve 8 GiB max, 7 GiB cleanup, 1.5 GiB reserve and 90-day viewing log independently',()=>{
 const s=read('web/app.js'),java=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(java,/MAX_IMAGE_CACHE = 8L \* 1024 \* 1024 \* 1024/);
 assert.match(java,/CLEAN_TO = 7L \* 1024 \* 1024 \* 1024/);
 assert.match(java,/FREE_RESERVE = 1536L \* 1024 \* 1024/);
 assert.match(java,/new File\(getFilesDir\(\), "gallery-images"\)/);
 assert.match(java,/new File\(imageDir,hashUrl\(src\)\+"\.img"\)/);
 assert.match(s,/pruneDays: 90/);
 assert.match(s,/store\.put\(entry\)/);
 assert.match(s,/dbPutMany\('seen'/);
 assert.match(s,/collectorMaxPerTick:4/);
});

test('CMA photograph indexing uses the same official CC0 API as other flat art',()=>{
 const s=read('web/app.js'),java=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(s,/const types=\['Painting','Drawing','Print','Photograph'\]/);
 assert.match(java,/Arrays\.asList\("Painting","Drawing","Print","Photograph"\)/);
 assert.match(java,/openaccess-api\.clevelandart\.org/);
});
