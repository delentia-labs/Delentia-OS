"""HTTP status must not label a mismatched stored report verified."""
from rct_control_plane.intent_contract import IntentContractStore
from rct_control_plane.readonly_service import ROUTE
from rct_control_plane.tests.test_readonly_service_real import service as _service, post
from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop

base_service = _service


def test_http_status_refuses_report_that_disagrees_with_valid_receipts(base_service, tmp_path):
    client, body, _, _ = base_service
    plan = post(client, body).json()['contract']
    headers = {'Authorization': 'Bearer alice-token'}
    done = client.post(ROUTE + '/' + plan['id'] + '/confirm', headers=headers,
                      json={'schema_version': '1', 'version': plan['version'], 'plan_sha256': plan['plan_sha256']})
    assert done.status_code == 200 and done.json()['contract']['verified']
    store = IntentContractStore(_loop(tmp_path, 'alice')._persistence, 'alice')
    contract = store.get(plan['id'])
    contract['execution_report']['quote_total'] = '999.00'
    # Controlled internal-state inconsistency; no public write/import API is used.
    store.transition(contract, 'criteria_satisfied')
    response = client.get(ROUTE + '/' + plan['id'], headers=headers)
    assert response.status_code == 404
    assert 'verified' not in response.json()
