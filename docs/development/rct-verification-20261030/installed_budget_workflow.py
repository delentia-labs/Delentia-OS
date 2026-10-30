"""Installed wheel HTTP contract/restart probe, no generation or paid API."""
import tempfile,os,json,hashlib,sys,argparse
from pathlib import Path
args=argparse.ArgumentParser();args.add_argument('--out',required=True);a=args.parse_args()
with tempfile.TemporaryDirectory() as td:
 root=Path(td);os.environ['DELENTIA_HOME']=str(root/'home')
 os.environ['DELENTIA_RCT7_JUDGE']='off';os.environ['DELENTIA_RCT7_CHAIN']='off'
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 from rct_control_plane import api_tokens,mcp_server,autonomous_loop,component_execution
 from rct_control_plane.api_auth import ApiTokenMiddleware
 from rct_control_plane.readonly_service import ROUTE,ReadOnlyBoundary,install_route,load_policy
 from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
 from rct_control_plane.persistence import ControlPlanePersistence
 from rct_control_plane.skill_library import SkillLibrary
 from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
 from rct_control_plane.intent_contract import IntentContractStore
 assert str(Path(component_execution.__file__)).startswith(str(Path(sys.prefix)))
 async def forbidden(*a,**k):raise AssertionError('generation forbidden')
 autonomous_loop.decide_next_action=forbidden
 workspace=root/'workspace';workspace.mkdir();raw=b'{"schema_version":1,"total":"0.10","currency":"THB","total_is_final":true}'
 (workspace/'quote.json').write_bytes(raw);mcp_server.REPO_ROOT=workspace
 tokens=root/'tokens.json';tokens.write_text(json.dumps({'users':[{'name':'alice','token_sha256':api_tokens.hash_token('probe-token')}]}),encoding='utf-8')
 os.environ['DELENTIA_API_TOKENS_FILE']=str(tokens);os.environ.pop('DELENTIA_API_TOKEN',None)
 p=root/'policy.json';p.write_text(json.dumps({'schema_version':'1','workspace_id':'local','workspace_root':str(workspace),'actor_files':{'alice':['quote.json']}}),encoding='utf-8');os.environ['DELENTIA_READONLY_POLICY']=str(p)
 policy=load_policy();kernel=AlgorithmKernel41()
 def factory(actor):
  return GovernedAutonomousLoop(mcp_server=mcp_server.mcp,persistence=ControlPlanePersistence(db_path=str(root/(actor+'.db'))),kernel=kernel,skill_library=SkillLibrary(db_path=str(root/(actor+'_skills.db'))),max_iterations=5,namespace=actor)
 def client():
  app=FastAPI();install_route(app,policy,factory);app.add_middleware(ApiTokenMiddleware);app.add_middleware(ReadOnlyBoundary,policy=policy);return TestClient(app)
 c=client();headers={'Authorization':'Bearer probe-token'};body={'schema_version':'1','executor_version':'verified_budget_v1','workspace_id':'local','budget':'0.30 THB','evidence':{'relative_path':'quote.json','sha256':hashlib.sha256(raw).hexdigest()}}
 planned=c.post(ROUTE,headers=headers,json=body);assert planned.status_code==200,planned.text
 plan=planned.json()['contract'];assert plan['state']=='plan_ready' and not plan['verified'] and not plan['receipts']
 done=c.post(ROUTE+'/'+plan['id']+'/confirm',headers=headers,json={'schema_version':'1','version':plan['version'],'plan_sha256':plan['plan_sha256']});assert done.status_code==200,done.text
 contract=done.json()['contract'];assert contract['verified'] and contract['report']['remaining']=='0.20'
 reopened=client().get(ROUTE+'/'+plan['id'],headers=headers);assert reopened.status_code==200 and reopened.json()['contract']['verified']
 assert c.get(ROUTE+'/'+plan['id']).status_code==401
 store=IntentContractStore(factory('alice')._persistence,'alice');bad=store.get(plan['id']);bad.pop('execution_receipts');store.transition(bad,'criteria_satisfied')
 assert client().get(ROUTE+'/'+plan['id'],headers=headers).status_code==404
 result={'installed_module':str(component_execution.__file__),'python':sys.version,'checks':{'plan_before_execute':True,'confirmed_exact_arithmetic':True,'reopened_app_status':True,'anonymous_status_refused':True,'missing_receipts_refused':True},'paid_calls':0,'limitations':['deterministic budget workflow, not capable-model evaluation','reopened application/factory, not OS process crash test']}
 Path(a.out).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
