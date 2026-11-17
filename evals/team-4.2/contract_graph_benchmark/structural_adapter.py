"""Read-only structural baseline: original concept anchors + dated graph traversal.

No lexical/embedding retrieval and no benchmark-gold access. The catalog is a
frozen projection of the user-supplied design, not learned from test labels.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'app/team-4.2/src'))


class StructuralRetriever:
    def __init__(self, corpus_path, config, graph=None):
        self.config = config
        raw = Path(corpus_path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != config['corpus_sha256']:
            raise ValueError('Structural adapter corpus checksum mismatch')
        self.corpus = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
        self.allowed_docs = {p['document_key'] for p in self.corpus}
        self.by_article = defaultdict(list)
        for p in self.corpus:
            self.by_article[p['provision_id']].append(p)
        catalog_path = ROOT / config['concept_catalog']
        catalog_raw = catalog_path.read_bytes()
        if hashlib.sha256(catalog_raw).hexdigest() != config['concept_catalog_sha256']:
            raise ValueError('Structural concept catalog checksum mismatch')
        catalog = json.loads(catalog_raw)
        self.concepts = {c['id']: c for c in catalog['concepts']}
        self.store = None
        if graph is None:
            from rag.contracts.graph.neo4j_store import GraphConfig
            from rag.legal.graph.neo4j_store import LegalGraphStore
            from rag.legal.graph.query import LegalGraph
            self.store = LegalGraphStore(GraphConfig(
                os.environ.get('NEO4J_URI', config['uri']), os.environ.get('NEO4J_USER', 'neo4j'),
                os.environ['NEO4J_PASSWORD'], os.environ.get('NEO4J_DATABASE', 'neo4j')),
                name=config['namespace'])
            try:
                graph = LegalGraph(self.store).pinned()
            except Exception:
                self.store.close()
                raise
        self.graph = graph
        if graph.snapshot_id != config['snapshot_id']:
            self.close()
            raise ValueError('Structural graph snapshot differs from frozen benchmark')
        self.cache = {}
        self.cache_hits = 0

    def close(self):
        if self.store is not None:
            self.store.close()

    def metadata(self):
        return {'graph_build_id': self.graph.build_id, 'snapshot_id': self.graph.snapshot_id,
            'concept_catalog_sha256': self.config['concept_catalog_sha256'],
            'corpus_sha256': self.config['corpus_sha256'], 'read_only': True,
            'cache_entries': len(self.cache), 'cache_hits': self.cache_hits,
            'timing_note': 'Sequential run; deterministic graph-query cache shared across cases.',
            'catalog_origin': 'Original user-provided 2026-11-14 concepts.yaml, unchanged anchor projection.'}

    def _query(self, method, *args):
        key = (method,) + tuple(a.isoformat() if hasattr(a, 'isoformat') else a for a in args)
        if key not in self.cache:
            self.cache[key] = getattr(self.graph, method)(*args)
        else:
            self.cache_hits += 1
        return self.cache[key]

    def _document_rows(self, key, day):
        cache_key = 'document_rows', key, day.isoformat()
        if cache_key in self.cache:
            self.cache_hits += 1
            return self.cache[cache_key]
        # Only value-source documents selected by the existing replacement chain.
        rows = self.graph._run(
            "MATCH (p:Provision {document_key: $key, kind: 'article', build_id: $bid})"
            "-[:HAS_VERSION]->(v:ProvisionVersion {build_id: $bid}) "
            "MATCH (d:LawDoc {node_id: $key, build_id: $bid}) "
            "WHERE v.valid_from <= $day AND (v.valid_to IS NULL OR v.valid_to > $day) "
            "RETURN v.text AS text, {provision_id: p.node_id, document_key: d.node_id, "
            "valid_from: v.valid_from, valid_to: v.valid_to, raw_checksum: d.raw_checksum, "
            "version_id: v.node_id} AS citation ORDER BY p.order",
            key=key, day=day.isoformat(), bid=self.graph.build_id)
        self.cache[cache_key] = rows
        return rows

    def _map_row(self, row, day, problems):
        citation = row.get('citation', {})
        pid = citation.get('provision_id', '')
        doc, sep, address = pid.partition('#')
        if doc not in self.allowed_docs or not sep:
            return []
        article = doc + '#' + address.split('.')[0]
        candidates = [p for p in self.by_article.get(article, []) if p['valid_from'] <= day
            and (p['valid_to'] is None or day < p['valid_to'])]
        versions = {p['version_key'] for p in candidates}
        if len(versions) != 1:
            problems.append({'reason': 'missing_or_ambiguous_canonical_version', 'pid': pid})
            return []
        if any(p['raw_checksum'] != citation.get('raw_checksum') for p in candidates):
            problems.append({'reason': 'graph_source_checksum_mismatch', 'pid': pid})
            return []
        # Reconstruct the canonical article and locate exactly the graph-returned
        # clause/point. Do not broaden a narrow anchor to the entire article.
        chars = {}
        for p in candidates:
            chars.update(enumerate(p['text'], p['start']))
        text = ''.join(chars[i] for i in range(max(chars) + 1))
        selected = row.get('text', '').strip()
        if not selected or text.count(selected) != 1:
            problems.append({'reason': 'graph_text_not_unique_in_canonical_article', 'pid': pid})
            return []
        a = text.index(selected)
        b = a + len(selected)
        return [p for p in candidates if p['start'] < b and p['end'] > a]

    def retrieve(self, case):
        context = case.get('context', {})
        if context.get('jurisdiction', 'VN') != 'VN' or (
            context.get('contract_type') not in (None, 'labor_contract')
            and context.get('employment_regime') != 'labor_contract'):
            return {'decision': 'out_of_scope', 'evidence': [], 'missing_context': [], 'source_warnings': []}
        if not context.get('assessment_date'):
            return {'decision': 'insufficient_context', 'evidence': [],
                'missing_context': ['assessment_date'], 'source_warnings': []}
        day = date.fromisoformat(context['assessment_date'])
        selected_concepts, problems = [], []
        for item in case.get('concepts', []):
            concept = self.concepts.get(item['id'])
            if concept is None:
                problems.append({'reason': 'unknown_concept', 'concept_id': item['id']})
            elif concept.get('scope') != 'out_of_scope':
                selected_concepts.append(concept)
        anchors = list(dict.fromkeys(a['pid'] for c in selected_concepts for a in c.get('anchors', [])))
        direct, values, guidance, refs = [], [], [], []
        for pid in anchors:
            row = self._query('text_at', pid, day)
            if row.get('in_force') is True:
                direct.append(row)
            else:
                problems.append({'reason': row.get('reason', 'inactive_anchor'), 'pid': pid})
        value_keys = list(dict.fromkeys(s['document_key'] for c in selected_concepts for s in c.get('value_sources', [])))
        for key in value_keys:
            for item in self._query('applicable', key, day):
                active = item['document']['document_key']
                if active in self.allowed_docs:
                    values.extend(self._document_rows(active, day))
        for pid in anchors:
            guidance.extend(self._query('guidance', pid, day))
            for ref in self._query('references', pid, day, 'in'):
                source = ref.get('citation', {}).get('provision_id')
                if source and source.partition('#')[0] in self.allowed_docs:
                    source_row = self._query('text_at', source, day)
                    if source_row.get('in_force') is True:
                        guidance.append(source_row)
            for ref in self._query('references', pid, day):
                target = ref['target']
                if ref.get('target_in_force') and target.partition('#')[0] in self.allowed_docs:
                    target_row = self._query('text_at', target, day)
                    if target_row.get('in_force') is True:
                        refs.append(target_row)
        # Frozen order: direct anchors, active value-source body, implementing
        # guidance, one-hop references; source order within each category.
        ids, used, nbytes, trace = [], set(), 0, []
        for category, rows in [('anchor', direct), ('value_source', values), ('guidance', guidance), ('reference', refs)]:
            for row in rows:
                for p in self._map_row(row, day.isoformat(), problems):
                    if p['passage_id'] in used:
                        continue
                    used.add(p['passage_id'])
                    cost = len(p['text'].encode('utf-8'))
                    if len(ids) >= self.config['max_passages'] or nbytes + cost > self.config['max_evidence_utf8_bytes']:
                        continue
                    ids.append(p['passage_id'])
                    nbytes += cost
                    trace.append({'passage_id': p['passage_id'], 'via': category,
                        'provision_id': row['citation']['provision_id']})
        cmap = {p['passage_id']: p for p in self.corpus}
        return {'decision': 'ready', 'evidence': ids, 'missing_context': [],
            'source_warnings': sorted({cmap[pid]['verification_status'] for pid in ids
                if cmap[pid]['verification_status'] != 'verified'}),
            'problems': problems, 'retrieval_trace': trace,
            'graph_build_id': self.graph.build_id, 'snapshot_id': self.graph.snapshot_id}


def build_retriever(corpus_path, config):
    return StructuralRetriever(corpus_path, config)
