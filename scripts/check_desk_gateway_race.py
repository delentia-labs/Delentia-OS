"""Browser regression: a delayed OLD health failure cannot undo a new connection.

Only the old failing request is intercepted; the new gateway is the real isolated
local API. This controlled race test is separate from the real demo recording.
"""
import asyncio
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright, expect


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path='/usr/lib/chromium/chromium', chromium_sandbox=True)
        page = await browser.new_page()
        seen, release = asyncio.Event(), asyncio.Event()

        async def delayed_failure(route):
            seen.set()
            await release.wait()
            await route.abort('failed')

        await page.route('http://localhost:8000/health', delayed_failure)
        await page.goto('http://127.0.0.1:3021/settings')
        await asyncio.wait_for(seen.wait(), timeout=5)
        await page.get_by_label('ที่อยู่ Gateway').fill('http://127.0.0.1:8021')
        async with page.expect_response(lambda r: r.url == 'http://127.0.0.1:8021/health' and r.status == 200):
            await page.get_by_role('button', name='บันทึก', exact=True).click()
        await expect(page.get_by_text(re.compile('^API ทำงาน v'))).to_be_visible()
        await expect(page.get_by_text('ต่อ API ไม่ได้', exact=True)).to_have_count(0)
        async with page.expect_event('requestfailed', predicate=lambda r: r.url == 'http://localhost:8000/health'):
            release.set()
        await page.wait_for_timeout(500)
        await expect(page.get_by_text(re.compile('^API ทำงาน v'))).to_be_visible()
        await expect(page.get_by_text('ต่อ API ไม่ได้', exact=True)).to_have_count(0)
        Path('/out/gateway-race.json').write_text(json.dumps({'passed': True, 'old_failure_intercepted': True, 'new_api_real': True}))
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
