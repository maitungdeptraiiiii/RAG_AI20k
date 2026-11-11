"""Kho SQLite của kho luật: văn bản, quan hệ, thao tác (nội dung bất biến), bản dựng, phiên bản, duyệt."""

from __future__ import annotations

import dataclasses
import json
import sqlite3
import types
import typing
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, TypeVar, Union, get_args, get_origin

from rag.legal.models import (AmendmentOperation, BuildRun, DocumentRelation, LegalDocument, ProvisionVersion,
                              ReviewDecision, ReviewItem, ReviewStatus)
from rag.legal.targets import law_name

T = TypeVar("T")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (document_key TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS relations (source_key TEXT, target_key TEXT, relation TEXT, payload TEXT NOT NULL,
    PRIMARY KEY (source_key, target_key, relation));
CREATE TABLE IF NOT EXISTS operations (operation_id TEXT PRIMARY KEY, source_key TEXT, target_key TEXT,
    review_status TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS builds (seq INTEGER PRIMARY KEY AUTOINCREMENT, build_id TEXT UNIQUE, document_key TEXT,
    payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS versions (build_id TEXT, document_key TEXT, provision_id TEXT, valid_from TEXT,
    valid_to TEXT, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS versions_lookup ON versions (build_id, document_key, valid_from);
CREATE INDEX IF NOT EXISTS versions_pid ON versions (build_id, provision_id);
CREATE TABLE IF NOT EXISTS review_items (review_id TEXT PRIMARY KEY, kind TEXT, document_key TEXT, operation_id TEXT,
    provision_id TEXT, status TEXT, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions (seq INTEGER PRIMARY KEY AUTOINCREMENT, review_id TEXT, payload TEXT NOT NULL);
"""


def encode(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: encode(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, (list, tuple)):
        return [encode(x) for x in obj]
    if isinstance(obj, dict):
        return {k: encode(v) for k, v in obj.items()}
    return obj


def decode(tp: Any, value: Any) -> Any:
    if value is None:
        return None
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        inner = [a for a in get_args(tp) if a is not type(None)]
        return decode(inner[0], value)
    if origin is Literal:
        return value
    if origin is tuple:
        args = get_args(tp)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(decode(args[0], v) for v in value)
        return tuple(decode(a, v) for a, v in zip(args, value))
    if origin in (dict, list):
        return value if origin is dict else list(value)
    if tp is datetime:
        return datetime.fromisoformat(value)
    if tp is date:
        return date.fromisoformat(value)
    if dataclasses.is_dataclass(tp):
        hints = typing.get_type_hints(tp)
        return tp(**{f.name: decode(hints[f.name], value.get(f.name)) for f in dataclasses.fields(tp) if f.name in value})
    return value


def _dump(obj: Any) -> str:
    return json.dumps(encode(obj), ensure_ascii=False, sort_keys=True)


def _load(cls: type[T], payload: str) -> T:
    return decode(cls, json.loads(payload))


class LegalStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # --- văn bản / quan hệ -------------------------------------------------------------

    def upsert_document(self, doc: LegalDocument) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO documents VALUES (?, ?)", (doc.document_key, _dump(doc)))

    def document(self, key: str) -> LegalDocument | None:
        with self._conn() as c:
            row = c.execute("SELECT payload FROM documents WHERE document_key=?", (key,)).fetchone()
        return _load(LegalDocument, row[0]) if row else None

    def documents(self) -> list[LegalDocument]:
        with self._conn() as c:
            rows = c.execute("SELECT payload FROM documents ORDER BY document_key").fetchall()
        return [_load(LegalDocument, r[0]) for r in rows]

    def add_relation(self, rel: DocumentRelation) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO relations VALUES (?, ?, ?, ?)",
                      (rel.source_key, rel.target_key, rel.relation, _dump(rel)))

    def relations(self, key: str) -> list[DocumentRelation]:
        with self._conn() as c:
            rows = c.execute("SELECT payload FROM relations WHERE source_key=? OR target_key=? "
                             "ORDER BY source_key, target_key, relation", (key, key)).fetchall()
        return [_load(DocumentRelation, r[0]) for r in rows]

    # --- thao tác ----------------------------------------------------------------------

    def add_operations(self, ops: Sequence[AmendmentOperation]) -> int:
        n = 0
        with self._conn() as c:
            for o in ops:
                cur = c.execute("INSERT OR IGNORE INTO operations VALUES (?, ?, ?, ?, ?)",
                                (o.operation_id, o.source_document_key, o.target_document_key, o.review_status, _dump(o)))
                n += cur.rowcount
        return n

    def refresh_machine_operations(self, ops: Sequence[AmendmentOperation], *, source_key: str | None = None,
                                   now: datetime | None = None) -> tuple[list[str], list[str]]:
        """Thêm thao tác mới; ghi đè thao tác đã có nhưng CHƯA có người duyệt bằng đánh giá mới của máy.
        Với `source_key`: thao tác máy của văn bản đó không còn được sinh ra -> `rejected` (reviewer "system");
        thao tác người đã duyệt mà không còn được sinh ra -> trả về để mở mục duyệt (không tự huỷ quyết định người).
        Trả về (id bị loại, id thao tác người duyệt bị mất)."""
        retired: list[str] = []
        human_missing: list[str] = []
        with self._conn() as c:
            for o in ops:
                row = c.execute("SELECT payload FROM operations WHERE operation_id=?", (o.operation_id,)).fetchone()
                if row is None:
                    c.execute("INSERT INTO operations VALUES (?, ?, ?, ?, ?)", (o.operation_id, o.source_document_key,
                              o.target_document_key, o.review_status, _dump(o)))
                    continue
                old = _load(AmendmentOperation, row[0])
                if old.reviewer is None and old.review_status != "rejected" and old != o:
                    c.execute("UPDATE operations SET target_key=?, review_status=?, payload=? WHERE operation_id=?",
                              (o.target_document_key, o.review_status, _dump(o), o.operation_id))
            if source_key is not None:
                produced = {o.operation_id for o in ops}
                rows = c.execute("SELECT payload FROM operations WHERE source_key=? AND review_status != 'rejected'",
                                 (source_key,)).fetchall()
                for (payload,) in rows:
                    old = _load(AmendmentOperation, payload)
                    if old.operation_id in produced or old.supersedes_operation_id is not None:
                        continue                 # bản sửa của người duyệt không do parser sinh ra
                    if old.reviewer is None:
                        self._set_review(c, old.operation_id, "rejected", "system",
                                         "operation.superseded_by_replan", now or datetime.now().astimezone())
                        retired.append(old.operation_id)
                    else:
                        human_missing.append(old.operation_id)
        return retired, human_missing

    def operations(self, *, target_key: str | None = None, source_key: str | None = None,
                   include_rejected: bool = False) -> list[AmendmentOperation]:
        sql, args = "SELECT payload FROM operations WHERE 1=1", []
        if target_key is not None:
            sql += " AND target_key=?"
            args.append(target_key)
        if source_key is not None:
            sql += " AND source_key=?"
            args.append(source_key)
        if not include_rejected:
            sql += " AND review_status != 'rejected'"
        with self._conn() as c:
            rows = c.execute(sql + " ORDER BY rowid", args).fetchall()
        return [_load(AmendmentOperation, r[0]) for r in rows]

    def operation(self, op_id: str) -> AmendmentOperation | None:
        with self._conn() as c:
            row = c.execute("SELECT payload FROM operations WHERE operation_id=?", (op_id,)).fetchone()
        return _load(AmendmentOperation, row[0]) if row else None

    def _set_review(self, c: sqlite3.Connection, op_id: str, status: ReviewStatus, reviewer: str, note: str,
                    at: datetime) -> None:
        row = c.execute("SELECT payload FROM operations WHERE operation_id=?", (op_id,)).fetchone()
        if row is None:
            raise KeyError(op_id)
        op = dataclasses.replace(_load(AmendmentOperation, row[0]), review_status=status, reviewer=reviewer,
                                 review_note=note, reviewed_at=at)
        c.execute("UPDATE operations SET review_status=?, payload=? WHERE operation_id=?", (status, _dump(op), op_id))

    def set_review(self, op_id: str, status: ReviewStatus, reviewer: str, note: str, at: datetime) -> None:
        with self._conn() as c:
            self._set_review(c, op_id, status, reviewer, note, at)

    def supersede_operation(self, old_id: str, new_op: AmendmentOperation, reviewer: str, note: str,
                            at: datetime) -> None:
        new_op = dataclasses.replace(new_op, supersedes_operation_id=old_id)
        with self._conn() as c:
            self._set_review(c, old_id, "rejected", reviewer, note, at)
            c.execute("INSERT INTO operations VALUES (?, ?, ?, ?, ?)", (new_op.operation_id, new_op.source_document_key,
                      new_op.target_document_key, new_op.review_status, _dump(new_op)))

    # --- bản dựng / phiên bản ------------------------------------------------------------

    def save_build(self, run: BuildRun, versions: Sequence[ProvisionVersion]) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM builds WHERE build_id=?", (run.build_id,))
            c.execute("DELETE FROM versions WHERE build_id=?", (run.build_id,))
            c.execute("INSERT INTO builds (build_id, document_key, payload) VALUES (?, ?, ?)",
                      (run.build_id, run.document_key, _dump(run)))
            c.executemany("INSERT INTO versions VALUES (?, ?, ?, ?, ?, ?)",
                          [(run.build_id, v.document_key, v.provision_id, v.valid_from.isoformat(),
                            v.valid_to.isoformat() if v.valid_to else None, _dump(v)) for v in versions])

    def builds(self, key: str) -> list[BuildRun]:
        with self._conn() as c:
            rows = c.execute("SELECT payload FROM builds WHERE document_key=? ORDER BY seq", (key,)).fetchall()
        return [_load(BuildRun, r[0]) for r in rows]

    def latest_build(self, key: str) -> BuildRun | None:
        runs = self.builds(key)
        return runs[-1] if runs else None

    def _build_id(self, key: str, build_id: str | None) -> str | None:
        if build_id is not None:
            return build_id
        run = self.latest_build(key)
        return run.build_id if run else None

    def first_valid_from(self, key: str) -> date | None:
        """Ngày bắt đầu sớm nhất của bản dựng mới nhất — một truy vấn, không giải mã payload phiên bản."""
        bid = self._build_id(key, None)
        if bid is None:
            return None
        with self._conn() as conn:
            row = conn.execute("SELECT MIN(valid_from) FROM versions WHERE build_id=? AND document_key=?",
                               (bid, key)).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None

    def provisions_as_of(self, key: str, day: date, *, build_id: str | None = None) -> list[ProvisionVersion]:
        bid = self._build_id(key, build_id)
        if bid is None:
            return []
        d = day.isoformat()
        with self._conn() as c:
            rows = c.execute("SELECT payload FROM versions WHERE build_id=? AND document_key=? AND valid_from<=? "
                             "AND (valid_to IS NULL OR valid_to>?) ORDER BY rowid", (bid, key, d, d)).fetchall()
        return [_load(ProvisionVersion, r[0]) for r in rows]

    def provision_history(self, provision_id: str, *, build_id: str | None = None) -> list[ProvisionVersion]:
        key = provision_id.partition("#")[0]
        bid = self._build_id(key, build_id)
        if bid is None:
            return []
        with self._conn() as c:
            rows = c.execute("SELECT payload FROM versions WHERE build_id=? AND provision_id=? ORDER BY valid_from",
                             (bid, provision_id)).fetchall()
        return [_load(ProvisionVersion, r[0]) for r in rows]

    def versions(self, key: str, *, build_id: str | None = None) -> list[ProvisionVersion]:
        bid = self._build_id(key, build_id)
        if bid is None:
            return []
        with self._conn() as c:
            rows = c.execute("SELECT payload FROM versions WHERE build_id=? ORDER BY provision_id, valid_from",
                             (bid,)).fetchall()
        return [_load(ProvisionVersion, r[0]) for r in rows]

    def laws_in_force(self, day: date) -> list[LegalDocument]:
        out = []
        for doc in self.documents():
            if doc.is_consolidated:
                continue
            bid = self._build_id(doc.document_key, None)
            if bid is None:
                continue
            d = day.isoformat()
            with self._conn() as c:
                hit = c.execute("SELECT 1 FROM versions WHERE build_id=? AND valid_from<=? AND (valid_to IS NULL OR "
                                "valid_to>?) LIMIT 1", (bid, d, d)).fetchone()
            if hit:
                out.append(doc)
        return out

    def law_family(self, name: str) -> list[LegalDocument]:
        wanted = law_name(name)
        docs = [d for d in self.documents() if not d.is_consolidated and law_name(d.title) == wanted]
        return sorted(docs, key=lambda d: d.issued_on or date.min)

    # --- duyệt ---------------------------------------------------------------------------

    def add_review_item(self, item: ReviewItem, *, reopen: bool = False) -> None:
        """Thêm mục duyệt. Mục cùng id đã đóng: mở lại nếu `reopen` hoặc nếu lần đóng cuối là của hệ thống."""
        with self._conn() as c:
            row = c.execute("SELECT status FROM review_items WHERE review_id=?", (item.review_id,)).fetchone()
            if row is not None:
                if row[0] == "resolved":
                    last = c.execute("SELECT payload FROM decisions WHERE review_id=? ORDER BY seq DESC LIMIT 1",
                                     (item.review_id,)).fetchone()
                    by_system = last is not None and _load(ReviewDecision, last[0]).reviewer == "system"
                    if reopen or by_system:
                        opened = dataclasses.replace(item, status="open")
                        c.execute("UPDATE review_items SET status='open', payload=? WHERE review_id=?",
                                  (_dump(opened), item.review_id))
                return
            dup = c.execute("SELECT 1 FROM review_items WHERE status='open' AND kind=? AND document_key=? "
                            "AND operation_id IS ? AND provision_id IS ?",
                            (item.kind, item.document_key, item.operation_id, item.provision_id)).fetchone()
            if dup:
                return
            c.execute("INSERT INTO review_items VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (item.review_id, item.kind, item.document_key, item.operation_id, item.provision_id,
                       item.status, _dump(item)))

    def review_items(self, status: str | None = "open") -> list[ReviewItem]:
        sql = "SELECT payload FROM review_items" + (" WHERE status=?" if status else "") + " ORDER BY rowid"
        with self._conn() as c:
            rows = c.execute(sql, (status,) if status else ()).fetchall()
        return [_load(ReviewItem, r[0]) for r in rows]

    def review_item(self, review_id: str) -> ReviewItem | None:
        with self._conn() as c:
            row = c.execute("SELECT payload FROM review_items WHERE review_id=?", (review_id,)).fetchone()
        return _load(ReviewItem, row[0]) if row else None

    def resolve_review(self, decision: ReviewDecision) -> None:
        with self._conn() as c:
            row = c.execute("SELECT payload FROM review_items WHERE review_id=?", (decision.review_id,)).fetchone()
            if row is None:
                raise KeyError(decision.review_id)
            item = dataclasses.replace(_load(ReviewItem, row[0]), status="resolved")
            c.execute("UPDATE review_items SET status='resolved', payload=? WHERE review_id=?",
                      (_dump(item), decision.review_id))
            c.execute("INSERT INTO decisions (review_id, payload) VALUES (?, ?)", (decision.review_id, _dump(decision)))

    def decisions(self, review_id: str) -> list[ReviewDecision]:
        with self._conn() as c:
            rows = c.execute("SELECT payload FROM decisions WHERE review_id=? ORDER BY seq", (review_id,)).fetchall()
        return [_load(ReviewDecision, r[0]) for r in rows]


__all__ = ["LegalStore", "decode", "encode"]
