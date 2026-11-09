"""Văn bản sửa đổi -> danh sách chỉ dẫn có cấu trúc (ParsedDirective). Theo luật, không LLM.

Mỗi Điều có tiêu đề bắt đầu bằng hành động ("Sửa đổi, bổ sung ... của Luật X") là một nhóm chỉ dẫn cho
luật X. Trong Điều: mỗi khoản là một chỉ dẫn; khoản có điểm cấu trúc là "vỏ chứa" (các điểm là chỉ dẫn con,
kế thừa Điều/khoản nêu ở khoản). Điều không chia khoản: dòng thân đầu tiên (hoặc tiêu đề) là chỉ dẫn.
Một chỉ dẫn nêu nhiều đích được tách thành nhiều ParsedDirective; nội dung trích dẫn chia theo nhãn đơn vị.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from rag.legal.models import Address, OperationType, ParseStatus, Provision

_ACTION = re.compile(r"sửa\s+đổi\s*,\s*bổ\s+sung|sửa\s+đổi|bổ\s+sung|bãi\s+bỏ|thay\s+thế", re.IGNORECASE)
_ACTION_START = re.compile(r"^(?:sửa\s+đổi|bổ\s+sung|bãi\s+bỏ|thay\s+thế|thay\s+(?:cụm\s+)?từ)", re.IGNORECASE)
_TOKEN = re.compile(
    r"(?P<title>tên\s+điều)(?:\s+(?P<title_num>\d+[a-zđ]?)\b)?"
    r"|(?P<lead>đoạn\s+mở\s+đầu|khổ\s+đầu)"
    r"|điểm\s+(?P<point>[a-zđ]\d*)\b"
    r"|khoản\s+(?P<clause>\d+[a-zđ]?)\b"
    r"|điều\s+(?P<article>\d+[a-zđ]?)\b", re.IGNORECASE)
_UNSUPPORTED = re.compile(r"phụ\s+lục|biểu\s+thuế|\bbiểu\b|số\s+thứ\s+tự|danh\s+mục|\bmục\s+[IVXLC]+\b", re.IGNORECASE)
_PHRASE = r"[\"“](?P<old>.+?)[\"”]"
_REPLACE_TEXT = re.compile(
    r"thay(?:\s+thế)?\s+(?:cụm\s+)?(?:từ\s+ngữ|từ)\s+" + _PHRASE + r"\s+bằng\s+(?:cụm\s+)?(?:từ\s+ngữ\s+|từ\s+)?"
    r"[\"“](?P<new>.+?)[\"”](?P<scope>.*)$", re.IGNORECASE)
_DELETE_TEXT = re.compile(r"(?:bãi\s+bỏ|bỏ)\s+(?:cụm\s+)?(?:từ\s+ngữ|từ)\s+" + _PHRASE + r"(?P<scope>.*)$", re.IGNORECASE)
_MENTIONS_PHRASE = re.compile(r"cụm\s+từ|từ\s+ngữ", re.IGNORECASE)
_BULK = re.compile(r"một\s+số|toàn\s+bộ|các\s+điều|các\s+khoản|trong\s+(?:Bộ\s+)?luật", re.IGNORECASE)
_LABEL = re.compile(r"^\s*(?:\d+[a-zđ]?\.|[a-zđ]\d*\))\s+")
_LEVEL = {"article": 0, "clause": 1, "point": 2}
_KIND = {"article": "ARTICLE", "clause": "CLAUSE", "point": "POINT"}


@dataclass(frozen=True)
class ParsedDirective:
    source_locator: str
    source_address: Address
    source_span: tuple[int, int]
    sequence: int
    target_law_name: str | None
    target_law_number: str | None
    operation_type: OperationType
    target: Address | None
    anchor: Address | None
    new_text: str | None
    old_phrase: str | None
    parse_status: ParseStatus
    reasons: tuple[str, ...]


@dataclass
class _Tok:
    kind: str          # title | lead | point | clause | article
    value: str | None


@dataclass
class _Target:
    op: OperationType
    target: Address | None
    anchor: Address | None
    reasons: tuple[str, ...] = ()


def strip_quotes(text: str) -> str:
    text = text.strip()
    if text[:1] in ('"', "“"):
        text = text[1:]
    return re.sub(r"[\"”][.;,]?\s*$", "", text).strip()


def _tokens(text: str) -> list[_Tok]:
    out = []
    for m in _TOKEN.finditer(text):
        if m.group("title"):
            out.append(_Tok("title", m.group("title_num")))
        elif m.group("lead"):
            out.append(_Tok("lead", None))
        else:
            kind = next(k for k in ("point", "clause", "article") if m.group(k))
            out.append(_Tok(kind, m.group(kind).lower()))
    return out


def _split(tokens: list[_Tok]) -> tuple[list[_Tok], list[_Tok]]:
    """(đích, bổ ngữ): các token đầu cùng cấp là đích; phần còn lại (cấp cao hơn) là bổ ngữ."""
    if not tokens:
        return [], []
    if any(t.kind in ("title", "lead") for t in tokens):
        return [t for t in tokens if t.kind in ("title", "lead")], [t for t in tokens if t.kind not in ("title", "lead")]
    level = tokens[0].kind
    n = 0
    while n < len(tokens) and tokens[n].kind == level:
        n += 1
    return tokens[:n], tokens[n:]


def _groups(tokens: list[_Tok]) -> list[tuple[list[_Tok], list[_Tok]]]:
    """Tách danh sách đích thành nhóm, mỗi nhóm mang bổ ngữ riêng:
    "khoản 2 Điều 10 và khoản 3 Điều 11" -> [khoản 2 | Điều 10], [khoản 3 | Điều 11];
    "điểm b và điểm c khoản 4" -> [điểm b, điểm c | khoản 4]."""
    if not tokens or any(t.kind in ("title", "lead") for t in tokens):
        return [_split(tokens)]
    groups: list[list[_Tok]] = []
    cur: list[_Tok] = []
    for t in tokens:
        if cur:
            level = cur[0].kind
            quals = {x.kind for x in cur if x.kind != level}
            in_quals = cur[-1].kind != level
            if _LEVEL[t.kind] > _LEVEL[cur[-1].kind] or (in_quals and (t.kind == level or t.kind in quals)):
                groups.append(cur)
                cur = []
        cur.append(t)
    groups.append(cur)
    return [_split(g) for g in groups]


def _ctx(quals: list[_Tok]) -> dict[str, str]:
    ctx: dict[str, str] = {}
    for t in quals:
        if t.kind in ("clause", "article") and t.kind not in ctx:
            ctx[t.kind] = t.value
    return ctx


def _address(tok: _Tok, *ctxs: dict[str, str], inherited: Address | None = None) -> Address | None:
    def get(level: str) -> str | None:
        for c in ctxs:
            if level in c:
                return c[level]
        if inherited is not None:
            return inherited.article if level == "article" else inherited.clause
        return None

    if tok.kind == "title":
        art = tok.value or get("article")
        return Address(art, part="title") if art else None
    if tok.kind == "lead":
        clause, art = get("clause"), get("article")
        return Address(art, clause, part="lead_in") if art and clause else None
    if tok.kind == "article":
        return Address(tok.value)
    art = get("article")
    if tok.kind == "clause":
        return Address(art, tok.value) if art else None
    clause = get("clause")
    return Address(art, clause, tok.value) if art and clause else None


def _op_for(action: str, tok: _Tok, insert: bool) -> OperationType:
    if tok.kind == "title":
        return "REPLACE_ARTICLE_TITLE"
    if tok.kind == "lead":
        return "REPLACE_CLAUSE_LEAD_IN"
    kind = _KIND[tok.kind]
    act = re.sub(r"\s+", " ", action.casefold())
    if act == "bãi bỏ":
        return f"DELETE_{kind}"  # type: ignore[return-value]
    if act == "bổ sung" and insert:
        return f"INSERT_{kind}"  # type: ignore[return-value]
    if act == "bổ sung":
        return f"INSERT_{kind}"  # type: ignore[return-value]
    return f"REPLACE_{kind}"  # type: ignore[return-value]


def _parse_header(header: str, inherited: Address | None) -> tuple[list[_Target], str | None, str | None, ParseStatus | None]:
    """-> (đích, old_phrase, new_phrase, trạng thái ép buộc nếu có)."""
    if _UNSUPPORTED.search(header):
        arts = [t for t in _tokens(header) if t.kind == "article"]
        target = Address(arts[-1].value) if arts else (Address(inherited.article) if inherited else None)
        return [_Target("UNSUPPORTED", target, None, ("operation.unsupported_table_or_appendix",))], None, None, "unsupported"

    m = _REPLACE_TEXT.search(header) or _DELETE_TEXT.search(header)
    if m:
        new_phrase = m.groupdict().get("new") or ""
        scope = m.group("scope")
        groups = [g for g in _groups(_tokens(scope)) if g[0]]
        if not groups:
            reason = "operation.bulk_text_scope" if _BULK.search(scope) or not scope.strip() else "operation.text_scope_unknown"
            return [_Target("REPLACE_TEXT", None, None, (reason,))], m.group("old"), new_phrase, "partial"
        out = []
        for targets, quals in groups:
            ctx = _ctx(quals)
            for tok in targets:
                addr = _address(tok, ctx, inherited=inherited)
                out.append(_Target("REPLACE_TEXT", addr, None, () if addr else ("operation.target_unresolved",)))
        return out, m.group("old"), new_phrase, None
    if _MENTIONS_PHRASE.search(header):
        # có nhắc "cụm từ" nhưng không đúng mẫu thay/bãi bỏ cụm từ: không đoán thành sửa/xoá cả đơn vị
        return [_Target("REPLACE_TEXT", None, None, ("operation.phrase_wording_unparsed",))], None, None, "partial"

    actions = list(_ACTION.finditer(header))
    if not actions:
        return [], None, None, "failed"
    segments = []
    for i, a in enumerate(actions):
        rest = header[a.end(): actions[i + 1].start() if i + 1 < len(actions) else len(header)]
        parts = re.split(r"\bvào\s+sau\b", rest, maxsplit=1, flags=re.IGNORECASE)
        sep = len(parts) == 2
        new_part, anchor_part = (parts[0], parts[1]) if sep else (rest, "")
        new_groups = [(t, _ctx(q)) for t, q in _groups(_tokens(new_part))]
        anchor_targets, anchor_quals = _split(_tokens(anchor_part))
        segments.append((a.group(0), new_groups, anchor_targets[:1], _ctx(anchor_quals), bool(sep)))
    last = segments[-1]
    trailing: dict[str, str] = dict(last[3] if last[4] else (last[1][-1][1] if last[1] else {}))

    out: list[_Target] = []
    for action, new_groups, anchor_targets, anchor_ctx, is_insert in segments:
        anchor = _address(anchor_targets[0], anchor_ctx, trailing, inherited=inherited) if anchor_targets else None
        for new_targets, new_ctx in new_groups:
            for tok in new_targets:
                ctxs = [new_ctx, anchor_ctx, trailing]
                if tok.kind == "lead":
                    # đoạn mở đầu khoản N: khoản lấy từ bổ ngữ ngay sau
                    ctxs = [new_ctx, trailing]
                addr = _address(tok, *ctxs, inherited=inherited)
                op = _op_for(action, tok, is_insert)
                reasons: tuple[str, ...] = ()
                if addr is None:
                    reasons = ("operation.target_unresolved",)
                elif op.startswith("INSERT") and anchor is None:
                    reasons = ("operation.insert_anchor_missing",)
                out.append(_Target(op, addr, anchor if op.startswith("INSERT") else None, reasons))
    if not out:
        return [], None, None, "failed"
    return out, None, None, None


def _label_pattern(target: _Target) -> re.Pattern[str] | None:
    a = target.target
    if a is None:
        return None
    if target.op in ("REPLACE_ARTICLE_TITLE", "REPLACE_ARTICLE", "INSERT_ARTICLE"):
        return re.compile(rf"^\s*Điều\s+{re.escape(a.article)}\s*[.:]")
    if target.op in ("REPLACE_CLAUSE", "INSERT_CLAUSE", "REPLACE_CLAUSE_LEAD_IN"):
        return re.compile(rf"^\s*{re.escape(a.clause or '')}\.\s")
    if target.op in ("REPLACE_POINT", "INSERT_POINT"):
        return re.compile(rf"^\s*{re.escape(a.point or '')}\)\s")
    return None


def _assign_content(targets: list[_Target], content: str) -> list[tuple[str | None, tuple[str, ...]]]:
    """Nội dung mới cho từng đích (None cho DELETE/REPLACE_TEXT/UNSUPPORTED)."""
    needs = [t.op not in ("DELETE_ARTICLE", "DELETE_CLAUSE", "DELETE_POINT", "REPLACE_TEXT", "UNSUPPORTED")
             for t in targets]
    result: list[tuple[str | None, tuple[str, ...]]] = [(None, ())] * len(targets)
    idxs = [i for i, n in enumerate(needs) if n]
    if not idxs:
        return result
    if not content.strip():
        for i in idxs:
            result[i] = (None, ("operation.missing_new_text",))
        return result
    lines = strip_quotes(content).split("\n")

    def finish(i: int, text: str) -> tuple[str, tuple[str, ...]]:
        if targets[i].op == "REPLACE_ARTICLE_TITLE":
            first = text.split("\n")[0]
            m = re.match(r"^\s*Điều\s+\d+[a-zđ]?\s*[.:]\s*(.*)$", first)
            return (m.group(1).strip() if m else first.strip()), ()
        return text.strip(), ()

    if len(idxs) == 1:
        result[idxs[0]] = finish(idxs[0], "\n".join(lines))
        return result
    starts = []
    pos = 0
    for i in idxs:
        pattern = _label_pattern(targets[i])
        found = next((j for j in range(pos, len(lines)) if pattern and pattern.match(lines[j])), None)
        if found is None:
            for k in idxs:
                result[k] = (None, ("operation.cannot_split_content",))
            return result
        starts.append(found)
        pos = found + 1
    for n, i in enumerate(idxs):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        text = "\n".join(lines[starts[n]:end])
        if targets[i].op == "REPLACE_CLAUSE_LEAD_IN":
            body = text.split("\n")
            cut = next((j for j in range(1, len(body)) if re.match(r"^\s*[a-zđ]\d*\)\s", body[j])), len(body))
            text = "\n".join(body[:cut])
        result[i] = finish(i, text)
    return result


def _target_law(title: str) -> tuple[str | None, str | None]:
    idx = max(title.rfind("của Luật"), title.rfind("của Bộ luật"))
    if idx < 0:
        return None, None
    name = title[idx + 4:].strip().rstrip(".;")
    m = re.match(r"^(.*?)\s+số\s+(\d+/\d{4}/[A-Z0-9Đ]+)\s*$", name)
    if not m:
        return name, None
    bare = m.group(1).strip()
    return (None if bare.casefold() in ("luật", "bộ luật") else bare), m.group(2)


def _header_and_content(text: str) -> tuple[str, str]:
    lines = text.split("\n")
    return _LABEL.sub("", lines[0]).strip(), "\n".join(lines[1:])


def parse_directives(provisions: Sequence[Provision], *,
                     default_target: tuple[str | None, str | None] = (None, None)) -> list[ParsedDirective]:
    articles = [p for p in provisions if p.kind == "article"]
    titles = {p.address.article: p.text for p in provisions if p.kind == "article_title"}
    out: list[ParsedDirective] = []

    def emit(unit: Provision, locator: str, header: str, content: str, inherited: Address | None,
             law: tuple[str | None, str | None]) -> None:
        targets, old, new_phrase, forced = _parse_header(header, inherited)
        if forced == "failed":
            out.append(ParsedDirective(locator, unit.address, unit.span, len(out), law[0], law[1], "UNSUPPORTED",
                                       None, None, None, None, "failed", ("operation.unparsed_header",)))
            return
        contents = _assign_content(targets, content)
        for t, (text, extra) in zip(targets, contents):
            reasons = t.reasons + extra
            if forced == "unsupported":
                status: ParseStatus = "unsupported"
            elif forced == "partial" or reasons:
                status = "failed" if "operation.target_unresolved" in reasons else "partial"
            else:
                status = "exact"
            out.append(ParsedDirective(locator, unit.address, unit.span, len(out), law[0], law[1], t.op, t.target,
                                       t.anchor, new_phrase if t.op == "REPLACE_TEXT" else text, old, status,
                                       tuple(reasons)))

    for art in articles:
        title = titles.get(art.address.article, "")
        if not _ACTION_START.match(title):
            continue
        law = _target_law(title)
        if law == (None, None):
            law = default_target
        if law == (None, None):
            continue
        clauses = [p for p in provisions if p.kind == "clause" and p.parent_id == art.provision_id]
        a_no = art.address.article
        if not clauses:
            body = art.text.split("\n")[1:]
            if body and _ACTION.search(body[0]):
                header, content = body[0].strip(), "\n".join(body[1:])
            else:
                header, content = title, "\n".join(body)
            emit(art, f"Điều {a_no}", header, content, None, law)
            continue
        for cl in clauses:
            header, content = _header_and_content(cl.text)
            points = [p for p in provisions if p.kind == "point" and p.parent_id == cl.provision_id]
            locator = f"Điều {a_no} > {cl.address.clause}"
            if not points:
                if _ACTION.search(header) or _REPLACE_TEXT.search(header):
                    emit(cl, locator, header, content, None, law)
                continue
            _, quals = _split(_tokens(header))
            ctx = _ctx(quals) or _ctx(_tokens(header))
            inherited = Address(ctx["article"], ctx.get("clause")) if "article" in ctx else None
            for pt in points:
                p_header, p_content = _header_and_content(pt.text)
                emit(pt, f"{locator} > {pt.address.point}", p_header, p_content, inherited, law)
    return out


__all__ = ["ParsedDirective", "parse_directives", "strip_quotes"]
