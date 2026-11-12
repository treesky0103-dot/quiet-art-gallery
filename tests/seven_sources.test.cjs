const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const C=require('../web/core.js');
const ids=['rijks','nga','getty','smk','paris','london','walters'];
function sample(license='Public domain',width=2500,height=3600,title='File:Sample painting.jpg',artist='Rembrandt van Rijn'){
 return {query:{pages:[{pageid:91827,title,imageinfo:[{width,height,mime:'image/jpeg',thumburl:'https://upload.wikimedia.org/wikipedia/commons/thumb/painting.jpg',descriptionurl:'https://commons.wikimedia.org/wiki/File:Sample_painting.jpg',extmetadata:{LicenseShortName:{value:license},Artist:{value:artist}}}]}]}};
}
test('seven public collection categories including Paris Municipal Museum representative',()=>{
 assert.deepEqual(C.ADDITIONAL_MUSEUMS.slice(0,7).map(x=>x.id),ids);
 assert.equal(C.ADDITIONAL_MUSEUMS.length,21);
 assert.equal(new Set(C.ADDITIONAL_MUSEUMS.map(x=>x.category)).size,21);
 assert.equal(C.ADDITIONAL_MUSEUMS.find(x=>x.id==='paris').category,'Paintings in Musée Carnavalet');
 assert.equal(C.MOVEMENTS.length,17);
 assert.deepEqual(C.MOVEMENTS.slice(-4).map(x=>x.id),['asian','african','additional','modern']);
});
test('Public-domain 2D extra museum image qualifies; smaller or restricted files do not',()=>{
 for(const m of C.ADDITIONAL_MUSEUMS){
  const art=C.normalizeAdditionalCommons(sample(),'rijks'===m.id?'rijks':m.id)[0];
  assert.equal(art.source,m.label);
  assert.equal(C.eligibleArt(art),true);
  assert.equal(C.metadataResolutionOkay(art),true);
 }
 assert.equal(C.eligibleArt(C.normalizeAdditionalCommons(sample('CC BY 4.0'),'getty')[0]),false);
 assert.equal(C.metadataResolutionOkay(C.normalizeAdditionalCommons(sample('Public domain',1100,2400),'london')[0]),false);
 assert.equal(C.normalizeAdditionalCommons(sample('Public domain',2600,3500,'File:Museum gallery interior.jpg'),'nga').length,0);
 assert.equal(C.normalizeAdditionalCommons(sample('Public domain',2600,3500,'File:Painting detail.jpg'),'smk').length,0);
});
test('Museum artist evidence maps extra source to style, otherwise neutral collection slot',()=>{
 const rem=C.normalizeAdditionalCommons(sample(),'rijks')[0];
 assert.equal(C.classifyMovement(rem),'baroque');
 const unknown=C.normalizeAdditionalCommons(sample('Public domain',2400,3200,'File:Unknown work.jpg','Unidentified artist'),'nga')[0];
 assert.equal(C.classifyMovement(unknown),'additional');
 assert.equal(C.classifyMovement({...unknown,rightsOK:false}),null);
});
test('New museums use existing 90 day duplicate protection',()=>{
 const art=C.normalizeAdditionalCommons(sample(),'walters')[0],now=Date.now();
 assert.equal(C.pickCandidate([art],'portrait',new Map([[art.key,now-86400000]]),now),-1);
});
test('Native Android API whitelist includes 7 known IDs and Commons image-size demand',()=>{
 const java=fs.readFileSync(require('node:path').join(__dirname,'../android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java'),'utf8');
 assert.match(java,/type\.equals\("additionalCommons"\)/);
 for(const m of C.ADDITIONAL_MUSEUMS)assert(java.includes('"'+m.category+'"'),m.category);
 assert(java.includes('iiurlwidth=2000'));
});
