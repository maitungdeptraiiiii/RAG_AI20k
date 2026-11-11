"""Đồng bộ sang kho luật có phiên bản (spec 2026-11-11-new-store-sync-design.md)."""

from pathlib import Path

import yaml

LEGAL = Path(__file__).resolve().parents[3] / "data" / "team-4.2" / "legal"


def test_seeds_cover_legacy_map():
    seeds = {(x["type"], x["number"]) for x in yaml.safe_load((LEGAL / "seeds.yaml").read_text(encoding="utf-8"))["laws"]}
    legacy = yaml.safe_load((LEGAL / "legacy_map.yaml").read_text(encoding="utf-8"))["laws"]
    assert len(legacy) == 6
    assert all((x["type"], x["number"]) in seeds for x in legacy)
