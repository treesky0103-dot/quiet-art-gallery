'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');
const a=JSON.parse(root('data/v188_smithsonian_verified_sources.json'));
test('exactly one new institution and one existing institution upgraded, no false two-new count',()=>{
 assert.equal(a.new_institution_count,1);
 assert.equal(a.upgraded_existing_institution_count,1);
 assert.deepEqual(a.activated_direct_smithsonian_units,['nmaahc','fsg']);
 assert.equal(a.sources[0].source_kind,'new institution outside earlier 135');
 assert.match(a.sources[1].source_kind,/existing 85/);
 assert.equal(a.sources[0].samples.length,2);
 assert.equal(a.sources[1].samples.length,1);
});
test('NMAAHC real 1595px CC0 poster JPEGs are documented with immutable content hashes',()=>{
 for(const img of a.sources[0].samples){
  assert(img.width>=1000&&img.height>=1400);
  assert(img.bytes>60000&&img.bytes<8*1024*1024);
  assert.match(img.sha256,/^[0-9a-f]{64}$/);
 }
 const artwork=a.sources[1].samples[0];
 assert.equal(artwork.width,1622);
 assert.equal(artwork.height,2000);
 assert.match(artwork.sha256,/^[0-9a-f]{64}$/);
 assert.equal(a.sources[1].rejected_samples[0].width,872);
});
test('Smithsonian new unit APIs are finite allowlists, never arbitrary user-host requests',()=>{
 const native=root('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(native,/Arrays\.asList\("npg","chndm","nmaahc","fsg"\)/);
 assert.match(native,/unit\.equals\("nmaahc"\)/);
 assert.match(native,/Smithsonian National Museum of Asian Art/);
 assert.match(native,/smithsonianArtCandidate\(new JSONObject\(line\),parts\[0\]\)/);
 assert.match(native,/metadataUsage==null\|\|!"CC0"/);
 assert.match(native,/usage==null\|\|!"CC0"/);
 assert.match(native,/if\(width<1000\|\|height<1400\|\|height<=width\)/);
 assert.match(native,/MAX_IMAGE_CACHE = 8L \* 1024 \* 1024 \* 1024/);
});
test('Collector schedules both new safe sources and persists separate cursors',()=>{
 const app=root('web/app.js'),html=root('web/index.html');
 assert.match(app,/smNmaahc:'국립아프리카계미국인역사문화박물관/);
 assert.match(app,/smFsg:'스미스소니언 국립아시아미술관/);
 assert.match(app,/smithsonianNmaahcShard:0/);
 assert.match(app,/smithsonianFsgShard:0/);
 assert.match(app,/source==='smNmaahc'/);
 assert.match(app,/source==='smFsg'/);
 assert.match(app,/kind=isNpg\?'npg':source==='smChndm'\?'chndm':source==='smNmaahc'\?'nmaahc':'fsg'/);
 assert.match(app,/addCandidates\(normalizeBatch\('smithsonianShard',res\)\)/);
 assert.match(html,/show-v188/);
 assert.match(html,/전시 관리 · v1\.8\.8/);
});
test('V188 source audit packaged in both web and Android assets without copy discrepancies',()=>{
 const x=root('web/v188-verified-sources.json');
 assert.equal(x,root('android-app/app/src/main/assets/v188-verified-sources.json'));
 assert.equal(x,root('data/v188_smithsonian_verified_sources.json'));
 assert.match(root('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java'),/v188-verified-sources\.json/);
 assert.match(root('android-app/app/build.gradle'),/applicationId 'com\.gallery\.kiosk\.v188'/);
 assert.match(root('android-app/app/build.gradle'),/versionName '1\.8\.8-global6'/);
});
