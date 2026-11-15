"""Live five-target evidence. Never simulates successful observations."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from backend.app.models import SearchRequest
from backend.app.services.resolver import resolve_target
from backend.app.services.spherex import search_spherex, download_frame
from backend.app.services.science import ScienceDependencyMissing, open_science, preview_details

TARGETS=["Barnard's Star",'Epsilon Indi B','WISE 0855','RW Aurigae','R Draconis']

async def examine(name):
    out={'name':name,'status':'NOT_TESTED','coordinate_source':None,'ra':None,'dec':None,
         'observations':0,'dates':[],'fits_preview':None,'science':None,'errors':[]}
    try:
        if name=='WISE 0855':
            # Challenge-provided coordinates; a manual-source reference, not a claim
            # that a name resolver succeeded or detected the object.
            res=await resolve_target(name,ra='08:55:10.831',dec='-07:14:42.53')
        else:
            res=await resolve_target(name)
        out.update(ra=res['ra'],dec=res['dec'],coordinate_source=res['coordinate_source'])
        data=await search_spherex(SearchRequest(ra=res['ra'],dec=res['dec'],max_records=12))
        out['observations']=data['count']
        out['dates']=sorted(set(r['date'] for r in data['observations'] if r['date']))
        if data['errors']:out['errors'].extend(data['errors'])
        if not data['observations']:
            out['status']='NO_COVERAGE_FOUND' if not data['errors'] else 'UPSTREAM_ERROR'
            return out
        out['status']='LIVE_METADATA_RECEIVED'
        try:
            record=data['observations'][0]
            key,path,meta=await download_frame(record,res['ra'],res['dec'],5)
            out['fits_preview']={'id':key,'size_bytes':path.stat().st_size,'cutout_source':meta['cutout_url']}
            info=open_science(path)
            out['science']=preview_details(info)
            out['status']='LIVE_FITS_READ';out['errors'].append('Still requires independent astrometric/photometric QA before scientific pass.')
        except (ScienceDependencyMissing,ValueError,Exception) as err:
            out['errors'].append(f'FITS processing: {type(err).__name__}: {str(err)[:200]}')
        return out
    except Exception as err:
        out['status']='FAILED_OR_UNAVAILABLE';out['errors'].append(f'{type(err).__name__}: {str(err)[:250]}')
        return out

async def main():
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument('--live',action='store_true',help='Required: contact official live archives')
    a=args.parse_args()
    if not a.live:
        print('No live test was made. Supply --live to contact astronomy archives.')
        return
    rows=[]
    for name in TARGETS:
        print('Testing',name,flush=True)
        rows.append(await examine(name))
    data={'generated_utc':datetime.now(timezone.utc).isoformat(),
          'live_integration_attempted':True,'independent_scientific_discoveries_confirmed':0,
          'targets':rows}
    output=Path(__file__).resolve().parents[1]/'reports'/'targets_live.json'
    output.write_text(json.dumps(data,indent=2,ensure_ascii=False))
    print('Saved evidence:',output)
    for t in rows:print(t['name'],':',t['status'],t['observations'],'observations')

if __name__=='__main__':asyncio.run(main())
