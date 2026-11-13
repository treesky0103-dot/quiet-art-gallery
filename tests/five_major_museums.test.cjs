const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const C = require('../web/core.js');

const expected = [
  ['louvre', 'Paintings in the Louvre', 'Painting'],
  ['orsay', "Paintings in the Musée d'Orsay", 'Painting'],
  ['british', 'Prints in the British Museum', 'Print'],
  ['prado', 'Paintings in the Museo del Prado', 'Painting'],
  ['hermitage', 'Paintings in the Hermitage', 'Painting']
];
const root = path.join(__dirname, '..');
const source = rel => fs.readFileSync(path.join(root, rel), 'utf8');
function fixture({id = 987654, title = 'File:Portrait by artist.jpg', license = 'Public domain', width = 1600, height = 2400, mime = 'image/jpeg'} = {}) {
  return {query: {pages: [{pageid: id, title, imageinfo: [{
    width, height, mime,
    thumburl: 'https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Portrait.jpg/2000px-Portrait.jpg',
    descriptionurl: 'https://commons.wikimedia.org/wiki/File:Portrait.jpg',
    extmetadata: {LicenseShortName: {value: license}, Artist: {value: 'Unidentified artist'}}
  }]}]}};
}
test('five distinct verified Commons category names join the original 35 institutions', () => {
  assert.equal(C.ADDITIONAL_MUSEUMS.length, 26);
  assert.equal(3 + C.ASIAN_MUSEUMS.length + C.AFRICAN_MUSEUMS.length +
    C.ADDITIONAL_MUSEUMS.length + C.SMITHSONIAN_MUSEUMS.length, 40);
  assert.equal(new Set(C.ADDITIONAL_MUSEUMS.map(m => m.category)).size, 26);
  assert.deepEqual(C.ADDITIONAL_MUSEUMS.slice(-5).map(m => [m.id,m.category,m.type || 'Painting']), expected);
});
test('native Android and browser ship identical allowed Commons collection names', () => {
  const java = source('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
  const app = source('web/app.js');
  const html = source('web/index.html');
  for (const [id, category] of expected) {
    assert(java.includes('"'+id+'"'), id);
    assert(java.includes('"'+category+'"'), category);
  }
  assert.match(java, /type\.equals\("additionalCommons"\)/);
  assert.match(app, /kind==='asianCommons'\|\|kind==='africanCommons'\|\|kind==='additionalCommons'/);
  assert(html.includes('총 40곳'));
  for (const file of ['app.js','core.js','index.html']) {
    assert.equal(source('web/'+file),source('android-app/app/src/main/assets/'+file), file);
  }
});
test('all museums use 2D file type, public-domain filter and 75 percent portrait rule', () => {
  for (const [id, category, type] of expected) {
    const a = C.normalizeAdditionalCommons(fixture(),id)[0];
    assert.equal(a.type,type,category);
    assert.equal(a.source,C.ADDITIONAL_MUSEUMS.find(m=>m.id===id).label);
    assert.equal(a.rightsOK,true);
    assert.equal(C.eligibleArt(a),true);
    assert.equal(C.metadataResolutionOkay(a),true);
    assert.equal(C.fillsPortraitScreen(a.width,a.height,1000,1600,.75),true);
    assert.equal(C.classifyMovement(a),'additional');
    assert.equal(C.eligibleArt(C.normalizeAdditionalCommons(fixture({license:'CC BY 4.0'}),id)[0]),false);
    assert.equal(C.metadataResolutionOkay(C.normalizeAdditionalCommons(fixture({width:999}),id)[0]),false);
    assert.equal(C.normalizeAdditionalCommons(fixture({title:'File:Framed painting on gallery wall.jpg'}),id).length,0);
  }
  assert.equal(C.normalizeAdditionalCommons(fixture(),'fake-museum').length,0);
  assert.equal(C.fillsPortraitScreen(1700,1200,1000,1600,.75),false);
});
test('26 categories all visited under stride 11, and 90 day repeat protection unchanged', () => {
  const app=source('web/app.js');
  assert(app.includes('(state.additionalOrder++*11)%C.ADDITIONAL_MUSEUMS.length'));
  const visited=new Set(Array.from({length:26},(_,i)=>(i*11)%26));
  assert.equal(visited.size,26);
  const now=Date.parse('2026-11-14T00:00:00Z');
  const a=C.normalizeAdditionalCommons(fixture({id:123456}), 'louvre')[0];
  const b=C.normalizeAdditionalCommons(fixture({id:123456}), 'prado')[0];
  assert.equal(a.key,b.key);
  assert.equal(C.pickCandidate([b], 'portrait', new Map([[a.key,now-24*3600000]]),now),-1);
  assert.equal(C.canReshow(now-89*86400000,now),false);
  assert.equal(C.canReshow(now-90*86400000,now),true);
  assert.match(app, /intervalMs: 30000/);
  assert.match(app, /pruneDays: 90/);
});
