from rag.legal.text import html_to_legal_text


def test_inline_spans_are_joined_not_split():
    html = ('<p>mua sắm phải được <span>Th</span><span>ủ</span><span> </span><span>t</span>'
            '<span>ướ</span><span>ng Chính ph</span><span>ủ</span> cho phép;</p>')
    assert html_to_legal_text(html) == "mua sắm phải được Thủ tướng Chính phủ cho phép;"


def test_blocks_and_br_become_lines():
    html = "<div><p>Điều 1. <strong>Phạm vi</strong></p><p>1. A<br/>B</p><table><tr><td>x</td><td>y</td></tr></table></div>"
    assert html_to_legal_text(html).splitlines() == ["Điều 1. Phạm vi", "1. A", "B", "x", "y"]


def test_whitespace_and_nfc():
    html = "<p>  Điều 5.   Tên  </p><p>   </p><p>Luật</p>"
    assert html_to_legal_text(html) == "Điều 5. Tên\nLuật"
