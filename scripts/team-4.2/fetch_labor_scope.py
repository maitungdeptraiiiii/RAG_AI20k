"""Fetch the frozen labor-scope queue into immutable staging, without changing CURRENT.

python scripts/team-4.2/fetch_labor_scope.py
Re-runs reuse only checksum-verified successful receipts from the same queue.
No LLM/API key is required. No Contract Graph or bridge files are modified.
"""
from __future__ import annotations

import argparse
import gzip
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app/team-4.2/src'))
from rag.ingest.vbpl import VbplClient, metadata_from_detail
from rag.legal.crawl import document_from_detail
from rag.legal.keys import document_key, normalize_number
from rag.legal.rawfiles import write_text
from rag.legal.store import encode
from rag.legal.text import html_to_legal_text

DEFAULT_LEGAL = ROOT / 'app/team-4.2/data/team-4.2/legal'
DEFAULT_QUEUE = ROOT / 'data/team-4.2/legal/labor-scope-fetch-queue.json'
TYPES = {'luat': 'Luật', 'nghi-dinh': 'Nghị định', 'thong-tu': 'Thông tư', 'nghi-quyet': 'Nghị quyết',
         'quyet-dinh': 'Quyết định'}
SCOPE = 'labor-scope-v1-26'
FALLBACKS = {
    'thong-tu:59/2015/TT-BLĐTBXH': {
        'landing': 'https://congbao.chinhphu.vn/van-ban/thong-tu-so-59-2015-tt-bldtbxh-18869/13409.htm',
        'pdfs': ['https://vanban.bhxhtphcm.gov.vn/bitstream/BHXHTPHCM_123456789/1455/3/tt59-bldtbxh.pdf'],
        'issue_date': '2015-12-29', 'effective_from': '2016-02-15'},
    'nghi-quyet:17/2022/UBTVQH15': {
        'landing': 'https://congbao.chinhphu.vn/van-ban/nghi-quyet-so-17-2022-ubtvqh15-36956/40162.htm',
        'pdfs': ['https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2022/3/36956/40162-1-2022287-28817-2022-ubtvqh15.pdf'],
        'issue_date': '2022-03-23', 'effective_from': '2022-04-01'},
    'nghi-dinh:399/2026/NĐ-CP': {
        'landing': 'https://chinhphu.vn/?classid=1&docid=220166&pageid=27160',
        'pdfs': [
            'https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/11/399_2026_nd-cp_02112026_6-signed.signed.pdf',
            'https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/11/399_2026_nd-cp_02112026_7-signed.pdf'],
        'issue_date': '2026-11-02', 'effective_from': '2027-01-01'},
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def immutable(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Immutable artifact collision')
    else:
        path.write_bytes(data)
    return path


def identity_matches(detail, expected_key):
    meta = metadata_from_detail(detail)
    return (document_key(meta['doc_type'] or '', meta['doc_number'] or '') == expected_key
        and not meta['is_consolidated'])


def checked_get(client, url):
    def request():
        response = client.session.get(url, timeout=client.timeout)
        response.raise_for_status()
        return response
    return client._call(request)


def fetch_pdf_fallback(client, item, legal_dir, staging, detail=None, discovered_via=SCOPE):
    """Explicit official-source fallback, never follow a related document as the target."""
    from datetime import date
    import pymupdf
    from bs4 import BeautifulSoup
    from rag.legal.models import LegalDocument

    key = item['document_key']
    config = FALLBACKS.get(key)
    if not config:
        raise ValueError('No verified PDF fallback configured for ' + key)
    kind, number = key.split(':', 1)
    landing = checked_get(client, config['landing'])
    landing_text = BeautifulSoup(landing.text, 'html.parser').get_text(' ', strip=True)
    if normalize_number(number) not in normalize_number(landing_text):
        raise ValueError('Landing-page identity mismatch')
    html_path = immutable(staging / 'html' / (sha(landing.content) + '.html'), landing.content)
    attachments, texts = [], []
    for index, url in enumerate(config['pdfs']):
        response = checked_get(client, url)
        data = response.content
        if not data.startswith(b'%PDF'):
            raise ValueError('Source did not return a PDF')
        path = immutable(staging / 'binaries' / (sha(data) + '.pdf'), data)
        with pymupdf.open(stream=data, filetype='pdf') as pdf:
            text = '\n'.join(page.get_text() for page in pdf)
            pages = len(pdf)
        if len(text.strip()) < 500:
            raise ValueError('PDF requires OCR; not counted as successful text download')
        text_path, text_checksum = write_text(legal_dir / 'raw', key + f'-pdf-{index}', text)
        attachments.append({'url': url, 'path': path.relative_to(legal_dir).as_posix(),
            'sha256': sha(data), 'pages': pages, 'role': 'body' if index == 0 else 'annex',
            'extracted_text_path': text_path.relative_to(legal_dir).as_posix(),
            'extracted_text_sha256': sha(text_path.read_bytes()),
            'verification_status': 'needs_review'})
        texts.append(text)
    if normalize_number(number) not in normalize_number('\n'.join(texts)):
        raise ValueError('PDF set does not contain the expected document number')
    body = texts[0]
    if not re.search(r'\bĐiều\s+\d+', body):
        raise ValueError('No extractable articles in PDF body')
    raw_path, _ = write_text(legal_dir / 'raw', key, body)
    checksum = sha(raw_path.read_bytes())
    now = datetime.now(timezone.utc)
    if detail is not None:
        if not identity_matches(detail, key):
            raise ValueError('Fallback API metadata identity mismatch')
        doc = document_from_detail(detail, raw_path, body, discovered_via=discovered_via)
        doc = replace(doc, text_source='file', field_sources={'raw_text': {
            'source': 'file', 'at': now.isoformat(), 'detail': config['pdfs'][0]}})
        source_response = detail
        metadata = metadata_from_detail(detail)
        response_format = 'normalized_json_from_official_api'
    else:
        doc = LegalDocument(document_key=key, vbpl_id='', title=item['title'], doc_type=TYPES[kind],
            doc_number=number, issuer=None, issued_on=date.fromisoformat(config['issue_date']),
            vbpl_effective_from=date.fromisoformat(config['effective_from']), vbpl_effective_to=None,
            eff_status=None, is_consolidated=False, raw_text_path=str(raw_path), raw_checksum=checksum,
            fetched_at=now, discovered_via=discovered_via, text_source='file', source_verified=True,
            field_sources={'raw_text': {'source': 'file', 'at': now.isoformat(), 'detail': config['pdfs'][0]}})
        metadata = {'title': item['title'], 'doc_type': TYPES[kind], 'doc_number': number,
            'issue_date': config['issue_date'], 'effective_from': config['effective_from'],
            'effective_to': None, 'effective_status': None, 'source_url': config['landing'],
            'source': 'official_landing_page_and_pdf', 'verification_status': 'needs_review'}
        source_response = metadata
        response_format = 'metadata_receipt_from_official_landing_page'
    response_bytes = (json.dumps(source_response, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
    response_path = immutable(staging / 'responses' / (sha(response_bytes) + '.json'), response_bytes)
    return {'document_key': key, 'status': 'downloaded', 'characters': len(body),
        'metadata': metadata, 'legal_document': encode(doc), 'text_path': raw_path.relative_to(legal_dir).as_posix(),
        'text_sha256': checksum, 'html_path': html_path.relative_to(legal_dir).as_posix(),
        'html_sha256': sha(landing.content), 'html_role': 'official_metadata_landing_page',
        'response_path': response_path.relative_to(legal_dir).as_posix(),
        'response_sha256': sha(response_bytes), 'response_format': response_format,
        'source_format': 'pdf', 'attachments': attachments, 'review_status': 'needs_review_pdf_extraction',
        'annex_status': 'downloaded_not_reviewed' if len(attachments) > 1 else 'not_assessed',
        'import_status': 'staged_not_imported'}


def fetch_one(client, item, legal_dir, staging, discovered_via=SCOPE):
    key = item['document_key']
    kind, number = key.split(':', 1)
    wanted = TYPES[kind]
    candidates = client.search_by_number(number)
    candidates = [i for i in candidates if (
        (i.get('docType') or {}).get('name', '').casefold() == wanted.casefold()
        and normalize_number(i.get('docNum') or '') == normalize_number(number))]
    problems = []
    for item_stub in candidates:
        detail = client.detail(str(item_stub['id']))
        if not identity_matches(detail, key):
            problems.append('detail_identity_mismatch')
            continue
        html = (detail.get('documentContent') or {}).get('content') or ''
        text = html_to_legal_text(html)
        if len(text) < 500 or not re.search(r'\bĐiều\s+\d+', text):
            if key in FALLBACKS:
                return fetch_pdf_fallback(client, item, legal_dir, staging, detail=detail, discovered_via=discovered_via)
            problems.append('empty_or_incomplete_body')
            continue
        # Keep both the source HTML and a normalized JSON response, content addressed.
        detail_bytes = (json.dumps(detail, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
        html_bytes = html.encode('utf-8')
        detail_path = immutable(staging / 'responses' / (sha(detail_bytes) + '.json'), detail_bytes)
        html_path = immutable(staging / 'html' / (sha(html_bytes) + '.html'), html_bytes)
        raw_path, _ = write_text(legal_dir / 'raw', key, text)
        doc = document_from_detail(detail, raw_path, text, discovered_via=discovered_via)
        if doc.document_key != key or sha(raw_path.read_bytes()) != doc.raw_checksum:
            raise ValueError('Saved text identity/checksum mismatch')
        metadata = metadata_from_detail(detail)
        return {'document_key': key, 'status': 'downloaded', 'characters': len(text),
            'metadata': metadata, 'legal_document': encode(doc),
            'text_path': raw_path.relative_to(legal_dir).as_posix(), 'text_sha256': doc.raw_checksum,
            'html_path': html_path.relative_to(legal_dir).as_posix(), 'html_sha256': sha(html_bytes),
            'response_path': detail_path.relative_to(legal_dir).as_posix(), 'response_sha256': sha(detail_bytes),
            'response_format': 'normalized_json_from_official_api',
            'original_pdf_filename': detail.get('documentContentFileName'),
            'original_doc_filename': detail.get('documentContentFileDocName'),
            'review_status': 'downloaded_not_legally_reviewed',
            'annex_status': 'not_assessed', 'import_status': 'staged_not_imported'}
    if not candidates and key in FALLBACKS:
        return fetch_pdf_fallback(client, item, legal_dir, staging, discovered_via=discovered_via)
    raise ValueError(f'No exact typed document with substantial legal text: {key}; candidates={len(candidates)}; {problems}')


def valid_receipt(row, legal_dir):
    if row.get('status') != 'downloaded':
        return False
    for field in ('text', 'html', 'response'):
        p = legal_dir / row[field + '_path']
        if not p.exists() or sha(p.read_bytes()) != row[field + '_sha256']:
            return False
    for attachment in row.get('attachments', []):
        for path_key, hash_key in [('path', 'sha256'), ('extracted_text_path', 'extracted_text_sha256')]:
            p = legal_dir / attachment[path_key]
            if not p.exists() or sha(p.read_bytes()) != attachment[hash_key]:
                return False
    return True


def pack_staging(queue_path=DEFAULT_QUEUE, legal_dir=DEFAULT_LEGAL):
    """Portable supplement only; leave the published corpus bundle/snapshot untouched."""
    legal_dir, queue_path = Path(legal_dir).resolve(), Path(queue_path)
    staging = legal_dir / 'supplements/labor-scope-v1-26'
    report_path = staging / 'fetch-report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    queue = json.loads(queue_path.read_text(encoding='utf-8'))
    expected = {r['document_key'] for r in queue['documents']}
    if report['queue_sha256'] != sha(queue_path.read_bytes()) or set(report['documents']) != expected or report['failures']:
        raise ValueError('Cannot pack incomplete or mismatched queue')
    files = {report_path.relative_to(legal_dir).as_posix(): sha(report_path.read_bytes())}
    for row in report['documents'].values():
        if not valid_receipt(row, legal_dir):
            raise ValueError('Invalid download receipt: ' + row['document_key'])
        for field in ('text', 'html', 'response'):
            files[row[field + '_path']] = row[field + '_sha256']
        for att in row.get('attachments', []):
            files[att['path']] = att['sha256']
            files[att['extracted_text_path']] = att['extracted_text_sha256']
    shared = ROOT / 'data/team-4.2/legal'
    bundle = shared / 'labor-scope-supplement-26.tar.gz'
    with bundle.open('wb') as output, gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w') as tar:
            for rel in sorted(files):
                path = (legal_dir / rel).resolve()
                if not path.is_relative_to(legal_dir) or sha(path.read_bytes()) != files[rel]:
                    raise ValueError('Invalid artifact path/checksum')
                info = tar.gettarinfo(path, arcname=rel)
                info.mtime = info.uid = info.gid = 0
                info.uname = info.gname = ''
                with path.open('rb') as stream:
                    tar.addfile(info, stream)
    manifest = {'artifact': 'labor-scope-supplement-26', 'documents': len(expected),
        'queue_sha256': report['queue_sha256'], 'bundle_sha256': sha(bundle.read_bytes()),
        'files': files, 'import_status': 'staged_not_imported', 'runtime_graph_changed': False}
    atomic_json(shared / 'labor-scope-supplement-26.manifest.json', manifest)
    atomic_json(shared / 'labor-scope-download-report.json', report)
    return {'documents': len(expected), 'files': len(files), 'bundle_bytes': bundle.stat().st_size,
        'bundle_sha256': manifest['bundle_sha256']}


def main(queue_path=DEFAULT_QUEUE, legal_dir=DEFAULT_LEGAL, only=None):
    legal_dir, queue_path = Path(legal_dir), Path(queue_path)
    staging = legal_dir / 'supplements/labor-scope-v1-26'
    staging.mkdir(parents=True, exist_ok=True)
    queue = json.loads(queue_path.read_text(encoding='utf-8'))
    items = queue['documents']
    if len({r['document_key'] for r in items}) != len(items) or queue['count'] != len(items):
        raise ValueError('Invalid or duplicate queue entries')
    report_path = staging / 'fetch-report.json'
    report = {'queue_sha256': sha(queue_path.read_bytes()), 'scope_version': queue['scope_version'],
        'requested': len(items), 'documents': {}, 'failures': {}, 'runtime_graph_changed': False}
    if report_path.exists():
        previous = json.loads(report_path.read_text(encoding='utf-8'))
        if previous['queue_sha256'] != report['queue_sha256']:
            raise ValueError('Queue changed since staging began')
        report = previous
    client = VbplClient(timeout=25, attempts=3, delay=.4)
    current = (legal_dir / 'CURRENT').read_bytes() if (legal_dir / 'CURRENT').exists() else None
    try:
        for item in items:
            key = item['document_key']
            if only and key not in only:
                continue
            if valid_receipt(report['documents'].get(key, {}), legal_dir):
                print(json.dumps({'key': key, 'status': 'cached'}, ensure_ascii=False), flush=True)
                continue
            try:
                row = fetch_one(client, item, legal_dir, staging)
                report['documents'][key] = row
                report['failures'].pop(key, None)
                print(json.dumps({'key': key, 'status': 'downloaded', 'characters': row['characters']}, ensure_ascii=False), flush=True)
            except Exception as exc:
                report['documents'].pop(key, None)
                report['failures'][key] = f'{type(exc).__name__}: {exc}'
                print(json.dumps({'key': key, 'status': 'failed', 'error_type': type(exc).__name__}, ensure_ascii=False), flush=True)
            finally:
                report['updated_at'] = datetime.now(timezone.utc).isoformat()
                report['downloaded'] = len(report['documents'])
                atomic_json(report_path, report)
    finally:
        client.session.close()
    if current is not None and (legal_dir / 'CURRENT').read_bytes() != current:
        raise RuntimeError('CURRENT changed concurrently; staging did not publish a snapshot')
    print(json.dumps({'requested': len(items), 'downloaded': len(report['documents']),
        'failed': len(report['failures']), 'report': str(report_path)}, ensure_ascii=False), flush=True)
    return 0 if len(report['documents']) == len(items) and not report['failures'] else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--queue', type=Path, default=DEFAULT_QUEUE)
    ap.add_argument('--legal-dir', type=Path, default=DEFAULT_LEGAL)
    ap.add_argument('--only', action='append')
    ap.add_argument('--pack-only', action='store_true', help='Verify and package successful staging without network requests')
    args = ap.parse_args()
    if args.pack_only:
        print(json.dumps(pack_staging(args.queue, args.legal_dir), ensure_ascii=False))
    else:
        raise SystemExit(main(args.queue, args.legal_dir, args.only))
