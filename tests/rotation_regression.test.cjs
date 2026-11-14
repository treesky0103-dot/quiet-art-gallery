const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const load=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
test('Native Android WebView 180 rotation',()=>{
 const java=load('android-app/app/src/main/java/com/gallery/kiosk/MainActivity.java');
 assert.match(java,/@JavascriptInterface\s+public void setDisplayRotation\(boolean upsideDown\)/);
 assert.match(java,/web\.setRotation\(upsideDown \? 180f : 0f\)/);
 const gradle=load('android-app/app/build.gradle');
 assert.match(gradle,/versionName '(?:1\.6\.6|1\.7\.3-portrait30|1\.7\.4-mixed|1\.7\.5-mediafull|1\.7\.6-urbanart|1\.8\.0-worldart|1\.8\.1-collectorv2)'/);
 assert.match(gradle,/applicationId 'com\.gallery\.kiosk\.(?:v166|portrait30|mixedmedia|mediafull|urbanart|worldart|collectorv2)'/);
});
test('Rotation is saved, restored and settings close automatically',()=>{
 const app=load('web/app.js');
 assert.match(app,/function applyRotation\(\)/);
 assert.match(app,/GalleryAndroid\.setDisplayRotation\(state\.flipped\)/);
 assert.match(app,/state\.flipped=!!\(flip&&flip\.value\);\s*applyRotation\(\);/);
 assert.match(app,/state\.flipped=!!enabled;\s*applyRotation\(\);/);
 assert.match(app,/el\('rotate-180'\)\.addEventListener\('click',async\(\)=>\{/);
 assert.match(app,/finally\{closeSettings\(\);\}/);
});
test('Browser rotates visible layers directly, not BODY',()=>{
 const css=load('web/style.css');
 assert.match(css,/body\.upside-down\{transform:none!important/);
 assert.match(css,/body\.upside-down:not\(\.native-rotation\) #viewer\{transform:rotate\(180deg\)!important/);
 assert.match(css,/body\.upside-down:not\(\.native-rotation\) #caption/);
 assert.match(css,/body\.upside-down:not\(\.native-rotation\) #hud/);
});