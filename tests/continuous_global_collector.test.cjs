'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const C=require('../web/core.js');
const read=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');
test('global open art includes non-museum books, independent artists, year collections',()=>{
  const cats=C.GLOBAL_OPEN_ART_CATEGORIES;
  assert.equal(cats.length,12);
  assert(cats.some(x=>x.id==='british-library'));
  assert(cats.some(x=>x.id==='independent'));
  assert(cats.some(x=>x.id==='r19'));
  assert.equal(new Set(cats.map(x=>x.id)).size,cats.length);
  assert.equal(new Set(cats.map(x=>x.category)).size,cats.length);
});
test('unlicensed Commons file and fake creation year remain excluded',()=>{
  const raw={query:{pages:[{
    pageid:54321,title:'File:Original artwork.jpg',
    imageinfo:[{url:'https://upload.wikimedia.org/wikipedia/commons/a/a1/Original_artwork.jpg',
      width:1600,height:2200,mime:'image/jpeg',
      extmetadata:{LicenseShortName:{value:'CC0'},Artist:{value:'Example creator'}}}]
  }]}};
  const out=C.normalizeGlobalCommons(raw,'p20');
  assert.equal(out.length,1);
  assert.equal(out[0].key,'commons:54321');
  assert.equal(out[0].rightsOK,true);
  assert.equal(out[0].yearStart,null);
  assert.equal(C.artworkEra(out[0]),'unknown','category century cannot become artist production year');
  assert.equal(C.eligibleArt(out[0]),true);
  const forbidden=structuredClone(raw);
  forbidden.query.pages[0].imageinfo[0].extmetadata.LicenseShortName.value='All rights reserved';
  assert.equal(C.eligibleArt(C.normalizeGlobalCommons(forbidden,'p20')[0]),false);
  assert.deepEqual(C.normalizeGlobalCommons(raw,'not-registered'),[]);
});
test('global category request is bounded in web and Android; not arbitrary URLs',()=>{
  const app=read('web/app.js'),native=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
  assert.match(app,/kind==='globalCommons'/);
  assert.match(app,/C\.GLOBAL_OPEN_ART_CATEGORIES\.find/);
  assert.match(app,/offset>100000/);
  assert.match(native,/type\.equals\("globalCommons"\)/);
  assert.match(native,/int off=bounded\(parts\[1\],0,100000\)/);
  assert.match(native,/commons\.wikimedia\.org\/w\/api\.php/);
  assert(!native.includes('userSuppliedArbitraryUrl'));
});
test('collector makes progress only while visible, rate-limits attempts and saves pool',()=>{
  const app=read('web/app.js');
  assert.match(app,/collectorEveryMs:120000/);
  assert.match(app,/maxPrefetchPerPump:3/);
  assert.match(app,/attempted>=5/);
  assert.match(app,/document\.hidden/);
  assert.match(app,/prefetchedKeys\.delete\(art\.key\)/);
  assert.match(app,/key:'candidatePool'/);
  assert.match(app,/startContinuousCollector\(\);/);
  assert.match(app,/collectorRunning:false/);
});
test('native gallery cache holds max 8GB but retains 1.5GB free and persistent app-private storage',()=>{
  const java=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
  assert.match(java,/MAX_IMAGE_CACHE = 8L \* 1024 \* 1024 \* 1024/);
  assert.match(java,/CLEAN_TO = 7L \* 1024 \* 1024 \* 1024/);
  assert.match(java,/FREE_RESERVE = 1536L \* 1024 \* 1024/);
  assert.match(java,/new File\(getFilesDir\(\), "gallery-images"\)/);
  assert.match(java,/old\.renameTo\(dest\)/);
  assert.match(java,/getUsableSpace\(\)/);
  assert.match(java,/imageDir\.getUsableSpace\(\)<FREE_RESERVE\+MAX_IMAGE_BYTES/);
});
