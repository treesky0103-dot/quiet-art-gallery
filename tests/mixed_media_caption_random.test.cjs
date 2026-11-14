const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const C=require('../web/core.js');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const sample={key:'commons:98324',image:'https://upload.wikimedia.org/wikipedia/commons/thumb/a/a4/test.jpg',
  type:'Photograph',classification:'Photograph',rightsOK:true,license:'CC0',
  title:'Bird',artist:'Photographer',width:1200,height:1800};

test('non-fixed unbiased media order: Fisher-Yates works across medium types',()=>{
 const list=[{type:'Painting',key:'p'},{type:'Photograph',key:'f'},
             {type:'Animation Still',key:'a'},{type:'Illustration',key:'i'}];
 const out=C.shuffledCopy(list,()=>0);
 assert.deepEqual(out.map(x=>x.key),['f','a','i','p']);
 assert.deepEqual(list.map(x=>x.key),['p','f','a','i'],'original order is unchanged');
 assert.deepEqual(C.shuffledCopy([],()=>0),[]);
 const app=read('web/app.js');
 assert.match(app,/const eligible=C\.shuffledCopy\(state\.pool/);
 assert.match(app,/const all=C\.shuffledCopy\(items\.filter/);
 assert.match(app,/return all\[Math\.floor\(Math\.random\(\)\*all\.length\)\]/);
 assert.doesNotMatch(app,/const sources=\['Painting','Photograph','Illustration'\]/);
});

test('unified label is work, artist and verified year only',()=>{
 assert.equal(C.artworkYearLabel({yearStart:1888,yearEnd:1888}),'1888');
 assert.equal(C.artworkYearLabel({yearStart:1890,yearEnd:1895}),'1890–1895');
 assert.equal(C.artworkYearLabel({date:'2021'}),'2021');
 assert.equal(C.artworkYearLabel({date:'Uploaded 2025'}),'연도 미상');
 assert.equal(C.artworkYearLabel({yearStart:1930,yearEnd:1890}),'연도 미상');
 const app=read('web/app.js'),style=read('web/style.css'),html=read('web/index.html');
 assert.match(app,/ui\.meta\.textContent=C\.tidyLabel\(show\.art\.artist,'작가 미상'\)\+' · '\+C\.artworkYearLabel\(show\.art\)/);
 assert.match(app,/ui\.meta\.textContent=C\.tidyLabel\(last\.art\.artist,'작가 미상'\)\+' · '\+C\.artworkYearLabel\(last\.art\)/);
 assert.match(html,/<footer id="caption"[^>]*><div id="art-title"><\/div><div id="art-meta"><\/div><\/footer>/);
 assert.match(style,/#viewer\{bottom:var\(--gallery-caption-h\)\}/);
 assert.match(style,/\.caption,\.caption\.active\{/);
});

test('photos, illustrations and static animation stills require same provenance gate',()=>{
 assert.equal(C.eligibleArt(sample),true);
 assert.equal(C.eligibleArt({...sample,type:'Illustration',classification:'Illustration'}),true);
 assert.equal(C.eligibleArt({...sample,type:'Animation Still',classification:'Animation Still'}),true);
 assert.equal(C.eligibleArt({...sample,rightsOK:false}),false);
 assert.equal(C.eligibleArt({...sample,description:'Photograph of painting in a gallery'}),false);
 assert.equal(C.eligibleArt({...sample,image:'javascript:alert(1)'}),false);
 assert.equal(C.eligibleArt({...sample,type:'Sculpture',classification:'Sculpture'}),false);
});

test('Wikimedia still image metadata produces correct classification and artist fallback',()=>{
 const category=C.MIXED_MEDIA_CATEGORIES.find(x=>x.id==='photo-nature');
 assert.ok(category);
 const make=(license,mime)=>({query:{pages:[{pageid:98324,title:'File:Morning birds.jpg',imageinfo:[{
   mime,width:1800,height:2400,thumburl:sample.image,
   descriptionurl:'https://commons.wikimedia.org/wiki/File:Morning_birds.jpg',
   extmetadata:{LicenseShortName:{value:license},Artist:{value:'A. Maker'}}
 }]}]}});
 const photos=C.normalizeMixedMediaCommons(make('CC0','image/jpeg'),'photo-nature');
 assert.equal(photos.length,1);
 assert.equal(photos[0].type,'Photograph');
 assert.equal(photos[0].artist,'A. Maker');
 assert.equal(photos[0].rightsOK,true);
 assert.equal(C.eligibleArt(photos[0]),true);
 assert.equal(C.normalizeMixedMediaCommons(make('All Rights Reserved','image/jpeg'),'photo-nature')[0].rightsOK,false);
 assert.equal(C.normalizeMixedMediaCommons(make('CC0','image/gif'),'animation-still')[0].rightsOK,false);
 assert.equal(C.eligibleArt(C.normalizeMixedMediaCommons(make('CC0','image/jpeg'),'animation-still')[0]),true);
});
