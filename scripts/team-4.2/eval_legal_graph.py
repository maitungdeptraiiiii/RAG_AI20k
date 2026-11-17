"""Repeatable Legal Graph benchmark: integrity, real API cases, provenance, latency.

This is a curated regression benchmark, not a legal accuracy certification.
No bridge, concept catalog, rule engine, embeddings or LLM calls are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app/team-4.2/src'))
from rag.contracts.graph.neo4j_store import GraphConfig
from rag.legal.graph.build import build_legal_graph, validate
from rag.legal.graph.neo4j_store import LegalGraphStore
from rag.legal.graph.query import LegalGraph
from rag.legal.snapshots import SnapshotManager


def norm(text):
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def evaluate(case, graph):
    day = date.fromisoformat(case['day'])
    method = case['method']
    checks, statuses = [], []
    if method == 'text_at':
        result = graph.text_at(case['pid'], day)
        checks.append(result.get('in_force') == case['in_force'])
        if 'reason' in case:
            checks.append(result.get('reason') == case['reason'])
        text = result.get('text', '')
        citation = result.get('citation', {})
        if case['in_force']:
            checks.append(bool(citation.get('source_url') and citation.get('raw_checksum')))
            statuses.append(citation.get('verification_status', 'missing'))
    elif method == 'applicable':
        result = graph.applicable(case['document_key'], day)
        checks.append(sorted(x['document']['document_key'] for x in result) == sorted(case['documents']))
        text = ''
    elif method == 'references':
        result = graph.references(case['pid'], day, case.get('direction', 'out'))
        checks.append(set(case['targets_include']) <= {x['target'] for x in result})
        text = ''
    elif method == 'guidance':
        result = graph.guidance(case['pid'], day)
        checks.append(set(case['sources_include']) <= {x['citation']['provision_id'] for x in result})
        text = ''
    elif method == 'appendices':
        result = graph.appendices(case['document_key'], day)
        checks.append(case.get('min_count', 0) <= len(result) <= case.get('max_count', math.inf))
        text = '\n'.join(x['text'] for x in result)
        statuses.extend(x.get('verification_status') or 'missing' for x in result)
    else:
        raise ValueError(f'Unknown benchmark method: {method}')
    checks.extend(norm(fragment) in norm(text) for fragment in case.get('contains', []))
    return {'passed': all(checks), 'checks': checks, 'verification_statuses': statuses,
            'observed': result if method == 'applicable' else
                {'count': len(result)} if isinstance(result, list) else
                {'in_force': result.get('in_force'), 'reason': result.get('reason'),
                 'text_excerpt': result.get('text', '')[:240],
                 'source_url': result.get('citation', {}).get('source_url'),
                 'verification_status': result.get('citation', {}).get('verification_status')}}


def main(args):
    manager = SnapshotManager(args.legal_dir)
    snapshot = manager.current()
    corpus = manager.store(snapshot.snapshot_id)
    start = time.perf_counter()
    build = build_legal_graph(corpus, snapshot.snapshot_id)
    errors = validate(build, corpus)
    report = {'benchmark': 'legal-graph-labor-v1', 'snapshot_id': snapshot.snapshot_id,
              'dataset_sha256': hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
              'evaluated_at': datetime.now(timezone.utc).isoformat(),
              'build_id': build.build_id, 'validation_errors': errors, 'graph': build.report,
              'build_seconds': time.perf_counter() - start, 'cases': [],
              'limits': ['Curated regression cases; not exhaustive legal coverage.',
                         'Passing retrieval does not verify a needs_review/conflicted source.',
                         'Latency is a single local run, not a load benchmark.']}
    if not errors and not args.structural_only:
        store = LegalGraphStore(GraphConfig(args.uri, args.user, os.environ.get('NEO4J_PASSWORD', ''), args.database), name=args.namespace)
        try:
            if args.publish:
                store.publish(build)
            meta = store.current()
            if not meta or meta['current_build'] != build.build_id:
                raise RuntimeError('Graph not published or stale; run with --publish against the intended namespace')
            graph = LegalGraph(store).pinned()
            for line in args.dataset.read_text(encoding='utf-8').splitlines():
                if not line.strip():
                    continue
                case = json.loads(line)
                begin = time.perf_counter()
                try:
                    result = evaluate(case, graph)
                except Exception as exc:
                    result = {'passed': False, 'error': f'{type(exc).__name__}: {exc}'}
                report['cases'].append({'id': case['id'], 'method': case['method'],
                    'source': case['source'], 'latency_ms': (time.perf_counter() - begin) * 1000, **result})
        except Exception as exc:
            report['setup_error'] = f'{type(exc).__name__}: {exc}'
        finally:
            store.close()
    rows = report['cases']
    latencies = sorted(x['latency_ms'] for x in rows)
    report['summary'] = {'total': len(rows), 'passed': sum(x['passed'] for x in rows),
        'failed': sum(not x['passed'] for x in rows),
        'verification_statuses': dict(Counter(s for row in rows for s in row.get('verification_statuses', []))),
        'p50_ms': latencies[len(latencies)//2] if latencies else None,
        'p95_ms': latencies[math.ceil(len(latencies)*.95)-1] if latencies else None,
        'mode': 'structural_only' if args.structural_only else 'neo4j_api'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'validation_errors': len(errors), **report['summary'], 'report': str(args.out)}, ensure_ascii=False))
    return 1 if errors or report['summary']['failed'] or report.get('setup_error') else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--legal-dir', type=Path, default=ROOT/'app/team-4.2/data/team-4.2/legal')
    ap.add_argument('--dataset', type=Path, default=ROOT/'evals/team-4.2/datasets/legal_graph_labor_v1.jsonl')
    ap.add_argument('--out', type=Path, default=ROOT/'evals/team-4.2/results/legal-graph-labor-v1/evaluation.json')
    ap.add_argument('--uri', default=os.environ.get('NEO4J_URI', 'bolt://localhost:7687'))
    ap.add_argument('--user', default=os.environ.get('NEO4J_USER', 'neo4j'))
    ap.add_argument('--database', default=os.environ.get('NEO4J_DATABASE', 'neo4j'))
    ap.add_argument('--namespace', default='legal')
    ap.add_argument('--publish', action='store_true')
    ap.add_argument('--structural-only', action='store_true')
    raise SystemExit(main(ap.parse_args()))
