"""Durable contract confirmation tests; no provider or paid dispatch."""
import copy

import pytest

from rct_control_plane.intent_contract import IntentContractError, IntentContractStore
from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop


def setup(tmp_path):
    store = IntentContractStore(_loop(tmp_path, 'reviewer')._persistence, 'reviewer')
    binding = {'actor': 'reviewer', 'workspace_root': str(tmp_path.resolve()),
               'policy_sha256': 'a' * 64, 'catalog_sha256': 'b' * 64}
    review = {'schema_version': 1, 'binding': binding, 'proposal': {
        'schema_version': 1, 'material_criteria': [{'id': 'C1', 'statement': 'Return JSON',
        'polarity': 'required', 'source_quotes': ['Return JSON']}], 'constraints': [], 'unknowns': []}}
    contract = store.create('Return JSON', [{'kind': 'json_object'}], tmp_path, intent_review=review)
    confirmation = {k: contract[k] for k in ('version', 'plan_sha256')}
    confirmation['contract_id'] = contract['id']
    return store, contract, binding, confirmation, review


def test_review_survives_reopen_and_exact_confirmation_claims_once(tmp_path):
    store, c, binding, confirmation, review = setup(tmp_path)
    review['proposal']['material_criteria'][0]['statement'] = 'mutated'
    reopened = IntentContractStore(store.db, 'reviewer')
    assert reopened.get(c['id'])['plan']['intent_review']['proposal']['material_criteria'][0]['statement'] == 'Return JSON'
    running = reopened.claim(c['id'], 1, review_binding=binding, intent_confirmation=confirmation)
    assert running['state'] == 'running' and running['version'] == 2
    with pytest.raises(IntentContractError):
        store.claim(c['id'], 1, review_binding=binding, intent_confirmation=confirmation)


@pytest.mark.parametrize('field', ['actor', 'workspace_root', 'policy_sha256', 'catalog_sha256',
                                  'contract_id', 'version', 'plan_sha256', 'missing_binding', 'missing_confirmation', 'bool_version'])
def test_changed_or_missing_bindings_refuse_without_state_change(tmp_path, field):
    store, c, binding, confirmation, _ = setup(tmp_path)
    if field in binding:
        binding[field] = 'c' * 64 if field.endswith('sha256') else 'other'
    elif field == 'missing_binding': binding = None
    elif field == 'missing_confirmation': confirmation = None
    elif field == 'bool_version': confirmation['version'] = True
    else: confirmation[field] = 2 if field == 'version' else 'd' * 64
    with pytest.raises(IntentContractError, match='confirmation refused'):
        store.claim(c['id'], 1, review_binding=binding, intent_confirmation=confirmation)
    assert store.get(c['id']) == c


def test_replanning_cannot_drop_review_requirement(tmp_path):
    store, c, binding, confirmation, _ = setup(tmp_path)
    running = store.claim(c['id'], 1, review_binding=binding, intent_confirmation=confirmation)
    waiting = store.transition(running, 'waiting_for_clarification')
    with pytest.raises(IntentContractError, match='new reviewed contract'):
        store.claim(c['id'], waiting['version'], response='Different intent', revised_goal='New goal')
    assert store.get(c['id']) == waiting


@pytest.mark.parametrize('case', ['wrong_actor', 'wrong_root', 'missing_obligation', 'unknown', 'bool_schema', 'bool_proposal'])
def test_invalid_review_rejected_before_insert(tmp_path, case):
    store, _, _, _, original = setup(tmp_path)
    review = copy.deepcopy(original)
    if case == 'wrong_actor': review['binding']['actor'] = 'other'
    if case == 'wrong_root': review['binding']['workspace_root'] = '/other'
    if case == 'missing_obligation': review['proposal']['material_criteria'][0]['id'] = 'unmatched'
    if case == 'unknown': review['proposal']['unknowns'] = [{'id': 'q', 'question': 'Which JSON?', 'critical': True, 'source_quotes': ['JSON']}]
    if case == 'bool_schema': review['schema_version'] = True
    if case == 'bool_proposal': review['proposal']['schema_version'] = True
    with pytest.raises(ValueError):
        store.create('Return JSON', [{'kind': 'json_object'}], tmp_path, intent_review=review)
    with store.db._connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM intent_contracts').fetchone()[0] == 1


def test_unreviewed_contract_cannot_accept_typed_confirmation(tmp_path):
    store, _, binding, confirmation, _ = setup(tmp_path)
    c = store.create('Return JSON', [{'kind': 'json_object'}], tmp_path)
    with pytest.raises(IntentContractError, match='no typed intent review'):
        store.claim(c['id'], 1, review_binding=binding, intent_confirmation=confirmation)


def test_concurrent_confirmations_have_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    store, c, binding, confirmation, _ = setup(tmp_path)
    barrier = Barrier(2)

    def claim():
        barrier.wait(timeout=10)
        try:
            return store.claim(c['id'], 1, review_binding=binding, intent_confirmation=confirmation)['state']
        except IntentContractError:
            return 'refused'

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sorted(results) == ['refused', 'running']
    assert store.get(c['id'])['version'] == 2


def test_confirmation_invalidated_by_plan_change(tmp_path):
    store, c, binding, confirmation, _ = setup(tmp_path)
    changed = copy.deepcopy(c)
    changed['plan']['intent_review']['proposal']['material_criteria'][0]['statement'] = 'Review revised JSON requirement'
    current = store.transition(changed, 'plan_ready')
    # Even the current version cannot make the old plan digest valid.
    confirmation['version'] = current['version']
    with pytest.raises(IntentContractError, match='confirmation refused'):
        store.claim(c['id'], current['version'], review_binding=binding, intent_confirmation=confirmation)
    assert store.get(c['id']) == current
