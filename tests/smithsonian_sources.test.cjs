const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const C=require('../web/core.js');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const museums=C.SMITHSONIAN_MUSEUMS;
function response({pageid=135871,title='File:Portrait of a woman - Smithsonian American Art Museum.jpg',
  width=1550,height=2200,mime='image/jpeg',license='Public domain',artist='George Henry'}={}){
 return {query:{pages:[{pageid,title,imageinfo:[{
   width,height,mime,thumburl:'https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Smithsonian_Art.jpg/2000px-Smithsonian_Art.jpg',
   url:'https://upload.wikimedia.org/wikipedia/commons/a/a1/Smithsonian_Art.jpg',
   descriptionurl:'https://commons.wikimedia.org/wiki/File:Smithsonian_Art.jpg',
   extmetadata:{LicenseShortName:{value:license},Artist:{value:artist}}}]}]}};
}
test('two logically distinct Smithsonian museums and one NMAA with three actual Freer categories',()=>{
 assert.equal(museums.length,2);
 assert.deepEqual(museums.map(m=>m.id),['saam','nmaa']);
 assert.equal(museums[0].categories.length,1);
 assert.equal(museums[1].categories.length,3);
 assert.equal(museums[0].categories[0],'Paintings in the Smithsonian American Art Museum');
 assert.deepEqual(museums[1].categories,[
 'Paintings from China in the Freer Gallery',
 'Paintings from Japan in the Freer Gallery of Art',
 'Paintings from India in the Freer Gallery of Art'
 ]);
 assert.equal(3+C.ASIAN_MUSEUMS.length+C.AFRICAN_MUSEUMS.length+C.ADDITIONAL_MUSEUMS.length+museums.length,35);
});
test('CC0 and Public domain files normalize for both museum sources and classify into correct rotation',()=>{
 const a=C.normalizeSmithsonianCommons(response(),'saam');
 assert.equal(a.length,1);
 assert.equal(a[0].rightsOK,true);
 assert.equal(a[0].source,museums[0].label);
 assert.equal(C.eligibleArt(a[0]),true);
 assert.equal(C.metadataResolutionOkay(a[0]),true);
 assert.equal(C.classifyMovement(a[0]),'additional');
 const n=C.normalizeSmithsonianCommons(response({license:'CC0 1.0'}),'nmaa')[0];
 assert.equal(n.source,museums[1].label);
 assert.equal(n.rightsOK,true);
 assert.equal(C.classifyMovement(n),'asian');
 assert.equal(C.fillsPortraitScreen(n.width,n.height,1000,1600,.75),true);
});
test('CC BY, TIFF, framed photos and interior rooms are excluded',()=>{
 assert.equal(C.eligibleArt(C.normalizeSmithsonianCommons(response({license:'CC BY 4.0'}),'saam')[0]),false);
 assert.equal(C.eligibleArt(C.normalizeSmithsonianCommons(response({mime:'image/tiff'}),'nmaa')[0]),false);
 assert.equal(C.normalizeSmithsonianCommons(response({title:'File:Art museum gallery interior.jpg'}),'saam').length,0);
 assert.equal(C.normalizeSmithsonianCommons(response({title:'File:Framed painting photographed on a wall.jpg'}),'nmaa').length,0);
 assert.equal(C.normalizeSmithsonianCommons(response(),'not-a-smithsonian').length,0);
});
test('medium resolution can pass, but inadequate or narrow landscape is filtered',()=>{
 const ok=C.normalizeSmithsonianCommons(response({width:1000,height:1600}),'nmaa')[0];
 assert.equal(C.metadataResolutionOkay(ok),true);
 assert.equal(C.highResolution(ok.width,ok.height),false);
 assert.equal(C.fillsPortraitScreen(ok.width,ok.height,1000,1600,.75),true);
 const tiny=C.normalizeSmithsonianCommons(response({width:999,height:2400}),'nmaa')[0];
 assert.equal(C.metadataResolutionOkay(tiny),false);
 const wrong=C.normalizeSmithsonianCommons(response({width:1700,height:1000}),'saam')[0];
 assert.equal(C.fillsPortraitScreen(wrong.width,wrong.height,1000,1600,.75),false);
});
test('one Commons image is counted as one artwork across both Smithsonian museums',()=>{
 const a=C.normalizeSmithsonianCommons(response({pageid:434995}),'saam')[0];
 const b=C.normalizeSmithsonianCommons(response({pageid:434995}),'nmaa')[0];
 assert.equal(a.key,b.key);
 assert.equal(C.imageIdentity(a),C.imageIdentity(b));
 assert.equal(C.fingerprint(a),C.fingerprint(b));
 const now=Date.parse('2026-11-13T00:00:00Z');
 assert.equal(C.pickCandidate([b],'portrait',new Map([[a.key,now-1000]]),now),-1);
 assert.equal(C.canReshow(now-89*86400000,now),false);
});
test('both browser and native Android allowlist only official configured Commons categories',()=>{
 const app=read('web/app.js'), java=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(app,/kind==='smithsonianCommons'/);
 assert.match(app,/museum\.categories\[idx\]/);
 assert.match(java,/type\.equals\("smithsonianCommons"\)/);
 for(const m of museums){
  assert(java.includes('"'+m.id+'"'));
  for(const cat of m.categories)assert(java.includes('"'+cat+'"'),cat);
 }
 assert.match(java,/int catIndex=bounded\(parts\[1\],0,categories\[museum\]\.length-1\)/);
 assert.match(java,/int off=bounded\(parts\[2\],0,100000\)/);
 assert.match(java,/iiurlwidth=2000/);
 assert.match(app,/const cursorKey=museum\.id\+':'\+idx/);
 assert.match(app,/state\.smithsonianCategoryOrder\+\+%museum\.categories\.length/);
 assert.match(app,/const sources=\[[^\n]*'smithsonian'/);
 assert.match(app,/C\.normalizeSmithsonianCommons/);
 assert.match(app,/sourceCount:[^\n]*\+C\.SMITHSONIAN_MUSEUMS\.length/);
});
test('new user-visible info, independent APK ID and original 75 percent policy remain',()=>{
 const html=read('web/index.html'), gradle=read('android-app/app/build.gradle');
 assert(html.includes('전시 관리 · v1.6.6'));
 assert(html.includes('총 35곳'));
 assert(html.includes('75% 이상'));
 assert(html.includes('고화질 우선'));
 assert(html.includes('스미스소니언 미국미술관'));
 assert(html.includes('스미스소니언 국립아시아미술관'));
 assert(gradle.includes("applicationId 'com.gallery.kiosk.v166'"));
 assert(gradle.includes("versionName '1.6.6'"));
 assert(gradle.includes('versionCode 13'));
 const app=read('web/app.js');
 assert.match(app,/pruneDays: 90/);
 assert.match(app,/intervalMs: 30000/);
 assert.match(app,/minimumPortraitFill:\.75/);
 assert.match(app,/C\.qualityTier\(b\)-C\.qualityTier\(a\)/);
 assert.match(app,/const csv=await r\.text\(\);await importHistoryCsv\(csv\)/);
});
