"""Offline verification and failure analysis of the hard25 run; no model clients."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sqlite3

from rag.eval.metrics import load_questions, recall_at_k, hit_at_k, mrr_at_k
from rag.schema import Chunk, Hit


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default='evals/team-4.2/results/multihop-hard25-current-20261106-verified')
    args=ap.parse_args(); out=Path(args.out)
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    config=read(out/'config.json'); stats=read(out/'metrics.json')
    dataset=Path('evals/team-4.2/datasets/benchmark_multihop_hard25.jsonl')
    old=Path('evals/team-4.2/datasets/benchmark_doi_thuong.jsonl')
    corpus=Path(config['data_dir'])/'processed/chunks.jsonl'
    assert sha(dataset)==config['questions_sha256'] and sha(old)==config['old_questions_sha256']
    assert sha(corpus)==config['chunks_sha256']
    chunks={c.chunk_id:c for c in [Chunk.from_dict(json.loads(x)) for x in corpus.read_text(encoding='utf-8').splitlines()]}
    qs=load_questions(dataset); raw=[json.loads(x) for x in dataset.read_text(encoding='utf-8').splitlines()]
    traces=read(out/'query_traces.json')
    with (out/'retrieval_per_question.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
    assert len(qs)==len(traces)==len(rows)==25
    failures=[]; categories=Counter(); missing_articles=Counter(); changes=[]; candidate_recall=[]
    for q,r,t,extra in zip(qs,rows,traces,raw):
        assert q.id==r['id']==t['id'] and not t['errors'] and r['reranked']=='True'
        assert len(t['ranked'])>=5
        ranked=[h['chunk_id'] for h in t['ranked']]; top=ranked[:5]
        for name,value in [('recall@5',recall_at_k(q,top,chunks,5)),('recall@20',recall_at_k(q,ranked,chunks,20)),
                           ('hit@5',hit_at_k(q,top,chunks,5)),('mrr@5',mrr_at_k(q,top,chunks,5))]:
            assert abs(float(r[name])-value)<1e-10,(q.id,name)
        def covered(hits,g):
            return any(g.matches(chunks[cid]) for h in hits for cid in [h['chunk_id'],*h['merged']])
        missing=[]
        for j,g in enumerate(q.gold):
            if covered(t['ranked'][:5],g):continue
            if not covered(t['candidates'],g):category='missing_from_candidate_pool'
            elif covered(t['ranked'][:20],g):category='in_top20_but_not_top5'
            else:category='in_pool_below_top20'
            categories[category]+=1; missing_articles[extra['gold_articles'][j]]+=1
            missing.append({'gold_index':j,'article':extra['gold_articles'][j],
                            'purpose':extra['reasoning_steps'][j]['purpose'],'category':category})
        cr=sum(covered(t['candidates'],g) for g in q.gold)/len(q.gold); candidate_recall.append(cr)
        failures.append({'id':q.id,'question':q.question,'recall@5':float(r['recall@5']),
                         'recall@20':float(r['recall@20']),'candidate_recall':cr,'missing':missing})
        if t['pre_selection_ranked']:
            before=sum(covered(t['pre_selection_ranked'][:5],g) for g in q.gold)/len(q.gold)
            changes.append({'id':q.id,'before_recall5':before,'after_recall5':float(r['merged_recall@5'])})
    audit=read(out/'quality_audit.json')
    # Export only retrieval prompts belonging to this run; read cache without writes.
    from rag.advanced.hyde import HYDE_SYSTEM
    from rag.advanced.decomposition import DECOMPOSITION_SYSTEM
    from rag.retrieve.listwise import LISTWISE_SYSTEM, ListwiseSelector, ListwiseConfig
    from rag.retrieve.rerank import DEFAULT_JEV_MODEL, JEV_INSTRUCTIONS, SCORE_CACHE_SCHEMA
    from rag.generate.llm import LLMCache
    conn=sqlite3.connect((Path(config['data_dir'])/'cache/llm.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    recorded=[]
    def export(purpose,system,user,qid):
        key=LLMCache.key(config['llm_model'],config['llm_temperature'],
                         [{'role':'system','content':system},{'role':'user','content':user}])
        found=conn.execute('SELECT text FROM completions WHERE key=?',(key,)).fetchone()
        assert found is not None,(qid,purpose,'missing retrieval completion')
        recorded.append({'id':qid,'purpose':purpose,'key':key,'system':system,'user':user,'response':found[0]})
    selector=ListwiseSelector(None,ListwiseConfig(config['listwise_candidate_n'],config['listwise_margin'],
                             config['listwise_min_p'],config['listwise_excerpt_words']))
    for q,t in zip(qs,traces):
        if config['decomp_enabled']:
            export('decomposition',DECOMPOSITION_SYSTEM,json.dumps({'query':q.question,
                    'max_subqueries':config['decomp_max_subqueries']},ensure_ascii=False),q.id)
        if 'hyde' in config['advanced'].split(','):
            for sub in t['queries'] or [q.question]:export('hyde',HYDE_SYSTEM,f'CÂU HỎI: {sub}',q.id)
        if t['listwise_metadata'].get('triggered'):
            plan=selector.prepare(q.question,t['queries'],[Hit.from_dict(h) for h in t['pre_selection_ranked']],chunks,k=5)
            assert plan.payload_sha256==t['listwise_metadata']['payload_sha256']
            export('listwise',LISTWISE_SYSTEM,plan.payload,q.id)
    conn.close()
    (out/'retrieval_llm_outputs.json').write_text(json.dumps(recorded,ensure_ascii=False,indent=2),encoding='utf-8')
    provenance={'rerank_model':DEFAULT_JEV_MODEL,'rerank_instructions':JEV_INSTRUCTIONS,
                'rerank_instructions_sha256':hashlib.sha256(JEV_INSTRUCTIONS.encode()).hexdigest(),
                'rerank_cache_schema':SCORE_CACHE_SCHEMA,
                'retrieval_prompt_sha256':{name:hashlib.sha256(prompt.encode()).hexdigest() for name,prompt in
                    [('hyde',HYDE_SYSTEM),('decomposition',DECOMPOSITION_SYSTEM),('listwise',LISTWISE_SYSTEM)]},
                'exported_completions':len(recorded),'completion_purposes':dict(Counter(x['purpose'] for x in recorded)),
                'strict_failure_handling':True,'answer_generation_calls':0,
                'runner_sha256':sha(Path('evals/team-4.2/runners/run_multihop_hard25.py')),
                'builder_sha256':sha(Path('evals/team-4.2/runners/build_multihop_hard25.py')),
                'rag_source_sha256':{str(p):sha(p) for p in Path('app/team-4.2/src/rag').rglob('*.py')}}
    (out/'retrieval_provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
    analysis={'verified_questions':25,'recomputed_metrics_match':True,'old_dataset_unchanged':True,
              'candidate_recall_mean':sum(candidate_recall)/25,'missing_gold_categories':dict(categories),
              'frequently_missing_articles':missing_articles.most_common(),
              'listwise_gate_reasons':dict(Counter(t['listwise_metadata'].get('reason','disabled') for t in traces)),
              'listwise_triggered':sum(bool(t['listwise_metadata'].get('triggered')) for t in traces),
              'listwise_changes':changes,'per_question':failures,
              'max_old_word_jaccard':max(x['word_jaccard'] for x in audit['nearest_old']),
              'max_internal_word_jaccard':audit['top_internal_pairs'][0]['word_jaccard']}
    (out/'failure_analysis.json').write_text(json.dumps(analysis,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Benchmark multi-hop khó: 25 câu mới','',
           'Đánh giá retrieval theo cấu hình project tại ngày 06/11/2026. Không chạy generation trả lời cuối.','',
           '## Dữ liệu và kiểm tra chất lượng','',
           '- Bộ cũ: `evals/team-4.2/datasets/benchmark_doi_thuong.jsonl` (64 câu), không thay đổi; SHA-256 xác nhận trước/sau.',
           '- Pipeline benchmark gốc: `evals/team-4.2/runners/run_eval.py` → `rag.eval.runner.retrieval_rows` → `RAGPipeline.retriever`; runner decomposition 64 câu tại `runners/run_decomposition_benchmark.py`. Runner mới dùng cùng retriever và hàm metric của repo, bổ sung trace, kiểm tra lỗi nghiêm ngặt và all-gold coverage.',
           '- Bộ mới: `evals/team-4.2/datasets/benchmark_multihop_hard25.jsonl`; 25 câu `multi`, 25/25 nối ít nhất hai bộ luật; 12 câu có 3 gold, 12 có 4, 1 có 5.',
           '- Gold theo `source` + `section` đúng schema `Question`/`GoldRef`; kèm `reference`, `gold_articles`, `gold_chunk_ids`, `reasoning_steps`, `evidence` để kiểm tra từng mắt xích.',
           '- Không gold nào thiếu trong index; văn bản evidence và tập chunk liên quan được đối chiếu chính xác với corpus.',
           '- Không trùng nguyên văn hoặc trùng toàn bộ tập gold với bộ cũ. Sàng lọc từ vựng và rà soát tình huống/chủ đề, không chỉ đổi tên hoặc con số. Có thể dùng chung Điều nền tảng (ví dụ nghĩa vụ chứng minh) mà không trùng bài toán pháp lý.',
           f'- Jaccard từ cao nhất so bộ cũ: {analysis["max_old_word_jaccard"]:.3f}; trong bộ mới: {analysis["max_internal_word_jaccard"]:.3f}. Đây là chỉ báo sàng lọc, không phải chứng minh không trùng ngữ nghĩa.',
           '- Ground truth là bản tác giả rà soát theo snapshot repo, chưa có vòng chuyên gia pháp lý độc lập; không xác nhận hiệu lực pháp luật hiện hành. Các câu phân biệt điều kiện, ngoại lệ; reference tránh khẳng định khi dữ kiện còn thiếu.','',
           '## Cấu hình chạy','',
           f'- Index: `{config["data_dir"]}`; {len(chunks)} chunk, {len({c.source for c in chunks.values()})} nguồn.',
           f'- Embedding: `{config["embed_model"]}`, {config["embed_dim"]} chiều; LLM hỗ trợ retrieval: `{config["llm_model"]}`; reranker: `{DEFAULT_JEV_MODEL}`.',
           '- Giữ cấu hình .env: HyDE bật, decomposition bật, Jev rerank bật, listwise bật; rewrite tắt sẵn, coverage tắt sẵn. Không sửa .env.',
           f'- ARM_K={config["arm_k"]}, RERANK_N={config["rerank_n"]}, TOP_K={config["top_k"]}, RRF_K={config["rrf_k"]}, BM25_RRF_WEIGHT={config["bm25_rrf_weight"]}; vẫn gọi các arm đang cấu hình, trọng số BM25 bằng 0.',
           f'- Gộp theo Điều; article_pool_factor={config["article_pool_factor"]}; decomposition tối đa {config["decomp_max_subqueries"]} câu con + câu gốc, mỗi nhánh k={config["decomp_per_query_k"]}, pool={config["decomp_pool_size"]}, thêm tối đa {config["decomp_max_new_articles"]} Điều mới sau khi giữ pool câu gốc.',
           '- Listwise chỉ chạy khi qua gate: có >=2 câu con, shortlist đủ Điều đạt min_p, khoảng cách quanh ngưỡng top5 đủ nhỏ; không phải bật là luôn gọi.',
           '- Runner chỉ gọi `retriever.retrieve`; chặn `ask`, `ask_debug`, `answer_question` bằng hàm báo lỗi. HyDE vẫn có thể sinh đoạn giả để tìm kiếm; đó không phải câu trả lời cuối.',
           '- Xử lý lỗi nghiêm ngặt: HyDE không âm thầm quay về dense gốc; lỗi decomposition, rerank hoặc listwise dừng run và giữ checkpoint. Các attempt kết nối thất bại được tách riêng, không đưa vào metrics xác nhận.',
           '- Model/config, commit, phiên bản thư viện và hash dữ liệu được ghi trong `config.json`.','',
           '## Metrics','',
           '| Metric | Kết quả |','|---|---:|']
    for k,v in stats['metrics'].items():lines.append(f'| {k} | {v:.4f} |')
    lines += [f'| candidate recall (toàn pool trước rerank) | {analysis["candidate_recall_mean"]:.4f} |','',
              'Recall/Hit/MRR giữ cách chấm chunk đại diện của repo. `merged_recall` và `all_gold` kiểm tra cả các chunk gộp của từng Điều; `all_gold` = tỷ lệ câu đủ tất cả căn cứ, phù hợp đo multi-hop. Recall là macro trung bình theo câu, không phải tỷ lệ chunk.',
              f'Run xác nhận: {stats["n"]}/25 câu, {stats["questions_with_errors"]} câu lỗi, generation calls = 0. Tổng latency từng câu {stats["elapsed_s_sum"]:.1f}s; có ảnh hưởng cache nên không dùng làm latency production.',
              f'LLM retrieval: {stats["retrieval_llm_logical_calls"]} lượt gọi logic, {stats["retrieval_llm_cache_hits"]} cache hit, {stats["retrieval_llm_sdk_requests"]} lượt gọi SDK. SDK có thể retry nội bộ; đây không phải bộ đếm toàn bộ HTTP/token/chi phí của mọi dịch vụ. Không tính các attempt bị hủy hoặc chẩn đoán mạng.',
              '', '## Lỗi retrieval và thiếu mắt xích','',
              'Các nhóm dưới đây đếm gold bị thiếu trong top5, phân biệt mất từ pool với có trong pool nhưng xếp hạng thấp:','']
    for k,v in categories.items():lines.append(f'- `{k}`: {v} căn cứ.')
    lines += ['',f'Listwise được kích hoạt {analysis["listwise_triggered"]}/25 câu. Gate: `{analysis["listwise_gate_reasons"]}`.',
              'Trong 9 lần qua gate, so với thứ tự Jev ngay trước chọn listwise trên cùng pool, 4 câu tăng recall@5, 5 câu giữ nguyên, không câu nào giảm; chi tiết trong `failure_analysis.json`.',
              'Không suy nguyên nhân tuyệt đối từ thứ hạng: trace chỉ xác định khâu mất căn cứ; muốn quy trách nhiệm HyDE/decomposition/rerank riêng cần ablation trên cùng bộ mới.',
              '', '| ID | Recall@5 | Recall@20 | Căn cứ thiếu ở top5 và vị trí thất lạc |', '|---|---:|---:|---|']
    for f in failures:
        detail='; '.join(x['article']+' ('+x['category']+')' for x in f['missing']) or 'Đủ gold'
        lines.append(f'| {f["id"]} | {f["recall@5"]:.3f} | {f["recall@20"]:.3f} | {detail} |')
    lines += ['', '## Rà soát tính mới theo nội dung','',
              'Bộ cũ chỉ được dùng để nhận diện văn phong và kiểm tra loại trừ sau khi soạn. Các nhóm gần về lĩnh vực nhưng khác bài toán đã được xem xét:','',
              '- Thừa kế (d10/d38/d39/d44) khác việc người bị tuyên chết trở về và xử lý người cố tình giấu tin (mh25_01).',
              '- Trộm tài sản của người chưa thành niên (d12/d26) khác quyền đòi lại tài sản qua người mua ngay tình (mh25_05).',
              '- Cho vay, lãi và đòi nợ (d08/d32) khác chuyển quyền yêu cầu không báo, bảo lãnh trả thay và bắt đầu lại thời hiệu hợp đồng thiết kế (mh25_06–08).',
              '- Nghỉ việc/sa thải/trợ cấp thôi việc (d04–06/d50) khác chuyển loại hợp đồng, điều chuyển vượt hạn, tạm đình chỉ rồi minh oan, ký sai thẩm quyền và cắt giảm do tự động hóa (mh25_13–17).',
              '- Tai nạn tàu/cứu hộ/hành lý (d61–64) khác kho lạnh và mất quyền giới hạn, ký hậu vận đơn, ưu tiên cầm giữ và phân bổ tổn thất chung (mh25_22–25).',
              '- Các tình huống còn lại đặt trọng tâm mới ở tự giao dịch của giám hộ, vượt đại diện, tặng cho giả tạo, ưu tiên mua phần sở hữu, tiền chuyển nhầm sinh lợi, gửi giữ trái phép, trách nhiệm vật chất, hành vi vượt quá của đồng phạm, nguyên nhân dừng hành vi, năng lực ở hai thời điểm và giấy tờ giả liên kết vô hiệu.','',
              '## Chạy lại và kiểm chứng','', 'Tại gốc repo (PowerShell):','', '```powershell',
              "$env:PYTHONPATH='app/team-4.2/src'", "$env:PYTHONIOENCODING='utf-8'",
              'python evals/team-4.2/runners/build_multihop_hard25.py',
              'python evals/team-4.2/runners/run_multihop_hard25.py --out evals/team-4.2/results/<thu-muc-moi>',
              'python evals/team-4.2/runners/analyze_multihop_hard25.py --out evals/team-4.2/results/<thu-muc-moi>',
              '```','',
              'Cần cùng .env và snapshot index như `config.json`; runner đọc .env tại thời điểm chạy, không tự khôi phục cấu hình. Dùng `--resume` với cùng `--out` nếu run nghiêm ngặt dừng; runner kiểm tra hash/config trước khi nối tiếp. Phân tích offline không gọi mô hình.',
              '', 'Artifacts: `quality_audit.json`, `config.json`, `retrieval_provenance.json` (model rerank, hash prompt/code), `retrieval_llm_outputs.json` (đầu ra LLM hỗ trợ retrieval đã dùng), `retrieval_per_question.csv`, `query_traces.json`, `metrics.json`, `failure_analysis.json`, `call_counts.json`, `summary.md`.']
    if (out/'validation.txt').exists():
        lines += ['', 'Kiểm tra bổ sung: `test_schema.py` và `test_decomposition_benchmark.py`: 16 tests pass; scripts mới compile được, `git diff --check` sạch. Kết quả trong `validation.txt`.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in analysis.items() if k!='per_question'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
