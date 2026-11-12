const test=require('node:test');
const assert=require('node:assert/strict');
const C=require('../web/core.js');
const sample=(short='Public domain',license='pd',url='https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Some-art.jpg/843px-Some-art.jpg')=>({
  query:{pages:[{pageid:1234,title:'File:Joseon painting.jpg',imageinfo:[{
    width:1280,height:2300,mime:'image/jpeg',thumburl:url,
    extmetadata:{Artist:{value:'<span>Kim Hong-do</span>'},LicenseShortName:{value:short},License:{value:license}}
  }]}]}
});
test('Five Asian museum categories have unique IDs and known collection names',()=>{
  assert.deepEqual(C.ASIAN_MUSEUMS.map(m=>m.id),['korea','tokyo','kyoto','nara','taipei']);
  assert.equal(new Set(C.ASIAN_MUSEUMS.map(m=>m.category)).size,5);
});
test('Public domain Asian paintings enter a separate slot after thirteen western schools',()=>{
  const a=C.normalizeAsianCommons(sample(),'korea')[0];
  assert.equal(a.source,'국립중앙박물관');
  assert.equal(a.artist,'Kim Hong-do');
  assert.equal(a.title,'Joseon painting');
  assert.equal(C.eligibleArt(a),true);
  assert.equal(C.classifyMovement(a),'asian');
  assert.equal(C.MOVEMENTS.length,14);
  assert.equal(C.MOVEMENTS[0].id,'renaissance');
  assert.equal(C.MOVEMENTS[12].id,'contemporary');
  assert.equal(C.MOVEMENTS[13].id,'asian');
});
test('Attribution-required, copyrighted and unknown Commons licenses are not silently accepted',()=>{
  for(const label of ['CC BY 4.0','CC BY-SA 4.0','Copyrighted','Unknown']){
    const art=C.normalizeAsianCommons(sample(label,'cc-by-4.0'),'nara')[0];
    assert.equal(C.eligibleArt(art),false,label);
  }
  assert.equal(C.eligibleArt(C.normalizeAsianCommons(sample('CC0 1.0','cc0'),'taipei')[0]),true);
});
test('Whitelist Wikimedia image host, not lookalike hosts and forbidden formats',()=>{
  assert.equal(C.safeURL('https://upload.wikimedia.org/wikipedia/commons/x.jpg'),true);
  assert.equal(C.safeURL('https://upload.wikimedia.org.evil.test/x.jpg'),false);
  assert.equal(C.safeURL('http://upload.wikimedia.org/x.jpg'),false);
  assert.equal(C.eligibleArt(C.normalizeAsianCommons(sample('Public domain','pd','https://bad.example/a.jpg'),'tokyo')[0]),false);
  const x=sample();x.query.pages[0].imageinfo[0].mime='image/tiff';
  assert.equal(C.eligibleArt(C.normalizeAsianCommons(x,'kyoto')[0]),false);
});
test('New Asian slot respects existing 90-day seen-record embargo',()=>{
  const a=C.normalizeAsianCommons(sample(),'kyoto')[0];
  const at=Date.parse('2026-11-12T00:00:00Z');
  assert.equal(C.pickCandidate([a],'portrait',new Map([[a.key,at]]),at+86400000),-1);
  assert.equal(C.pickCandidate([a],'portrait',new Map([[a.key,at]]),at+C.NINETY_DAYS_MS),0);
  assert.equal(C.classifyMovement({...a,rightsOK:false}),null);
});
test('Metropolitan Asian Art department is grouped with Asian paintings',()=>{
  const a=C.normalizeMet({objectID:32,title:'Ink landscape',artistDisplayName:'Unknown',primaryImageSmall:'https://images.metmuseum.org/images/a.jpg',objectName:'Painting',classification:'Paintings',medium:'Ink on silk',department:'Asian Art',isPublicDomain:true});
  assert.equal(C.eligibleArt(a),true);
  assert.equal(C.classifyMovement(a),'asian');
});
