"""Reject incomplete schemas, invented IDs and quotes before state changes."""

from __future__ import annotations

import re

from rag.agent.contracts import Assessment, Claim, OutputError, Requirement


def obj(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise OutputError(f"Expected object keys: {', '.join(keys)}")
    return value


def text(value, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise OutputError("Expected a bounded nonempty string")
    return value.strip()


def items(value, maximum):
    if not isinstance(value, list) or len(value) > maximum:
        raise OutputError("Invalid list size")
    return value


def identifiers(value, allowed, *, nonempty=False):
    values = items(value, len(allowed))
    if any(not isinstance(v, str) or v not in allowed for v in values):
        raise OutputError("Unknown identifier")
    if len(set(values)) != len(values) or (nonempty and not values):
        raise OutputError("Duplicate or empty identifiers")
    return tuple(values)


def parse_plan(data, maximum):
    obj(data, ("requirements", "clarification"))
    clarification = data["clarification"]
    if clarification is not None:
        clarification = text(clarification)
    requirements = []
    for i, row in enumerate(items(data["requirements"], maximum), 1):
        obj(row, ("id", "question", "depends_on"))
        if row["id"] != f"R{i}":
            raise OutputError("Requirements must use ordered R identifiers")
        dependencies = identifiers(row["depends_on"], {r.id for r in requirements})
        requirements.append(Requirement(row["id"], text(row["question"]), dependencies))
    if not requirements and clarification is None:
        raise OutputError("Empty plan without clarification")
    return requirements, clarification


def parse_queries(value, requirement_ids, maximum):
    queries = []
    for row in items(value, maximum):
        obj(row, ("requirement_id", "query"))
        if not isinstance(row["requirement_id"], str) or row["requirement_id"] not in requirement_ids:
            raise OutputError("Query has an unknown requirement")
        queries.append((row["requirement_id"], text(row["query"])))
    return queries


def find_soft_span(quote: str, text: str) -> tuple[int, int] | None:
    """Find the exact or normalized character span of quote within text."""
    if not quote or not text:
        return None
    quote = quote.strip()
    if not quote:
        return None

    # 1. Exact match
    if "[...]" not in quote:
        pos = text.find(quote)
        if pos != -1:
            return pos, pos + len(quote)

    # 2. Strip surrounding quotes and punctuation
    stripped = quote.strip(" \t\r\n\"'“”‘’«».,;:!?…-")
    if stripped and len(stripped) >= 3 and "[...]" not in stripped:
        pos = text.find(stripped)
        if pos != -1:
            return pos, pos + len(stripped)

    # 3. Normalized whitespace (map indices back to original text)
    clean_chars = []
    orig_indices = []
    in_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if not in_space:
                clean_chars.append(" ")
                orig_indices.append(i)
                in_space = True
        else:
            clean_chars.append(ch)
            orig_indices.append(i)
            in_space = False

    if clean_chars:
        clean_text = "".join(clean_chars)
        clean_quote = " ".join((stripped or quote).split())

        if clean_quote and len(clean_quote) >= 3:
            # 3a. Exact whitespace-collapsed match
            pos = clean_text.find(clean_quote)
            if pos != -1:
                start_orig = orig_indices[pos]
                end_orig = orig_indices[pos + len(clean_quote) - 1] + 1
                return start_orig, end_orig

            # 3b. Case-insensitive whitespace-collapsed match
            pos = clean_text.lower().find(clean_quote.lower())
            if pos != -1:
                start_orig = orig_indices[pos]
                end_orig = orig_indices[pos + len(clean_quote) - 1] + 1
                return start_orig, end_orig

            # 3c. Ellipsis in quote: split by ..., …, [...]
            parts = re.split(r"\s*(?:\.\.\.|…|\[\.\.\.\])\s*", quote)
            parts = [p.strip(" \t\r\n\"'“”‘’«».,;:!?…-") for p in parts if len(p.strip(" \t\r\n\"'“”‘’«».,;:!?…-")) >= 5]
            if len(parts) >= 2:
                first = " ".join(parts[0].split())
                last = " ".join(parts[-1].split())
                p_first = clean_text.lower().find(first.lower())
                if p_first != -1:
                    p_last = clean_text.lower().find(last.lower(), p_first + len(first))
                    if p_last != -1 and (p_last + len(last) - p_first) <= 2000:
                        start_orig = orig_indices[p_first]
                        end_orig = orig_indices[p_last + len(last) - 1] + 1
                        return start_orig, end_orig

    return None


def parse_quotes(value, bundle, allowed=None):
    evidence_ids = []
    quotes = {}
    intervals = {}
    for row in items(value, max(1, len(bundle)) * 4):
        obj(row, ("id", "quote"))
        eid = row["id"]
        if not isinstance(eid, str) or eid not in bundle or (allowed is not None and eid not in allowed):
            raise OutputError("Quote points outside the supplied evidence bundle")
        raw_quote = text(row["quote"], 2000)
        span = find_soft_span(raw_quote, bundle[eid].text)
        if span is None:
            raise OutputError("Quote is not an exact source span")
        start, end = span
        old_start, old_end = intervals.get(eid, (start, end))
        candidate_interval = (min(start, old_start), max(end, old_end))
        a, b = candidate_interval
        # Several premises may come from separate clauses in the same article.
        # Keep their enclosing ORIGINAL span, never concatenate a fabricated quote.
        if "[...]" in bundle[eid].text[a:b]:
            raise OutputError("A citation cannot bridge an omitted source segment")
        intervals[eid] = candidate_interval
        quotes[eid] = bundle[eid].text[a:b]
        if eid not in evidence_ids:
            evidence_ids.append(eid)
    return tuple(evidence_ids), quotes


def parse_assessment(data, requirements, bundle, available_xrefs, limit):
    obj(data, ("assessments", "followup_queries", "xref_ids"))
    req_ids = {r.id for r in requirements}
    seen, assessments = set(), []
    statuses = {"supported", "partial", "missing", "conflicting", "missing_user_fact"}
    for row in items(data["assessments"], len(requirements)):
        obj(row, ("requirement_id", "status", "evidence", "reason"))
        rid = row["requirement_id"]
        if not isinstance(rid, str) or rid not in req_ids or rid in seen:
            raise OutputError("Missing, duplicate or unknown assessment")
        if not isinstance(row["status"], str) or row["status"] not in statuses:
            raise OutputError("Invalid assessment status")
        eids, _ = parse_quotes(row["evidence"], bundle)
        if row["status"] in {"supported", "partial", "conflicting"} and not eids:
            raise OutputError("Assessment without supporting source spans")
        seen.add(rid)
        assessments.append(Assessment(rid, row["status"], eids, text(row["reason"])))
    if seen != req_ids:
        raise OutputError("Assessments must cover every requirement")
    queries = parse_queries(data["followup_queries"], req_ids, limit)
    xrefs = identifiers(data["xref_ids"], set(available_xrefs))
    return assessments, queries, xrefs


def parse_claims(data, requirements, bundle):
    obj(data, ("claims",))
    req_ids = {r.id for r in requirements}
    claims = []
    for row in items(data["claims"], 24):
        obj(row, ("text", "evidence_ids", "requirement_ids"))
        content = text(row["text"], 3000)
        if re.search(r"<\s*/?\s*[a-zA-Z]|!\[|javascript\s*:", content, re.I):
            raise OutputError("Claims may not inject HTML or remote images")
        if re.search(r"\[\s*\d+(?:\s*[,;]\s*\d+)*\s*\]", content):
            content = re.sub(r"\[\s*\d+(?:\s*[,;]\s*\d+)*\s*\]", "", content)
            content = re.sub(r"\s+([.,;:!?])", r"\1", content)
            content = re.sub(r"\s{2,}", " ", content).strip()
        if not content:
            continue
        eids = identifiers(row["evidence_ids"], set(bundle), nonempty=True)
        rids = identifiers(row["requirement_ids"], req_ids, nonempty=True)
        claims.append(Claim(content, eids, rids))
    return claims


def parse_verification(data, requirements, claims, bundle, limit, warnings=None):
    obj(data, ("claims", "requirements", "facts_preserved", "scope_respected", "followup_queries"))
    for key in ("facts_preserved", "scope_respected"):
        if type(data[key]) is not bool:
            raise OutputError("Verification flags must be booleans")
    verdicts, quotes = {}, {}
    for row in items(data["claims"], len(claims)):
        if isinstance(row, dict) and "evidence" not in row:
            # mô hình đôi khi bỏ khoá "evidence" (thường ở khẳng định không được ủng hộ): coi là không có trích dẫn
            # -> khẳng định không qua kiểm chứng; không bỏ cả câu trả lời vì một khoá thiếu
            row = {**row, "evidence": []}
        obj(row, ("index", "supported", "reason", "evidence"))
        idx = row["index"]
        if type(idx) is not int or idx not in range(len(claims)) or idx in verdicts:
            raise OutputError("Invalid claim index")
        if type(row["supported"]) is not bool:
            raise OutputError("Claim verdict must be boolean")
        eids, spans = parse_quotes(row["evidence"], bundle, claims[idx].evidence_ids)
        if row["supported"] and set(eids) != set(claims[idx].evidence_ids):
            verdicts[idx] = False
        else:
            verdicts[idx] = row["supported"]
        text(row["reason"])
        quotes[idx] = spans
    if set(verdicts) != set(range(len(claims))):
        raise OutputError("Missing claim verdict")
    req_ids = {r.id for r in requirements}
    coverage = {}
    for row in items(data["requirements"], len(req_ids)):
        obj(row, ("id", "covered"))
        rid = row["id"]
        if not isinstance(rid, str) or rid not in req_ids or rid in coverage or type(row["covered"]) is not bool:
            raise OutputError("Invalid requirement verdict")
        coverage[rid] = row["covered"]
    if set(coverage) != req_ids:
        raise OutputError("Missing requirement verdict")
    try:
        queries = parse_queries(data["followup_queries"], req_ids, limit)
    except OutputError:
        # Optional action suggestions must never invalidate already verified
        # claims. Discard malformed actions, record degradation, and do not run
        # any unvalidated query. Core verdict/quote errors still fail closed.
        queries = []
        if warnings is not None:
            warnings.append("invalid_verifier_followups_discarded")
    return verdicts, coverage, quotes, queries
