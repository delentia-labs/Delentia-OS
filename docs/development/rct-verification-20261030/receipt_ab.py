import os,tempfile,json,asyncio,copy,argparse
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);parser.add_argument('--arm',required=True);args=parser.parse_args()
with tempfile.TemporaryDirectory() as td:
 root=Path(td);os.environ['DELENTIA_HOME']=str(root/'home');os.environ['DELENTIA_RCT7_JUDGE']='off';os.environ['DELENTIA_RCT7_CHAIN']='off'
 from rct_control_plane import autonomous_loop,mcp_server
 from rct_control_plane.tests.test_verified_budget_real import setup
 from rct_control_plane.verified_budget import validate_receipts,digest,BudgetPipeline
 from rct_control_plane.intent_contract import IntentContractStore
 async def no_model(*a,**k):raise AssertionError('generation forbidden')
 autonomous_loop.decide_next_action=no_model
 world=root/'workspace';world.mkdir();mcp_server.REPO_ROOT=world
 loop,context,criteria=setup(root,world)
 prepared=asyncio.run(loop.run('Compare within budget',acceptance_criteria=criteria,planning_context=context));c=prepared['intent_contract']
 assert prepared['stopped_reason']=='plan_ready' and not prepared['steps']
 result=asyncio.run(loop.continue_intent(c['id'],c['version']));contract=result['intent_contract'];assert contract['state']=='criteria_satisfied'
 cases=[]
 def accepted(receipts):
  try:validate_receipts(contract['plan'],contract['id'],'verified',receipts);return True
  except ValueError:return False
 def rehash(rs):
  previous='0'*64
  for r in rs:
   r['previous_sha256']=previous;r['output_sha256']=digest(r['output']);r['receipt_sha256']=digest({k:v for k,v in r.items() if k!='receipt_sha256'});previous=r['receipt_sha256']
 cases.append({'case':'valid_history','accepted':accepted(contract['execution_receipts']),'expected':True})
 for change in ('false_verdict','wrong_criterion','wrong_total','wrong_remainder','wrong_composed_report','wrong_source'):
  rs=copy.deepcopy(contract['execution_receipts']);by={r['component_id']:r['output'] for r in rs}
  if change=='false_verdict':by['check_C1']['satisfied']=False
  elif change=='wrong_criterion':by['check_C1']['criterion_id']='C999'
  elif change=='wrong_total':by['compare_budget']['quote_total']='0.00'
  elif change=='wrong_remainder':by['compare_budget']['remaining']='999999.00'
  elif change=='wrong_composed_report':by['compose_answer']['within_budget']=False
  else:by['inspect_sources']['relative_path']='other.json'
  rehash(rs);cases.append({'case':change,'accepted':accepted(rs),'expected':False})
 data={'arm':args.arm,'scope':'author-written deterministic receipt consistency checks; not capable-model evaluation or proof of source truth','paid_calls':0,'cases':cases,'correct_cases':sum(c['accepted']==c['expected'] for c in cases),'total_cases':len(cases)}
 Path(args.out).write_text(json.dumps(data,indent=2)+'\n')
 print(json.dumps({'arm':args.arm,'correct_cases':data['correct_cases'],'total_cases':len(cases),'paid_calls':0}))
