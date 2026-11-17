"""Guard source identity and immutable receipts for the 26-document crawl."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('fetch_labor_scope', ROOT / 'scripts/team-4.2/fetch_labor_scope.py')
crawl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crawl)


def detail(number='12/2025/TT-BNV', doc_type='Thông tư', body=None):
    return {'id': '179089', 'docNum': number, 'docType': {'name': doc_type},
        'title': 'test', 'documentContent': {'content': body or '<p>Điều 1. Phạm vi</p><p>' + 'Nội dung pháp luật. ' * 50 + '</p>'},
        'isConsolidatedDocument': False}


def test_identity_rejects_related_wrong_document_and_type():
    key = 'thong-tu:12/2025/TT-BNV'
    assert crawl.identity_matches(detail(), key)
    assert not crawl.identity_matches(detail('59/2015/TT-BLĐTBXH'), key)
    assert not crawl.identity_matches(detail(doc_type='Nghị định'), key)
    d = detail(); d['isConsolidatedDocument'] = True
    assert not crawl.identity_matches(d, key)


def test_download_receipt_checksum_detects_tampering(tmp_path):
    row = {'status': 'downloaded'}
    for field in ('text', 'html', 'response'):
        p = tmp_path / field; p.write_bytes(field.encode())
        row[field + '_path'] = field
        row[field + '_sha256'] = crawl.sha(p.read_bytes())
    assert crawl.valid_receipt(row, tmp_path)
    (tmp_path / 'text').write_bytes(b'changed')
    assert not crawl.valid_receipt(row, tmp_path)


def test_immutable_cannot_overwrite_source(tmp_path):
    p = tmp_path / 'source'
    crawl.immutable(p, b'original')
    crawl.immutable(p, b'original')
    with pytest.raises(ValueError, match='collision'):
        crawl.immutable(p, b'changed')


def test_fetch_exact_typed_body_and_roundtrip_receipt(tmp_path):
    d = detail()
    class Client:
        def search_by_number(self, number):
            return [d, detail(doc_type='Nghị định')]
        def detail(self, doc_id):
            return d
    staging = tmp_path / 'supplements/test'
    row = crawl.fetch_one(Client(), {'document_key': 'thong-tu:12/2025/TT-BNV'}, tmp_path, staging)
    assert row['metadata']['doc_number'] == '12/2025/TT-BNV'
    assert row['import_status'] == 'staged_not_imported'
    assert crawl.valid_receipt(row, tmp_path)


def test_fallback_only_when_explicit_identity_configured(tmp_path):
    class Client:
        def search_by_number(self, number):
            return []
    with pytest.raises(ValueError, match='No exact typed document'):
        crawl.fetch_one(Client(), {'document_key': 'thong-tu:999/2025/TT-BNV'}, tmp_path, tmp_path / 'stage')
