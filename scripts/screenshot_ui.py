"""Offline screenshots of actual app UI, without pretending they are NASA observations."""
import asyncio
import shutil
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    root=Path(__file__).resolve().parents[1]
    output=root/'reports'
    html=(root/'frontend/static/index.html').read_text()
    css=(root/'frontend/static/style.css').read_text()
    js=(root/'frontend/static/app.js').read_text()
    html=html.replace('<link rel="stylesheet" href="/assets/style.css" />','').replace('<script type="module" src="/assets/app.js"></script>','')
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,executable_path=shutil.which('chromium') or shutil.which('google-chrome'), args=['--no-sandbox','--disable-dev-shm-usage'])
        page=await browser.new_page(viewport={'width':1440,'height':940},device_scale_factor=1)
        errors=[]
        page.on('pageerror',lambda e: errors.append(str(e)))
        await page.set_content(html)
        await page.add_style_tag(content=css)
        await page.add_script_tag(content=js)
        await page.screenshot(path=str(output/'skyshift_home_desktop.png'),full_page=True,timeout=10000)
        await page.locator('[data-nav="explore"]').first.click()
        await page.screenshot(path=str(output/'skyshift_explorer_desktop.png'),full_page=True,timeout=10000)
        await page.set_viewport_size({'width':390,'height':844})
        await page.locator('[data-nav="home"]').first.click()
        await page.screenshot(path=str(output/'skyshift_home_mobile.png'),full_page=True,timeout=10000)
        print('JS runtime errors:',errors)
        print('Mobile overflow:',await page.evaluate('document.documentElement.scrollWidth > innerWidth'))
        await browser.close()

if __name__=='__main__':asyncio.run(main())
