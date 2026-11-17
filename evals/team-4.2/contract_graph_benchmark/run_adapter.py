"""Run any retriever through a public-input-only adapter, then score separately.

Adapter module contract:
    build_retriever(corpus_path: Path, config: dict) -> object
    object.retrieve(case: dict) -> dict
    object.close()  # optional

retrieve returns decision, evidence (ordered canonical passage IDs),
missing_context, source_warnings. It must not receive/read gold or seeds.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import platform
import time
from pathlib import Path

from benchmark import HERE, digest, load_jsonl, make_run, verify, write_json


def run_adapter(adapter_path, config_path, out, folder=HERE, split='test'):
    folder, adapter_path = Path(folder), Path(adapter_path)
    manifest = verify(folder)[0]
    inputs = load_jsonl(folder / 'inputs.jsonl')
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    spec = importlib.util.spec_from_file_location('contract_benchmark_adapter', adapter_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    started = time.perf_counter()
    retriever = module.build_retriever(folder / 'corpus.generated.jsonl', copy.deepcopy(config))
    setup_seconds = time.perf_counter() - started
    predictions = []
    try:
        for inp in inputs:
            if split != 'all' and inp['split'] != split:
                continue
            # family_id and split are evaluation bookkeeping, not retrieval hints.
            public_case = {key: copy.deepcopy(inp[key]) for key in ('id', 'concepts', 'contract_text', 'context')}
            started = time.perf_counter()
            try:
                result = retriever.retrieve(public_case)
                if not isinstance(result, dict):
                    raise TypeError('retrieve() must return a dict')
                result = {**result, 'id': inp['id']}
            except Exception as exc:
                result = {'id': inp['id'], 'decision': 'error', 'evidence': [],
                    'missing_context': [], 'source_warnings': [], 'error_type': type(exc).__name__}
            result['latency_ms'] = (time.perf_counter() - started) * 1000
            predictions.append(result)
    finally:
        get_metadata = getattr(retriever, 'metadata', None)
        adapter_metadata = get_metadata() if get_metadata else {}
        close = getattr(retriever, 'close', None)
        if close:
            close()
    run_path = make_run(folder, out, config.get('system', adapter_path.stem), config, predictions)
    metadata = json.loads(run_path.read_text(encoding='utf-8'))
    metadata.update({'adapter_sha256': digest(adapter_path.read_bytes()),
        'adapter_metadata': adapter_metadata,
        'python_version': platform.python_version(), 'setup_seconds': setup_seconds,
        'split': split, 'policy': manifest['policy']})
    write_json(run_path, metadata)
    return run_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--folder', type=Path, default=HERE)
    parser.add_argument('--split', choices=['dev', 'test', 'all'], default='test')
    args = parser.parse_args()
    print(run_adapter(args.adapter, args.config, args.out, args.folder, args.split))
