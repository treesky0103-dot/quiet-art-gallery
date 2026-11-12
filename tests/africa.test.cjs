const test=require('node:test');
const assert=require('node:assert/strict');
const C=require('../web/core.js');
function mock(title='File:Quiet_Painting.jpg',rights='Public domain',w=2000,h=2600){
 return {query:{pages:[{pageid:123,title,imageinfo:[{mime:'image/jpeg',width:w,height:h,thumburl:'https://upload.wikimedia.org/wikipedia/commons/thumb/demo.jpg',descriptionurl:'https://commons.wikimedia.org/wiki/File:Quiet_Painting.jpg',extmetadata:{LicenseShortName:{value:rights},Artist:{value:'Painter X'}}}]}]}};
}
test('African museum sources are explicit, institution-linked categories',()=>{
 assert.deepEqual(C.AFRICAN_MUSEUMS.map(x=>x.id),['iziko','ethiopia','zimbabwe','johannesburg']);
 assert(C.AFRICAN_MUSEUMS.every(x=>x.category.includes('Paintings')));
 assert.deepEqual(C.MOVEMENTS.slice(-2).map(m=>m.id),['asian','african']);
});
test('Only public-domain/CC0 2D files become African painting candidates',()=>{
 for(const m of C.AFRICAN_MUSEUMS){
  const a=C.normalizeAfricanCommons(mock(),'iziko'===m.id?'iziko':m.id)[0];
  assert.equal(a.museumRegion,'africa');assert.equal(C.eligibleArt(a),true);
  assert.equal(C.metadataResolutionOkay(a),true);
  assert.equal(C.classifyMovement(a),'african');
 }
 assert.equal(C.normalizeAfricanCommons(mock('File:Art.jpg','CC BY 4.0'),'iziko')[0].rightsOK,false);
 assert.equal(C.normalizeAfricanCommons(mock('File:Art.jpg','Public domain',1000,2500),'iziko')[0].rightsOK,true);
 assert.equal(C.metadataResolutionOkay(C.normalizeAfricanCommons(mock('File:Art.jpg','Public domain',1000,2500),'iziko')[0]),false);
});
test('Gallery interior and sculpture photos excluded by Commons filename',()=>{
 for(const name of ['File:exhibition view in museum.jpg','File:sculpture in gallery.jpg','File:gallery interior photo.jpg','File:visitors with paintings.jpg']){
  assert.equal(C.normalizeAfricanCommons(mock(name),'iziko').length,0,name);
 }
});
test('African museum art does not override 90 day repeat ban',()=>{
 const a=C.normalizeAfricanCommons(mock(),'ethiopia')[0];
 const now=Date.now();
 const seen=new Map([[a.key,now-2*86400000]]);
 assert.equal(C.pickCandidate([a],'portrait',seen,now),-1);
 assert.equal(C.canReshow(now-91*86400000,now),true);
});
