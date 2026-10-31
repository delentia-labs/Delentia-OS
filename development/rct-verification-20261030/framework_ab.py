"""Deterministic framework A/B, no model, source truth or paid inference claim."""
import argparse,json,time,statistics
from pathlib import Path
from pydantic import Field
from rct_control_plane import component_execution as ce
from rct_control_plane.rct_plan import PlanItem
Base=getattr(ce,'CriterionVerification',PlanItem)
class Empty(PlanItem):pass
class Verdict(Base):
 criterion_id:str
 satisfied:bool
class Number(PlanItem):value:int
class FromNumber(PlanItem):source:Number
class Limit(PlanItem):value:int=Field(gt=0)
class Rule(PlanItem):threshold:int
class Config(PlanItem):rule:Rule

def make(nodes,registry,criteria=(),callback=None):
 return ce.ComponentScheduler({'schema_version':1,'nodes':nodes},registry,criteria,{},callback or (lambda *a:None))
def verdict(value):
 receipts=[]
 try:
  s=make([{'id':'check','handler':'v','phase':'verify','criteria':['C1']}],{'v':ce.Handler(Empty,Verdict,'verify',lambda i:value)},['C1'],lambda k,v:receipts.append(v))
  s.drain('verify');s.require_complete()
  return {'accepted':True,'receipts':len(receipts)}
 except ValueError:
  return {'accepted':False,'receipts':len(receipts)}
def literal():
 try:
  make([{'id':'n','handler':'n','phase':'compute','parameters':{'value':0}}],{'n':ce.Handler(Limit,Number,'compute',lambda i:{'value':i.value})})
  return True
 except ValueError:return False

def mutate(kind):
 p={'schema_version':1,'nodes':[{'id':'n','handler':'n','phase':'compute','parameters':{'rule':{'threshold':5}}}]}
 s=ce.ComponentScheduler(p,{'n':ce.Handler(Config,Number,'compute',lambda i:{'value':i.rule.threshold})},[],{},lambda *a:None)
 if kind=='input':p['nodes'][0]['parameters']['rule']['threshold']=99
 else:s.program.nodes[0].parameters['rule']['threshold']=99
 s.drain('compute');s.require_complete();return s.outputs['n']['value']

def output_mutation():
 s=make([{'id':'a','handler':'read','phase':'observation'},{'id':'b','handler':'use','phase':'compute','depends_on':['a'],'inputs':{'source':'a'}}],
  {'read':ce.Handler(Empty,Number,'observation',None),'use':ce.Handler(FromNumber,Number,'compute',lambda i:{'value':i.source.value})})
 s.observe('a',{'value':2});s.outputs['a']['value']=99;s.drain('compute');s.require_complete();return s.outputs['b']['value']

def reentrant():
 calls=[];s=None
 def handler(i):
  calls.append(1)
  if len(calls)==1:s.drain('compute')
  return {'value':1}
 s=make([{'id':'n','handler':'n','phase':'compute'}],{'n':ce.Handler(Empty,Number,'compute',handler)})
 try:s.drain('compute');s.require_complete()
 except ValueError:pass
 return len(calls)

def reset():
 attempts=[]
 def receipt(*args):
  attempts.append(1)
  if len(attempts)==1:raise OSError('controlled receipt failure')
 s=make([{'id':'n','handler':'n','phase':'compute'}],{'n':ce.Handler(Empty,Number,'compute',lambda i:{'value':1})},callback=receipt)
 try:s.drain('compute')
 except OSError:pass
 try:
  s.failed=None;s.drain('compute');s.require_complete();return True
 except (ValueError,AttributeError):return False

def untyped():
 try:
  make([{'id':'n','handler':'n','phase':'verify','criteria':['C1']}],{'n':ce.Handler(Empty,Number,'verify',lambda i:{'value':1})},['C1'])
  return True
 except ValueError:return False

def main():
 a=argparse.ArgumentParser();a.add_argument('--out',required=True);a.add_argument('--arm',required=True);args=a.parse_args()
 rows=[]
 def add(name,observed,expected):rows.append({'case':name,'observed':observed,'expected':expected,'correct':observed==expected})
 add('valid_bound_verdict',verdict({'criterion_id':'C1','satisfied':True})['accepted'],True)
 add('negative_verdict',verdict({'criterion_id':'C1','satisfied':False})['accepted'],False)
 add('wrong_criterion',verdict({'criterion_id':'C2','satisfied':True})['accepted'],False)
 add('truthy_string',verdict({'criterion_id':'C1','satisfied':'true'})['accepted'],False)
 add('invalid_literal_admission',literal(),False)
 add('caller_program_mutation',mutate('input'),5)
 add('inspection_program_mutation',mutate('view'),5)
 add('observed_output_mutation',output_mutation(),2)
 add('reentrant_execution_count',reentrant(),1)
 add('failed_callback_reset',reset(),False)
 add('untyped_verifier_admission',untyped(),False)
 times=[]
 for _ in range(20):assert verdict({'criterion_id':'C1','satisfied':True})['accepted']
 for _ in range(1000):
  start=time.perf_counter_ns();assert verdict({'criterion_id':'C1','satisfied':True})['accepted'];times.append(time.perf_counter_ns()-start)
 ordered=sorted(times)
 d={'arm':args.arm,'scope':'framework deterministic regression/microbenchmark, not model or semantic RCT-7 evaluation','paid_calls':0,'cases':rows,'correct_cases':sum(r['correct'] for r in rows),'total_cases':len(rows),'valid_one_node_microbenchmark':{'samples':len(times),'median_ns':statistics.median(times),'p95_ns':ordered[int(.95*(len(ordered)-1))]},'limitations':['author-written cases, not independent holdout','one-node CPU overhead, not whole-workflow latency','before/after under one machine, no capable model tested']}
 Path(args.out).write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k!='cases'}))
if __name__=='__main__':main()
