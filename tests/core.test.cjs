const test=require('node:test');
const assert=require('node:assert/strict');
const C=require('../web/core.js');
const art={key:'cma:7',image:'https://openaccess-cdn.clevelandart.org/art/7.jpg',title:'Garden',artist:'Jane Roe',rightsOK:true,type:'Painting',license:'CC0',width:400,height:700};
test('only HTTPS image hosts from selected museums',()=>{
 for(const url of ['http://www.artic.edu/iiif/2/x/full/843,/0/default.jpg','https://localhost/test.jpg','https://openaccess-cdn.clevelandart.org.evil.test/p','https://user:pass@www.artic.edu/x','https://www.artic.edu:8443/x','javascript:alert(1)','file:///etc/passwd'])assert.equal(C.safeURL(url),false,url);
 for(const url of [art.image,'https://images.metmuseum.org/CRDImages/ep/original/DP123.jpg','https://www.artic.edu/iiif/2/a/full/843,/0/default.jpg'])assert.equal(C.safeURL(url),true,url);
});
test('reject all non-flat works and restricted works',()=>{
 assert.equal(C.eligibleArt(art),true);
 for(const type of ['Sculpture','Ceramics','Photograph','Furniture','3D installation','Tapestry']) assert.equal(C.eligibleArt({...art,type,medium:'',classification:''}),false,type);
 assert.equal(C.eligibleArt({...art,rightsOK:false}),false);
 assert.equal(C.eligibleArt({...art,description:'gallery view with frame'}),false);
 assert.equal(C.eligibleArt({...art,image:'http://www.artic.edu/abc'}),false);
 assert.equal(C.eligibleArt({...art,type:'Drawing',medium:'',classification:''}),true);
});
test('70% portrait targets each ten slots',()=>{
 for(let k=0;k<20;k++)assert.equal(Array.from({length:10},(_,i)=>C.targetOrientation(k*10+i)).filter(x=>x==='portrait').length,7);
 assert.equal(C.targetOrientation(7),'other');
});
test('90 days strict with clock reversal protection',()=>{
 const now=Date.parse('2026-11-12T03:00:00Z');
 assert.equal(C.canReshow(now-90*24*60*60*1000,now),true);
 assert.equal(C.canReshow(now-90*24*60*60*1000+1,now),false);
 assert.equal(C.canReshow(now+300,now),false);
 assert.equal(C.canReshow(null,now),true);
});
test('10am KST refresh boundary',()=>{
 assert.equal(C.kstRenewalDay(Date.parse('2026-11-12T00:59:59Z')),'2026-11-11');
 assert.equal(C.kstRenewalDay(Date.parse('2026-11-12T01:00:00Z')),'2026-11-12');
 assert.equal(C.kstRenewalDay(Date.parse('2026-11-12T15:40:00Z')),'2026-11-12');
});
test('normalization allows public domain painting only',()=>{
 const a=C.normalizeCleveland({id:4,title:'Violet',share_license_status:'CC0',type:'Painting',technique:'Oil on canvas',images:{web:{url:art.image,width:700,height:900}},creators:[{description:'Artist'}]});
 assert.equal(C.eligibleArt(a),true);assert.equal(C.orientation(a),'portrait');
 assert.equal(C.eligibleArt(C.normalizeCleveland({...a,share_license_status:'Other'})),false);
 const b=C.normalizeChicago({id:27992,title:'Sunday',is_public_domain:true,image_id:'2d484387-2509-5e8e-2c43-22f9981972eb',artwork_type_title:'Painting'},'https://www.artic.edu/iiif/2');
 assert.equal(C.eligibleArt(b),true);
 assert.equal(C.eligibleArt(C.normalizeChicago({id:5,is_public_domain:true,image_id:'bad/',artwork_type_title:'Painting'},'https://www.artic.edu/iiif/2')),false);
});
test('seen fingerprint prevents duplicate title artist cross-source',()=>{
 const previous=Date.parse('2026-11-11T00:00:00Z');
 const items=[art,{...art,key:'aic:8',image:'https://www.artic.edu/iiif/2/a/full/843,/0/default.jpg'}];
 const seen=new Map([[C.fingerprint(art),previous]]);
 assert.equal(C.pickCandidate(items,'portrait',seen,Date.parse('2026-11-12T00:00:00Z')),-1);
});

test('13 museum-style movements ordered and curator metadata prioritized',()=>{
 const names=['renaissance','baroque','rococo','neoclassicism','romanticism','realism',
 'impressionism','post-impressionism','expressionism','cubism','surrealism','abstract','contemporary'];
 assert.deepEqual(C.MOVEMENTS.map(x=>x.id),names);
 for(const m of C.MOVEMENTS){
   const explicit={...art,artist:'Unlisted Maker',style:m.en};
   assert.equal(C.classifyMovement(explicit),m.id,m.en);
 }
 assert.equal(C.classifyMovement({...art,artist:'Vincent van Gogh (1853–1890)'}),'post-impressionism');
 assert.equal(C.classifyMovement({...art,artist:'After Vincent van Gogh'}),null);
 assert.equal(C.classifyMovement({...art,artist:'Pablo Picasso'}),null);
 assert.equal(C.classifyMovement({...art,style:'Post-Impressionism',artist:'Mary Cassatt'}),'post-impressionism');
 assert.equal(C.classifyMovement({...art,date:'1880',artist:'Anonymous'}),null,'year must not assign styles');
});
test('skip unsupported movements instead of mislabelling',()=>{
 assert.equal(C.nextAvailableMovementIndex(0,id=>id==='romanticism'),4);
 assert.equal(C.nextAvailableMovementIndex(11,id=>id==='rococo'),2);
 assert.equal(C.nextAvailableMovementIndex(0,id=>false),-1);
});
test('bottom text strips replacement square glyphs, with safe missing fallback',()=>{
 assert.equal(C.tidyLabel('□ Garden ▯ ■', '제목 미상'),'Garden');
 assert.equal(C.tidyLabel('�� □', '작가 미상'),'작가 미상');
});
