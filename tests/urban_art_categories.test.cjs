const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const C=require('../web/core.js');
function file(p){return fs.readFileSync(p,'utf8')}

test('three distinct user-requested styles are searchable and may be displayed as 2D images',()=>{
 const kinds=new Set(C.MIXED_MEDIA_CATEGORIES.map(x=>x.kind));
 for(const kind of ['Contemporary Art','Street Art','Graffiti']) assert.ok(kinds.has(kind));
 for(const x of C.MIXED_MEDIA_CATEGORIES.slice(-3)) {
   const painting={key:'commons:125',source:'Wikimedia Commons',title:'Original '+x.kind,
     artist:'작가 미상',type:x.kind,classification:x.kind,medium:'',width:1000,height:1667,
     rightsOK:true,license:'CC0',
     image:'https://upload.wikimedia.org/wikipedia/commons/a/ab/example.jpg'};
   assert.equal(C.eligibleArt(painting),true,x.kind);
   assert.equal(C.eligibleArt({...painting,rightsOK:false}),false);
 }
 const source=file('web/app.js');
 assert.match(source,/items\.length>2110/);
 assert.match(source,/C\.shuffledCopy/);
 assert.match(source,/C\.artworkYearLabel/);
});

test('native request bridge exposes only the three known art categories',()=>{
 const java=file('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(java,/"contemporary-art","street-art","graffiti"/);
 assert.match(java,/"Contemporary art","Street art","Graffiti"/);
 assert.match(java,/PortraitAdapter\.convert/);
 assert.match(java,/ART_INTERVAL_MS = 30000L/);
 const gradle=file('android-app/app/build.gradle');
 assert.match(gradle,/versionName '1\.7\.6-urbanart'/);
 assert.match(gradle,/applicationId 'com\.gallery\.kiosk\.urbanart'/);
});

test('require PD/CC0 static rights and keep unknown creation dates explicitly unknown',()=>{
 const base={query:{pages:[{pageid:2653,title:'File:Graffiti in Sydney.jpg',
 imageinfo:[{width:4000,height:3000,mime:'image/jpeg',
 thumburl:'https://upload.wikimedia.org/wikipedia/commons/a/ab/ab.jpg',
 extmetadata:{LicenseShortName:{value:'CC0'},Artist:{value:'Original photographer'}}}]}]}};
 const out=C.normalizeMixedMediaCommons(base,'graffiti');
 assert.equal(out.length,1);
 assert.equal(out[0].type,'Graffiti');
 assert.equal(out[0].rightsOK,true);
 assert.equal(C.eligibleArt(out[0]),true);
 assert.equal(C.artworkYearLabel(out[0]),'연도 미상');
 base.query.pages[0].imageinfo[0].extmetadata.LicenseShortName.value='All rights reserved';
 const notFree=C.normalizeMixedMediaCommons(base,'street-art');
 assert.equal(notFree[0].rightsOK,false);
 assert.equal(C.eligibleArt(notFree[0]),false);
});
