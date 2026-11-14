'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const C=require('../web/core.js');
const source=p=>fs.readFileSync(path.resolve(__dirname,'..',p),'utf8');

test('90 days * 30 seconds exact 80:20 year allocation',()=>{
 const q=C.eraQuota90Days();
 assert.deepEqual(q,{total:259200,post1800:207360,remainder:51840});
 const sample=Array.from({length:500},(_,i)=>C.targetPost1800(i));
 assert.equal(sample.filter(Boolean).length,400);
 assert.deepEqual(sample.slice(0,5),[true,true,true,true,false]);
});
test('artwork year numeric ranges handle 1800 inclusive and boundary ambiguity',()=>{
 assert.equal(C.artworkEra({yearStart:1800,yearEnd:1800}),'post1800');
 assert.equal(C.artworkEra({yearStart:1799,yearEnd:1799}),'pre1800');
 assert.equal(C.artworkEra({yearStart:1799,yearEnd:1801}),'unknown');
 assert.equal(C.artworkEra({yearStart:2025,yearEnd:2026}),'post1800');
 assert.equal(C.artworkEra({yearStart:2027,yearEnd:2027}),'unknown');
 assert.equal(C.artworkEra({yearStart:2021,yearEnd:1890}),'unknown');
 assert.equal(C.artworkEra({yearStart:0,yearEnd:0}),'pre1800');
 assert.equal(C.artworkEra({date:'uploaded 2024'}),'unknown');
 assert.equal(C.artworkEra({title:'19th century painting'}),'unknown');
 assert.equal(C.artworkEra(null),'unknown');
});
test('museum adapter retains actual artwork creation dates, not digitization dates',()=>{
 const cm=C.normalizeCleveland({id:1,title:'a',type:'Painting',share_license_status:'CC0',
     images:{print:{url:'https://openaccess-cdn.clevelandart.org/a.jpg',width:2000,height:3000}},
     creation_date_earliest:1878,creation_date_latest:1880});
 assert.equal(C.artworkEra(cm),'post1800');
 const ci=C.normalizeChicago({id:22,title:'b',artwork_type_title:'Painting',
     date_start:1790,date_end:1792,image_id:'abcdef1234567890',is_public_domain:true},
     'https://www.artic.edu/iiif/2');
 assert.equal(C.artworkEra(ci),'pre1800');
 const met=C.normalizeMet({objectID:34,objectName:'Painting',objectBeginDate:1780,
     objectEndDate:1810,isPublicDomain:true});
 assert.equal(C.artworkEra(met),'unknown');
});
test("original new art year evidence is separate from old painting's photograph date",()=>{
 assert.equal(C.artworkEra({modern:true,rightsOK:true,modernEvidence:'year-title'}),
    'post1800');
 assert.equal(C.artworkEra({modern:true,rightsOK:true,modernEvidence:'original-digital-title'}),
    'post1800');
 assert.equal(C.artworkEra({modern:true,rightsOK:false,modernEvidence:'year-title'}),
    'unknown');
 assert.equal(C.artworkEra({modern:true,rightsOK:true,modernEvidence:''}),
    'unknown');
});
test('gallery does not enforce seventeen schools and shows actual achieved fraction',()=>{
 const app=source('web/app.js'), html=source('web/index.html');
 assert(app.includes('a.movement=C.classifyMovement(a)||\'unclassified\''));
 assert(app.includes('C.targetPost1800(state.stats.slot)'));
 assert(app.includes('post1800Shown'));
 assert(!app.includes('for(let delta=0;delta<C.MOVEMENTS.length;delta++)'));
 assert(html.includes('무작위로 전시합니다'));
 assert(html.includes('회화·사진·일러스트·애니메이션·현대미술'));
 assert(html.includes('30분당 60점'));
});
