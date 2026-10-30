import asyncio,json,tempfile
from pathlib import Path
from research.daaes.budget_guard import BudgetPolicy,ExperimentLedger,GuardedProvider,BudgetExceeded
from rct_control_plane.llm_provider import LLMProvider,LLMUsage
class Fake(LLMProvider):
 model='local-fixture-no-network'
 def __init__(self):
  self.calls=0;self.started=asyncio.Event();self.two=asyncio.Event();self.release=asyncio.Event()
 async def complete(self,*a,**k):
  self.calls+=1;self.started.set()
  if self.calls==2:self.two.set()
  await self.release.wait();self.last_usage=LLMUsage(1,1,0.0);return 'ok'
async def main():
 result={}
 with tempfile.TemporaryDirectory() as td:
  base=Path(td)
  for label,policy in [('negative',BudgetPolicy(total_usd=-1)),('nonfinite',BudgetPolicy(total_usd=float('nan'),warning_usd=float('nan'),stop_new_runs_usd=float('nan'),reserve_usd=float('nan'),max_cost_per_run_usd=float('nan')))]:
   try:
    b=ExperimentLedger(base/(label+'.json'),policy).start_run(label)
    reserved=b.before_call(1,1,0.1,0.1)
    result['policy_'+label]={'admitted':True,'reservation':reserved}
   except (ValueError,BudgetExceeded) as e:result['policy_'+label]={'admitted':False,'exception':type(e).__name__}
  ledger=ExperimentLedger(base/'tokens.json',BudgetPolicy(max_llm_calls_per_run=3,max_input_tokens_per_run=1,max_output_tokens_per_run=1))
  inner=Fake();provider=GuardedProvider(inner,ledger.start_run('tokens'),0.1,0.1)
  a=asyncio.create_task(provider.complete('hello',max_tokens=1));await asyncio.wait_for(inner.started.wait(),5)
  b=asyncio.create_task(provider.complete('hello',max_tokens=1))
  try:await asyncio.wait_for(inner.two.wait(),5)
  finally:inner.release.set();outcomes=await asyncio.gather(a,b,return_exceptions=True)
  result['inflight_tokens']={'input_cap':1,'output_cap':1,'fake_provider_calls':inner.calls,'finished_input':ledger.state['runs']['tokens']['input_tokens'],'finished_output':ledger.state['runs']['tokens']['output_tokens'],'errors':[type(o).__name__ for o in outcomes if isinstance(o,BaseException)]}
  # Positive control: the original in-flight CALL finding is fixed.
  ledger2=ExperimentLedger(base/'calls.json',BudgetPolicy(max_llm_calls_per_run=1))
  inner2=Fake();p2=GuardedProvider(inner2,ledger2.start_run('calls'),0.1,0.1)
  a=asyncio.create_task(p2.complete('hello',max_tokens=1));await asyncio.wait_for(inner2.started.wait(),5)
  refused=False
  try:await p2.complete('hello',max_tokens=1)
  except BudgetExceeded:refused=True
  finally:inner2.release.set();await a
  result['original_call_cap']={'configured':1,'fake_provider_calls':inner2.calls,'second_refused':refused}
  for name,price in [('negative_price',-1.0),('nan_price',float('nan'))]:
   try:ExperimentLedger(base/(name+'.json'),BudgetPolicy()).start_run(name).before_call(1,1,price,price);result[name]='admitted'
   except BudgetExceeded:result[name]='refused'
 Path('/workspace/delentia-rct-evidence-20261030/budget-followup.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
asyncio.run(main())
