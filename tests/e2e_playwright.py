"""Browser DOM + core flow test using Chrome's about:blank, mocked API/images and
in-memory IndexedDB adapter. Sandbox blocks all navigation, including localhost.
This is NOT a real Android or third-party integration test.
"""
import base64,io,json,time
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]/'web'
def data_image(size):
 im=Image.new('RGB',size,'#9fb6b0');out=io.BytesIO();im.save(out,'PNG')
 return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()
PORTRAIT=data_image((1250,1850));LANDSCAPE=data_image((1850,1250))
STUB = (Path(__file__).with_name('stub.js')).read_text()
def main():
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=browser.new_page(viewport={'width':416,'height':680})
  page.goto('about:blank')
  html=(ROOT/'index.html').read_text()
  html=html.replace('<script src="core.js"></script>','').replace('<script src="app.js"></script>','').replace('<link rel="stylesheet" href="style.css">','')
  page.set_content(html)
  page.evaluate('window.__portrait = '+json.dumps(PORTRAIT)+'; window.__landscape = '+json.dumps(LANDSCAPE))
  page.add_script_tag(content=STUB)

  page.add_style_tag(content=(ROOT/'style.css').read_text())
  page.add_script_tag(content=(ROOT/'core.js').read_text())
  errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
  page.add_script_tag(content=(ROOT/'app.js').read_text())

  page.wait_for_function('window.__galleryDiagnostic().shown >= 11',timeout=20000)
  d=page.evaluate('window.__galleryDiagnostic()');print('MOCK DIAG',json.dumps(d,ensure_ascii=False))
  assert d['shown']>=11 and d['portrait']>=11 and d['other']==0,d
  keys=page.evaluate('window.__GALLERY_TEST__.shown.map(x=>x.key)')
  assert len(keys)==len(set(keys)),'duplicate during cycle'
  shown=page.evaluate('window.__GALLERY_TEST__.shown')
  order=['renaissance','baroque','rococo','neoclassicism','romanticism','realism',
      'impressionism','post-impressionism','expressionism','cubism','surrealism','abstract','contemporary']
  assert [x['movement'] for x in shown[:11]]==order[:11], shown[:11]
  assert page.locator('#caption').evaluate('(e)=>getComputedStyle(e).opacity')=='1', 'caption is not persistently visible'
  assert 'Artist ' in page.locator('#art-meta').inner_text()
  assert '클리블랜드' not in page.locator('#art-meta').inner_text()
  assert '세로형' not in page.locator('#art-meta').inner_text()
  assert 'Artwork ' in page.locator('#art-title').inner_text()
  print('PASS: 11 consecutive movement categories, title/artist-only persistent caption')
  page.locator('#viewer').click(position={'x':100,'y':70});page.locator('#open-settings').click()
  assert page.locator('#settings').is_visible()
  assert '90일' in page.locator('#settings').inner_text()
  assert '100MB' in page.locator('#settings').inner_text()
  page.locator('#rotate-180').click()
  assert page.locator('body').evaluate('(e)=>e.classList.contains("upside-down")')
  assert page.locator('#settings').is_hidden(),'closing settings must immediately reveal rotated painting'
  assert page.locator('#viewer').evaluate('(e)=>getComputedStyle(e).transform').startswith('matrix(-1, 0, 0, -1'), 'artwork was not rotated'
  page.evaluate("document.getElementById('open-settings').click()")
  assert page.locator('#settings').is_visible()
  assert page.locator('#rotation-status').inner_text()=='180° 회전 중'
  page.locator('#rotate-180').click()
  assert not page.locator('body').evaluate('(e)=>e.classList.contains("upside-down")')
  assert page.locator('#settings').is_hidden()
  assert page.locator('#viewer').evaluate('(e)=>getComputedStyle(e).transform')=='none'
  page.evaluate("document.getElementById('open-settings').click()")
  assert page.locator('#rotation-status').inner_text()=='기본 방향'
  assert page.locator('#audit-now').count()==1
  page.locator('#audit-now').click()
  page.wait_for_function("document.getElementById('audit-summary').textContent.includes('조회한 메타데이터')",timeout=12000)
  report=page.locator('#audit-summary').inner_text()
  assert '이지코 남아공 국립미술관' in report and '에티오피아 국립박물관' in report,report
  assert '암스테르담 국립미술관' in report and '런던 내셔널갤러리' in report,report
  assert '전체 작품 수' in report and '실제 픽셀 확인 필요' in report,report
  print('PASS: sampled 12-source inventory audit and explicit coverage limitation')
  print('PASS: 180-degree rotation toggle and readable bottom title/artist')
  page.locator('#settings-done').click()
  page.locator('#toggle-pause').click();count=page.evaluate('window.__galleryDiagnostic().shown')
  time.sleep(.6);assert page.evaluate('window.__galleryDiagnostic().shown')==count,'pause issue'
  page.locator('#toggle-pause').click()
  page.wait_for_function('(n)=>window.__galleryDiagnostic().shown>n',arg=count,timeout=4000)
  assert page.locator('#art-a').evaluate('(e)=>getComputedStyle(e).objectFit')=='contain'
  # Import round-trip protects 90-day repeat history across uninstall/reinstall.
  assert page.locator('#import-history').count()==1
  imported=page.evaluate(r"""async () => {
    const now=Date.now(), day=86400000;
    const valid=new Date(now-day).toISOString();
    const old=new Date(now-91*day).toISOString();
    const future=new Date(now+day).toISOString();
    const csv='key,shown_at\r\n'+
      JSON.stringify('cma:99999')+','+valid+'\r\n'+
      JSON.stringify('aic:88888')+','+old+'\r\n'+
      JSON.stringify('met:77777')+','+future+'\r\n';
    const result=await window.__galleryTestImportCsv(csv);
    return {result,valid:window.__dbTables.seen.get('cma:99999'),
      expired:window.__dbTables.seen.has('aic:88888'),
      future:window.__dbTables.seen.has('met:77777')};
  }""")
  assert imported['result']['imported']==1,imported
  assert imported['result']['skipped']==2,imported
  assert imported['valid'] and not imported['expired'] and not imported['future'],imported
  bad=page.evaluate(r"""async () => {
    try{await window.__galleryTestImportCsv('other-header\r\n"cma:1",2026-11-12T00:00:00.000Z');return false}
    catch(e){return e.message.includes('CSV')}
  }""")
  assert bad,'invalid CSV header accepted'
  print('PASS: CSV restore validation, out-of-window and future entries blocked')
  assert not errors,errors
  print('PASS: Chrome DOM, 80%+ portrait only, no-repeat, persistence calls, rotation and settings')
  browser.close()
if __name__=='__main__':main()
