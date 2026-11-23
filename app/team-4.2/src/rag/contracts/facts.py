"""Thông tin nền của hợp đồng, trích theo lô trên toàn bộ hợp đồng (spec 2026-11-13 §4).

Mỗi giá trị phải kèm trích dẫn có thật trong hợp đồng; trích dẫn không khớp -> bỏ giá trị (không đoán). Mọi ứng viên
của mọi lô được giữ ở `facts["candidates"]`; bảng xác minh (verify.py) dựng từ đó.

Các lô chạy TUẦN TỰ: lô sau nhận danh sách bên mà các lô trước đã trích (`known_parties`) để không trích lại.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any, Sequence

from rag.contracts.batches import Batch, make_batches, run_batches
from rag.contracts.llm_json import ContractAIError, ask_json, quote_ok
from rag.contracts.models import Contract
from rag.contracts.verify import all_specs, normalize_value

FACTS_PROMPT = """Bạn đọc MỘT PHẦN của một hợp đồng tiếng Việt (các đơn vị có uid trong "units") và trích thông tin nền.
"context" và "references" là đoạn khác của cùng hợp đồng, chỉ để HIỂU (định nghĩa, các bên, dẫn chiếu): KHÔNG trích
giá trị nào từ chúng — phần đó đã được đọc ở lượt khác.
Trả JSON:
{"type": "loại hợp đồng hoặc 'chưa rõ'",
 "parties": [{"name": "tên đầy đủ của bên", "role": "vai trò trong hợp đồng, vd. Bên cho thuê", "unit": "uid", "quote": "trích nguyên văn"}],
 "sign_date": {"value": "YYYY-MM-DD", "unit": "uid", "quote": "trích nguyên văn"}, hoặc danh sách [{...}, {...}] khi
   hợp đồng ghi nhiều ngày ký khác nhau, hoặc null,
 "effective_date": {...} hoặc null, "end_date": {...} hoặc null (ngày hết hạn ghi rõ của CHÍNH hợp đồng), "value": {"value": "...", "unit": "uid", "quote": "..."} hoặc null,
 "term": {...} hoặc null,
 "other_dates": [{"label": "...", "value": "YYYY-MM-DD", "unit": "uid", "quote": "..."}],
 "fields": {"<key trong fields_wanted>": {"value": "...", "unit": "uid", "quote": "trích nguyên văn"}}}
Giá trị là con số (tiền, thời hạn, tỉ lệ — vd. "value", "term", tiền thuê, lương, lãi suất): thêm "norm" là giá trị
đọc ra, ghi đúng từng con số như văn bản viết (bằng chữ số hay bằng chữ đều đọc ra số), KHÔNG cộng, KHÔNG đổi đơn vị:
 thời hạn {"parts": [{"n": <số>, "unit": "hour|day|workday|week|month|year"}, ...]} ("2 năm 6 tháng" -> hai phần);
 tiền {"amount": <số đồng>, "currency": "VND|USD"}; tỉ lệ {"value": <số>, "per": "day|month|year" hoặc null}.
 Có nhiều con số khác loại (lương và phụ cấp) thì "norm" chỉ là giá trị của đúng trường được hỏi.
Quy tắc: "quote" phải là đoạn chép NGUYÊN VĂN từ đơn vị "unit"; "unit" phải là một uid trong "units".
Không tìm thấy thì để null / bỏ khóa, không suy đoán. Ngày dạng YYYY-MM-DD. Trường có "options": "value" phải là
đúng một lựa chọn trong đó.
- parties: "known_parties" là các bên đã trích từ phần trước của hợp đồng. KHÔNG trả lại các bên đó, kể cả khi đoạn này
  gọi họ bằng tên gọi tắt hay vai trò ("Bên A", "Company"). Chỉ trả bên MỚI xuất hiện trong "units" (vd. bên bảo lãnh,
  bên ký thêm ở cuối). Mỗi bên một mục, "name" là tên riêng đầy đủ, không phải vai trò.
- sign_date: ngày các bên ký / lập CHÍNH hợp đồng này — ngày ghi ở phần mở đầu ("Hôm nay, ngày …", "lập ngày …",
  "dated / made / entered into as of …") hoặc ngày ghi cạnh chữ ký. Mỗi bên ký một ngày khác nhau, hoặc ngày ở phần
  mở đầu khác ngày ở chữ ký: trả DANH SÁCH đủ các ngày đó. Không lấy ngày của phụ lục, bản sửa đổi, văn bản đính kèm
  hay văn bản khác được nhắc tới. Câu chỉ nói hợp đồng "có hiệu lực từ …" ("effective as of …") là effective_date,
  không phải sign_date.
- term: thời hạn của CHÍNH hợp đồng (từ khi có hiệu lực tới khi hết hạn), không phải thời hạn của một nghĩa vụ, bảo
  hành, giấy phép, thử việc hay cam kết không cạnh tranh."""

_SCALARS = ("sign_date", "effective_date", "end_date", "value", "term")
_BRACKETS = re.compile(r"\([^)]*\)")
_QUOTED = re.compile(r"[\"“”'‘’]")
_ROLE_SPLIT = re.compile(r"[/;,()]|\s[-–—]\s")


def _norm(v: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(v or "")).split()).casefold()


def _key(text: Any) -> str:
    """Khóa so tên: bỏ dấu câu, hoa thường, khoảng trắng thừa."""
    return " ".join(re.sub(r"[^\w]+", " ", _norm(_QUOTED.sub(" ", str(text or "")))).split())


def _name_key(name: Any) -> str:
    """Khóa của tên bên, bỏ phần trong ngoặc: 'Alpha Holdings, Inc. ("Alpha")' -> 'alpha holdings inc'."""
    return _key(_BRACKETS.sub(" ", str(name or "")))


def _aliases(party: dict) -> set[str]:
    """Tên gọi khác của một bên đã biết: các phần của vai trò ("FDMS / SERVICERS"), chữ trong ngoặc ở tên ("Alpha"),
    và tên gọi tắt đọc từ văn bản hợp đồng (`aliases`)."""
    parts = _ROLE_SPLIT.split(str(party.get("role") or "")) + _BRACKETS.findall(str(party.get("name") or ""))
    parts += list(party.get("aliases") or [])
    return {k for k in (_key(x) for x in parts) if len(k) >= 2}


_AFTER_NAME = re.compile(r"[^()\n]{0,80}?\(([^()\n]{1,100})\)")
_IN_QUOTES = re.compile(r"[\"“]([^\"“”]{1,60})[\"”]")
_CALLED = re.compile(r"gọi\s+(?:tắt\s+)?(?:chung\s+)?là\s+(.{1,60})", re.IGNORECASE)


def _text_aliases(contract: Contract, party: dict) -> list[str]:
    """Tên gọi tắt mà hợp đồng đặt cho bên, đọc ngay sau tên bên trong đơn vị nguồn:
    'Beta Tech, Inc., a Nevada corporation ("Beta")', 'Công ty X (sau đây gọi là "Bên B")', 'Ông A (Bên A)'."""
    tokens = _BRACKETS.sub(" ", str(party.get("name") or "")).split()
    text = _unit_text(contract, party.get("unit"))
    if not tokens or not text:
        return []
    m = re.search(r"\s+".join(re.escape(t) for t in tokens), text, re.IGNORECASE)
    after = _AFTER_NAME.match(text, m.end()) if m else None
    if after is None:
        return []
    inside = after.group(1)
    found = _IN_QUOTES.findall(inside)
    if not found:
        called = _CALLED.search(inside)
        # ngoặc không có dấu nháy: chỉ nhận dạng "(Bên A)"; "(USA)", "(Delaware)" là chú thích, không phải tên gọi tắt
        found = [called.group(1)] if called else ([inside] if re.match(r"bên\s+\S", inside.strip(), re.IGNORECASE)
                                                  and len(inside.split()) <= 4 else [])
    return [" ".join(a.split()).strip(" .,;:") for a in found if a.strip()]


def _merge_party(parties: list[dict], p: dict) -> None:
    """Thêm `p` vào `parties` nếu là bên mới. Trùng TÊN (không phải trùng vai trò) -> đã có. Tên của `p` là bí danh của
    đúng một bên đã có -> đã có; là nhãn chung của nhiều bên ("SERVICERS") -> không phải một bên, bỏ.
    Không khớp theo tập con token: "Nantz" và "Nantz Communications" là hai bên khác nhau."""
    key = _name_key(p.get("name"))
    if not key:                                        # không có tên: chỉ còn vai trò để phân biệt
        if not any(_norm(q.get("role")) == _norm(p.get("role")) for q in parties):
            parties.append(p)
        return
    if any(_name_key(q.get("name")) == key for q in parties):
        return
    if any(key in _aliases(q) for q in parties):
        return
    parties.append(p)


def _distinct_roles(parties: list[dict]) -> None:
    """Vai trò là mã của bên (chọn "Bạn là bên nào"): hai bên cùng vai trò -> "vai trò — tên"."""
    seen: dict[str, int] = {}
    for p in parties:
        seen[_norm(p.get("role"))] = seen.get(_norm(p.get("role")), 0) + 1
    for p in parties:
        if seen[_norm(p.get("role"))] > 1 and p.get("name"):
            p["role"] = f"{p['role']} — {_BRACKETS.sub('', str(p['name'])).strip()}"


def _unit_text(contract: Contract, uid: Any) -> str:
    u = contract.unit(str(uid or ""))
    return u.text if u is not None else ""


def _checked(contract: Contract, item: Any, batch: Batch) -> dict | None:
    """Ứng viên hợp lệ: trích dẫn có nguyên văn trong một đơn vị CỦA LÔ. Ngữ cảnh và đơn vị tham khảo chỉ để hiểu: giá
    trị trích từ đó bị bỏ (lô sở hữu đơn vị ấy sẽ trích), tránh hai lô diễn đạt một giá trị theo hai cách.
    `unit` được sửa thành đơn vị của lô thực sự chứa trích dẫn (mô hình hay ghi nhầm uid hoặc ghi nhãn "Điều 5")."""
    if not isinstance(item, dict):
        return None
    quote = str(item.get("quote") or "")
    if item.get("unit") not in batch.uids or not quote_ok(_unit_text(contract, item.get("unit")), quote):
        home = next((uid for uid in batch.uids if quote_ok(_unit_text(contract, uid), quote)), None)
        if home is None:
            return None
        item = item | {"unit": home}
    return {k: item.get(k) for k in ("value", "norm", "label", "name", "role", "unit", "quote") if item.get(k) is not None}


def _iso(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _wanted(specs: Sequence[dict]) -> list[dict]:
    return [{"key": s["key"], "label": s["label"], "hint": s.get("hint", ""),
             **({"options": s["options"]} if isinstance(s.get("options"), list) else {})}
            for s in specs if s["key"] not in ("party", "sign_date", "type", *_SCALARS)]


def _payload(batch: Batch, known: list[dict], specs: Sequence[dict]) -> dict:
    return {"units": batch.payload_units(), "context": list(batch.context), "references": list(batch.references),
            "known_parties": [{"name": p.get("name"), "role": p.get("role")} for p in known],
            "fields_wanted": _wanted(specs)}


def _add(cands: dict[str, list[dict]], key: str, item: dict | None) -> None:
    if item is None or item.get("value") in (None, ""):
        return
    bucket = cands.setdefault(key, [])
    if not any(_norm(c["value"]) == _norm(item["value"]) for c in bucket):
        bucket.append({k: item[k] for k in ("value", "norm", "unit", "quote") if k in item})


def _items(raw: Any) -> list:
    """Một giá trị hoặc danh sách giá trị (hợp đồng ghi nhiều ngày ký)."""
    return raw if isinstance(raw, list) else [raw]


def extract_facts(llm, contract: Contract, *, on_event=None, extra_fields: Sequence[dict] = ()) -> dict:
    """`extra_fields`: trường các gói đang dùng khai thêm (`pack.yaml` extract_fields), trích cùng danh mục chung."""
    specs = {s["key"]: s for s in all_specs()}
    for f in extra_fields:
        specs.setdefault(f["key"], dict(f))
    spec_list = list(specs.values())
    parties: list[dict] = []

    def read(batch: Batch) -> dict:
        if on_event:
            on_event({"type": "fact_batch", "status": "start", "uids": batch.uids, "batch": batch.index})
        data = ask_json(llm, FACTS_PROMPT, _payload(batch, parties, spec_list), contract.mask_state)
        for p in (_checked(contract, x, batch) for x in data.get("parties") or []):
            if p and p.get("role"):
                found = _text_aliases(contract, p)
                _merge_party(parties, p | {"aliases": found} if found else p)
        if on_event:
            on_event({"type": "fact_batch", "status": "done", "uids": batch.uids, "batch": batch.index})
        return data

    # Later batches depend on parties collected from earlier batches. Keep this
    # extraction sequential even when independent tag/review batches run in parallel.
    run = run_batches(make_batches(contract), read, workers=1)
    if not run.results:
        raise ContractAIError()
    _distinct_roles(parties)
    types: list[str] = []
    other: list[dict] = []
    cands: dict[str, list[dict]] = {}
    for batch, data in run.results:
        kind = str(data.get("type") or "").strip()
        if kind and kind.casefold() != "chưa rõ":
            types.append(kind)
        for key in _SCALARS:
            for raw in _items(data.get(key)):
                item = _checked(contract, raw, batch)
                if item and key in ("sign_date", "effective_date", "end_date"):
                    item = item | {"value": _iso(item.get("value")).isoformat()} if _iso(item.get("value")) else None
                _add(cands, key, item)
        other += [d for d in (_checked(contract, x, batch) for x in data.get("other_dates") or []) if d]
        fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
        for key, raw in fields.items():
            item = _checked(contract, raw, batch) if key in specs else None
            if item is not None:
                value = normalize_value(specs[key], item.get("value"), contract)
                _add(cands, key, item | {"value": value} if value is not None else None)

    facts: dict[str, Any] = {"type": types[0] if types else "chưa rõ", "parties": parties, "other_dates": other}
    for key in _SCALARS:                                   # dạng cũ: giá trị duy nhất, nhiều giá trị -> ứng viên đầu
        facts[key] = (cands.get(key) or [None])[0]
    if types:
        # mỗi lô tự đoán loại từ đoạn nó đọc: lấy loại của lô đầu tiên (có phần mở đầu), không coi là mâu thuẫn
        cands["type"] = [{"value": types[0]}]
    facts["candidates"] = cands
    facts["questions"] = list(contract.facts.get("questions") or [])
    facts["coverage"] = {"read": len(run.read_uids), "total": len(contract.units)}
    if (contract.facts or {}).get("document_kind"):            # loại đã nhận diện (classify_contract) giữ qua lần trích
        facts["document_kind"] = contract.facts["document_kind"]
    facts["warnings"] = run.warnings()
    signed = cands.get("sign_date") or []
    if len(signed) == 1 and contract.sign_date_source != "user":
        contract.sign_date, contract.sign_date_source = _iso(signed[0]["value"]), "text"
    elif not signed:
        facts["sign_date"] = None
    contract.facts = facts
    return facts


__all__ = ["FACTS_PROMPT", "extract_facts"]
