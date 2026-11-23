"""Prompt và danh mục dữ kiện phải theo kịp các gói hiện có (không còn nhớ riêng gói lao động)."""
from rag.bridge.tagger import TAG_PROMPT_VERSION, tag_prompt
from rag.contracts.classify import document_kinds
from rag.contracts.verify import catalog
from rag.rules.loader import load_pack


def test_every_pack_document_kind_has_a_fact_catalog_type():
    mapped = catalog()["document_kinds"]
    missing = [k for k in document_kinds() if k not in mapped]
    assert not missing, f"loại văn bản chưa có kiểu danh mục dữ kiện (rơi về đoán theo chữ): {missing}"
    assert all(t in catalog()["types"] for t in mapped.values())


def test_tag_prompt_names_the_label_of_each_pack():
    for pack in ("consumer", "commercial", "civil_lease", "civil_loan", "labor"):
        spec = load_pack(pack)
        text = tag_prompt(spec.context())
        assert spec.document_label in text


def test_tag_prompt_explains_every_kind_in_use():
    from pathlib import Path
    import yaml
    from rag.rules.loader import PACKS_ROOT
    kinds = yaml.safe_load((Path(PACKS_ROOT) / "kinds.yaml").read_text(encoding="utf-8"))["kinds"]
    used = [k for k, v in kinds.items() if v.get("domains")]
    text = tag_prompt()
    assert [k for k in used if k not in text] == [], "prompt gán khái niệm phải nêu mọi kind đang dùng"


def test_tag_prompt_version_bumped():
    assert TAG_PROMPT_VERSION == "concept-tag-5"
