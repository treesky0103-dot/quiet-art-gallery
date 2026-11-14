const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const C=require('../web/core.js');
const source=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');
function commons(title='File:Trees on Red 4, 2024.jpg',license='CC0',w=2800,h=3900,id=13045){
 return {query:{pages:[{pageid:id,title,imageinfo:[{
   width:w,height:h,mime:'image/jpeg',
   thumburl:'https://upload.wikimedia.org/wikipedia/commons/a/aa/Trees.jpg',
   descriptionurl:'https://commons.wikimedia.org/wiki/File:Trees.jpg',
   extmetadata:{Artist:{value:'Original Maker'},LicenseShortName:{value:license}}
 }]}]}};
}
const UUID='d2ac498b-482e-45d3-b6c3-5c27840b882f';
function openverse(title='Digital painting CAFE',license='cc0',sourceValue='wikimedia'){
 return {results:[{id:UUID,title,creator:'Original Artist',license,source:sourceValue,
   width:1414,height:2000,watermarked:false,
   url:'https://upload.wikimedia.org/wikipedia/commons/4/4f/Digital_painting_CAFE.png',
   foreign_landing_url:'https://commons.wikimedia.org/wiki/File:Digital_painting_CAFE.png'}]};
}
test('modern category discovery is bounded and does not scrape Behance',()=>{
 assert.equal(C.MODERN_CATEGORIES.length,5);
 assert.equal(C.MODERN_OPENVERSE_TERMS.length,3);
 const java=source('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 for(const m of C.MODERN_CATEGORIES) assert(java.includes('"'+m.category+'"'),m.category);
 assert(java.includes('api.openverse.org/v1/images/'));
 assert(java.includes('license=cc0%2Cpdm'));
 assert(java.includes('source=wikimedia'));
 assert(!java.includes('www.behance.net'));
 const app=source('web/app.js');
 assert(app.includes("kind==='modernCommons'"));
 assert(app.includes("kind==='openverseModern'"));
 assert(app.includes("source==='modern'"));
 assert(app.includes("state.modernOrder++%3"));
});
test('1800+ 80-percent target is exactly four of each five display slots',()=>{
 for(let base=0;base<500;base+=5){
   const ids=Array.from({length:5},(_,i)=>base+i).filter(C.targetPost1800);
   assert.deepEqual(ids,[base,base+1,base+2,base+3]);
 }
 assert.deepEqual(C.eraQuota90Days(),{total:259200,post1800:207360,remainder:51840});
 const app=source('web/app.js');
 assert.match(app,/C.targetPost1800\(state\.stats\.slot\)/);
 assert.match(app,/C.artworkEra\(a\)/);
 assert.match(app,/C.artworkEra\(show\.art\)/);
});
test('2024 CC0 portrait original is admitted and routed to a dedicated modern group',()=>{
 const v=C.normalizeModernCommons(commons(),'2020s');
 assert.equal(v.length,1);
 assert.equal(v[0].modern,true);
 assert.equal(C.eligibleArt(v[0]),true);
 assert.equal(C.metadataResolutionOkay(v[0]),true);
 assert.equal(C.classifyMovement(v[0]),'modern');
 assert.equal(C.fillsPortraitScreen(v[0].width,v[0].height,1000,1600,.80),true);
});
test('old museum scan, image of framed work, or restricted creator license does not become modern art',()=>{
 assert.deepEqual(C.normalizeModernCommons(commons('File:Catherine II by Levitskiy 1794.jpg'),'century'),[]);
 assert.deepEqual(C.normalizeModernCommons(commons('File:Photo of Gallery paintings 2024.jpg'),'2020s'),[]);
 assert.deepEqual(C.normalizeModernCommons(commons('File:Trees on Red 4, 2024.jpg','CC BY 4.0'),'2020s'),[]);
 assert.deepEqual(C.normalizeModernCommons(commons('File:Trees on Red 4, 2024.jpg','CC0',1000,1100),'2020s')
   .filter(C.metadataResolutionOkay),[]);
});
test('explicit original digital painting from Openverse CC0 Wikimedia is admitted',()=>{
 const art=C.normalizeModernOpenverse(openverse())[0];
 assert.equal(art.key,'openverse:'+UUID);
 assert.equal(art.modern,true);
 assert.equal(art.rightsOK,true);
 assert.equal(art.movement,undefined);
 assert.equal(C.classifyMovement(art),'modern');
 assert.equal(C.eligibleArt(art),true);
 assert.equal(C.fillsPortraitScreen(art.width,art.height,1000,1600,.80),true);
});
test('Openverse keyword hits are rejected if historic, copyright restricted or outside Wikimedia',()=>{
 assert.deepEqual(C.normalizeModernOpenverse(openverse('Manuscript illustration from 1812')),[]);
 assert.deepEqual(C.normalizeModernOpenverse(openverse('A digital painting 1996')),[]);
 assert.deepEqual(C.normalizeModernOpenverse(openverse('Digital painting CAFE','by')),[]);
 assert.deepEqual(C.normalizeModernOpenverse(openverse('Digital painting CAFE','cc0','flickr')),[]);
 assert.deepEqual(C.normalizeModernOpenverse({results:[{...openverse().results[0],url:'https://example.org/a.png'}]}),[]);
});
test('Android API still uses 30 seconds, v1.6.6 isolated app and 90d dedup',()=>{
 const java=source('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert(java.includes('ART_INTERVAL_MS = 30000L'));
 assert(java.includes('openverseModern'));
 const app=source('web/app.js');
 assert(app.includes('hydrateHistory'));
 assert(app.includes('visualHashes'));
 const gradle=source('android-app/app/build.gradle');
 assert(gradle.includes("versionName '1.7.5-mediafull'"));
 assert(gradle.includes("applicationId 'com.gallery.kiosk.mediafull'"));
 const html=source('web/index.html');
 assert(html.includes('분야 순서 없이 무작위로 전시'));
 assert(html.includes('id="modern-count"'));
});
