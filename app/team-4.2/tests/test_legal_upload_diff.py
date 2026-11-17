from rag.legal.upload.diff import diff_articles


def test_whitespace_only_differences_are_same():
    d = diff_articles("Điều 1. A  b\nĐiều 2. C", "Điều 1. A b\nĐiều 2.  C", "k")
    assert d.same == 2 and d.changed == ()


def test_changed_added_removed():
    d = diff_articles("Điều 1. A\nĐiều 2. B\nĐiều 3. C", "Điều 1. A\nĐiều 2. B sửa\nĐiều 4. D", "k")
    assert d.same == 1 and [c.article for c in d.changed] == ["2"] and d.added == ("4",) and d.removed == ("3",)
    assert ("insert", "sửa") in d.changed[0].ops


def test_subtree_and_letter_labels_in_document_order():
    old = "Điều 5a. B\n1. x\na) y\nĐiều 2. C"
    new = "Điều 5a. B\n1. x\na) z\nĐiều 2. C\nĐiều 9. N\nĐiều 1. M"
    d = diff_articles(old, new, "k")
    assert d.same == 1 and [c.article for c in d.changed] == ["5a"]
    assert ("delete", "y") in d.changed[0].ops and ("insert", "z") in d.changed[0].ops
    assert d.added == ("9", "1") and d.removed == ()
