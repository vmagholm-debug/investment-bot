"""Merge a reviewed batch into GitHub; the feed push triggers paper analysis."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
from miljon_signals import validate, stamp

REPO = 'vmagholm-debug/investment-bot'


def merge(current, batch, now=None):
    validate(current); validate(batch)
    now = now or datetime.now(timezone.utc)
    rows = {r['id']: r for r in current['signals']}
    changed = False
    for row in batch['signals']:
        if stamp(row['published_at']) > now or stamp(row['expires_at']) <= now:
            continue
        old = rows.get(row['id'])
        if old and any(old[k] != row[k] for k in ('ticker','published_at','expires_at')):
            raise ValueError('Existing signal identity/dates cannot be rewritten: ' + row['id'])
        if old != row:
            rows[row['id']] = row
            changed = True
    if not changed:
        return None
    # Retain all active rows; only remove expired rows if approaching the bound.
    ordered = sorted(rows.values(), key=lambda r:r['published_at'], reverse=True)
    if len(ordered) > 200 and any(stamp(r['expires_at']) > now for r in ordered[200:]):
        raise ValueError('More than 200 active signals; needs explicit capacity review')
    return validate({'version':1,'updated_at':now.isoformat(),'signals':ordered[:200]})


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('batch', type=Path)
    args=parser.parse_args()
    batch=validate(json.loads(args.batch.read_text()))
    endpoint=f'repos/{REPO}/contents/miljon_signals.json'
    remote=json.loads(subprocess.check_output(['gh','api',endpoint+'?ref=main'],text=True))
    current=json.loads(base64.b64decode(remote['content']))
    result=merge(current,batch)
    if result is None:
        print('No new or corrected signals; no push or execution triggered.')
        return
    encoded=base64.b64encode((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode()).decode()
    payload={'message':'Update reviewed MiljonBot candidates','branch':'main','sha':remote['sha'],'content':encoded}
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'request.json';path.write_text(json.dumps(payload))
        # Compare-and-swap SHA prevents concurrent publishers from losing signals.
        response=json.loads(subprocess.check_output(['gh','api','--method','PUT',endpoint,'--input',str(path)],text=True))
    print('Published signal commit: '+response['commit']['sha'])
    print('Feed push triggers run.yml; a successful push is not a confirmed trade.')


if __name__ == '__main__':
    main()
