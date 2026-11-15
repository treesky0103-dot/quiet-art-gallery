'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');
const C=require('../web/core.js');
const audit=JSON.parse(read('data/new50_provider_audit_20261115.json'));
const old=JSON.parse(read('android-app/app/src/main/assets/art-sources-85.json'));
const valid={
 id:'gw6bb9yd',
 source:{id:'j4zabc9a',title:'Botanical watercolour',genres:[{label:'Watercolors'},{label:'Paintings'}],contributors:[]},
 locations:[{url:'https://iiif.wellcomecollection.org/image/V0035845/info.json',license:{id:'pdm'}}],
 aspectRatio:.70
};
test('50 new sources are unique and do not pretend 50 automatic connectors',()=>{
 assert.equal(audit.items.length,50);
 assert.equal(new Set(audit.items.map(x=>x.name.toLowerCase())).size,50);
 assert.equal(old.entries.length,85);
 assert.equal(audit.items.filter(x=>x.enabled_in_apk).length,1);
 assert.equal(audit.items.find(x=>x.enabled_in_apk).name,'Wellcome Collection');
 assert.equal(audit.items.filter(x=>x.images_validated_and_stored_on_tablet>0).length,0);
});
test('PDM Wellcome paintings produce one verified-format allowlisted IIIF image URL',()=>{
 const a=C.normalizeWellcome(valid);
 assert(a);
 assert.equal(a.key,'wellcome:gw6bb9yd');
 assert.equal(a.type,'Painting');
 assert.equal(a.license,'PDM');
 assert.equal(a.rightsOK,true);
 assert.equal(a.image,'https://iiif.wellcomecollection.org/image/V0035845/full/2000,/0/default.jpg');
 assert.equal(C.safeURL(a.image),true);
 assert.equal(C.eligibleArt(a),true);
 assert.equal(C.metadataResolutionOkay(a),true);
});
test('Reject missing rights, broad search hits, unauthorized servers and 3D art',()=>{
 const p=structuredClone(valid);
 p.locations[0].license.id='cc-by';assert.equal(C.normalizeWellcome(p),null);
 p.locations[0].license.id='pdm';p.source.genres=[{label:'Books'}];assert.equal(C.normalizeWellcome(p),null);
 p.source.genres=[{label:'Paintings'}];p.source.title='Photograph of gallery installation';assert.equal(C.normalizeWellcome(p),null);
 p.source.title='Painting';p.locations[0].url='https://evil.example/image/X/info.json';
 assert.equal(C.normalizeWellcome(p),null);
 assert.equal(C.safeURL('https://iiif.wellcomecollection.org/image/V0035845/full/full/0/default.jpg'),false);
 assert.equal(C.safeURL('https://iiif.wellcomecollection.org/image/V0035845/full/2000,/0/default.jpg?foo=bar'),false);
});
test('Native, browser and collector all route only fixed Wellcome search terms',()=>{
 const a=read('web/app.js'),j=read('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(a,/kind==='wellcome'/);
 assert.match(a,/request\('wellcome',index\+':'\+page\)/);
 assert.match(a,/locations\.license/);
 assert.match(a,/C\.normalizeWellcome/);
 assert.match(a,/source==='wellcome'/);
 assert.match(j,/type\.equals\("wellcome"\)/);
 assert.match(j,/bounded\(parts\[0\],0,9\)/);
 assert.match(j,/locations\.license=pdm/);
 assert.match(j,/iiif\.wellcomecollection\.org/);
 assert.match(j,/2000,\/0\/default/);
});
test('50 sources are readable in settings without inventing artwork collection counts',()=>{
 const page=read('web/index.html'),app=read('web/app.js');
 assert.match(page,/show-new50/);
 assert.match(app,/reviewed_candidates!==50/);
 assert.match(app,/기존 85곳 외/);
});
