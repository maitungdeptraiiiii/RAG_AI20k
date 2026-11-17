"""Evidence retrieval benchmark for employment-contract analysis. No graph/bridge writes."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sqlite3
import statistics
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEFAULT_LEGAL = ROOT / 'app/team-4.2/data/team-4.2/legal'
VERSION = 'contract-evidence-v1.0-draft'
MAX_BYTES = 16000
MAX_PASSAGES = 20


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def write_jsonl(path, values):
    Path(path).write_bytes(b''.join(json_bytes(value) for value in values))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def live(row, day):
    return row['valid_from'] <= day and (row['valid_to'] is None or day < row['valid_to'])


def source_text(legal_dir, doc):
    path = Path(doc['raw_text_path'])
    if not path.exists():
        path = legal_dir / 'raw' / path.name
    raw = path.read_bytes()
    if digest(raw) != doc['raw_checksum']:
        raise ValueError(f"Raw source checksum mismatch: {doc['document_key']}")
    return raw.decode('utf-8')


def prepare(legal_dir=DEFAULT_LEGAL, folder=HERE, rebuild=False):
    """Freeze source data; never derive gold from the output of a tested retriever."""
    folder, legal_dir = Path(folder), Path(legal_dir)
    seeds = json.loads((folder / 'seeds.json').read_text(encoding='utf-8'))
    frozen = folder / 'manifest.json'
    snapshot_id = (json.loads(frozen.read_text(encoding='utf-8'))['snapshot_id']
        if frozen.exists() and not rebuild else (legal_dir / 'CURRENT').read_text().strip())
    # Use SQLite read-only: preparing an eval cannot change the corpus snapshot.
    path = legal_dir / 'snapshots' / snapshot_id / 'catalog.sqlite'
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as conn:
        docs = {json.loads(row[0])['document_key']: json.loads(row[0])
                for row in conn.execute('SELECT payload FROM documents')}
        latest = {row[0]: row[1] for row in conn.execute(
            'SELECT document_key, build_id FROM builds WHERE seq IN '
            '(SELECT MAX(seq) FROM builds GROUP BY document_key)')}
        versions = []
        for key in seeds['corpus_documents']:
            if key not in docs or key not in latest:
                raise ValueError(f'Missing corpus document/build: {key}')
            versions.extend(json.loads(row[0]) for row in conn.execute(
                'SELECT payload FROM versions WHERE document_key=? AND build_id=?', (key, latest[key]))
                if json.loads(row[0])['kind'] == 'article')
    versions.sort(key=lambda row: (row['provision_id'], row['valid_from']))
    passages, by_pid, raw_sources = [], defaultdict(list), {}
    for key in seeds['corpus_documents']:
        raw_sources[key] = source_text(legal_dir, docs[key])
    for v in versions:
        text = v['text']
        vid = digest(json_bytes([v['provision_id'], v['valid_from'], v['valid_to'], text]))[:24]
        v['version_key'] = vid
        by_pid[v['provision_id']].append(v)
        doc = docs[v['document_key']]
        url = doc.get('field_sources', {}).get('raw_text', {}).get('detail') or (
            'https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=' + doc['vbpl_id'])
        start = 0
        while start < len(text):
            end = min(start + 800, len(text))
            # Break at whitespace, so retrieval chunks do not split a word.
            if end < len(text):
                boundary = text.rfind(' ', start + 600, end)
                if boundary > start:
                    end = boundary
            passages.append({'passage_id': f'{vid}:{start}:{end}', 'version_key': vid,
                'provision_id': v['provision_id'], 'document_key': v['document_key'],
                'start': start, 'end': end, 'text': text[start:end],
                'valid_from': v['valid_from'], 'valid_to': v['valid_to'],
                'verification_status': v['verification_status'],
                'source_url': url, 'raw_checksum': doc['raw_checksum']})
            if end == len(text):
                break
            start = end - 120
    inputs, gold = [], []
    for fi, family in enumerate(seeds['families'], 1):
        for vi, variant in enumerate(family['variants'], 1):
            # Opaque public identifiers: names such as "missing-date" would leak the expected decision.
            cid, fid = f'ce1-{fi:03d}-{vi:02d}', f'ce1-f{fi:03d}'
            context = {**family.get('context', {}), **variant.get('context', {})}
            inp = {'id': cid, 'family_id': fid, 'split': family['split'],
                'concepts': family['concepts'], 'contract_text': variant['contract_text'],
                'context': context}
            groups = []
            for i, group in enumerate(variant.get('evidence', family.get('evidence', []))):
                alternatives = []
                for selector in group:
                    day = context.get('assessment_date')
                    date.fromisoformat(day)  # Evidence cases must specify the relevant event date.
                    hits = [v for v in by_pid[selector['pid']] if live(v, day)]
                    if len(hits) != 1:
                        raise ValueError(f'{cid}: ambiguous/missing version: {selector["pid"]}')
                    v = hits[0]
                    quote = selector['quote']
                    if v['text'].count(quote) != 1:
                        raise ValueError(f'{cid}: quote not unique in version: {quote}')
                    raw = raw_sources[v['document_key']]
                    # Whitespace-only normalization for independent original-source cross-check.
                    if ' '.join(quote.split()) not in ' '.join(raw.split()):
                        raise ValueError(f'{cid}: quote absent from immutable original source')
                    start = v['text'].index(quote)
                    alternatives.append({'provision_id': v['provision_id'],
                        'version_key': v['version_key'], 'start': start, 'end': start + len(quote),
                        'quote': quote, 'source_url': next(p['source_url'] for p in passages
                            if p['version_key'] == v['version_key']),
                        'raw_checksum': docs[v['document_key']]['raw_checksum'],
                        'verification_status': v['verification_status'],
                        'original_source_quote_checked': True})
                groups.append({'group_id': str(i + 1), 'alternatives': alternatives})
            gold.append({'id': cid, 'family_id': fid, 'authoring_family': family['family_id'], 'split': family['split'],
                'category': family['category'], 'decision': variant.get('decision', family.get('decision', 'ready')),
                'required_context': variant.get('required_context', family.get('required_context', [])),
                'evidence_groups': groups, 'rationale': family['rationale'],
                'annotation_status': 'source_checked_draft',
                'review_note': 'Authored and source-cross-checked by coding assistant; independent human review pending.'})
            inputs.append(inp)
    blobs = {'corpus.generated.jsonl': b''.join(map(json_bytes, passages)),
             'inputs.jsonl': b''.join(map(json_bytes, inputs)), 'gold.jsonl': b''.join(map(json_bytes, gold))}
    manifest = {'benchmark': VERSION, 'snapshot_id': snapshot_id,
        'source_bundle_sha256': json.loads((ROOT / 'data/team-4.2/legal/corpus-manifest.json').read_text())['bundle_sha256'],
        'seed_sha256': digest((folder / 'seeds.json').read_bytes()),
        'files': {name: digest(blob) for name, blob in blobs.items()},
        'corpus_documents': seeds['corpus_documents'], 'counts': {'cases': len(inputs),
            'families': len(seeds['families']), 'passages': len(passages),
            'splits': dict(Counter(row['split'] for row in inputs))},
        'policy': {'max_evidence_utf8_bytes': MAX_BYTES, 'max_passages': MAX_PASSAGES,
            'required_span_coverage': 1.0, 'date_intervals': '[from,to)',
            'track': 'contract_text+provided_concepts+context',
            'primary_metric': 'complete_evidence_pass_rate',
            'review_required_for_certified_score': True},
        'source_documents': {key: {'raw_checksum': docs[key]['raw_checksum'],
            'source_verified': docs[key]['source_verified']} for key in seeds['corpus_documents']}}
    manifest_path = folder / 'manifest.json'
    if manifest_path.exists() and not rebuild:
        if json.loads(manifest_path.read_text(encoding='utf-8')) != manifest:
            raise ValueError('Frozen benchmark changed. Use a new version, or explicitly --rebuild during authoring.')
    for name, blob in blobs.items():
        (folder / name).write_bytes(blob)
    write_json(manifest_path, manifest)
    return manifest


def verify(folder=HERE):
    folder = Path(folder)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        if digest((folder / name).read_bytes()) != expected:
            raise ValueError(f'Benchmark checksum mismatch: {name}; regenerate exact frozen corpus with prepare')
    if digest((folder / 'seeds.json').read_bytes()) != manifest['seed_sha256']:
        raise ValueError('Seed authoring file changed without a new benchmark manifest')
    inputs, gold, corpus = (load_jsonl(folder / name) for name in
        ('inputs.jsonl', 'gold.jsonl', 'corpus.generated.jsonl'))
    for name, rows, key in [('inputs', inputs, 'id'), ('gold', gold, 'id'), ('corpus', corpus, 'passage_id')]:
        if len({row[key] for row in rows}) != len(rows):
            raise ValueError(f'Duplicate IDs in {name}')
    if {r['id'] for r in inputs} != {r['id'] for r in gold}:
        raise ValueError('Input/gold IDs differ')
    families = defaultdict(set)
    for row in inputs:
        families[row['family_id']].add(row['split'])
        if set(row) != {'id', 'family_id', 'split', 'concepts', 'contract_text', 'context'}:
            raise ValueError('Unexpected public input field; possible gold leakage')
    if any(len(splits) != 1 for splits in families.values()):
        raise ValueError('Family leakage across dev/test')
    corpus_map = {r['passage_id']: r for r in corpus}
    for row in gold:
        if row['decision'] == 'ready' and not row['evidence_groups']:
            raise ValueError('Ready case without gold evidence')
        for group in row['evidence_groups']:
            if not group['alternatives']:
                raise ValueError('Empty evidence group')
            for alt in group['alternatives']:
                chunks = [p for p in corpus if p['version_key'] == alt['version_key']]
                if not covers(alt, chunks):
                    raise ValueError(f'Gold span not in corpus: {row["id"]}')
                chars = {}
                for p in chunks:
                    chars.update(enumerate(p['text'], p['start']))
                if ''.join(chars[i] for i in range(alt['start'], alt['end'])) != alt['quote']:
                    raise ValueError(f'Gold quote/offset mismatch: {row["id"]}')
    return manifest, inputs, gold, corpus_map


def covers(alt, evidence):
    intervals = sorted((max(p['start'], alt['start']), min(p['end'], alt['end']))
        for p in evidence if p['version_key'] == alt['version_key']
        and p['end'] > alt['start'] and p['start'] < alt['end'])
    end = alt['start']
    for a, b in intervals:
        if a > end:
            return False
        end = max(end, b)
    return end >= alt['end']


def case_score(inp, gold, prediction, corpus, policy):
    errors, evidence = [], []
    if not isinstance(prediction, dict):
        raise ValueError('Each prediction must be a JSON object')
    refs = prediction.get('evidence', [])
    if not isinstance(refs, list) or any(not isinstance(p, str) for p in refs):
        return {'passed': False, 'retrieval_passed': False, 'errors': ['invalid_evidence_format'], 'coverage': 0.0,
                'temporal_errors': 0, 'recalled_at': {'5': 0.0, '10': 0.0}}
    if len(refs) != len(set(refs)):
        errors.append('duplicate_passages')
    if len(refs) > policy['max_passages']:
        errors.append('passage_budget_exceeded')
    for pid in refs:
        if pid not in corpus:
            errors.append('unknown_passage:' + pid)
        else:
            evidence.append(corpus[pid])
    nbytes = sum(len(p['text'].encode('utf-8')) for p in evidence)
    if nbytes > policy['max_evidence_utf8_bytes']:
        errors.append('byte_budget_exceeded')
    day = inp['context'].get('assessment_date')
    temporal = sum(not live(p, day) for p in evidence) if day else 0
    if temporal:
        errors.append('wrong_effective_version')
    if not day and evidence:
        errors.append('evidence_without_assessment_date')
    # Relevance coverage is independent of decision/classification correctness.
    def coverage(rows):
        groups = gold['evidence_groups']
        return sum(any(covers(alt, rows) for alt in g['alternatives']) for g in groups) / len(groups) if groups else 1.0
    cov = coverage(evidence)
    if cov < 1.0:
        errors.append('missing_required_evidence')
    if prediction.get('decision') != gold['decision']:
        errors.append('wrong_decision')
    if gold['decision'] == 'out_of_scope' and evidence:
        errors.append('out_of_scope_must_abstain')
    fields = prediction.get('missing_context', [])
    if not isinstance(fields, list) or any(not isinstance(f, str) for f in fields) or set(fields) != set(gold['required_context']):
        errors.append('wrong_missing_context')
    unsafe = sorted({p['verification_status'] for p in evidence if p['verification_status'] != 'verified'})
    flags = prediction.get('source_warnings', [])
    if not isinstance(flags, list) or any(not isinstance(f, str) for f in flags) or not set(unsafe).issubset(flags):
        errors.append('unreported_source_quality')
    # Ranking diagnosis only; no claim of exhaustive passage relevance labels/precision.
    ranks = [k for k in range(1, len(evidence) + 1) if coverage(evidence[:k]) == 1.0]
    retrieval_errors = [e for e in errors if e not in {'wrong_decision', 'wrong_missing_context'}]
    return {'passed': not errors, 'retrieval_passed': not retrieval_errors,
        'errors': errors, 'coverage': cov, 'evidence_bytes': nbytes, 'temporal_errors': temporal,
        'complete_at_rank': min(ranks) if ranks and gold['evidence_groups'] else None,
        'recalled_at': {str(k): coverage(evidence[:k]) for k in (5, 10)},
        'retrieved_count': len(refs), 'source_statuses': unsafe}


def bootstrap(values, seed=20261117):
    if not values:
        return None
    rng = random.Random(seed)
    samples = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(2000))
    return [samples[49], samples[1949]]


def evaluate(run_path, folder=HERE, split='test'):
    folder, run_path = Path(folder), Path(run_path)
    manifest, inputs, gold, corpus = verify(folder)
    run = json.loads(run_path.read_text(encoding='utf-8'))
    if run.get('manifest_sha256') != digest((folder / 'manifest.json').read_bytes()):
        raise ValueError('Run manifest mismatch: evaluated against a different benchmark')
    if not run.get('config') or not run.get('system'):
        raise ValueError('Run must record system and configuration')
    predictions = load_jsonl(run_path.parent / run['predictions_file'])
    pmap = {p['id']: p for p in predictions}
    if len(pmap) != len(predictions):
        raise ValueError('Duplicate prediction IDs')
    known = {i['id'] for i in inputs}
    if set(pmap) - known:
        raise ValueError('Unknown prediction IDs')
    gs = {g['id']: g for g in gold}
    rows = []
    for inp in inputs:
        if split != 'all' and inp['split'] != split:
            continue
        prediction = pmap.get(inp['id'], {})
        score = case_score(inp, gs[inp['id']], prediction, corpus, manifest['policy'])
        if not prediction:
            score['passed'] = score['retrieval_passed'] = False
            score['errors'].append('missing_prediction')
        latency = prediction.get('latency_ms')
        if latency is not None and (not isinstance(latency, (int, float)) or not math.isfinite(latency) or latency < 0):
            raise ValueError('Invalid latency_ms')
        rows.append({'id': inp['id'], 'family_id': inp['family_id'], 'split': inp['split'],
            'category': gs[inp['id']]['category'], 'decision': gs[inp['id']]['decision'],
            'latency_ms': latency, **score})
    groups = defaultdict(list)
    for row in rows:
        groups[row['family_id']].append(int(row['passed']))
    family_scores = [statistics.mean(vals) for vals in groups.values()]
    review_file = folder / 'reviews.jsonl'
    reviews = load_jsonl(review_file) if review_file.exists() else []
    # Review binds the exact full gold row; editing a label invalidates the approval.
    latest_reviews = {r['id']: r for r in reviews}
    approved = {r['id'] for r in latest_reviews.values() if r.get('decision') == 'approved'
        and r.get('reviewer') and r.get('reviewer_type') == 'human'
        and r.get('reviewed_at') and r.get('note')
        and r.get('gold_sha256') == digest(json_bytes(gs.get(r['id'])))}
    certified = all(row['id'] in approved for row in rows) and bool(rows)
    retrieval = [r for r in rows if r['decision'] == 'ready']
    latencies = sorted(row['latency_ms'] for row in rows if row['latency_ms'] is not None)
    return {'benchmark': manifest['benchmark'], 'manifest_sha256': run['manifest_sha256'],
        'run_sha256': digest(run_path.read_bytes()),
        'predictions_sha256': digest((run_path.parent / run['predictions_file']).read_bytes()),
        'run_metadata': {k: v for k, v in run.items() if k not in {'system', 'config', 'manifest_sha256'}},
        'system': run['system'], 'config': run['config'], 'split': split,
        'score_status': 'human_reviewed' if certified else 'provisional_pending_independent_review',
        'human_reviewed_cases': sum(row['id'] in approved for row in rows),
        'summary': {'total': len(rows), 'passed': sum(r['passed'] for r in rows),
            'pass_rate': statistics.mean(int(r['passed']) for r in rows) if rows else None,
            'family_macro_pass_rate': statistics.mean(family_scores) if family_scores else None,
            'family_bootstrap_95ci': bootstrap(family_scores),
            'ready_case_retrieval_pass_rate': statistics.mean(int(r['retrieval_passed']) for r in retrieval) if retrieval else None,
            'evidence_group_recall': statistics.mean(r['coverage'] for r in retrieval) if retrieval else None,
            'temporal_error_cases': sum(r['temporal_errors'] > 0 for r in rows),
            'p50_ms': statistics.median(latencies) if latencies else None,
            'p95_ms': latencies[math.ceil(.95 * len(latencies))-1] if latencies else None,
            'latency_sample_count': len(latencies)},
        'by_category': {cat: {'total': len(rr), 'passed': sum(r['passed'] for r in rr)}
            for cat in sorted({r['category'] for r in rows})
            for rr in [[r for r in rows if r['category'] == cat]]}, 'cases': rows,
        'limits': ['Synthetic contract clauses, not independently labeled real contracts.',
            'Gold quotes cross-checked against original corpus text; legal completeness awaits independent review.',
            'Qrels are minimal required evidence groups, not exhaustive relevance labels.',
            'No answer-generation, violation-classification or bridge evaluation.',
            'Source timing and unresolved legal-source quality remain explicit.']}


def make_run(folder, out, system, config, predictions):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / 'predictions.jsonl', predictions)
    run = {'system': system, 'config': config,
        'manifest_sha256': digest((Path(folder) / 'manifest.json').read_bytes()),
        'predictions_file': 'predictions.jsonl'}
    write_json(out / 'run.json', run)
    return out / 'run.json'


def oracle(folder, out):
    """Harness sanity check only. Reads gold: NEVER a retrieval model result."""
    manifest, inputs, gold, corpus = verify(folder)
    predictions = []
    for g in gold:
        ids = []
        for group in g['evidence_groups']:
            alt = group['alternatives'][0]
            ids += [p['passage_id'] for p in corpus.values() if p['version_key'] == alt['version_key']
                and p['start'] < alt['end'] and p['end'] > alt['start']]
        ids = list(dict.fromkeys(ids))
        predictions.append({'id': g['id'], 'decision': g['decision'], 'missing_context': g['required_context'],
            'evidence': ids, 'source_warnings': sorted({corpus[p]['verification_status'] for p in ids
                if corpus[p]['verification_status'] != 'verified'})})
    return make_run(folder, out, 'oracle-harness-only', {'reads_gold': True, 'not_a_model_score': True}, predictions)


def lexical(folder, out):
    """Deterministic public-input-only TF-IDF baseline, NOT structural/HippoRAG."""
    manifest, inputs, _gold, corpus = verify(folder)
    # This baseline uses only inputs + canonical corpus after integrity validation.
    def terms(text):
        return re.findall(r'\w+', text.casefold())
    index = defaultdict(list)
    for pid, p in corpus.items():
        tf = Counter(terms(p['text']))
        for term, freq in tf.items():
            index[term].append((pid, 1 + math.log(freq)))
    n = len(corpus)
    predictions = []
    for inp in inputs:
        start = time.perf_counter()
        query = inp['contract_text'] + ' ' + ' '.join(c['description'] for c in inp['concepts'])
        scores = defaultdict(float)
        for term in set(terms(query)):
            postings = index.get(term, [])
            idf = math.log(1 + n / (1 + len(postings)))
            for pid, tf in postings:
                scores[pid] += tf * idf
        day = inp['context'].get('assessment_date')
        ids, budget = [], 0
        for pid in sorted(scores, key=lambda p: (-scores[p], p)):
            p = corpus[pid]
            if day and not live(p, day):
                continue
            cost = len(p['text'].encode('utf-8'))
            if budget + cost > manifest['policy']['max_evidence_utf8_bytes']:
                continue
            ids.append(pid)
            budget += cost
            if len(ids) == manifest['policy']['max_passages']:
                break
        predictions.append({'id': inp['id'], 'decision': 'ready', 'missing_context': [], 'evidence': ids,
            'source_warnings': sorted({corpus[p]['verification_status'] for p in ids if corpus[p]['verification_status'] != 'verified'}),
            'latency_ms': (time.perf_counter() - start) * 1000})
    return make_run(folder, out, 'lexical-tfidf', {'seed': 0, 'query_fields': ['contract_text', 'concepts.description'],
        'date_filter': True, 'decision_policy': 'always_ready', 'reads_gold_for_retrieval': False}, predictions)


def compare(a, b):
    if any(a[key] != b[key] for key in ('manifest_sha256', 'split')):
        raise ValueError('Comparison requires identical benchmark and split')
    ar, br = ({r['id']: r for r in report['cases']} for report in (a, b))
    if set(ar) != set(br):
        raise ValueError('Paired comparison requires identical case IDs')
    families = defaultdict(list)
    for cid in ar:
        families[ar[cid]['family_id']].append(int(br[cid]['passed']) - int(ar[cid]['passed']))
    delta = [statistics.mean(v) for v in families.values()]
    return {'a': a['system'], 'b': b['system'], 'metric': 'family_macro_pass_rate',
        'b_minus_a': statistics.mean(delta), 'paired_family_bootstrap_95ci': bootstrap(delta),
        'score_status': [a['score_status'], b['score_status']]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--folder', type=Path, default=HERE)
    sub = ap.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--legal-dir', type=Path, default=DEFAULT_LEGAL); p.add_argument('--rebuild', action='store_true')
    sub.add_parser('verify')
    p = sub.add_parser('score'); p.add_argument('--run', type=Path, required=True); p.add_argument('--split', choices=['dev', 'test', 'all'], default='test'); p.add_argument('--out', type=Path, required=True)
    for command in ('oracle', 'lexical'):
        p = sub.add_parser(command); p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('compare'); p.add_argument('a', type=Path); p.add_argument('b', type=Path)
    args = ap.parse_args()
    if args.command == 'prepare':
        result = prepare(args.legal_dir, args.folder, args.rebuild)['counts']
    elif args.command == 'verify':
        result = verify(args.folder)[0]['counts']
    elif args.command == 'score':
        report = evaluate(args.run, args.folder, args.split)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.out, report)
        result = {'score_status': report['score_status'], **report['summary']}
    elif args.command in ('oracle', 'lexical'):
        result = str((oracle if args.command == 'oracle' else lexical)(args.folder, args.out))
    else:
        result = compare(*(json.loads(path.read_text(encoding='utf-8')) for path in (args.a, args.b)))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
