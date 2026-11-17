"""Benchmark scoring must catch retrieval failures instead of rewarding gold leakage."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FILE = ROOT / 'evals/team-4.2/contract_graph_benchmark/benchmark.py'
spec = importlib.util.spec_from_file_location('contract_graph_benchmark', FILE)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


@pytest.fixture
def example():
    inp = {'context': {'assessment_date': '2025-03-01'}}
    gold = {'decision': 'ready', 'required_context': [], 'evidence_groups': [
        {'alternatives': [{'version_key': 'v1', 'start': 1, 'end': 8}]},
        {'alternatives': [{'version_key': 'v2', 'start': 0, 'end': 4}]}]}
    corpus = {'a': {'version_key': 'v1', 'start': 0, 'end': 5, 'text': 'abcde',
                   'valid_from': '2021-01-01', 'valid_to': None, 'verification_status': 'verified'},
              'b': {'version_key': 'v1', 'start': 4, 'end': 10, 'text': 'efghij',
                   'valid_from': '2021-01-01', 'valid_to': None, 'verification_status': 'verified'},
              'c': {'version_key': 'v2', 'start': 0, 'end': 6, 'text': 'klmnop',
                   'valid_from': '2021-01-01', 'valid_to': None, 'verification_status': 'verified'}}
    prediction = {'decision': 'ready', 'evidence': ['a', 'b', 'c'], 'missing_context': [], 'source_warnings': []}
    policy = {'max_passages': 20, 'max_evidence_utf8_bytes': 16000}
    return inp, gold, prediction, corpus, policy


def test_complete_multi_evidence_passes(example):
    assert bench.case_score(*example)['passed']


def test_missing_exception_fails(example):
    example[2]['evidence'] = ['a', 'b']
    result = bench.case_score(*example)
    assert not result['passed']
    assert result['coverage'] == .5


def test_partial_span_does_not_pass(example):
    example[2]['evidence'] = ['a', 'c']
    assert 'missing_required_evidence' in bench.case_score(*example)['errors']


def test_wrong_version_same_address_cannot_cover_gold(example):
    example[3]['a']['version_key'] = example[3]['b']['version_key'] = 'other'
    assert not bench.case_score(*example)['passed']


@pytest.mark.parametrize('valid_from,valid_to', [('2025-03-02', None), ('2021-01-01', '2025-03-01')])
def test_half_open_temporal_interval(example, valid_from, valid_to):
    example[3]['c'].update(valid_from=valid_from, valid_to=valid_to)
    assert 'wrong_effective_version' in bench.case_score(*example)['errors']


def test_correct_evidence_plus_inactive_distractor_fails(example):
    example[3]['old'] = {**example[3]['a'], 'valid_to': '2024-01-01'}
    example[2]['evidence'].append('old')
    assert not bench.case_score(*example)['passed']


def test_fake_citation_fails(example):
    example[2]['evidence'].append('nonexistent')
    assert any(e.startswith('unknown_passage:') for e in bench.case_score(*example)['errors'])


def test_duplicate_and_over_budget_fails(example):
    example[2]['evidence'].append('a')
    example[4]['max_passages'] = 3
    example[4]['max_evidence_utf8_bytes'] = 1
    errors = bench.case_score(*example)['errors']
    assert {'duplicate_passages', 'passage_budget_exceeded', 'byte_budget_exceeded'}.issubset(errors)


def test_utf8_byte_budget_not_character_count(example):
    example[3]['a']['text'] = 'ế' * 10
    example[4]['max_evidence_utf8_bytes'] = 30
    assert 'byte_budget_exceeded' in bench.case_score(*example)['errors']


def test_needs_review_must_be_reported(example):
    example[3]['c']['verification_status'] = 'needs_review'
    assert 'unreported_source_quality' in bench.case_score(*example)['errors']
    example[2]['source_warnings'] = ['needs_review']
    assert bench.case_score(*example)['passed']


def test_empty_retrieval_not_automatic_abstention_pass(example):
    example[1].update(decision='insufficient_context', required_context=['assessment_date'], evidence_groups=[])
    example[0]['context'] = {}
    example[2].update(evidence=[], decision='insufficient_context')
    assert not bench.case_score(*example)['passed']
    example[2]['missing_context'] = ['assessment_date']
    assert bench.case_score(*example)['passed']


def test_bad_format_fails_without_losing_score_fields(example):
    example[2]['evidence'] = 'a'
    score = bench.case_score(*example)
    assert not score['passed'] and not score['retrieval_passed']


@pytest.mark.parametrize('field', ['missing_context', 'source_warnings'])
def test_invalid_nested_metadata_is_a_case_failure(example, field):
    example[2][field] = [{'unexpected': 'object'}]
    assert not bench.case_score(*example)['passed']


def test_alternative_source_group_accepts_one_valid_alternative(example):
    example[1]['evidence_groups'][0]['alternatives'].append({'version_key': 'v2', 'start': 0, 'end': 4})
    example[2]['evidence'] = ['c']
    assert bench.case_score(*example)['passed']


def test_compare_rejects_different_corpus_or_split():
    with pytest.raises(ValueError, match='identical benchmark'):
        bench.compare({'manifest_sha256': 'a', 'split': 'test'}, {'manifest_sha256': 'b', 'split': 'test'})


def test_frozen_gold_has_no_public_answer_keys():
    folder = FILE.parent
    inputs = bench.load_jsonl(folder / 'inputs.jsonl')
    gold = bench.load_jsonl(folder / 'gold.jsonl')
    assert len(inputs) == len(gold) >= 60
    assert {r['id'] for r in inputs} == {r['id'] for r in gold}
    families = {}
    for row in inputs:
        assert row['id'].startswith('ce1-') and row['family_id'].startswith('ce1-f')
        assert set(row) == {'id', 'family_id', 'split', 'concepts', 'contract_text', 'context'}
        assert all(set(c) == {'id', 'description'} for c in row['concepts'])
        families.setdefault(row['family_id'], set()).add(row['split'])
    assert all(len(splits) == 1 for splits in families.values())


def test_gold_checksum_change_invalidates_review():
    original = {'id': 'x', 'evidence_groups': []}
    changed = {**original, 'evidence_groups': [{'alternatives': []}]}
    assert bench.digest(bench.json_bytes(original)) != bench.digest(bench.json_bytes(changed))


def test_evaluate_counts_missing_cases_and_rejects_duplicate_ids(tmp_path, monkeypatch, example):
    inp, g, pred, corpus, policy = example
    inp.update(id='ce1-001-01', family_id='ce1-f001', split='test')
    g.update(id=inp['id'], family_id=inp['family_id'], split='test', category='cross_article')
    manifest = {'benchmark': 'test', 'policy': policy}
    monkeypatch.setattr(bench, 'verify', lambda folder: (manifest, [inp], [g], corpus))
    bench.write_json(tmp_path / 'manifest.json', manifest)
    run = bench.make_run(tmp_path, tmp_path / 'run', 'fake', {'name': 'test'}, [])
    result = bench.evaluate(run, tmp_path)
    assert result['summary']['passed'] == 0
    assert 'missing_prediction' in result['cases'][0]['errors']
    assert result['score_status'] == 'provisional_pending_independent_review'
    pred['id'] = inp['id']
    bench.write_jsonl(run.parent / 'predictions.jsonl', [pred, pred])
    with pytest.raises(ValueError, match='Duplicate prediction'):
        bench.evaluate(run, tmp_path)


def test_evaluate_review_is_bound_to_gold_and_latest_decision(tmp_path, monkeypatch, example):
    inp, g, pred, corpus, policy = example
    inp.update(id='ce1-001-01', family_id='ce1-f001', split='test')
    g.update(id=inp['id'], family_id=inp['family_id'], split='test', category='cross_article')
    pred['id'] = inp['id']
    manifest = {'benchmark': 'test', 'policy': policy}
    monkeypatch.setattr(bench, 'verify', lambda folder: (manifest, [inp], [g], corpus))
    bench.write_json(tmp_path / 'manifest.json', manifest)
    run = bench.make_run(tmp_path, tmp_path / 'run', 'fake', {'name': 'test'}, [pred])
    approval = {'id': inp['id'], 'reviewer': 'test reviewer', 'reviewer_type': 'human',
        'reviewed_at': '2026-11-17', 'note': 'fixture only', 'decision': 'approved',
        'gold_sha256': bench.digest(bench.json_bytes(g))}
    bench.write_jsonl(tmp_path / 'reviews.jsonl', [approval])
    assert bench.evaluate(run, tmp_path)['score_status'] == 'human_reviewed'
    bench.write_jsonl(tmp_path / 'reviews.jsonl', [approval, {**approval, 'decision': 'rejected'}])
    assert bench.evaluate(run, tmp_path)['score_status'] == 'provisional_pending_independent_review'
    bench.write_jsonl(tmp_path / 'reviews.jsonl', [{**approval, 'gold_sha256': 'stale'}])
    assert bench.evaluate(run, tmp_path)['score_status'] == 'provisional_pending_independent_review'


def test_verify_rejects_tampered_corpus(tmp_path):
    (tmp_path / 'corpus.generated.jsonl').write_text('tampered', encoding='utf-8')
    bench.write_json(tmp_path / 'manifest.json', {'files': {'corpus.generated.jsonl': bench.digest(b'original')}})
    with pytest.raises(ValueError, match='checksum mismatch'):
        bench.verify(tmp_path)


def test_adapter_receives_only_public_fields_and_records_case_errors(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(FILE.parent))
    adapter_spec = importlib.util.spec_from_file_location('contract_benchmark_runner', FILE.with_name('run_adapter.py'))
    runner = importlib.util.module_from_spec(adapter_spec)
    adapter_spec.loader.exec_module(runner)
    policy = {'max_passages': 20, 'max_evidence_utf8_bytes': 16000}
    monkeypatch.setattr(runner, 'verify', lambda folder: ({'policy': policy}, [], [], {}))
    bench.write_json(tmp_path / 'manifest.json', {'policy': policy})
    public = {'id': 'opaque-1', 'family_id': 'hidden-family', 'split': 'test',
              'concepts': [], 'context': {}, 'contract_text': 'ok'}
    bench.write_jsonl(tmp_path / 'inputs.jsonl', [public, {**public, 'id': 'opaque-2', 'contract_text': 'raise'}])
    config = tmp_path / 'config.json'
    bench.write_json(config, {'system': 'test-fixture', 'closed_file': str(tmp_path / 'closed')})
    adapter = tmp_path / 'adapter.py'
    adapter.write_text('''
from pathlib import Path
def build_retriever(corpus_path, config):
    class Retriever:
        def retrieve(self, case):
            assert set(case) == {'id', 'concepts', 'contract_text', 'context'}
            if case['contract_text'] == 'raise':
                raise RuntimeError('fixture error')
            return {'id': 'cannot-override-id', 'decision': 'ready', 'evidence': [],
                    'missing_context': [], 'source_warnings': []}
        def close(self):
            Path(config['closed_file']).write_text('closed')
    return Retriever()
''', encoding='utf-8')
    run_path = runner.run_adapter(adapter, config, tmp_path / 'output', tmp_path)
    rows = bench.load_jsonl(run_path.parent / 'predictions.jsonl')
    assert rows[0]['id'] == 'opaque-1'
    assert rows[1]['decision'] == 'error' and rows[1]['error_type'] == 'RuntimeError'
    assert all(row['latency_ms'] >= 0 for row in rows)
    assert (tmp_path / 'closed').read_text() == 'closed'
