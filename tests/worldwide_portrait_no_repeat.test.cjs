const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const C=require('../web/core.js');
const ROOT=path.join(__dirname,'..');
const src=p=>fs.readFileSync(path.join(ROOT,p),'utf8');
const first=['rijks','nga','getty','smk','paris','london','walters'];
const oceania=['ngv','nsw','aus-nga','south-aus','queensland','auckland','dunedin'];
const latam=['brasil-mnba','argentina-mnba','chile-mnba','peru-mali','colombia-mnc','uruguay-mnav','brasil-pina'];
test('all 14 independently probed Oceania / South America museums are configured in Java and JS',()=>{
 assert.equal(C.ADDITIONAL_MUSEUMS.length,21);
 assert.deepEqual(C.ADDITIONAL_MUSEUMS.slice(0,7).map(x=>x.id),first);
 assert.deepEqual(C.ADDITIONAL_MUSEUMS.slice(7,14).map(x=>x.id),oceania);
 assert.deepEqual(C.ADDITIONAL_MUSEUMS.slice(14).map(x=>x.id),latam);
 assert.equal(new Set(C.ADDITIONAL_MUSEUMS.map(x=>x.category)).size,21);
 const java=src('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 for(const m of C.ADDITIONAL_MUSEUMS){
   assert(java.includes('"'+m.category+'"'),m.id+' missing from Android whitelist');
   assert(java.includes('"'+m.id+'"'),m.id+' missing from Android ID list');
 }
 const app=src('web/app.js');
 assert.match(app,/state\.additionalOrder\+\+\*8/);
 assert.match(app,/CONFIG\.minimumPortraitFill/);
});
test('minimum 80% area on the ACTUAL portrait tablet size; never crop landscape/near-square',()=>{
 assert.equal(C.fillsPortraitScreen(1250,1850,1000,1600,.80),true);
 assert.equal(C.fillsPortraitScreen(1000,2000,1000,1600,.80),true);
 assert.equal(C.fillsPortraitScreen(1400,1800,1000,1600,.80),true); // ~80.35%
 assert.equal(C.fillsPortraitScreen(900,1600,1000,1600,.80),true);
 assert.equal(C.fillsPortraitScreen(1600,900,1000,1600,.80),false);
 assert.equal(C.fillsPortraitScreen(1600,1600,1000,1600,.80),false);
 assert.equal(C.fillsPortraitScreen(1000,3000,1000,1600,.80),false);
 assert.equal(C.fillsPortraitScreen(1350,1600,1000,1600,.80),false);
 assert.equal(C.fillsPortraitScreen(1400,1800,900,1600,.80),false); // 16:9 harder
 assert(C.portraitScreenFill(1000,1600,1000,1600)>.999);
});
test('Commons same image identity regardless of image URL thumbnail size and museum tag',()=>{
 const a={key:'commons:123',title:'Study',artist:'A. Painter',image:'https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Work.jpg/2000px-Work.jpg'};
 const b={...a,key:'commons:678',image:'https://upload.wikimedia.org/wikipedia/commons/a/a1/Work.jpg'};
 assert.equal(C.imageIdentity(a),C.imageIdentity(b));
 assert(C.identityKeys(a).includes(C.imageIdentity(b)));
 assert.equal(C.fingerprint(a),C.fingerprint(b));
});
test('visual hashes prevent subtle resized duplicates but not unrelated pictures',()=>{
 assert.equal(C.hashDistance('0123456789abcdef','0123456789abcdef'),0);
 assert.equal(C.hashDistance('0123456789abcdef','0123456789abcdee'),1);
 assert.equal(C.hashDistance('0123456789abcdef','fedcba9876543210')>2,true);
 assert.equal(C.hashDistance('','0123456789abcdef'),64);
});
test('no 90-day emergency-repeat loophole, old history import supports Commons and visual keys',()=>{
 const app=src('web/app.js');
 assert.match(app,/const all=state\.offlineReady;/);
 assert.doesNotMatch(app,/const all=\[\.\.\.state\.offlineReady,\.\.\.state\.recentLoaded\]/);
 assert.match(app,/function emergencyChoice\(\)/);
 assert.match(app,/if\(item&&!seenInMemory\(item\.art,item\.visualHash\)/);
 assert.match(app,/return null; \/\/ HOLD current image/);
 assert.match(app,/await hydrateHistory\(\)/);
 assert.match(app,/commons:\[1-9\]/);
 assert.match(app,/vis:\[0-9a-f\]/);
 assert.match(app,/visualHashes:new Map\(\)/);
});
test('user choice: hold frame if candidate exhausted rather than repeat against 90d history',()=>{
 const app=src('web/app.js');
 assert.match(app,/state\.exhaustedTicks\+\+/);
 assert.match(app,/중복 재생하지 않습니다/);
 const java=src('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(java,/ART_INTERVAL_MS = 30000L/);
 const gradle=src('android-app/app/build.gradle');
 assert.match(gradle,/versionName '1\.6\.4'/);
 assert.match(gradle,/applicationId 'com\.gallery\.kiosk\.v164'/);
});