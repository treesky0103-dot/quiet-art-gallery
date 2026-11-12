"""Simulated blocked museum APIs: 4 bundled painting images still rotate on time.

This checks the browser scheduling logic. Android's Handler is also built but
must be physically tested on a real device for exact wake-up timing.
"""
import base64,io,json,time
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]/'web'
def image64():
 im=Image.new('RGB',(1400,1800),'#bbb0a2');out=io.BytesIO()
 im.save(out,format='PNG')
 return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode('ascii')
def main():
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=browser.new_page(viewport={'width':400,'height':640})
  page.goto('about:blank')
  html=(ROOT/'index.html').read_text().replace('<script src="core.js"></script>','').replace('<script src="app.js"></script>','').replace('<link rel="stylesheet" href="style.css">','')
  page.set_content(html)
  page.evaluate('window.__portrait='+json.dumps(image64())+';window.__landscape='+json.dumps(image64()))
  page.add_script_tag(content=(Path(__file__).with_name('stub.js')).read_text())
  page.evaluate("""() => {
    const deck=Array.from({length:4},(_,i)=>({
      key:'commons:'+(55000+i),source:'암스테르담 국립미술관',
      title:'Offline painting '+i,artist:'Painter '+i,
      image:'https://upload.wikimedia.org/wikipedia/commons/thumb/sample'+i+'.jpg',
      offlineAsset:'offline/fallback-'+i+'.jpg',
      type:'Painting',classification:'Painting',medium:'Oil on canvas',
      width:1400,height:1800,rightsOK:true,license:'Public domain',
      museumRegion:'additional',verifiedCollectionCategory:true,style:'',styles:[]
    }));
    window.GalleryAndroid={cacheStats:()=>JSON.stringify({bytes:0}),setDisplayRotation:()=>{}};
    window.fetch=async function(url){
      if(String(url).includes('offline-deck.json'))return {ok:true,json:async()=>deck};
      throw Error('simulated network outage');
    };
    window.__GALLERY_TEST__.intervalMs=250;
    window.__GALLERY_TEST__.shown=[];
    window.__GALLERY_TEST__.onShow=(art,orient,emergency)=>{
      window.__GALLERY_TEST__.shown.push({key:art.key,when:Date.now(),emergency});
    };
    window.__GALLERY_TEST__.request=async()=>new Promise(()=>{});
  }""")
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.add_style_tag(content=(ROOT/'style.css').read_text())
  page.add_script_tag(content=(ROOT/'core.js').read_text())
  page.add_script_tag(content=(ROOT/'app.js').read_text())
  page.wait_for_function('window.__galleryDiagnostic().offlineReady===4',timeout=12000)
  page.wait_for_function('window.__galleryDiagnostic().tickCount>=9',timeout=12000)
  diag=page.evaluate('window.__galleryDiagnostic()')
  frames=page.evaluate('window.__GALLERY_TEST__.shown')
  assert diag['emergencySwaps']==4,diag
  assert diag['shown']==4,diag
  assert diag['exhaustedTicks']>=5,diag
  assert diag['offlineReady']==4,diag
  assert all(x['key']!=y['key'] for x,y in zip(frames,frames[1:])),frames
  diff=[(b['when']-a['when']) for a,b in zip(frames,frames[1:])]
  assert min(diff)>=140 and max(diff)<650,diff
  assert len(frames)==len({x['key'] for x in frames})==4,frames
  assert all(x['emergency'] for x in frames),frames
  print('PASS: blocked API, 4 unique artworks, exhausted without repeating, cadence ms',diff,flush=True)
  page.locator('#viewer').click(position={'x':30,'y':100})
  page.locator('#toggle-pause').click()
  before=page.evaluate('window.__galleryDiagnostic().tickCount')
  time.sleep(.75)
  assert page.evaluate('window.__galleryDiagnostic().tickCount')==before,'pause did not stop rotation'
  page.locator('#toggle-pause').click()
  page.wait_for_function('(n)=>window.__galleryDiagnostic().tickCount>n',arg=before,timeout=3000)
  assert page.evaluate('window.__galleryDiagnostic().shown')==4,'unexpected repeat after resuming'
  print('PASS: pause/resume retains native-style 30sec clock contract',flush=True)
  assert not errors,errors
  browser.close()
if __name__=='__main__':main()
