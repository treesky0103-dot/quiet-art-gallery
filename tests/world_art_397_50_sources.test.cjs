const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const C=require('../web/core.js');
const read=p=>fs.readFileSync(p,'utf8');
const movements=JSON.parse(read('data/requested_art_movements_20261114.json'));
const providers=JSON.parse(read('data/50_requested_art_sources_20261114.json'));

test('397 actual requested movement names retained, but search terms are not misrepresented as downloaded work',()=>{
 const all=movements.groups.flatMap(x=>x.movements);
 assert.equal(all.length,397);
 assert.equal(movements.entry_count,397);
 assert.equal(movements.group_count,20);
 assert.equal(movements.english_query_terms,396);
 assert.equal(new Set(all.map(x=>x.name_ko)).size,395);
 for(const needed of ['신고전주의','바르비종파','인상주의','초현실주의','단색화','구타이','벵골화파','파푸냐 툴라 화파','회화주의 사진','생성형 영상예술','그래피티']) {
  if(needed==='그래피티') continue; // stand-alone media category in core
  assert.ok(all.some(x=>x.name_ko===needed),needed);
 }
 assert.match(movements.description,/not confirmed ingested artwork counts/);
});

test('50 source entries de-duplicate to 47; do not fake image ingestion on proprietary galleries',()=>{
 assert.equal(providers.entries.length,50);
 assert.equal(providers.unique_source_names,47);
 assert.equal(providers.automatic_search_integrations,2);
 assert.equal(providers.reference_only_excluding_duplicates,45);
 for(const name of ['Pixiv','Behance','Pinterest','DeviantArt','Google Arts & Culture','Street Art Cities','Magnum Photos','Newgrounds','Juxtapoz']) {
   const p=providers.entries.find(x=>x.name===name);
   assert.ok(p,name);assert.equal(p.content_download_enabled,false);
 }
 const connected=providers.entries.filter(x=>x.content_download_enabled);
 assert.deepEqual(connected.map(x=>x.name),['Wikimedia Commons','Openverse']);
});

test('movement API is bounded and queries source catalog, not caller-supplied arbitrary search strings',()=>{
 const java=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 const app=read('web/app.js');
 assert.match(java,/type\.equals\("movementCommons"\)/);
 assert.match(java,/getAssets\(\)\.open\("art-movements\.json"\)/);
 assert.match(java,/bounded\(parts\[0\],0,999\)/);
 assert.match(app,/C\.normalizeMovementCommons\(res,school\)/);
 assert.match(app,/state\.movementQueries/);
 assert.match(app,/items\.length>2700/);
 assert.match(java,/"art-providers\.json"/);
 assert.match(app,/show-movements/);
 assert.match(app,/show-providers/);
});

test('public-domain still visuals can be discovered as a search candidate, not misattributed to school',()=>{
 const school={name_ko:'인상주의',search_en:'Impressionism'};
 const fixture={query:{pages:[{pageid:191944,title:'File:Original painting - landscape.jpg',imageinfo:[{
   width:2400,height:3200,mime:'image/jpeg',
   thumburl:'https://upload.wikimedia.org/wikipedia/commons/a/ab/fake.jpg',
   extmetadata:{LicenseShortName:{value:'CC0'},Artist:{value:'Creator'},ImageDescription:{value:'An oil on canvas painting'}}
 }]}]}};
 const candidates=C.normalizeMovementCommons(fixture,school);
 assert.equal(candidates.length,1);
 assert.equal(candidates[0].schoolSearchTerm,'인상주의');
 assert.equal(candidates[0].schoolSearchIsAttribution,false);
 assert.equal(candidates[0].type,'Painting');
 assert.equal(candidates[0].rightsOK,true);
 assert.equal(C.eligibleArt(candidates[0]),true);
 fixture.query.pages[0].imageinfo[0].extmetadata.LicenseShortName.value='All Rights Reserved';
 assert.equal(C.normalizeMovementCommons(fixture,school)[0].rightsOK,false);
 fixture.query.pages[0].title='File:Gallery interior photograph.jpg';
 assert.deepEqual(C.normalizeMovementCommons(fixture,school),[]);
});
