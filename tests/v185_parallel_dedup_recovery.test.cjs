'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const read=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');

function visualPolicy(downloaded=[],inflight=[],offline=[]){
  const src=read('web/app.js'),begin=src.indexOf('  function similarDownloadedImage('),
    end=src.indexOf('  async function hydrateDownloadedIndex()',begin);
  assert(begin>0&&end>begin);
  const C=require('../web/core.js');
  const box={state:{downloadedVisualHashes:new Map(downloaded),
    inflightVisualHashes:new Map(inflight),offlineReady:offline},C};
  vm.runInNewContext(src.slice(begin,end)+'\nthis.similar=similarDownloadedImage;',box);
  return box.similar;
}
test('Visual fingerprints block duplicates across different artwork keys and source URLs',()=>{
  const check=visualPolicy([['museum:x','0123456789abcdef']]);
  assert.equal(check('0123456789abcdef','museum:y'),true);
  assert.equal(check('0123456789abcdee','museum:y'),true);
  assert.equal(check('0123456789abcdef','museum:x'),false);
  assert.equal(check('fedcba9876543210','museum:y'),false);
});
test('Concurrent visual reservations reject a second simultaneous copy',()=>{
  const check=visualPolicy([], [['museum:first','0123456789abcdef']]);
  assert.equal(check('0123456789abcdef','museum:second'),true);
  assert.equal(check('0123456789abcdef','museum:first'),false);
});
test('Bundled artwork fingerprints prevent downloading the same artwork twice',()=>{
  const check=visualPolicy([],[],[{art:{key:'offline/pack-0001'},visualHash:'0123456789abcdef'}]);
  assert.equal(check('0123456789abcdef','museum:remote'),true);
});
test('Android permits three different image downloads and serializes identical URLs',()=>{
  const native=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
  const app=read('web/app.js');
  assert.match(native,/new Semaphore\(3,true\)/);
  assert.match(native,/imageFileLocks=new Object\[64\]/);
  assert.match(native,/private WebResourceResponse artworkResponse\(String src\)/);
  assert.match(native,/synchronized\(imageFileLocks\[/);
  assert.match(native,/tryAcquire\(8,TimeUnit\.SECONDS\)/);
  assert.match(native,/IMAGE_FETCH_SLOTS\.release\(\)/);
  assert.match(app,/Promise\.all\(Array\.from\(\{length:Math\.min\(3,candidates\.length\)\}/);
  assert.match(app,/await collectOne\(candidates\[idx\]\)/);
  assert.match(app,/await seenRecently\(art,loaded\.visualHash\)/);
  assert.match(app,/similarDownloadedImage\(loaded\.visualHash,art\.key\)/);
});
test('App recovery preserves 90-day history and drops stale cache records',()=>{
  const app=read('web/app.js'),native=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java'),
    journal=read('android-app/app/src/main/java/com/gallery/kiosk/SeenIdentityLedger.java');
  assert.match(app,/await hydrateHistory\(\);/);
  assert.match(app,/await hydrateDownloadedIndex\(\);/);
  assert.match(app,/await restoreDownloadedInventory\(300\);/);
  assert.match(app,/if\(art&&!exists\)\{/);
  assert.match(app,/staleKeys\.push\(art\.key\)/);
  assert.match(app,/window\.addEventListener\('offline'/);
  assert.match(app,/window\.addEventListener\('online'/);
  assert.match(app,/\.filter\(\(\[_,entry\]\)=>!entry\.network\)/);
  assert.match(native,/claimArtworkKeys\(String keysJson\)/);
  assert.match(native,/seenIdentityLedger\.claim\(/);
  assert.match(journal,/db\.beginTransaction\(\)/);
  assert.match(journal,/db\.setTransactionSuccessful\(\)/);
  assert.match(journal,/NINETY_DAYS_MS=90L\*24\*60\*60\*1000/);
  assert.match(native,/\.put\("unshownImageFiles",Math\.max\(0,total-shown\)\)/);
  const claim=app.indexOf('GalleryAndroid.claimArtworkKeys(');
  const mark=app.indexOf('markSeen(show);',claim);
  assert(claim>0&&mark>claim,'native history is claimed before the artwork is shown');
});
