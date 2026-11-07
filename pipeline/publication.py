"""Confirm that the successfully built artifact is actually served by Pages."""
import argparse,json,time,os,re
from datetime import datetime,timezone
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


def can_cancel_conflict(runs,current_run,now_utc=None):
    """Only retire a completed Atlas run, while the shared publication lock is held."""
    owned=[r for r in runs if str(r['id'])!=str(current_run) and r.get('name') in {'Build and deploy Pages','Autonomous data release'} and r.get('head_branch')=='main']
    if not owned or any(r.get('status')!='completed' for r in owned):return False
    clock=now_utc or datetime.now(timezone.utc)
    return all((clock-datetime.fromisoformat(r['updated_at'].replace('Z','+00:00'))).total_seconds()>=120 for r in owned)

def deployment_version(sha,run,attempt):
    # Pages build versions are unique build strings, not necessarily a commit SHA.
    if not re.fullmatch(r'[a-f0-9]{40}',sha) or not str(run).isdigit() or not str(attempt).isdigit():raise ValueError('Invalid build identity')
    return sha+'-'+str(run)+'-'+str(attempt)

def deploy():
    """Use the documented Pages API, recovering only a stale completed Atlas deployment."""
    repo=os.environ['GITHUB_REPOSITORY'];run=os.environ['GITHUB_RUN_ID'];sha=os.environ['GITHUB_SHA']
    if repo!='oliver0923-hub/smj-research-atlas':raise ValueError('Unexpected publication target')
    version=deployment_version(sha,run,os.getenv('GITHUB_RUN_ATTEMPT','1'))
    root='https://api.github.com/repos/'+repo
    headers={'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
    with httpx.Client(timeout=40,headers=headers) as client:
        response=client.get(root+'/actions/runs/'+run+'/artifacts');response.raise_for_status()
        artifacts=[a for a in response.json()['artifacts'] if a['name']=='github-pages' and not a['expired']]
        if len(artifacts)!=1:raise ValueError('Exactly one current-run Pages artifact required')
        deployment=None
        for attempt in range(30):
            oidc=client.get(os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'],headers={'Authorization':'Bearer '+os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']});oidc.raise_for_status()
            r=client.post(root+'/pages/deployments',json={'artifact_id':artifacts[0]['id'],'pages_build_version':version,'oidc_token':oidc.json()['value']})
            if r.is_success:deployment=r.json();break
            message=r.json().get('message','')
            match=re.search(r'in progress deployment.*?cancel ([0-9a-f]{40}(?:-[0-9]+-[0-9]+)?)',message,re.I)
            if r.status_code!=400 or not match:r.raise_for_status()
            stale=match[1]
            prior=client.get(root+'/actions/runs',params={'head_sha':stale[:40],'per_page':100});prior.raise_for_status()
            if can_cancel_conflict(prior.json()['workflow_runs'],run):
                cancelled=client.post(root+'/pages/deployments/'+stale+'/cancel')
                if cancelled.status_code not in {200,202,204,404,409}:raise RuntimeError('Stale deployment recovery rejected: '+str(cancelled.status_code)+' '+cancelled.json().get('message','')[:300])
                print(json.dumps({'status':'retired_stale_atlas_deployment','revision':stale}),flush=True)
            time.sleep(10)
        if not deployment:raise RuntimeError('Pages conflict remained after bounded retries')
        deployment_id=str(deployment.get('id') or version)
        for attempt in range(60):
            state=client.get(root+'/pages/deployments/'+deployment_id);state.raise_for_status();status=state.json()['status']
            if status=='succeed':
                url=deployment.get('page_url') or 'https://oliver0923-hub.github.io/smj-research-atlas/'
                output=os.getenv('GITHUB_OUTPUT')
                if output:
                    with open(output,'a',encoding='utf-8') as f:f.write('page_url='+url+'\n')
                return {'status':'pages_api_success','page_url':url,'revision':sha,'build_version':version}
            if status in {'deployment_failed','deployment_perms_error','deployment_content_failed','deployment_cancelled','deployment_lost'}:raise RuntimeError('Pages status '+status)
            time.sleep(5)
        raise RuntimeError('Pages status did not complete within budget')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url');p.add_argument('--deploy',action='store_true');p.add_argument('--manifest',default='dist/data/publication.json');a=p.parse_args()
    print(json.dumps(deploy() if a.deploy else verify(a.url,json.loads(Path(a.manifest).read_text()))))
