"""Bounded budget jobs: reviewed contract reservation, not a general agent API."""
from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import HTTPException, Request

from rct_control_plane.contract_execution_guard import execution_guard
from rct_control_plane.intent_contract import IntentContractError, IntentContractStore
from rct_control_plane.jobs import JobError, JobService
from rct_control_plane.rct_plan import PlanItem
from rct_control_plane.readonly_service import ConfirmRequest, PublicContract, ROUTE, public_result
from rct_control_plane.verified_budget import digest

SCHEMA = """
CREATE TABLE IF NOT EXISTS readonly_budget_jobs (
 namespace TEXT NOT NULL, contract_id TEXT NOT NULL, review_version INTEGER NOT NULL,
 plan_sha256 TEXT NOT NULL, policy_sha256 TEXT NOT NULL, claimed_version INTEGER NOT NULL,
 job_id TEXT NOT NULL UNIQUE, PRIMARY KEY(namespace,contract_id,review_version)
);
"""


class BudgetJobResult(PlanItem):
    schema_version: Literal['1'] = '1'
    job_id: str
    status: Literal['queued', 'running', 'done', 'failed', 'cancelled', 'interrupted']
    task_outcome: str
    cancel_requested: bool
    verified: bool
    contract: PublicContract


def model_free_loop(loop):
    """Reject auxiliary execution/model paths without bypassing owner policy."""
    active_policy = loop._active_policy
    get_pipeline = loop._get_pipeline
    def policy():
        value, error = active_policy()
        if error or (value is not None and (value.jury_by_risk or any(rule.jury_tier for rule in value.rules))):
            raise IntentContractError('model-enabled jury is incompatible with this bounded profile')
        return value, error
    def pipeline():
        value = get_pipeline()
        if value is not None:
            raise IntentContractError('auxiliary pipeline is incompatible with this bounded profile')
        return value
    loop._active_policy = policy
    loop._get_pipeline = pipeline
    policy()
    pipeline()
    return loop



class BudgetJobs:
    def __init__(self, actor, policy, loop_factory, check_actor, authorized_contract):
        self.actor, self.policy, self.factory = actor, policy, loop_factory
        self.check_actor, self.authorized_contract = check_actor, authorized_contract
        loop = loop_factory(actor)
        self.store = IntentContractStore(loop._persistence, actor)
        self.db = loop._persistence
        with self.db._connect() as conn:
            conn.executescript(SCHEMA)
        self.jobs = JobService(self.db, self.run)

    def safe_loop(self):
        return model_free_loop(self.factory(self.actor))

    def binding(self, *, job_id=None, contract_id=None, review_version=None):
        with self.db._connect() as conn:
            if job_id is not None:
                row = conn.execute('SELECT contract_id,review_version,plan_sha256,policy_sha256,claimed_version,job_id '
                    'FROM readonly_budget_jobs WHERE namespace=? AND job_id=?', (self.actor, job_id)).fetchone()
            else:
                row = conn.execute('SELECT contract_id,review_version,plan_sha256,policy_sha256,claimed_version,job_id '
                    'FROM readonly_budget_jobs WHERE namespace=? AND contract_id=? AND review_version=?',
                    (self.actor, contract_id, review_version)).fetchone()
        if row is None:
            raise HTTPException(404, 'bound job not found')
        return dict(zip(('contract_id', 'review_version', 'plan_sha256', 'policy_sha256', 'claimed_version', 'job_id'), row, strict=True))

    def guard(self, conn, contract, binding):
        self.check_actor(self.actor)
        if (contract['id'] != binding['contract_id'] or contract['plan_sha256'] != binding['plan_sha256']
                or binding['policy_sha256'] != digest(self.policy.model_dump())):
            raise IntentContractError('bound execution changed')
        row = conn.execute("SELECT 1 FROM agent_job_owners o JOIN agent_jobs j ON j.id=o.job_id "
            "WHERE o.job_id=? AND o.token=? AND o.lease_until>? AND o.cancel_requested=0 "
            "AND j.namespace=? AND j.status='running'",
            (binding['job_id'], self.jobs._ownership.token, self.jobs._ownership.clock(), self.actor)).fetchone()
        if row is None:
            raise asyncio.CancelledError()

    async def run(self, namespace, goal, max_iterations, max_seconds, on_step):
        if namespace != self.actor:
            raise IntentContractError('job actor mismatch')
        request = json.loads(goal)
        binding = self.binding(contract_id=request['contract_id'], review_version=request['version'])
        if request['plan_sha256'] != binding['plan_sha256']:
            raise IntentContractError('job plan mismatch')
        self.check_actor(namespace)
        contract = self.authorized_contract(self.store, binding['contract_id'], namespace)
        if contract['version'] != binding['claimed_version'] or contract['state'] != 'running':
            raise IntentContractError('bound job cannot replay a progressed contract')
        loop = self.safe_loop()
        original_mcp = loop._mcp
        owner = self
        class ReadOnlyMCP:
            def __getattr__(self, name):
                return getattr(original_mcp, name)
            async def call_tool(self, name, arguments):
                evidence = contract['plan']['semantic_planning']['quote_evidence']
                if (name != 'delentia_read_repo_file' or arguments.get('relative_path') != evidence['relative_path']
                        or arguments.get('verified_read') is not True):
                    raise IntentContractError('operation outside bounded read-only job')
                with owner.db._connect() as conn:
                    owner.guard(conn, contract, binding)
                return await original_mcp.call_tool(name, arguments)
        loop._mcp = ReadOnlyMCP()
        token = execution_guard.set(lambda conn, data, state: self.guard(conn, data, binding))
        try:
            return await loop.run(contract['goal'], intent_contract=contract, on_step=on_step)
        finally:
            execution_guard.reset(token)

    def submit(self, contract, payload):
        try:
            self.safe_loop()
        except IntentContractError:
            raise HTTPException(409, 'host model configuration is incompatible with bounded execution') from None
        if payload.plan_sha256 != contract['plan_sha256']:
            raise HTTPException(409, 'plan digest changed')
        policy_hash = digest(self.policy.model_dump())
        def admit(conn, job_id):
            prior = conn.execute('SELECT job_id,plan_sha256,policy_sha256 FROM readonly_budget_jobs '
                'WHERE namespace=? AND contract_id=? AND review_version=?',
                (self.actor, contract['id'], payload.version)).fetchone()
            if prior is not None:
                if prior[1:] != (payload.plan_sha256, policy_hash):
                    raise IntentContractError('job binding changed')
                return prior[0]
            if contract['state'] != 'plan_ready' or contract['version'] != payload.version:
                raise IntentContractError('confirm the current plan version')
            claimed = self.store.transition(contract, 'running', connection=conn)
            conn.execute('INSERT INTO readonly_budget_jobs VALUES (?,?,?,?,?,?,?)',
                (self.actor, contract['id'], payload.version, payload.plan_sha256, policy_hash, claimed['version'], job_id))
            return None
        goal = json.dumps({'contract_id': contract['id'], 'version': payload.version, 'plan_sha256': payload.plan_sha256}, sort_keys=True)
        try:
            return self.jobs.submit(self.actor, goal, _admit=admit)
        except IntentContractError:
            raise HTTPException(409, 'contract/job admission changed') from None
        except JobError:
            raise HTTPException(429, 'job admission limit reached') from None

    def result(self, job_id):
        self.check_actor(self.actor)
        binding = self.binding(job_id=job_id)
        job = self.jobs.get(job_id, self.actor)
        if job is None:
            raise HTTPException(404, 'bound job not found')
        contract = self.authorized_contract(self.store, binding['contract_id'], self.actor)
        if (job['status'] in {'cancelled', 'failed', 'interrupted'} and contract['state'] == 'running'
                and contract['plan_sha256'] == binding['plan_sha256']):
            try:
                contract = self.store.transition(contract, 'interrupted')
            except IntentContractError:
                contract = self.authorized_contract(self.store, binding['contract_id'], self.actor)
        public = public_result(contract, self.actor, self.policy).contract
        return BudgetJobResult(job_id=job_id, status=job['status'], task_outcome=job['task_outcome'],
            cancel_requested=job['cancel_requested'], verified=job['status'] == 'done' and job['task_outcome'] == 'verified' and public.verified,
            contract=public)


def install_jobs(app, policy, loop_factory, check_actor, authorized_contract):
    app.state.readonly_job_services = {}
    def service(request):
        actor = check_actor(getattr(request.state, 'delentia_user', None))
        if actor not in app.state.readonly_job_services:
            app.state.readonly_job_services[actor] = BudgetJobs(actor, policy, loop_factory, check_actor, authorized_contract)
        return app.state.readonly_job_services[actor]

    @app.post(ROUTE + '/{contract_id}/jobs', response_model=BudgetJobResult, status_code=202)
    async def submit(contract_id: str, payload: ConfirmRequest, request: Request):
        from rct_control_plane.verified_budget import supports_verified_reads
        if not supports_verified_reads():
            raise HTTPException(501, 'verified backend unsupported')
        jobs = service(request)
        contract = authorized_contract(jobs.store, contract_id, jobs.actor)
        job = jobs.submit(contract, payload)
        return jobs.result(job['id'])

    @app.get(ROUTE + '/jobs/{job_id}', response_model=BudgetJobResult)
    async def status(job_id: str, request: Request):
        return service(request).result(job_id)

    @app.delete(ROUTE + '/jobs/{job_id}', response_model=BudgetJobResult)
    async def cancel(job_id: str, request: Request):
        jobs = service(request)
        jobs.result(job_id)  # authorize binding/contract before cancellation
        jobs.jobs.cancel(job_id, jobs.actor)
        return jobs.result(job_id)
