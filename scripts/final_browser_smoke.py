"""End-to-end Chromium QA with marked mock API fixtures (NOT live NASA data).
Validates actual frontend navigation, search, 422 error, fallback comparison,
scientific difference, language and mobile layout. Run with:
    python scripts/final_browser_smoke.py
"""
import asyncio
import base64
import json
import shutil
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'reports'
OUT.mkdir(exist_ok=True)
PNG = BytesIO()
Image.new('RGB', (24, 24), (33, 84, 140)).save(PNG, format='PNG')
PNG = PNG.getvalue()


def observation(year, suffix):
    return {
        'search_request_id': 'a'*32,
        'obs_id': f'TEST-MOCK-{year}-{suffix}',
        'date': f'{year}-06-{suffix+10:02d}T12:00:00Z',
        'collection': 'spherex_dr1' if year == 2025 else 'spherex_qr3',
        'ra': 133.8, 'dec': -7.2, 'detector': 2,
        'bandpass': 'D2',
        'em_min_m': 1.2e-6, 'em_max_m': 1.3e-6,
        'access_url': f'https://irsa.ipac.caltech.edu/ibe/data/spherex/{year}/mock-{suffix}.fits',
        'data_mode': 'real',
    }


async def main():
    records = [observation(y, n) for y in (2025, 2026) for n in range(3)]
    frames = [
        {'frame_id': f'{y}'*8, 'science': {'quality': 'valid_with_flags_masked', 'spectral_center': [1.24]},
         'preview_url': 'data:image/png;base64,'+base64.b64encode(PNG).decode(), 'fits_url':f'/api/fixture/{y}.fits',
         'provenance': {'observation': next(r for r in records if r['date'].startswith(str(y))),
                        'actual_fov_arcmin': 5, 'requested_fov_arcmin': 10,
                        'warning': 'smaller valid cutout'}} for y in (2025, 2026)
    ]
    errors=[]
    js_mock = f"""
    window.__annualRequests=[];
    const mockRecords={json.dumps(records,ensure_ascii=False)};
    const mockFrames={json.dumps(frames,ensure_ascii=False)};
    window.fetch = async (path, options={{}}) => {{
       const url=String(path).split('?')[0];
       const payload=options.body ? JSON.parse(options.body):{{}};
       let data, status=200;
       if(url==='/api/objects/resolve') data={{status:'ok',object:{{name:'WISE 0855',ra:133.8,dec:-7.2,type:'astronomical_object',coordinate_source:'TEST MOCK — NOT NASA',note:'Browser fixture only'}}}};
       else if(url==='/api/spherex/observations/search') data={{observations:mockRecords,count:6,year_counts:{{'2025':3,'2026':3}},status:'ok',request_id:'{'a'*32}',archive_rows:6,diagnostics:[]}};
       else if(url==='/api/spherex/frames/build') {{status=502;data={{message:'Upstream HTTP 422 (irsa.ipac.caltech.edu). Archive rejected this cutout.'}};}}
       else if(url==='/api/spherex/years/compare') {{window.__annualRequests.push(payload);data={{status:'ok',frames:mockFrames,years:[2025,2026],spectrally_comparable_at_cutout_center:true,attempts:[{{year:'2025',obs_id:'TEST-MOCK-2025-0',message:'HTTP 422'}}],message:'Browser test fixture only'}};}}
       else if(url==='/api/analysis/compare') data={{status:'ok',image_data_url:'data:image/png;base64,{base64.b64encode(PNG).decode()}',color_legend:{{positive:'red',negative:'blue'}},note:'MOCK DIFFERENCE, not real NASA data'}};
       else {{status=404;data={{message:'No test fixture for '+url}};}}
       return new Response(JSON.stringify(data),{{status,headers:{{'Content-Type':'application/json'}}}});
    }};
    """
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,
          executable_path=shutil.which('chromium') or shutil.which('google-chrome'),
          args=['--no-sandbox','--disable-dev-shm-usage'])
        page=await browser.new_page(viewport={'width':1440,'height':900})
        page.on('pageerror',lambda exc: errors.append(str(exc)))
        html=(ROOT/'frontend/static/index.html').read_text()
        html=html.replace('<link rel="stylesheet" href="/assets/style.css" />','')
        html=html.replace('<script type="module" src="/assets/app.js"></script>','')
        await page.set_content(html)
        await page.add_style_tag(content=(ROOT/'frontend/static/style.css').read_text())
        await page.add_script_tag(content=js_mock)
        await page.add_script_tag(content=(ROOT/'frontend/static/app.js').read_text())
        await page.locator('[data-nav="explore"]').first.click()
        await page.locator('#objectName').fill('WISE 0855')
        await page.locator('#skyForm [type=submit]').click()
        await page.locator('[data-action="compare-years"]').wait_for(timeout=6000)
        assert await page.locator('[data-record]').count()==6
        await page.locator('[data-record]').first.click()
        await page.get_by_text('رفض أرشيف NASA قصاصة FITS',exact=False).first.wait_for(timeout=6000)
        await page.locator('[data-action="compare-years"]').click()
        await page.locator('.half-cols img').first.wait_for(timeout=6000)
        assert await page.locator('.half-cols img').count()==2
        used=await page.evaluate('window.__annualRequests')
        assert used and used[0]['year_a']==2025 and used[0]['year_b']==2026
        assert await page.get_by_text('2025',exact=False).count()>=1
        assert await page.get_by_text('2026',exact=False).count()>=1
        await page.screenshot(path=str(OUT/'skyshift_final_comparison_desktop_MOCK.png'),full_page=True)
        await page.locator('[data-action="show-difference"]').click()
        await page.locator('img[src^="data:image/png;base64,"]').first.wait_for(timeout=6000)
        assert await page.get_by_text('MOCK DIFFERENCE',exact=False).count()==1
        await page.locator('#language').click()
        assert await page.evaluate('document.documentElement.dir')=='ltr'
        await page.locator('#language').click()
        assert await page.evaluate('document.documentElement.dir')=='rtl'
        await page.set_viewport_size({'width':390,'height':844})
        await page.screenshot(path=str(OUT/'skyshift_final_comparison_mobile_MOCK.png'),full_page=True)
        assert not await page.evaluate('document.documentElement.scrollWidth>window.innerWidth'), 'mobile horizontal overflow'
        await browser.close()
    print(json.dumps({'browser_tests':'PASS','mock_only':True,'annual_request_count':len(used),
                      'js_errors':errors,'mobile_overflow':False},ensure_ascii=False))
    assert not errors,errors

if __name__=='__main__':
    asyncio.run(main())
