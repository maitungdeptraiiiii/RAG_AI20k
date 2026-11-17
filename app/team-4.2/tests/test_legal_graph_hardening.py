from dataclasses import replace
from datetime import date

import pytest

from rag.legal.directives import _target_law, parse_directives
from rag.legal.effectivity import parse_effectivity
from rag.legal.graph.query import LegalGraph
from rag.legal.graph.refs import find_refs
from rag.legal.models import Address
from rag.legal.structure import parse_structure
from tests.test_legal_builder import FAKE, fake_build, history, op


def test_same_text_amendment_keeps_one_interval_and_evidence():
    amendment = op('REPLACE_CLAUSE', Address('17', '5'), '5. Khoản năm.')
    versions = history(fake_build([amendment]), FAKE + '#d17.k5')
    assert len(versions) == 1
    assert versions[0].valid_from == date(2021, 1, 1)
    assert versions[0].valid_to is None
    assert amendment.operation_id in versions[0].source_operations


def test_a_b_a_keeps_three_intervals():
    versions = history(fake_build([
        op('REPLACE_CLAUSE', Address('17', '5'), '5. Nội dung B.'),
        op('REPLACE_CLAUSE', Address('17', '5'), '5. Khoản năm.', effective=date(2025, 1, 1), seq=2),
    ]), FAKE + '#d17.k5')
    assert [v.text for v in versions] == ['5. Khoản năm.', '5. Nội dung B.', '5. Khoản năm.']
    assert [(v.valid_from, v.valid_to) for v in versions] == [
        (date(2021, 1, 1), date(2023, 1, 1)), (date(2023, 1, 1), date(2025, 1, 1)),
        (date(2025, 1, 1), None)]


def test_same_text_after_reinsertion_keeps_gap():
    versions = history(fake_build([
        op('DELETE_CLAUSE', Address('17', '5')),
        op('INSERT_CLAUSE', Address('17', '5'), '5. Khoản năm.', effective=date(2025, 1, 1), seq=2),
    ]), FAKE + '#d17.k5')
    assert len(versions) == 2
    assert versions[0].text == versions[1].text
    assert versions[0].valid_to < versions[1].valid_from


def test_pdf_indentation_does_not_break_version_tree():
    versions = fake_build([], text='Điều 1. Nội dung\n     1. Khoản một.\n     2. Khoản hai.')
    assert history(versions, FAKE + '#d1.k1')[0].text == '1. Khoản một.'


def test_inline_amendment_quote_is_separated_from_header():
    text = ('Điều 1. Sửa đổi khoản 2 Điều 4 của Nghị định số 145/2020/NĐ-CP\n'
            '1. Sửa đổi khoản 2 Điều 4 như sau: “2. Nội dung mới.”')
    ds = parse_directives(parse_structure(text, 'nghi-dinh:1/2025/NĐ-CP'))
    assert len(ds) == 1 and ds[0].new_text == '2. Nội dung mới.'
    assert ds[0].parse_status == 'exact'


def test_consolidation_named_amenders_define_the_cutoff():
    from rag.legal.vbhn import parse_consolidation_header
    text = ('Bộ luật Lao động số 45/2019/QH14 được sửa đổi, bổ sung bởi:\n'
            '1. Luật Công nghiệp công nghệ số số 71/2025/QH15, có hiệu lực từ ngày 01 tháng 01 năm 2026;\n'
            '2. Luật Dân số số 113/2025/QH15, có hiệu lực từ ngày 01 tháng 7 năm 2026.\n'
            'Điều 1. Phạm vi\nNội dung.')
    info = parse_consolidation_header(text)
    assert info.cutoff == date(2026, 7, 1)
    assert {n for n, d in info.included} == {'71/2025/QH15', '113/2025/QH15'}


def test_decree_amendment_resolves_number_with_full_suffix():
    assert _target_law('Sửa đổi khoản 2 Điều 4 của Nghị định số 145/2020/NĐ-CP như sau:') == (None, '145/2020/NĐ-CP')
    text = ('Điều 1. Sửa đổi, bổ sung một số điều của Nghị định số 145/2020/NĐ-CP\n'
            '1. Sửa đổi khoản 2 Điều 4 như sau:\n“2. Nội dung mới.”')
    ds = parse_directives(parse_structure(text, 'nghi-dinh:1/2025/NĐ-CP'))
    assert len(ds) == 1 and ds[0].target_law_number == '145/2020/NĐ-CP'
    assert ds[0].target == Address('4', '2')


def test_appendix_repeal_never_becomes_whole_document_repeal():
    text = ('Điều 2. Hiệu lực thi hành\n'
            'Nghị định này có hiệu lực từ ngày 01 tháng 7 năm 2025.\n'
            'Phụ lục III của Nghị định số 135/2020/NĐ-CP hết hiệu lực kể từ ngày Nghị định này có hiệu lực.')
    result = parse_effectivity(parse_structure(text, 'nghi-dinh:158/2025/NĐ-CP'))
    assert len(result.repeals) == 1
    assert result.repeals[0].partial and not result.repeals[0].units
    from rag.legal.operations import repeal_operations
    from tests.test_legal_graph import DOCS
    operations = repeal_operations(DOCS[-1], result, documents=DOCS)
    assert all(o.operation_type != 'REPEAL_DOCUMENT' for o in operations)
    assert all(o.review_status == 'pending' for o in operations)


@pytest.mark.parametrize('text,expected', [
    ('theo từ Điều 5 đến Điều 9 của Bộ luật Lao động', tuple(Address(str(i)) for i in range(5, 10))),
    ('điểm a và điểm b khoản 1 Điều 5', (Address('5', '1', 'a'), Address('5', '1', 'b'))),
])
def test_reference_lists_and_ranges_keep_offsets(text, expected):
    refs = find_refs(text)
    assert len(refs) == 1 and refs[0].addresses == expected
    assert text[refs[0].offset:refs[0].offset + len(refs[0].raw)] == refs[0].raw


def test_invalid_range_is_reported_without_guessing_a_document_reference():
    refs = find_refs('từ Điều 9 đến Điều 5')
    assert len(refs) == 1 and refs[0].problem == 'unsupported_range'


class ChangingStore:
    name = 'legal-test'
    def __init__(self):
        self.calls = []
        self.build = 'old'
    def current(self):
        return {'current_build': self.build, 'snapshot_id': 'snapshot-' + self.build}
    def run(self, query, **params):
        self.calls.append(params)
        return []


def test_pinned_request_survives_pointer_change():
    store = ChangingStore()
    reader = LegalGraph(store).pinned()
    store.build = 'new'
    reader.text_at('law#d1', date(2026, 1, 1))
    reader.references('law#d1', date(2026, 1, 1))
    assert all(c['bid'] == 'old' for c in store.calls)
    assert all(c['graph'] == 'legal-test' for c in store.calls)
    assert reader.snapshot_id == 'snapshot-old'
