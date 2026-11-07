"""Confirm that the successfully built artifact is actually served by Pages."""
import argparse,json,time
from pathlib import Path
import httpx

def matches_manifest(expected,actual):
    return isinstance(actual,dict) and all(actual.get(k)==v for k,v in expected.items())

def verify(url,expected,attempts=60):
    with httpx.Client(timeout=15,follow_redirects=True) as client:
        for attempt in range(attempts):
            try:
                r=client.get(url.rstrip('/')+'/data/publication.json',params={'release':expected.get('workflow_run'),'attempt':attempt,'ts':time.time_ns()},headers={'Cache-Control':'no-cache'})
                if r.is_success and matches_manifest(expected,r.json()):
                    return {'status':'live_version_verified',**expected}
            except (httpx.HTTPError,ValueError):pass
            if attempt+1<attempts:time.sleep(5)
    raise RuntimeError('Pages did not serve the expected build; previous live site may still be active')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--manifest',default='dist/data/publication.json');a=p.parse_args()
    print(json.dumps(verify(a.url,json.loads(Path(a.manifest).read_text()))))
