"""Export a human review packet; never auto-approve assistant-authored labels."""
import argparse
from pathlib import Path

from benchmark import HERE, digest, json_bytes, load_jsonl, verify, write_jsonl


def export_review(folder, out):
    folder, out = Path(folder), Path(out)
    _, inputs, gold, _ = verify(folder)
    imap = {i['id']: i for i in inputs}
    out.mkdir(parents=True, exist_ok=True)
    lines = ['# Rà soát nhãn benchmark phân tích hợp đồng', '',
        'Đây là nhãn do trợ lý tạo, chưa được duyệt độc lập. Không dùng kết quả hệ thống làm đáp án.', '',
        'Với mỗi case: kiểm tra đúng phạm vi, ngày áp dụng, đủ quy tắc và ngoại lệ; '
        'đối chiếu nguồn gốc, khoảng hiệu lực và mọi nhóm bằng chứng. '
        'Đánh dấu rejected nếu thiếu căn cứ; ghi đề xuất sửa trong note. '
        'Các case cùng family có quan hệ với nhau, không xem là các mẫu độc lập.', '']
    reviews = []
    for g in gold:
        inp = imap[g['id']]
        lines += [f'## {g["id"]}', '', inp['contract_text'], '',
            f'- Context: `{inp["context"]}`', f'- Concepts: `{inp["concepts"]}`',
            f'- Expected decision: `{g["decision"]}`', f'- Rationale: {g["rationale"]}', '']
        for group in g['evidence_groups']:
            lines += [f'### Nhóm bằng chứng {group["group_id"]}', '']
            for alt in group['alternatives']:
                lines += [f'- `{alt["provision_id"]}` / version `{alt["version_key"]}`',
                    f'- Source: {alt["source_url"]}', f'- Source status: `{alt["verification_status"]}`',
                    f'- Raw SHA256: `{alt["raw_checksum"]}`', '', '> ' + alt['quote'].replace('\n', '\n> '), '']
        reviews.append({'id': g['id'], 'gold_sha256': digest(json_bytes(g)),
            'reviewer': '', 'reviewer_type': 'human', 'decision': 'pending', 'reviewed_at': '', 'note': ''})
    (out / 'review.md').write_text('\n'.join(lines), encoding='utf-8')
    write_jsonl(out / 'reviews.template.jsonl', reviews)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder', type=Path, default=HERE)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    export_review(a.folder, a.out)
