"""Actual sandboxed Chromium UI recording. Synthetic data, real local API."""
import asyncio,json,time,re,os
from urllib.parse import urlsplit
from pathlib import Path
from playwright.async_api import async_playwright,expect

OUT=Path(os.environ.get('DELENTIA_DEMO_OUTPUT','/out'));OUT.mkdir(parents=True,exist_ok=True)
BASE=os.environ.get('DELENTIA_DEMO_BASE_URL','http://127.0.0.1:3021')
API=os.environ.get('DELENTIA_DEMO_API_URL','http://127.0.0.1:8021')
for url in (BASE,API):
 assert urlsplit(url).hostname in {'localhost','127.0.0.1','::1'}, 'Use an isolated loopback demo API only'
TEXT='ข้อมูลสาธิต: น้ำ กำลัง งบประมาณ 15,000.00 บาท — ไม่ใช่ข้อมูลลูกค้า (รอบ '+time.strftime('%H:%M:%S')+')'
async def main():
 frames=[];checks=[];errors=[];stop=False;stage='startup';start=time.monotonic()
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=os.environ.get('DELENTIA_DEMO_CHROMIUM','/usr/lib/chromium/chromium'),headless=True,chromium_sandbox=True)
  context=await browser.new_context(viewport={'width':1280,'height':900},locale='th-TH')
  page=await context.new_page()
  page.on('pageerror',lambda e:errors.append({'stage':stage,'error':str(e)}))
  await page.goto('chrome://sandbox')
  sandbox=await page.locator('body').inner_text()
  assert 'You are adequately sandboxed' in sandbox
  assert 'Seccomp-BPF sandbox\tYes' in sandbox
  async def capture():
   while not stop:
    try:
     name=f'frame-{len(frames):05d}.png'
     await page.screenshot(path=str(OUT/name))
     frames.append({'file':name,'seconds':time.monotonic()-start,'stage':stage})
    except Exception as exc:errors.append({'stage':'capture','error':type(exc).__name__})
    await asyncio.sleep(0.5)
  async def checkpoint(name):
   checks.append(name);await page.screenshot(path=str(OUT/(name+'.png')),full_page=True);await asyncio.sleep(3.0)
  recorder=asyncio.create_task(capture())
  failure=None
  try:
   stage='settings'
   await page.goto(BASE+'/settings')
   gateway=page.get_by_label('ที่อยู่ Gateway')
   await gateway.fill('http://127.0.0.1:59999')
   await page.get_by_role('button',name='ทดสอบการเชื่อมต่อ',exact=True).click()
   await expect(page.get_by_role('status')).to_contain_text('ไม่ได้')
   await checkpoint('01-offline-detected')
   stage='connect'
   await gateway.fill(API)
   await page.get_by_role('button',name='บันทึก',exact=True).click()
   await page.get_by_role('button',name='ทดสอบการเชื่อมต่อ',exact=True).click()
   await expect(page.get_by_role('status')).to_contain_text('เชื่อมต่อสำเร็จ: Delentia API')
   assert 'undefined' not in await page.get_by_role('status').inner_text()
   await expect(page.get_by_text('ต่อ API ไม่ได้',exact=True)).to_have_count(0)
   await checkpoint('02-connected')
   stage='remember'
   await page.get_by_role('link',name='ความจำ',exact=True).click()
   await page.get_by_label('สิ่งที่ agent ควรรู้').fill(TEXT)
   await page.get_by_role('button',name='บันทึกความจำ',exact=True).click()
   await expect(page.locator("p").filter(has_text=TEXT)).to_be_visible()
   await expect(page.locator('li button').filter(has_text=TEXT)).to_be_visible()
   await checkpoint('03-thai-memory')
   stage='reload'
   await page.reload()
   await expect(page.locator("p").filter(has_text=TEXT)).to_be_visible()
   await checkpoint('04-persisted-after-reload')
   stage='revoke'
   await page.get_by_role('button',name='เพิกถอน',exact=True).click()
   await page.get_by_label(re.compile('^เหตุผล')).fill('สิ้นสุดการทดสอบข้อมูลสังเคราะห์')
   await page.get_by_role('button',name='ยืนยันเพิกถอน',exact=True).click()
   await expect(page.locator("p").filter(has_text=TEXT)).to_have_count(0)
   await checkpoint('05-revoked-hidden')
   await page.get_by_role('button',name='แสดงที่เพิกถอนแล้ว',exact=True).click()
   await expect(page.locator("p").filter(has_text=TEXT)).to_be_visible()
   await checkpoint('06-revoked-audit-visible')
  except Exception as exc:
   failure=repr(exc);await page.screenshot(path=str(OUT/'failure.png'),full_page=True)
  finally:
   stop=True;await recorder
   result={'passed':failure is None and not errors,'failure':failure,'checks':checks,'page_errors':errors,'sandbox':sandbox,'frames':frames,'scope':'real GUI Settings/Memory with real isolated local API; no model generation, not RCT contract/chat E2E','synthetic_text':TEXT}
   (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
   await browser.close()
  assert failure is None,failure
  assert not [e for e in errors if e['stage']!='capture'],errors
if __name__ == '__main__':
 asyncio.run(main())
