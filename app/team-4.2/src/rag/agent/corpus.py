"""Immutable legacy-corpus view and conservative, explicit article xrefs.

This deliberately does not claim temporal/legal applicability. Unit IDs are
snapshot-scoped, and every xref has an exact source span and resolution status.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping

from rag.retrieve.merge import article_key, merged_chunk
from rag.schema import Chunk, Hit


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


@dataclass(frozen=True)
class Xref:
    id: str
    source_key: tuple[str, ...]
    source_chunk_id: str
    start: int
    end: int
    quote: str
    target_key: tuple[str, ...] | None
    status: str

    def to_dict(self):
        return {
            "id": self.id, "source_chunk_id": self.source_chunk_id,
            "start": self.start, "end": self.end, "quote": self.quote,
            "target": list(self.target_key) if self.target_key else None, "status": self.status,
        }


_ARTICLE = re.compile(r"^Điều\s+(\d+[a-zđ]?)\s*[.:]", re.I)
_REF = re.compile(r"\bĐiều\s+(\d+[a-zđ]?)\b", re.I)
_ABBREVIATIONS = {
    "bo luat dan su": ("blds",), "bo luat hinh su": ("blhs",),
    "bo luat to tung dan su": ("blttds",), "bo luat to tung hinh su": ("bltths",),
    "bo luat lao dong": ("blld",), "bo luat hang hai": ("blhh",),
}


class CorpusSnapshot:
    def __init__(self, revision: int, chunks: Mapping[str, Chunk]):
        self.revision, self.chunks = revision, chunks
        digest = hashlib.sha256()
        self.units: dict[tuple[str, ...], list[str]] = defaultdict(list)
        self.articles: dict[tuple[str, str], tuple[str, ...]] = {}
        self.aliases: dict[str, set[str]] = defaultdict(set)
        for cid, chunk in sorted(chunks.items()):
            digest.update(json.dumps(chunk.to_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8"))
            digest.update(b"\n")
            key = article_key(chunk)
            self.units[key].append(cid)
            section = (chunk.section or "").rsplit(" > ", 1)[-1].strip()
            heading = _ARTICLE.match(section)
            if heading:
                self.articles[(chunk.doc_id, heading[1].casefold())] = key
            stem = fold(Path(chunk.source).stem)
            stem = re.sub(r"\s+\d{4}$", "", stem)
            if stem.startswith(("bo luat ", "luat ", "nghi dinh ", "thong tu ")):
                self.aliases[stem].add(chunk.doc_id)
                for alias in _ABBREVIATIONS.get(stem, ()):
                    self.aliases[alias].add(chunk.doc_id)
        self.id = digest.hexdigest()
        self._xref_cache: dict[tuple[str, ...], list[Xref]] = {}

    def materialize(self, key: tuple[str, ...]) -> tuple[Chunk, tuple[str, ...]]:
        ids = tuple(self.units[key])
        hit = Hit(ids[0], 0.0, 1, "xref", ids[1:])
        return merged_chunk(hit, self.chunks), ids

    def xrefs(self, key: tuple[str, ...]) -> list[Xref]:
        if key in self._xref_cache:
            return self._xref_cache[key]
        refs = []
        seen = set()
        for cid in self.units[key]:
            chunk = self.chunks[cid]
            for match in _REF.finditer(chunk.text):
                # Exclude an article's own heading; never treat it as a citation.
                prefix = chunk.text[chunk.text.rfind("\n", 0, match.start()) + 1:match.start()]
                if not prefix.strip() and re.match(r"\s*[.:]", chunk.text[match.end():]):
                    continue
                tail = re.split(r"[.;\n]", chunk.text[match.end():match.end() + 180], maxsplit=1)[0]
                next_reference = _REF.search(tail)
                if next_reference:
                    tail = tail[:next_reference.start()]
                reference = chunk.text[match.start():match.end()] + tail
                normalized = fold(tail)
                doc = chunk.doc_id
                status = "resolved"
                mentions = set()
                for alias, docs in self.aliases.items():
                    if re.search(r"\b" + re.escape(alias) + r"\b", normalized):
                        mentions.update(docs)
                if len(mentions) == 1:
                    doc = next(iter(mentions))
                elif len(mentions) > 1:
                    status = "ambiguous"
                elif re.search(r"\b(?:bo luat|luat|nghi dinh|thong tu)\b", normalized):
                    if not re.search(r"\b(?:bo luat|luat|nghi dinh|thong tu) nay\b", normalized):
                        status = "unresolved_document"
                elif re.search(r"\bcủa\s+[A-ZĐ][A-ZĐ0-9]{1,}\b", tail):
                    status = "unresolved_document"
                target = self.articles.get((doc, match[1].casefold())) if status == "resolved" else None
                if target is None and status == "resolved":
                    status = "missing_target"
                signature = (reference, target, status)
                if signature in seen:
                    continue
                seen.add(signature)
                identity = json.dumps([self.id, cid, match.start(), reference], ensure_ascii=False)
                refs.append(Xref(
                    "X" + hashlib.sha256(identity.encode()).hexdigest()[:16], key, cid,
                    match.start(), match.end() + len(tail), reference, target, status,
                ))
        self._xref_cache[key] = refs
        return refs
