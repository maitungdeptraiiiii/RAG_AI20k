"""Text2Cypher có rào chắn cho agent trên đồ thị hợp đồng (spec 2026-11-16-contract-graph-agent §5.8).

LLM viết câu Cypher; ứng dụng (không phải model) quyết định có chạy hay không:
1. `check_cypher` kiểm tĩnh: chỉ đọc (không CREATE/MERGE/SET/DELETE/REMOVE/DROP/CALL/LOAD/USE/FOREACH…), chỉ nhãn và
   loại cạnh của đồ thị hợp đồng (không đọc đồ thị luật), mọi mệnh đề MATCH phải neo `contract_id: $cid` ngay trong
   mẫu và là MỘT đường liền (không dấu phẩy, không truy vấn con / mẫu trong biểu thức). Vì cạnh của đồ thị hợp đồng
   không bao giờ nối sang hợp đồng khác, mẫu liền có neo $cid chỉ chạm được nút của hợp đồng đó.
2. Chạy trong giao dịch chỉ đọc, có thời hạn và giới hạn số dòng (`ContractGraphStore.run_read`).
3. `clean_rows` kiểm lại kết quả: nút mang `contract_id` khác -> từ chối; bỏ `contract_id` / `build_id` khỏi đầu ra.
Rủi ro còn lại: giá trị vô hướng (count, chuỗi) không kiểm lại được ở bước 3 — lớp 1 là lớp chặn chính."""
from __future__ import annotations

import re

from rag.contracts.graph.build import SCHEMA

MAX_QUERY = 2000
MAX_ROWS = 50
TIMEOUT_S = 5.0
_LABELS = frozenset(SCHEMA["nodes"]) | {"CGNode"}
_RELS = frozenset(SCHEMA["relations"])

_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_STRING = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_FORBIDDEN = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD|CALL|USE|FOREACH|GRANT|DENY|REVOKE|"
                        r"ALTER|SHOW|TERMINATE|START|STOP|ENABLE|IMPORT)\b", re.I)
_SUBQUERY = re.compile(r"\b(EXISTS|COUNT|COLLECT)\s*\{|\[\s*\(", re.I)
_NODE_LABELS = re.compile(r"\(\s*[A-Za-z_]\w*\s*((?::\s*`?[A-Za-z_]\w*`?\s*)+)|\(\s*((?::\s*`?[A-Za-z_]\w*`?\s*)+)")
_WHERE_LABEL = re.compile(r"(?<!\[)\b[A-Za-z_]\w*:([A-Z]\w*)")    # n:Unit trong WHERE; bỏ [e:AMENDS]
_REL_TYPES = re.compile(r"\[\s*[A-Za-z_]?\w*\s*:\s*([^\]*{]+)")
_MATCH = re.compile(r"\b(?:OPTIONAL\s+)?MATCH\b", re.I)
_CLAUSE_END = re.compile(r"\b(WHERE|RETURN|WITH|MATCH|OPTIONAL|UNWIND|ORDER|UNION|LIMIT|SKIP)\b", re.I)
_LITERAL_CID = re.compile(r"contract_id\s*(?::|=|<>|IN)(?!\s*\$cid\b)", re.I)


def _strip(query: str) -> str:
    """Bỏ chú thích; thay chuỗi bằng '' để từ khóa trong chuỗi không bị tính."""
    return _STRING.sub("''", _COMMENT.sub(" ", query))


def _top_level_comma(text: str) -> bool:
    depth = 0
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            return True
    return False


def _names(raw: str) -> list[str]:
    return [x.strip().strip("`") for x in re.split(r"[:|&!]", raw) if x.strip().strip("`")]


def check_cypher(query: str) -> str | None:
    """None nếu được chạy; ngược lại một câu giải thích để agent sửa câu truy vấn."""
    if not isinstance(query, str) or not query.strip():
        return "câu truy vấn rỗng"
    if len(query) > MAX_QUERY:
        return f"câu truy vấn dài quá {MAX_QUERY} ký tự"
    raw = _COMMENT.sub(" ", query)
    if _LITERAL_CID.search(raw):
        return "contract_id chỉ được so với tham số $cid"
    q = _strip(query)
    m = _FORBIDDEN.search(q)
    if m:
        word = m.group(1).upper()
        kind = {"CALL": "CALL", "LOAD": "LOAD"}.get(word, "ghi / quản trị")
        return f"không được dùng {word} ({kind}): chỉ được đọc đồ thị hợp đồng"
    if _SUBQUERY.search(q):
        return "không dùng truy vấn con hay mẫu trong biểu thức (EXISTS{}, COUNT{}, [(…)|…]); dùng MATCH / OPTIONAL MATCH"
    for m in _NODE_LABELS.finditer(q):
        for name in _names(m.group(1) or m.group(2)):
            if name not in _LABELS:
                return f"nhãn {name} không thuộc đồ thị hợp đồng; được dùng: {sorted(_LABELS)}"
    for m in _WHERE_LABEL.finditer(q):
        if m.group(1) not in _LABELS:
            return f"nhãn {m.group(1)} không thuộc đồ thị hợp đồng"
    for m in _REL_TYPES.finditer(q):
        for name in _names(m.group(1)):
            if name not in _RELS:
                return f"loại cạnh {name} không thuộc đồ thị hợp đồng; được dùng: {sorted(_RELS)}"
    problem = _check_anchoring(q)
    if problem:
        return problem
    if not re.search(r"\bRETURN\b", q, re.I):
        return "thiếu RETURN"
    return None


_CLAUSE = re.compile(r"\b(?:OPTIONAL\s+)?MATCH\b|\bWITH\b", re.I)
_VARS = re.compile(r"[(\[]\s*([A-Za-z_]\w*)")
_ITEM = re.compile(r"\s*([A-Za-z_]\w*)\s*(?:AS\s+([A-Za-z_]\w*)\s*)?$", re.I)


def _split_top(text: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    return parts + [cur]


def _check_anchoring(q: str) -> str | None:
    """Đi lần lượt MATCH / WITH. Một MATCH hợp lệ khi mẫu (một đường liền) có `$cid` hoặc chứa một biến đã neo: cạnh
    của đồ thị hợp đồng không nối sang hợp đồng khác, nên cả đường nằm trong hợp đồng. Mọi biến của mẫu hợp lệ thành
    biến đã neo. WITH chỉ giữ biến chiếu nguyên dạng (`x` hoặc `x AS y`); biểu thức, gộp nhóm -> mất neo."""
    clauses = list(_CLAUSE.finditer(q))
    if not any("MATCH" in m.group(0).upper() for m in clauses):
        return "cần ít nhất một MATCH neo theo hợp đồng: MATCH (x:Nhãn {contract_id: $cid}) …"
    anchored: set[str] = set()
    for m in clauses:
        end = _CLAUSE_END.search(q, m.end())
        body = q[m.end():end.start() if end else len(q)]
        if m.group(0).upper().startswith("WITH"):
            keep = set()
            for item in _split_top(body):
                got = _ITEM.match(item)
                if got and got.group(1) in anchored:
                    keep.add(got.group(2) or got.group(1))
            anchored = keep
            continue
        if _top_level_comma(body):
            return "mỗi MATCH chỉ một mẫu liền, không nối bằng dấu phẩy; dùng MATCH riêng có $cid"
        names = set(_VARS.findall(body))
        if "$cid" not in body and not names & anchored:
            return ("mỗi MATCH phải neo {contract_id: $cid} ngay trong mẫu (không phải trong WHERE), "
                    "hoặc đi tiếp từ một biến đã neo")
        anchored |= names
    return None


def clean_rows(rows: list, contract_id: str) -> list:
    """Từ chối nếu có nút của hợp đồng khác; bỏ contract_id / build_id khỏi mọi dict."""
    def walk(v):
        if isinstance(v, dict):
            if "contract_id" in v and v["contract_id"] != contract_id:
                raise ValueError("kết quả có nút của hợp đồng khác")
            return {k: walk(x) for k, x in v.items() if k not in ("contract_id", "build_id")}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v
    return [walk(r) for r in rows]


__all__ = ["MAX_ROWS", "TIMEOUT_S", "check_cypher", "clean_rows"]
