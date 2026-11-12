const test=require('node:test');
const assert=require('node:assert/strict');
const C=require('../web/core.js');
test('preferred high-resolution tier still means 1200 short and 1600 long',()=>{
 for(const [w,h] of [[1200,1600],[1600,1200],[1400,1800],[2000,1450]])assert.equal(C.highResolution(w,h),true,w+'x'+h);
 for(const [w,h] of [[1199,2000],[1600,1199],[1000,1400],[500,800],[0,0],[-1,2000]])assert.equal(C.highResolution(w,h),false,w+'x'+h);
});
test('Commons original dimensions and Cleveland rendition use new acceptable medium threshold',()=>{
 assert.equal(C.metadataResolutionOkay({source:'클리블랜드',width:1000,height:1700}),true);
 assert.equal(C.metadataResolutionOkay({source:'클리블랜드',width:999,height:1700}),false);
 assert.equal(C.metadataResolutionOkay({source:'클리블랜드',width:1200,height:1700}),true);
 assert.equal(C.metadataResolutionOkay({source:'국립중앙박물관',museumRegion:'asia',width:760,height:2500}),false);
 assert.equal(C.metadataResolutionOkay({source:'국립중앙박물관',museumRegion:'asia',width:1800,height:2000}),true);
 assert.equal(C.metadataResolutionOkay({source:'시카고',width:0,height:0}),true);
});
test('Chicago IIIF request 2000 px; Met favors full image',()=>{
 const a=C.normalizeChicago({id:2,image_id:'2d484387-2509-5e8e-2c43-22f9981972eb',is_public_domain:true,artwork_type_title:'Painting'},'https://www.artic.edu/iiif/2');
 assert.match(a.image,/\/full\/2000,\/0\/default\.jpg$/);
 const b=C.normalizeMet({objectID:1,primaryImage:'https://images.metmuseum.org/full.jpg',primaryImageSmall:'https://images.metmuseum.org/low.jpg',isPublicDomain:true,classification:'Painting'});
 assert.equal(b.image,'https://images.metmuseum.org/full.jpg');
});
test('Low-resolution public-domain Asian painting is not usable despite rights OK',()=>{
 const raw={query:{pages:[{pageid:9,title:'File:Art.jpg',imageinfo:[{width:700,height:1800,mime:'image/jpeg',thumburl:'https://upload.wikimedia.org/x.jpg',extmetadata:{LicenseShortName:{value:'Public domain'},License:{value:'pd'}}}]}]}};
 const a=C.normalizeAsianCommons(raw,'korea')[0];
 assert.equal(C.eligibleArt(a),true);
 assert.equal(C.metadataResolutionOkay(a),false);
});
