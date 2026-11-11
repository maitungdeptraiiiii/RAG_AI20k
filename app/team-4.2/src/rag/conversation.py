"""Bounded conversation memory shared by normal RAG and Think.

User statements retain provenance and order; assistant text is reference context,
never a source of legal evidence. No model-generated summary overwrites history.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from threading import RLock
from time import monotonic

MAX_TURNS = 64
MAX_QUERY_CHARS = 8000
MAX_ANSWER_CHARS = 16000
MAX_HISTORY_CHARS = 128000


def normalize_history(history):
    from rag.generate.style import present_answer
    rows = []
    for row in history or []:
        if not isinstance(row, dict) or not isinstance(row.get("query"), str):
            continue
        if not row["query"].strip():
            continue
        answer = row.get("answer", "")
        if isinstance(answer, str):
            answer = present_answer(answer).text
        rows.append({
            "turn_id": str(row.get("turn_id") or "")[:128],
            "query": row["query"][:MAX_QUERY_CHARS],
            "answer": answer[:MAX_ANSWER_CHARS] if isinstance(answer, str) else "",
            "answer_truncated": bool(row.get("answer_truncated")) or
                                (isinstance(answer, str) and len(answer) > MAX_ANSWER_CHARS),
            "truncated": bool(row.get("truncated")) or len(row["query"]) > MAX_QUERY_CHARS
                         or (isinstance(answer, str) and len(answer) > MAX_ANSWER_CHARS),
        })
    trimmed = len(rows) > MAX_TURNS
    rows = rows[-MAX_TURNS:]
    # Preserve older user statements before spending storage on assistant prose.
    answer_budget = 64000
    for i in range(len(rows) - 1, -1, -1):
        row = rows[i]
        answer = row["answer"][:answer_budget] if i >= len(rows) - 8 else ""
        row["answer_truncated"] |= len(answer) < len(row["answer"])
        row["answer"] = answer
        answer_budget -= len(answer)
    size = sum(len(r["query"]) + len(r["answer"]) for r in rows)
    while len(rows) > 1 and size > MAX_HISTORY_CHARS:
        removed = rows.pop(0)
        size -= len(removed["query"]) + len(removed["answer"])
        trimmed = True
    if rows and trimmed:
        rows[0]["truncated"] = True
    return rows


def conversation_context(history):
    """Keep older user facts separate from recent, unverified assistant answers.

Budgets are character bounds (conservative payload limits, not token counts).
Whole user statements are kept; overflow is explicit rather than silently
claiming complete recall. Later corrections remain visible alongside originals.
"""
    rows = normalize_history(history)
    statements, recent = [], []
    used = 0
    truncated = any(row["truncated"] for row in rows)
    for i in range(len(rows) - 1, -1, -1):
        row = rows[i]
        if used + len(row["query"]) > 24000:
            truncated = True
            break
        statements.append({"turn_id": row["turn_id"] or f"history-{i + 1}",
                           "order": i + 1, "text": row["query"], "origin": "user"})
        used += len(row["query"])
    used = 0
    for i in range(len(rows) - 1, max(-1, len(rows) - 9), -1):
        row = rows[i]
        remaining = 24000 - used
        answer = row["answer"][:max(0, remaining)]
        if len(answer) < len(row["answer"]):
            truncated = True
        recent.append({"turn_id": row["turn_id"] or f"history-{i + 1}",
                       "query": row["query"], "assistant_context_unverified": answer,
                       "answer_truncated": row["answer_truncated"] or len(answer) < len(row["answer"])})
        used += len(answer)
    return {"user_statements": list(reversed(statements)),
            "recent_turns": list(reversed(recent)), "truncated": truncated,
            "assistant_history_truncated": len(rows) > 8 or any(r["answer_truncated"] for r in rows),
            "policy": "User statements are attributed context, not legal evidence. Resolve topic, "
                      "corrections and open questions against the current message. Do not carry "
                      "unrelated topics forward. Assistant answers are unverified reference context. "
                      "If a required antecedent is missing or ambiguous, ask instead of guessing."}


def masked_history(history, state):
    from rag.quality.pii import mask_text
    return [{**row, **{key: mask_text(row[key], state=state).masked_text
                       for key in ("query", "answer")}}
            for row in normalize_history(history)]


class ConversationBusy(RuntimeError):
    pass


@dataclass
class _Session:
    turns: list = field(default_factory=list)
    touched: float = field(default_factory=monotonic)
    busy: bool = False


class ConversationStore:
    """Single-process RAM store. UI history bootstraps after expiry/restart.

    An active session cannot be evicted or run concurrently: responses and PII
    state must remain ordered across mode switches. No extra external API calls.
    """
    def __init__(self, max_sessions=500, ttl_seconds=7200):
        self.max_sessions, self.ttl = max_sessions, ttl_seconds
        self._sessions = OrderedDict()
        self._lock = RLock()

    def begin(self, session_id, bootstrap=None):
        if not session_id:
            return normalize_history(bootstrap)
        with self._lock:
            now = monotonic()
            for key, value in list(self._sessions.items()):
                if not value.busy and now - value.touched > self.ttl:
                    del self._sessions[key]
            session = self._sessions.get(session_id)
            if session is not None and session.busy:
                raise ConversationBusy("Phiên chat đang xử lý một câu hỏi. Vui lòng chờ hoàn tất.")
            if session is None:
                while len(self._sessions) >= self.max_sessions:
                    idle = next((k for k, v in self._sessions.items() if not v.busy), None)
                    if idle is None:
                        raise ConversationBusy("Có quá nhiều phiên đang xử lý. Vui lòng thử lại.")
                    del self._sessions[idle]
                session = _Session(normalize_history(bootstrap))
                self._sessions[session_id] = session
            session.busy, session.touched = True, now
            self._sessions.move_to_end(session_id)
            return [dict(row) for row in session.turns]

    def remember(self, session_id, turn_id, query, response):
        if not session_id or response.get("error") or response.get("status") == "error":
            return
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            row = {"turn_id": turn_id or "", "query": query, "answer": response.get("answer", "")}
            # Idempotent completion/retry of a UI turn.
            existing = next((i for i, r in enumerate(session.turns)
                             if turn_id and r["turn_id"] == turn_id), None)
            if existing is not None:
                session.turns[existing] = row
            else:
                session.turns.append(row)
            session.turns = normalize_history(session.turns)
            session.touched = monotonic()

    def release(self, session_id):
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.busy, session.touched = False, monotonic()
