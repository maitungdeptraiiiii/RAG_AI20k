"""Import boundaries and demo entry points for the functional packages."""

import ast
import json
from pathlib import Path
import subprocess
import sys

import pytest


PROJECT = Path(__file__).resolve().parents[1]


def test_canonical_code_does_not_depend_on_legacy_package():
    paths = list((PROJECT / "scripts").glob("*.py"))
    for directory in ("models", "ingest", "versioning", "quality", "retrieve"):
        paths.extend((PROJECT / "src/rag" / directory).glob("*.py"))
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("rag.w02"), path
            elif isinstance(node, ast.Import):
                assert not any(alias.name.startswith("rag.w02") for alias in node.names), path


@pytest.mark.parametrize("module", [
    "scripts.demo_versioning", "scripts.demo_partial_versioning", "scripts.demo_review_queue",
])
def test_demo_commands(module):
    result = subprocess.run([sys.executable, "-X", "utf8", "-m", module], cwd=PROJECT,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["restart_preserved"] is True


def test_legacy_rag_schema_stays_distinct():
    from rag.models import ChunkV2
    from rag.schema import Chunk
    assert Chunk is not ChunkV2
