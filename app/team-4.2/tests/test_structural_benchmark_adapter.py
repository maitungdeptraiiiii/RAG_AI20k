"""Offline checks for the read-only structural adapter; no benchmark labels used."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FOLDER = ROOT / 'evals/team-4.2/contract_graph_benchmark'
spec = importlib.util.spec_from_file_location('structural_benchmark_adapter', FOLDER / 'structural_adapter.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class FakeGraph:
    build_id = 'test-build'
    snapshot_id = 'test-snapshot'

    def __init__(self):
        self.text = 'Đoạn căn cứ.'
        self.checksum = 'raw-sha'

    def text_at(self, pid, day):
        return {'in_force': True, 'text': self.text,
            'citation': {'provision_id': pid, 'raw_checksum': self.checksum}}

    def references(self, pid, day, direction='out'):
        return []

    def guidance(self, pid, day):
        return []


@pytest.fixture
def setup(tmp_path):
    p = {'passage_id': 'p1', 'version_key': 'v1', 'provision_id': 'bo-luat:45/2019/QH14#d26',
         'document_key': 'bo-luat:45/2019/QH14', 'text': 'Đoạn căn cứ.', 'start': 0, 'end': 12,
         'valid_from': '2021-01-01', 'valid_to': None, 'raw_checksum': 'raw-sha',
         'verification_status': 'needs_review'}
    p['end'] = len(p['text'])
    path = tmp_path / 'corpus.jsonl'
    path.write_text(json.dumps(p, ensure_ascii=False) + '\n', encoding='utf-8')
    config = json.loads((FOLDER / 'configs/structural-v1.json').read_text(encoding='utf-8'))
    config.update(corpus_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), snapshot_id='test-snapshot')
    case = {'id': 'opaque', 'concepts': [{'id': 'probation.pay'}],
            'context': {'assessment_date': '2025-03-01'}, 'contract_text': 'Ignored by structural.'}
    return path, config, case, FakeGraph()


def test_reads_graph_maps_source_and_reports_quality(setup):
    path, config, case, graph = setup
    retriever = adapter.StructuralRetriever(path, config, graph)
    result = retriever.retrieve(case)
    assert result['evidence'] == ['p1']
    assert result['source_warnings'] == ['needs_review']
    assert result['retrieval_trace'][0]['via'] == 'anchor'
    assert retriever.metadata()['read_only']


@pytest.mark.parametrize('wrong_field', ['text', 'checksum'])
def test_cannot_substitute_corpus_for_mismatching_graph_text(setup, wrong_field):
    path, config, case, graph = setup
    setattr(graph, wrong_field, 'different')
    result = adapter.StructuralRetriever(path, config, graph).retrieve(case)
    assert result['evidence'] == []
    assert result['problems']


def test_snapshot_and_corpus_hash_fail_closed(setup):
    path, config, case, graph = setup
    with pytest.raises(ValueError, match='snapshot'):
        adapter.StructuralRetriever(path, {**config, 'snapshot_id': 'another'}, graph)
    with pytest.raises(ValueError, match='corpus checksum'):
        adapter.StructuralRetriever(path, {**config, 'corpus_sha256': 'wrong'}, graph)


def test_generic_scope_and_date_guards(setup):
    path, config, case, graph = setup
    retriever = adapter.StructuralRetriever(path, config, graph)
    result = retriever.retrieve({**case, 'context': {'contract_type': 'residential_lease'}})
    assert result['decision'] == 'out_of_scope' and not result['evidence']
    result = retriever.retrieve({**case, 'context': {}})
    assert result['decision'] == 'insufficient_context'
    assert result['missing_context'] == ['assessment_date']


def test_unknown_concept_is_visible_and_not_guessed(setup):
    path, config, case, graph = setup
    result = adapter.StructuralRetriever(path, config, graph).retrieve({**case, 'concepts': [{'id': 'not-in-catalog'}]})
    assert not result['evidence']
    assert result['problems'][0]['reason'] == 'unknown_concept'
