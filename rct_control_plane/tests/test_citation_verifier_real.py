"""Hand-authored bilingual oracles, not model capability/holdout results."""
import copy
import hashlib
import json

import pytest

from rct_control_plane.citation_verifier import CitationInput, citation_capability, citation_registry, verify_extracts
from rct_control_plane.component_execution import ComponentScheduler, VerificationRejected
from rct_control_plane.intent_conditions import validate_conditioned_program
from rct_control_plane.typed_intent import parse_intent


def payload(text='ราคา 100 บาท\r\nTax included. 🙂'):
    raw = text.encode('utf-8')
    return {'sources': {'sources': [{'source_id': 'doc', 'text': text, 'sha256': hashlib.sha256(raw).hexdigest()}]},
            'report': {'schema_version': '1', 'offset_encoding': 'utf-8-bytes',
                       'extracts': [{'source_id': 'doc', 'start': 0, 'end': len(raw), 'text': text}]},
            'criterion_id': 'C1', 'required_source_ids': ['doc']}


@pytest.mark.parametrize('text', ['ราคา 100 บาท', 'Do not send email.', '  unchanged whitespace\r\n', '🙂 ไทย'])
def test_exact_utf8_extracts_preserve_negation_unicode_and_whitespace(text):
    result = verify_extracts(CitationInput.model_validate(payload(text)))
    assert result['satisfied'] and result['verification_scope'] == 'exact_extractive_citations'


@pytest.mark.parametrize('mutation,reason', [
    ('number','citation_span_mismatch'), ('negation','citation_span_mismatch'),
    ('hash','source_digest_mismatch'), ('duplicate_source','duplicate_source_identity'),
    ('duplicate_extract','duplicate_extract'), ('unknown','unknown_citation_source'),
    ('offset','citation_span_mismatch'), ('overflow','citation_span_mismatch'),
    ('omit','source_set_mismatch'), ('duplicate_required','invalid_required_sources')])
def test_faults_are_not_accepted(mutation, reason):
    value = payload('Do not send 100 THB.')
    item = value['report']['extracts'][0]
    if mutation == 'number': item['text'] = item['text'].replace('100', '900')
    if mutation == 'negation': item['text'] = item['text'].replace('not ', '')
    if mutation == 'hash': value['sources']['sources'][0]['sha256'] = '0'*64
    if mutation == 'duplicate_source': value['sources']['sources'] *= 2
    if mutation == 'duplicate_extract': value['report']['extracts'] *= 2
    if mutation == 'unknown': item['source_id'] = 'other'
    if mutation == 'offset': item['start'] = 1
    if mutation == 'overflow': item['end'] += 1
    if mutation == 'omit': value['required_source_ids'].append('second')
    if mutation == 'duplicate_required': value['required_source_ids'] *= 2
    result = verify_extracts(CitationInput.model_validate(value))
    assert not result['satisfied'] and reason in result['reasons']


def test_every_required_document_needs_a_valid_citation():
    value = payload()
    value['sources']['sources'].append({**value['sources']['sources'][0], 'source_id': 'second'})
    value['required_source_ids'].append('second')
    assert 'required_source_not_cited' in verify_extracts(CitationInput.model_validate(value))['reasons']
    value['report']['extracts'].append({**value['report']['extracts'][0], 'source_id': 'second'})
    assert verify_extracts(CitationInput.model_validate(value))['satisfied']


def test_python_character_offset_is_not_a_utf8_byte_offset():
    value = payload('ไทย')
    value['report']['extracts'][0]['end'] = len('ไทย')
    assert not verify_extracts(CitationInput.model_validate(value))['satisfied']


@pytest.mark.parametrize('field,value', [('start', True), ('end', -1), ('text', '')])
def test_invalid_extract_schema(field, value):
    data = payload()
    data['report']['extracts'][0][field] = value
    with pytest.raises(ValueError): CitationInput.model_validate(data)


@pytest.mark.parametrize('tampered', [False, True])
def test_registry_runs_through_existing_scheduler_and_rejects_false_receipt(tampered):
    data = payload()
    if tampered: data['report']['extracts'][0]['text'] = 'invented'
    parameters = {k: v for k, v in data.items() if k != 'sources'}
    program = {'schema_version': 1, 'nodes': [
        {'id': 'read', 'handler': 'observed_texts_v1', 'phase': 'observation'},
        {'id': 'verify', 'handler': 'verify_extracts_v1', 'phase': 'verify', 'depends_on': ['read'],
         'inputs': {'sources': 'read'}, 'parameters': parameters, 'criteria': ['C1']}]}
    intent = parse_intent('Extract citations', json.dumps({'schema_version': 1, 'material_criteria': [
        {'id': 'C1', 'statement': 'Extract citations', 'polarity': 'required', 'source_quotes': ['Extract citations']}]}))
    validate_conditioned_program(intent, program, citation_registry(), {}, {'C1': citation_capability()})
    receipts = []
    scheduler = ComponentScheduler(program, citation_registry(), {'C1'}, {}, lambda key, result: receipts.append((key, result)))
    scheduler.observe('read', copy.deepcopy(data['sources']))
    if tampered:
        with pytest.raises(VerificationRejected): scheduler.drain('verify')
        assert [r[0] for r in receipts] == ['read']
        with pytest.raises(ValueError): scheduler.require_complete()
    else:
        scheduler.drain('verify')
        scheduler.require_complete()
        assert [r[0] for r in receipts] == ['read', 'verify']


def test_exact_fragment_does_not_claim_semantic_entailment():
    data = payload('The amount is not 100 THB.')
    raw = data['sources']['sources'][0]['text'].encode('utf-8')
    start = raw.index(b'100 THB')
    data['report']['extracts'][0].update(start=start, end=start+7, text='100 THB')
    verdict = verify_extracts(CitationInput.model_validate(data))
    assert verdict['satisfied']
    assert verdict['verification_scope'] == 'exact_extractive_citations'
    # This is a correct span, NOT evidence that the amount actually is 100 THB.


def test_bilingual_subspan_uses_byte_offsets():
    data = payload('ราคา: 100 บาท 🙂')
    raw = data['sources']['sources'][0]['text'].encode('utf-8')
    quote = '100 บาท'
    start = raw.index(quote.encode('utf-8'))
    data['report']['extracts'][0].update(start=start, end=start+len(quote.encode('utf-8')), text=quote)
    assert verify_extracts(CitationInput.model_validate(data))['satisfied']


def test_freeform_summary_cannot_hide_outside_verified_extracts():
    data = payload()
    data['report']['summary'] = 'Unsupported invented conclusion'
    with pytest.raises(ValueError): CitationInput.model_validate(data)
