'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const C=require('../web/core.js');
const get=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');
test('global art aggregators are multiple independent public creator archives and retain clear licensing',()=>{
 assert.equal(C.GLOBAL_OPENVERSE_TERMS.length,12);
 assert(C.GLOBAL_OPENVERSE_TERMS.includes('original digital illustration'));
 assert(C.GLOBAL_OPENVERSE_TERMS.some(x=>x.includes('watercolor')));
 const fake={results:[
  {id:'abcd',title:'Original watercolor painting',source:'flickr',
   url:'https://live.staticflickr.com/123/abc_def.jpg',license:'cc0',
   width:1600,height:2400,creator:'Example Creator',foreign_landing_url:'https://flickr.com/photos/123'},
  {id:'abce',title:'Photograph of painting',source:'flickr',
   url:'https://live.staticflickr.com/124/abc_def.jpg',license:'cc0',
   width:1600,height:2400,creator:'Example Creator'},
  {id:'abcf',title:'Original watercolor painting',source:'flickr',
   url:'https://live.staticflickr.com/125/abc_def.jpg',license:'by-nc',
   width:1600,height:2400,creator:'Example Creator'},
  {id:'abcg',title:'Original watercolor painting',source:'example',
   url:'https://not-approved.invalid/image.jpg',license:'cc0',
   width:1600,height:2400,creator:'Example Creator'}
 ]};
 const actual=C.normalizeGlobalOpenverse(fake);
 assert.equal(actual.length,1);
 assert.equal(actual[0].key,'openverse-world:abcd');
 assert.equal(actual[0].rightsOK,true);
 assert.equal(C.eligibleArt(actual[0]),true);
 assert.equal(C.artworkEra(actual[0]),'unknown','upload date is not verified painting year');
});
test('multi-source Openverse returns a bounded source query with rejection and retry',()=>{
 const web=get('web/app.js'),java=get('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(web,/source==='worldOpenverse'/);
 assert.match(web,/kind==='worldOpenverse'/);
 assert.match(web,/C\.normalizeGlobalOpenverse\(response\)/);
 assert.match(web,/page>4/);
 assert.match(java,/type\.equals\("worldOpenverse"\)/);
 assert.match(java,/int idx=bounded\(parts\[0\],0,terms\.length-1\),page=bounded\(parts\[1\],1,4\)/);
 assert.match(java,/live\.staticflickr\.com/);
 assert.match(java,/host\.matches\("farm\[1-9\]/);
 assert(!java.includes('return src.startsWith("http")'));
});
test('web and native assets are identical',()=>{
 for(const x of ['core.js','app.js']){
  assert.equal(get('web/'+x),get('android-app/app/src/main/assets/'+x));
 }
});
test('external image harvesting runs only for public open-licensed HTTPS CDN URLs',()=>{
 const src=get('scripts/collect_global_open_art_multisource.py');
 assert(src.includes('ALLOWED_MEDIA_HOSTS'));
 assert(src.includes('OPEN_LICENSE'));
 assert(src.includes('check_https(url)'));
 assert(src.includes('check_https(url,api=True)'));
 assert(src.includes('Image.open'));
 assert(src.includes('sha256'));
 assert(src.includes('"actual_complete_259200":False'));
});
