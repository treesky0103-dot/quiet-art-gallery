const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const load=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');
test('Native Android uses non-blocking fixed-interval scheduler',()=>{
 const java=load('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(java,/ART_INTERVAL_MS = 30000L/);
 assert.match(java,/galleryClock\.postAtTime\(this,galleryDeadline\)/);
 assert.match(java,/@JavascriptInterface public void startArtworkClock\(int intervalMs\)/);
 assert.match(java,/window\.__galleryClockTick/);
 const app=load('web/app.js');
 assert.match(app,/window\.__galleryClockTick=\(\)=>advanceSlide\(\)/);
 assert.match(app,/function advanceSlide\(\)/);
 assert.match(app,/startArtworkClock\(CONFIG\.intervalMs\)/);
 assert.doesNotMatch(app,/setTimeout\(next,retry\?CONFIG\.retryMs:INTERVAL\)/);
});
test('Emergency offline high-res assets served by a strict Android path whitelist',()=>{
 const java=load('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(java,/offline-deck\.json/);
 assert.match(java,/offline\/fallback-\[0-3\]/);
 assert.match(java,/image\/jpeg/);
 const app=load('web/app.js');
 assert.match(app,/function emergencyChoice\(\)/);
 assert.match(app,/offlineReady/);
 assert.match(app,/recentLoaded/);
 assert.match(app,/function loadOfflineDeck\(\)/);
 assert.match(app,/art\.offlineAsset/);
});
test('Cleveland open access print rendition is preferred over 900px web image',()=>{
 const C=require('../web/core.js');
 const item={id:1,title:'Painting',type:'Painting',share_license_status:'CC0',
    images:{web:{url:'https://openaccess-cdn.clevelandart.org/a.jpg',width:620,height:900},
      print:{url:'https://openaccess-cdn.clevelandart.org/b.jpg',width:2333,height:3400}}};
 const a=C.normalizeCleveland(item);
 assert.equal(a.width,2333);
 assert.equal(a.height,3400);
 assert.equal(a.image,item.images.print.url);
 assert.equal(C.metadataResolutionOkay(a),true);
});
