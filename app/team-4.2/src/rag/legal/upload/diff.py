"""So sánh từng Điều giữa bản tải lên và bản đã có (cùng số hiệu), ở mức từ."""
from __future__ import annotations

import difflib
from dataclasses import dataclass

from rag.legal.structure import parse_structure


@dataclass(frozen=True)
class ArticleChange:
    article: str
    old_text: str
    new_text: str
    ops: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ArticleDiff:
    same: int
    changed: tuple[ArticleChange, ...]
    added: tuple[str, ...]
    removed: tuple[str, ...]


def _articles(text: str, key: str) -> dict[str, str]:
    """Nhãn Điều -> text đã gộp khoảng trắng (text của Điều đã gồm cả cây con)."""
    out: dict[str, str] = {}
    for p in parse_structure(text, key):
        if p.kind == "article" and p.address.article not in out:
            out[p.address.article] = " ".join(p.text.split())
    return out


def _word_ops(old: str, new: str) -> tuple[tuple[str, str], ...]:
    a, b = old.split(), new.split()
    ops: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            ops.append(("equal", " ".join(a[i1:i2])))
        else:
            if i2 > i1:
                ops.append(("delete", " ".join(a[i1:i2])))
            if j2 > j1:
                ops.append(("insert", " ".join(b[j1:j2])))
    return tuple(ops)


def diff_articles(old_text: str, new_text: str, key: str) -> ArticleDiff:
    old, new = _articles(old_text, key), _articles(new_text, key)
    same, changed = 0, []
    for label, o in old.items():
        n = new.get(label)
        if n is None:
            continue
        if n == o:
            same += 1
        else:
            changed.append(ArticleChange(label, o, n, _word_ops(o, n)))
    return ArticleDiff(same, tuple(changed), tuple(l for l in new if l not in old), tuple(l for l in old if l not in new))
