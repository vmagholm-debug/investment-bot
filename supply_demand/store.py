"""Atomic paper-state publication on a dedicated GitHub branch; never reset implicitly."""
import argparse
import base64
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from supply_demand.agent import initialize, validate_state

BRANCH='supply-demand-paper-state'
STATE_PATH='supply-demand/state.json'

class APIError(RuntimeError):pass

def api(repo,path,payload=None):
 cmd=['gh','api',f'repos/{repo}'+('/'+path if path else '')]
 if payload is not None:cmd+=['--method','POST','--input','-']
 r=subprocess.run(cmd,input=json.dumps(payload) if payload is not None else None,text=True,capture_output=True,timeout=45)
 if r.returncode:raise APIError(r.stderr.strip())
 return json.loads(r.stdout)


def pull(repo,folder,bootstrap=False):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 try:ref=api(repo,'git/ref/heads/'+BRANCH)
 except APIError as e:
  if '404' not in str(e):raise
  if not bootstrap:raise ValueError('Paper state branch is absent. Refusing to reset; explicit first initialization required.')
  default=api(repo,'')['default_branch'];ref=api(repo,'git/ref/heads/'+default);exists=False
 else:
  if bootstrap:raise ValueError('State branch already exists. Initialization refused; use normal restore.')
  exists=True
 head=ref['object']['sha'];commit=api(repo,'git/commits/'+head)
 if exists:
  tree=api(repo,'git/trees/'+commit['tree']['sha']+'?recursive=1')
  blob=next(x for x in tree['tree'] if x['path']==STATE_PATH)
  obj=api(repo,'git/blobs/'+blob['sha'])
  state=validate_state(json.loads(base64.b64decode(obj['content'])))
 else:state=initialize(datetime.now(timezone.utc))
 (folder/'state.json').write_text(json.dumps(state,ensure_ascii=False,allow_nan=False))
 (folder/'remote.json').write_text(json.dumps({'expected_head':head,'base_tree':commit['tree']['sha'],'branch_exists':exists}))
 print('Restored existing paper account' if exists else 'Explicit first paper-account initialization prepared')


def push(repo,folder):
 folder=Path(folder);meta=json.loads((folder/'remote.json').read_text());validate_state(json.loads((folder/'state.json').read_text()))
 if meta['branch_exists']:
  actual=api(repo,'git/ref/heads/'+BRANCH)['object']['sha']
  if actual!=meta['expected_head']:raise ValueError('Concurrent state change; refusing stale publication')
 tree=[]
 for filename in ('state.json','latest.json','trades.csv','summary.md'):
  content=(folder/filename).read_text()
  tree.append({'path':'supply-demand/'+filename,'mode':'100644','type':'blob','content':content})
 new_tree=api(repo,'git/trees',{'base_tree':meta['base_tree'],'tree':tree})
 commit=api(repo,'git/commits',{'message':'Record independent Supply & Demand paper run','tree':new_tree['sha'],'parents':[meta['expected_head']]})
 if not meta['branch_exists']:
  api(repo,'git/refs',{'ref':'refs/heads/'+BRANCH,'sha':commit['sha']})
 else:
  # GitHub rejects non-fast-forward moves: concurrent jobs cannot overwrite history.
  cmd=['gh','api',f'repos/{repo}/git/refs/heads/{BRANCH}','--method','PATCH','--input','-']
  r=subprocess.run(cmd,input=json.dumps({'sha':commit['sha'],'force':False}),text=True,capture_output=True,timeout=45)
  if r.returncode:raise APIError(r.stderr.strip())
 print(json.dumps({'branch':BRANCH,'commit':commit['sha']}))


def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['pull','push']);p.add_argument('--repo',default=os.environ.get('GITHUB_REPOSITORY','vmagholm-debug/investment-bot'));p.add_argument('--directory',required=True);p.add_argument('--initialize',action='store_true');a=p.parse_args()
 if a.mode=='pull':pull(a.repo,a.directory,a.initialize)
 else:push(a.repo,a.directory)

if __name__=='__main__':main()
