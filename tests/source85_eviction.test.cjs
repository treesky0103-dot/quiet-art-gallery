const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const cat=JSON.parse(read('data/85_source_registry_20261115.json'));
const bundled=JSON.parse(read('android-app/app/src/main/assets/art-sources-85.json'));

test('85 distinct provider names are genuinely distinguished by connection type',()=>{
 assert.equal(cat.entries_total,85);
 assert.equal(cat.entries.length,85);
 assert.equal(new Set(cat.entries.map(x=>x.name)).size,85);
 assert.equal(cat.direct_official_api,3);
 assert.equal(cat.museum_categories_via_wikimedia_commons,37);
 assert.equal(cat.external_site_links_only,45);
 assert.equal(cat.searchable_by_native_collector,40);
 assert.equal(cat.entries.filter(x=>x.status==='official_api').length,3);
 assert.equal(cat.entries.filter(x=>x.status==='commons_category').length,37);
 assert.equal(cat.entries.filter(x=>x.status==='external_browse_only').length,45);
 assert.deepEqual(cat,bundled);
 for(let i=0;i<85;i++)assert.equal(cat.entries[i].number,i+1);
 assert.ok(cat.entries.some(x=>x.name==='루브르 박물관'&&x.status==='commons_category'));
 assert.ok(cat.entries.some(x=>x.name==='Flickr'&&x.status==='external_browse_only'));
 assert.ok(cat.entries.every(x=>x.link===null||new URL(x.link).protocol==='https:'));
 assert.ok(cat.entries.filter(x=>x.link).length>=83);
});

test('all 85 are navigable in settings as labeled roles, never falsely promised as 85 image APIs',()=>{
 const ui=read('web/index.html'),app=read('web/app.js'),java=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(ui,/85개 공급원 연결 상태/);
 assert.match(ui,/id="source-catalog-links"/);
 assert.match(app,/fetch\('https:\/\/appassets\.gallery\/art-sources-85\.json'\)/);
 assert.match(app,/j\.entries_total!==85/);
 assert.match(app,/official_api/);
 assert.match(app,/commons_category/);
 assert.match(app,/openRegisteredSource\(item\.number-1\)/);
 assert.match(java,/openRegisteredSource\(int index\)/);
 assert.match(java,/getAssets\(\)\.open\("art-sources-85\.json"\)/);
 assert.match(java,/getJSONArray\("entries"\)\.getJSONObject\(index\)/);
 assert.match(java,/"art-sources-85\.json"/);
});

test('only actual displayed cached work enters native SQLite ledger; 8GiB->7GiB shown-only purge',()=>{
 const app=read('web/app.js'),java=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 const db=read('android-app/app/src/main/java/com/gallery/kiosk/ShownImageLedger.java');
 const policy=read('android-app/app/src/main/java/com/gallery/kiosk/ShownFirstEviction.java');
 assert.match(app,/tellNativeArtworkWasActuallyDisplayed\(show\.art\)/);
 assert.match(app,/tellNativeArtworkWasActuallyDisplayed\(last\.art\)/);
 assert.match(app,/!art\.offlineAsset/);
 assert.match(java,/markArtworkDisplayedNative\(url\)/);
 assert.match(java,/ShownFirstEviction\.select/);
 assert.match(java,/MAX_IMAGE_CACHE = 8L \* 1024 \* 1024 \* 1024/);
 assert.match(java,/CLEAN_TO = 7L \* 1024 \* 1024 \* 1024/);
 assert.match(java,/FREE_RESERVE = 1536L \* 1024 \* 1024/);
 assert.match(java,/if\(!makeRoomForIncoming\(MAX_IMAGE_BYTES\)\)/);
 assert.match(java,/return response\(507,"text\/plain",new byte\[0\]\)/);
 assert.match(java,/gallery-images/);
 assert.match(java,/shownLedger\.displayedFiles/);
 assert.match(java,/currentDisplayedHash/);
 assert.match(db,/first_shown_ms/);
 assert.match(db,/SQLiteDatabase\.CONFLICT_IGNORE/);
 assert.match(policy,/firstShownAt<=0/);
 assert.match(app,/dbPutMany\('seen'/);
 assert.match(app,/pruneDays: 90/);
});
