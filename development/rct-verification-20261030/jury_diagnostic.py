"""Bounded fake-only reproduction of the intermittent jury control failure."""
import asyncio,json,os,runpy
from pathlib import Path
ns=runpy.run_path('rct_control_plane/tests/test_jury_measure_round56_real.py')
from rct_control_plane import signedai_jury
original=signedai_jury.run_jury
problems=[]
async def observed(*args,**kwargs):
    result=await original(*args,**kwargs)
    issues=[{'model':v.model,'problem':v.problem,'vote':v.vote} for v in result.votes if v.problem]
    if issues:problems.append({'proposal_sha256':result.proposal_sha256,'issues':issues})
    return result
signedai_jury.run_jury=observed
results=[]
with ns['fake_openrouter'].FakeOpenRouter(ns['PRICES'],policy=ns['persona'](set(ns['MODELS'][:3]))) as server:
    os.environ['DELENTIA_OPENROUTER_BASE_URL']=server.base_url
    os.environ['OPENROUTER_API_KEY']=server.key
    os.environ['DELENTIA_JURY_CONFIG']=''
    for i in range(10):
        out=ns['run'](ns['MODELS'])
        results.append({'iteration':i+1,'result':out['result'],'unexpected_rows':[r for r in out['rows'] if r['safe'] and not r['passed']]})
value={'scope':'scripted fake provider on loopback; concurrent full-suite host load','paid_calls':0,'results':results,'voter_problems':problems}
Path('/workspace/delentia-rct-evidence-20261030/jury-diagnostic.json').write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps({'iterations':len(results),'unexpected_results':sum(x['result']['accuracy']!=0.5 for x in results),'voter_problems':problems}))
