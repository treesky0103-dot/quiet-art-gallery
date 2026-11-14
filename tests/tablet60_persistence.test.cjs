const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');

test('One-minute contract matches Java native clock, gallery JS and user-visible UI',()=>{
  const app=read('web/app.js');
  const native=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
  const page=read('web/index.html');
  const core=require('../web/core.js');
  assert.match(app,/intervalMs: 60000/);
  assert.match(native,/ART_INTERVAL_MS = 60000L/);
  assert.match(native,/if\(intervalMs!=60000\)return;/);
  assert.match(page,/1분 자동 전시/);
  assert.match(page,/129,600개 작품/);
  assert.deepEqual(core.eraQuota90Days(),{total:129600,post1800:103680,remainder:25920});
});

test('Downloaded but unshown candidates have a durable indexed inventory',()=>{
  const app=read('web/app.js');
  assert.match(app,/indexedDB\.open\('quiet-art-gallery-v1',2\)/);
  assert.match(app,/db\.createObjectStore\('downloaded',\{keyPath:'key'\}\)/);
  assert.match(app,/await dbPutMany\('downloaded',\[\{key:art\.key,art,when:Date\.now\(\)\}\]\)/);
  assert.match(app,/await restoreDownloadedInventory\(300\)/);
  assert.match(app,/await dbDelete\('downloaded',show\.art\.key\)/);
  assert.match(app,/await dbClear\('downloaded'\)/);
});

test('8GiB storage is reserved and saved-file count is measured, not guessed',()=>{
  const app=read('web/app.js');
  const java=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
  assert.match(java,/MAX_IMAGE_CACHE = 8L \* 1024 \* 1024 \* 1024/);
  assert.match(java,/CLEAN_TO = 7L \* 1024 \* 1024 \* 1024/);
  assert.match(java,/FREE_RESERVE = 1536L \* 1024 \* 1024/);
  assert.match(java,/\.put\("imageFiles",countCachedImageFiles\(\)\)/);
  assert.match(app,/Number\(s\.imageFiles\|\|0\)/);
  assert.match(app,/!state\.prefetchedKeys\.has\(a\.key\)/);
  assert.match(java,/shownLedger\.displayedFiles\(imageDir\)/);
});
