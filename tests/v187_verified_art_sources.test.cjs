'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const C=require('../web/core.js');
const rights=JSON.parse(read('data/v187_additional_verified_sources.json'));
const older=JSON.parse(read('data/new50_provider_audit_20261115.json'));
const princeton={
 objectid:9449,classification:'Drawings',datebegin:1894,dateend:1904,
 displaytitle:'Dancers',displaymaker:'Edgar Degas, 1834-1917',
 makers:[{dateend:'1917'}],restrictions:null,nowebuse:'False',creditlinerepro:'',
 media:[{uri:'https://media.artmuseum.princeton.edu/iiif/3/collection/x1954-13',
  isprimary:1,mediatypeid:1,restrictions:null}],medium:'Pastel and charcoal on tracing paper',
 displaydate:'1899',url:'https://artmuseum.princeton.edu/art/collections/objects/9449'
};
test('Princeton verified Degas public-domain API record normalizes to one portrait IIIF artwork',()=>{
 const art=C.normalizePrinceton(princeton);
 assert(art);
 assert.equal(art.key,'princeton:9449');
 assert.equal(art.source,'Princeton University Art Museum');
 assert.equal(art.image,'https://media.artmuseum.princeton.edu/iiif/3/collection/x1954-13/full/2000,/0/default.jpg');
 assert(C.safeURL(art.image));
 assert(C.eligibleArt(art));
 assert(C.metadataResolutionOkay(art));
});
test('Princeton rejects copyright-sensitive metadata and contemporary artists',()=>{
 for(const patch of [
  {restrictions:'Copyrighted'}, {nowebuse:'True'}, {creditlinerepro:'© 2026 example'},
  {classification:'Sculpture'}, {makers:[{dateend:'2015'}]}, {dateend:2020},
  {media:[{uri:'https://evil.tld/x',isprimary:1,mediatypeid:1,restrictions:null}]},
  {media:[{uri:'https://media.artmuseum.princeton.edu/iiif/3/collection/x1954-13',isprimary:1,mediatypeid:1,restrictions:'Restricted'}]}
 ]){
  const item={...princeton,...patch};assert.equal(C.normalizePrinceton(item),null,JSON.stringify(patch));
 }
});
test('Smithsonian ids are only accepted with fixed host/path/query; no other image host allowed',()=>{
 const ok='https://ids.si.edu/ids/deliveryService?id=NPG-NPG_85_158&max=2000';
 assert.equal(C.safeURL(ok),true);
 for(const uri of [
  'https://evil.example/ids/deliveryService?id=NPG-NPG_85_158&max=2000',
  'https://ids.si.edu/ids/deliveryService?id=NPG-NPG_85_158&max=4096',
  'https://ids.si.edu/ids/deliveryService?id=../../etc/passwd&max=2000',
  'https://ids.si.edu/ids/download?id=NPG-NPG_85_158.jpg',
  'https://ids.si.edu/ids/deliveryService?id=NPG-NPG_85_158&max=2000&h=1'
 ])assert.equal(C.safeURL(uri),false,uri);
});
test('Native fetch protects BOTH metadata and media CC0 and excludes 3D objects',()=>{
 const src=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(src,/smithsonianArtCandidate\(new JSONObject\(line\),parts\[0\]\)/);
 assert.match(src,/metadataUsage==null\|\|!"CC0"\.equals\(metadataUsage\.optString\("access"\)\)/);
 assert.match(src,/usage==null\|\|!"CC0"\.equals\(usage\.optString\("access"\)\)/);
 assert.match(src,/Arrays\.asList\("npg","chndm"\)/);
 assert.match(src,/if\(width<1000\|\|height<1400\|\|height<=width\)continue/);
 assert.match(src,/7\*1024\*1024/);
 assert.match(src,/smithsonianShard\(param\)/);
 assert.match(src,/item\.optString\("url"/);
});
test('All three vetted additions are linked; 50 candidate matrix accurately flags two enabled',()=>{
 assert.equal(rights.reviewed_new_units,3);
 assert.equal(rights.new_institutions.length,3);
 assert.equal(older.items.length,50);
 assert.equal(older.items.filter(x=>x.enabled_in_apk).length,2);
 assert(older.items.some(x=>x.name==='Cooper Hewitt Design Museum'&&x.enabled_in_apk));
 assert(rights.new_institutions.some(x=>x.name==='Princeton University Art Museum'));
 assert(rights.new_institutions.some(x=>x.name==='Smithsonian National Portrait Gallery'));
 const html=read('web/index.html'),app=read('web/app.js');
 assert.match(html,/show-v187/);
 assert.match(app,/source==='princeton'/);
 assert.match(app,/source==='smNpg'\|\|source==='smChndm'/);
 assert.match(app,/request\('smithsonianShard',kind\+':'\+shard\)/);
 assert.match(app,/reviewed_candidates!==50/);
 assert.match(app,/source==='wellcome'/);
});
