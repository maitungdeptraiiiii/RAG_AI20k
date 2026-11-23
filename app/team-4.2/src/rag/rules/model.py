"""Kiểu dữ liệu của rule engine: gói luật, ngữ cảnh đánh giá, lỗi nạp (spec §5.5, §7)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Mapping

from rag.rules.units import Units

CORE_FINDINGS = frozenset({"ok", "violation", "needs_facts", "conflict", "missing_content"})


class CatalogError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("Danh mục khái niệm lỗi:\n- " + "\n- ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Silence:
    """Kết quả khi hợp đồng không nói tới khái niệm: (status, finding) khi rule áp dụng và khi chưa biết có áp dụng."""
    applicable: tuple[str, str]
    unknown: tuple[str, str]


CORE_SILENCES: dict[str, Silence] = {
    "none": Silence(("PASS", "ok"), ("PASS", "ok")),
    "missing_content": Silence(("FAIL", "missing_content"), ("UNKNOWN", "needs_facts")),
}


@dataclass(frozen=True)
class Definition:
    """Một định nghĩa của dữ kiện suy ra (spec §5.3): lấy `value` hằng hoặc giá trị dữ kiện `from_fact` khi `when` đúng;
    `exception_of` trỏ id định nghĩa mà nó là ngoại lệ."""
    id: str
    when: dict | None
    exception_of: str | None
    from_fact: str | None
    has_value: bool                    # YAML có khóa `value` (False / None cũng là giá trị hợp lệ)
    value: Any
    anchors: tuple[dict, ...] = ()


@dataclass(frozen=True)
class DerivedFact:
    fact: str
    unit: str | None
    definitions: tuple[Definition, ...]
    object_type: str | None = None     # khai cho một kiểu đối tượng: mỗi đối tượng có giá trị riêng (spec §5.6)


# Bộ đọc giá trị cho dữ kiện cấp hợp đồng (cài ở rag.bridge.facts_map); gói chọn theo tên, không viết code mới.
DOCUMENT_PARSERS = frozenset({"duration", "duration_to_unit", "money", "percent", "flag", "enum", "contains", "text"})


@dataclass(frozen=True)
class DocumentFact:
    """Một dữ kiện cấp hợp đồng của gói: lấy từ trường trích `field` (facts.py), đọc bằng `parse`."""
    name: str
    unit: str | None
    field: str
    parse: str
    values: tuple[tuple[str, str], ...] = ()       # enum: (nhãn, mã); contains: (cụm chữ, mã) theo thứ tự ưu tiên


@dataclass(frozen=True)
class ObjectType:
    """Kiểu đối tượng của hồ sơ (spec §5.6): thuộc tính (`attrs`) và tham chiếu tới đối tượng khác (`refs`)."""
    name: str
    attrs: frozenset[str]
    refs: frozenset[str]
    # Cách rag.contracts.dossier dựng đối tượng từ văn bản (H1); bỏ trống -> kiểu chỉ dùng được với đối tượng cấp sẵn.
    documents: tuple[str, ...] = ()                      # loại văn bản (document_kind, hoặc "amendment") ứng với kiểu
    from_facts: Mapping[str, str] = field(default_factory=dict)   # thuộc tính -> dữ kiện cấp hợp đồng (document_facts)
    gap_after_end: tuple[str, str] | None = None         # (thuộc tính, ref): số ngày từ hết hạn tới văn bản kế tiếp cùng ref
    amends: str | None = None                            # ref trỏ tới đối tượng được phụ lục sửa
    states_target: str | None = None                     # thuộc tính: phụ lục ghi rõ điều khoản sửa
    states_valid_from: str | None = None                 # thuộc tính: phụ lục ghi thời điểm hiệu lực
    modifies: Mapping[str, str] = field(default_factory=dict)     # thuộc tính -> trường trích: phụ lục sửa đúng điều khoản chứa trường đó


@dataclass(frozen=True)
class UserQuestion:
    """Câu hỏi cho một dữ kiện người dùng (spec §8): `values` là miền giá trị khả dĩ để `next_questions` thử."""
    fact: str
    question: str
    values: tuple
    unit: str | None = None


@dataclass(frozen=True)
class Context:
    """Phần của gói mà logic thuần cần: đơn vị, dữ kiện cấp hợp đồng, bảng on_silence, dữ kiện suy ra."""
    units: Units
    document_facts: frozenset[str]
    silences: Mapping[str, Silence]
    derived: Mapping[str, DerivedFact] = field(default_factory=dict)
    questions: Mapping[str, UserQuestion] = field(default_factory=dict)
    input_units: Mapping[str, str | None] = field(default_factory=dict)   # dữ kiện đầu vào (hợp đồng + người dùng) -> đơn vị mặc định
    unit_forms: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # đơn vị -> cách viết sau con số ("/năm")
    document_specs: Mapping[str, DocumentFact] = field(default_factory=dict)  # dữ kiện cấp hợp đồng -> cách trích
    extract_fields: tuple[dict, ...] = ()        # trường cần LLM trích thêm (ngoài contracts/fact_catalog.json)
    document_label: str = "hợp đồng"             # tên loại văn bản cho prompt / hiển thị (vd. "hợp đồng vay tài sản")

    @property
    def reported(self) -> frozenset[str]:
        """Finding mang `outcome` (legality...): violation và mọi finding của bảng on_silence, trừ ok / needs_facts."""
        found = {f for s in self.silences.values() for f in (s.applicable[1], s.unknown[1])}
        return frozenset({"violation"} | found) - {"ok", "needs_facts"}


@dataclass(frozen=True)
class PackSpec:
    id: str
    version: str
    extends: tuple[str, ...]
    document_kinds: tuple[str, ...]
    units: Units
    document_facts: Mapping[str, str | None]      # dữ kiện cấp hợp đồng -> đơn vị
    user_facts: frozenset[str]
    findings: frozenset[str]                       # finding thêm ngoài CORE_FINDINGS
    silences: Mapping[str, Silence]                # đã gộp CORE_SILENCES
    derived: Mapping[str, DerivedFact] = field(default_factory=dict)
    user_fact_units: Mapping[str, str | None] = field(default_factory=dict)   # đơn vị mặc định khi người dùng trả lời một con số
    user_fact_questions: Mapping[str, UserQuestion] = field(default_factory=dict)
    concept_kinds: Mapping[str, tuple[str, ...]] = field(default_factory=dict)   # kind -> các loại slot concept phải có
    object_types: Mapping[str, ObjectType] = field(default_factory=dict)
    unit_forms: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    document_specs: Mapping[str, DocumentFact] = field(default_factory=dict)
    extract_fields: tuple[dict, ...] = ()
    document_labels: Mapping[str, str] = field(default_factory=dict)    # document_kind -> nhãn
    document_label: str = "hợp đồng"

    def context(self) -> Context:
        inputs = {**{n: None for n in self.user_facts}, **dict(self.user_fact_units), **dict(self.document_facts)}
        return Context(self.units, frozenset(self.document_facts), self.silences, self.derived, self.user_fact_questions,
                       inputs, self.unit_forms, self.document_specs, self.extract_fields, self.document_label)


# ── danh mục khái niệm (concepts.yaml) ──
OPS = frozenset({"eq", "lt", "lte", "gt", "gte", "in", "present", "absent"})
MODES = frozenset({"required", "threshold", "prohibited", "default"})
DEROGATIONS = frozenset({"floor", "mandatory", "default"})
SLOT_KINDS = frozenset({"duration", "percent", "money", "bool", "enum"})


@dataclass(frozen=True)
class Slot:
    name: str
    kind: Literal["duration", "percent", "money", "bool", "enum"]
    unit: str | None
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rule:
    id: str
    mode: str
    derogation: str
    on_silence: str
    applicability: dict | None
    law: dict
    cases: tuple[dict, ...]
    check: dict | None
    outcome: dict
    # Phép kiểm là một slot có/không "= false" (hợp đồng không có hạn chế): khái niệm có mặt mà slot không được điền
    # thì coi là không có hạn chế. Bộ nạp tự suy từ `check` khi YAML không ghi (spec §5.2).
    unstated_false: bool = False
    exception_of: str | None = None       # `<concept_id>/<rule_id>` của rule gốc mà rule này là ngoại lệ (spec §5.4)
    # Phép kiểm chỉ dùng dữ kiện người dùng cung cấp, không đến từ một điều khoản: có dữ kiện là xét, kể cả khi
    # khái niệm không có mặt (như rule chỉ dùng `document_facts`).
    standalone: bool = False
    # Rule xuyên đối tượng (spec §5.6): over = (biến, kiểu, where, history); group_by = ((tên, đường dẫn), ...).
    over: tuple[str, str, dict | None, bool] | None = None
    group_by: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Concept:
    id: str
    label: str
    scope: str
    phase: str
    holder: str
    counterparty: str
    applies_to: tuple[str, ...]
    describe: str
    phrasing: tuple[str, ...]
    slots: dict[str, Slot]
    anchors: tuple[dict, ...]
    value_sources: tuple[dict, ...]
    rules: tuple[Rule, ...]
    not_about: tuple[dict, ...] = ()   # [{text, see}]: điều khoản dễ gán nhầm vào khái niệm này; see = khái niệm đúng
    kind: str | None = None            # nhãn loại khái niệm (rate_cap, notice, ...): engine không dùng, bộ nạp kiểm slot (§5.5)


@dataclass(frozen=True)
class Catalog:
    version: str
    law_values_valid_from: date
    roles: dict[str, dict]
    concepts: dict[str, Concept]
    context: Context


def leaves(cond: Any) -> list[dict]:
    """Các lá {fact, op, ...} của một điều kiện all / any / not."""
    if not isinstance(cond, dict):
        return []
    for key in ("all", "any"):
        if key in cond:
            return [x for c in cond[key] for x in leaves(c)]
    if "not" in cond:
        return leaves(cond["not"])
    return [cond]
