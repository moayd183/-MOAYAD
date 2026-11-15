"""Optional health test: official SIA2, NASA Exoplanet TAP, Horizons and Sesame."""
import asyncio
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from backend.app.services.remote import get_bytes
from backend.app.settings import SIA_ENDPOINT, EXOPLANET_ENDPOINT

async def main():
    targets=[('IRSA SIA2',SIA_ENDPOINT,{'COLLECTION':'spherex_dr1','POS':'CIRCLE 133.795129 -7.245147 0.01','MAXREC':1}),
             ('NASA Exoplanet TAP',EXOPLANET_ENDPOINT,{'query':'select top 1 pl_name,ra,dec from pscomppars','format':'json'})]
    for label,url,params in targets:
        try:
            data=await get_bytes(url,params=params,max_bytes=3000000)
            print(label, 'LIVE RESPONSE',len(data),'bytes')
        except Exception as e:
            print(label,'UNAVAILABLE:',repr(e))

if __name__=='__main__':asyncio.run(main())
