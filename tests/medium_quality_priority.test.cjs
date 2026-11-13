const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const C=require('../web/core.js');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const art=(key,w,h,movement='additional')=>({key, width:w,height:h,movement,
 source:'유럽 미술관',image:'https://upload.wikimedia.org/wikipedia/commons/a/aaa/artwork.jpg',
 title:'Portrait '+key,artist:'Artist '+key,type:'Painting',rightsOK:true,license:'Public domain'});
test('75 percent threshold admits real portrait ratios formerly rejected by 80',()=>{
 const w=1000,h=2100,vw=1000,vh=1600;
 const actual=C.portraitScreenFill(w,h,vw,vh);
 assert(actual>=.75 && actual<.80);
 assert.equal(C.fillsPortraitScreen(w,h,vw,vh,.75),true);
 assert.equal(C.fillsPortraitScreen(w,h,vw,vh,.80),false);
 assert.equal(C.fillsPortraitScreen(w,h,vw,vh),true);
});
test('minimum accepted 1000 short 1400 long; 999 or 1399 remains excluded',()=>{
 for(const [w,h] of [[1000,1400],[1400,1000],[1000,1700],[1400,2000],[1200,1600]])
   assert.equal(C.acceptableResolution(w,h),true,String(w)+'x'+h);
 for(const [w,h] of [[999,2000],[2000,999],[1300,1399],[0,1600],[-1,2000],[800,1200]])
   assert.equal(C.acceptableResolution(w,h),false,String(w)+'x'+h);
 assert.equal(C.highResolution(1000,1400),false,'medium must not be mislabeled high');
 assert.equal(C.highResolution(1200,1600),true);
});
test('quality tiers order high 2, medium 1, unknown 0',()=>{
 const high=art('high',1200,1600), medium=art('medium',1000,1500);
 assert.equal(C.qualityTier(high),2);
 assert.equal(C.qualityTier(medium),1);
 assert.equal(C.qualityTier(art('unknown',0,0)),0);
 assert.deepEqual([medium,high].sort((a,b)=>C.qualityTier(b)-C.qualityTier(a)).map(x=>x.key),['high','medium']);
});
test('new thresholds are consistent across WebView and Android image-cache decoder',()=>{
 const js=read('web/app.js'),java=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(js,/minimumPortraitFill:\.75/);
 assert.match(js,/C\.acceptableResolution\(img\.naturalWidth,img\.naturalHeight\)/);
 assert.match(js,/eligible\.sort\(\(a,b\)=>C\.qualityTier\(b\)-C\.qualityTier\(a\)\)/);
 assert.match(java,/MIN_IMAGE_SHORT_SIDE = 1000/);
 assert.match(java,/MIN_IMAGE_LONG_SIDE = 1400/);
 assert.match(java,/acceptableResolution\(tmp\)/);
 assert.match(java,/acceptableResolution\(f\)/);
 assert.match(java,/ART_INTERVAL_MS = 30000L/);
});
test('75 percent applies only to unlocked portrait and does not weaken 90 day rule',()=>{
 const now=Date.parse('2026-11-13T00:00:00Z');
 const a=art('a',1000,1700);
 assert(C.eligibleArt(a));
 assert(C.metadataResolutionOkay({...a,museumRegion:'additional'}));
 assert.equal(C.canReshow(now-89*86400000,now),false);
 assert.equal(C.canReshow(now-90*86400000,now),true);
 const html=read('web/index.html');
 assert(html.includes('75% 이상'));
 assert(html.includes('1000px') && html.includes('1400px'));
 assert(html.includes('고화질 우선'));
 const gradle=read('android-app/app/build.gradle');
 assert(gradle.includes("applicationId 'com.gallery.kiosk.v166'"));
 assert(gradle.includes("versionName '1.6.6'"));
});
