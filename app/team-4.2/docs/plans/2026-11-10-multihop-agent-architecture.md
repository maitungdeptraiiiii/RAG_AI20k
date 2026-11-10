# Kế hoạch kiến trúc multi-hop có bằng chứng — Team 4.2

Ngày: 10/11/2026. Đây là bản thiết kế định hướng. V1 đã triển khai luồng snapshot-only,
adaptive search/xref, kiểm chứng, ngân sách và tích hợp Think; xem
[hướng dẫn runtime và giới hạn thực tế](../MULTIHOP_AGENT.md). Temporal integration P5
và acceptance trên holdout độc lập vẫn là công việc tiếp theo. Không suy ra chất lượng
semantic/pháp lý chỉ từ việc implementation có tests pass.

## 1. Quyết định và mục tiêu

Dùng một orchestrator chạy state machine có kiểu dữ liệu rõ ràng. Planner đề xuất nhu cầu và hành động; code kiểm tra phạm vi, nguồn, dependency, ngân sách và điều kiện chuyển trạng thái. Dữ liệu trung tâm là câu hỏi, các yêu cầu cần trả lời, bằng chứng và quan hệ hỗ trợ/phản bác.

Mục tiêu: tăng độ đúng và đầy đủ của đáp án trong phạm vi dữ liệu đã xác định; giữ khả năng truy vết và so sánh với baseline. Không cam kết loại bỏ mọi lần điều chỉnh. Cố định hợp đồng dữ liệu và bất biến để thay model, policy, số vòng hoặc nguồn truy xuất mà không viết lại pipeline.

Không cần hệ nhiều agent hay graph database cho phiên bản đầu. LLM đảm nhiệm các vai trò qua lời gọi riêng, dùng chung state có kiểm soát. Python dataclasses/Protocols theo phong cách repo, bộ điều phối Python và SQLite/JSONL đủ cho giai đoạn này. Có thể thay bộ chạy sau qua cùng contracts nếu xuất hiện nhu cầu vận hành thực tế.

## 2. Bằng chứng từ code và benchmark

- `pipeline.py`: `ask_debug()` và `ask_stream()` đều condense → retrieve → select_context → generate, nhưng thực hiện luồng riêng.
- `retrieve/hybrid.py`: `retrieve()` tự rewrite/decompose, lấy các nhánh, giữ pool câu gốc và thêm Điều mới, Jev rồi listwise hoặc coverage. Chưa có vòng tìm dựa trên nội dung vừa đọc. `_retrieve_single()` là private.
- `retrieve/context.py`: context lấy từ `ranked`, có ngân sách riêng; khác `hits[:5]` phục vụ benchmark. Không được gọi top-5 là context thực tế.
- `generate/answer.py`: `build_citations()` ánh xạ citation hợp lệ, bỏ số không tồn tại khỏi danh sách Citation; chưa sửa số sai trong văn bản và chưa kiểm tra nội dung nguồn hỗ trợ phát biểu.
- `models/content.py`: đã có `ChunkV2`, `Locator`, `TargetRef`; `BlockRelation` hiện chỉ có `next/contains/branch`, chưa phải quan hệ dẫn chiếu pháp luật.
- `retrieve/interfaces.py` đã định nghĩa `ScopedRetriever`; `models/results.py` đã có `ResolvedScope`. Tận dụng các hợp đồng này khi nối scope.
- `versioning/repository.py` nói rõ catalog hiện chưa thực hiện `CatalogRepository.stage/activate`; catalog commit không chứng minh đã có index. `UnitScopeResolver` chỉ chọn unit trước chunk, chưa chứng minh chất lượng retrieval.
- Báo cáo `multihop-hard25-current-20261106-verified/REPORT.md`: Hit@5=1.00, Recall@5≈0.7887, all_gold@5=0.44, all_gold@20=0.60, candidate recall=0.84; 14 căn cứ thiếu khỏi pool, 5 căn cứ có top20 nhưng ngoài top5.
- Hard25 chỉ đánh giá retrieval, generation calls=0. Nhãn theo snapshot repo, chưa được chuyên gia pháp lý độc lập duyệt; không xác nhận luật hiện hành.

Hệ quả: cần đo riêng tìm đủ bằng chứng, chọn đủ vào context và viết đúng đáp án. Tối ưu rerank hoặc thêm xref riêng lẻ không giải quyết tất cả ba tầng.

## 3. Luồng chuẩn duy nhất

```text
Request + conversation history
  → PrepareRequest: condense một lần, giữ dữ kiện và nguồn gốc dữ kiện
  → ResolveScope: chốt corpus snapshot, thời điểm và mức xác minh phiên bản
  → PlanRequirements: checklist, dependency và truy vấn đầu
  → FetchRound
      search / lookup_unit / follow_xref
      → materialize bằng chứng gốc và kiểm tra scope
      → rerank ứng viên theo nhu cầu
      → cập nhật sổ bằng chứng
  → AssessCoverage
      đủ → Compose
      thiếu tài liệu + còn ngân sách → NextActions → FetchRound
      thiếu dữ kiện làm thay đổi đáp án → Clarify hoặc đáp án có điều kiện
      không còn tiến triển / hết ngân sách → ComposePartial hoặc Abstain
  → SelectEvidenceBundle: kiểm tra lại coverage trên context thực sự đưa vào model
  → DraftAnswer: các phát biểu + evidence IDs
  → Verify: cấu trúc, dữ kiện, hỗ trợ nội dung, độ đầy đủ, phiên bản
      đạt → RenderFinal
      lỗi diễn đạt/citation → sửa tối đa một lần và kiểm tra lại
      thiếu bằng chứng → quay lại FetchRound nếu còn ngân sách chung
      chưa đạt và không sửa được → hạ mức kết luận / partial / abstain
  → RenderFinal → kết quả có trạng thái, citation, giới hạn
```

Orchestrator sở hữu toàn bộ vòng lặp; retriever, verifier và xref không tự mở vòng lặp tìm kiếm bên trong. Mọi lần quay lại fetch, kể cả từ verifier, đều tiêu cùng ngân sách.

## 4. Định nghĩa hop, ngân sách và điều kiện dừng

Tách ba đại lượng trong cả config lẫn trace:

- `retrieval_round`: một đợt thực thi các hành động lấy bằng chứng được lập trước, trên cùng phiên bản state. Một vòng có thể chứa nhiều tìm kiếm độc lập và nhiều lần đọc xref, có quota riêng.
- `dependency_depth`: độ sâu phụ thuộc của công việc/bằng chứng. Phát sinh khi kết quả đã đọc mở khóa một truy vấn hoặc đích cần đọc tiếp.
- `xref_depth`: số cạnh dẫn chiếu trên đường đi từ một bằng chứng gốc; mỗi nguồn gốc có đường đi riêng, không dùng một con số toàn cục để đánh dấu mọi node.

Giao diện có thể gọi retrieval round là hop, nhưng log phải lưu đúng các trường trên. Condense, plan, rerank, assess, compose, verify không tăng retrieval round. Một document mới chỉ phát hiện sau khi đọc round hiện tại sẽ được lấy ở round sau; không đệ quy mở rộng ngầm trong một tool call.

Profile thử nghiệm `balanced-v1`:

| Tham số đề xuất | Giá trị ban đầu | Ý nghĩa |
|---|---:|---|
| `max_retrieval_rounds` | 3 | Tổng các đợt fetch, gồm round sửa lỗi sau verifier |
| `initial_subqueries_max` | 3 | Cộng câu gốc thành tối đa 4 lượt search ở round đầu |
| `followup_searches_per_round` | 2 | Ưu tiên hai khoảng thiếu quan trọng nhất |
| `max_searches_total` | 8 | Quota toàn request, không reset theo nhánh |
| `max_xref_depth` | 2 | Giới hạn đường đi dẫn chiếu, độc lập số search |
| `max_xref_targets_per_round` | 6 | Chỉ đích liên quan đến yêu cầu chưa giải quyết |
| `max_xref_targets_total` | 12 | Trần đọc đích xref trên toàn request |
| `max_new_units_per_followup_round` | 10 | Giới hạn nội dung mới đưa vào xử lý |
| `max_retained_units` | 50 | Pool round đầu tối đa 30 + 10 + 10 |
| `max_answer_repairs` | 1 | Sửa đáp án, không tạo ngân sách retrieval mới |
| `context_max_blocks / words` | 10 / 2800 | Bắt đầu từ defaults trong code, ghi lại config hiệu lực |

Các giá trị trên là giả thuyết để đánh giá, không phải kết quả tối ưu. Cấu hình `.env` thực tế có thể khác defaults; manifest phải ghi cấu hình hiệu lực. Tăng rounds lên 4/5 chỉ đổi profile, không thay topology.

Thêm ngân sách số lời gọi model, token input/output, request dịch vụ và deadline toàn request. Chọn con số trước pilot theo ngân sách sản phẩm; không tuyên bố SLA khi chưa đo. Admission controller phải chừa ngân sách cho một lần compose+verify và finalization. Nếu không đủ, giảm retrieval hoặc kết thúc có giới hạn, tránh dùng hết ngân sách để tìm rồi không viết được đáp án.

Mỗi call đi qua gateway đếm cả cache hit, logical call, provider attempt/retry và usage thực có sẵn. Đặt timeout theo thời gian còn lại; tránh retry chồng giữa orchestrator và SDK. Giới hạn token cứng cần request cap phù hợp ở adapter, không chỉ cộng usage sau response. Hủy request phải ngăn lập lịch công việc mới và hủy lời gọi đang chạy khi backend hỗ trợ.

Dừng sớm khi các yêu cầu bắt buộc đủ bằng chứng và không còn mâu thuẫn trọng yếu; hoặc hết ngân sách; hoặc không có tiến triển sau một vòng có cơ hội tìm hợp lệ. Tiến triển là có bằng chứng hữu ích mới, giải quyết requirement hoặc làm rõ mâu thuẫn, không chỉ đổi câu chữ truy vấn. Ghi stop reason riêng: complete, missing_user_fact, corpus_gap, unresolved_scope, no_progress, budget_exhausted, tool_failure, cancelled.

Ba retrieval rounds không tương đương ba Điều luật. Nhiều Điều có thể lấy trong round đầu; chuỗi phụ thuộc sâu vẫn có thể vượt ngân sách và phải trả lời phần đã xác minh.

## 5. Hợp đồng dữ liệu cần chốt trước implementation

| Kiểu | Nội dung bắt buộc |
|---|---|
| `PreparedRequest` | raw question, standalone question, user facts có vị trí nguồn trong hội thoại, ngày yêu cầu, scope yêu cầu, ambiguity |
| `RunContext` | request ID, config/prompt/schema versions, snapshot/generation ID, catalog revision, deadline, budget ledger |
| `Requirement` | ID, nhu cầu, required/conditional, dependency IDs, điều kiện, trạng thái, evidence links |
| `EvidenceRef` | snapshot, document/unit/revision IDs khi xác minh được, chunk/block IDs, locator/span, checksum, nguyên văn |
| `EvidenceAssessment` | requirement ID, evidence IDs, supports/contradicts/insufficient, phạm vi điều kiện, lý do ngắn |
| `Action` | search/lookup_unit/follow_xref, requirement IDs, query/target, dependency IDs, giới hạn output |
| `Candidate` | EvidenceRef hoặc ID chờ materialize, nguồn phát hiện, round, branch, từng loại score và query ID |
| `Claim` | phát biểu, requirement IDs, evidence IDs, trực tiếp/suy ra/có điều kiện, các tiền đề |
| `VerificationReport` | lỗi theo claim/requirement, bằng chứng liên quan, loại lỗi, có thể sửa bằng hành động nào |
| `AgentResult` | answer/partial/clarify/abstain/error/cancelled, text, citations, unresolved requirements, scope warnings, stop reason |
| `AgentEvent` | event/schema version, sequence, request ID, loại sự kiện, payload đã validate |

Trạng thái requirement: pending, supported, partial, conflicting, missing_user_fact, unavailable_in_scope. `supported` luôn gắn scope và evidence version; đây là đánh giá nội bộ có thể sai, không phải chứng nhận đúng tuyệt đối.

Đồ thị requirement ban đầu phải không có chu trình. Khi evidence mới lộ ra tiền đề quan trọng, cho phép thêm requirement có lý do và dependency rõ ràng, validate lại và áp giới hạn kích thước. Không dùng trần ba subquery làm trần số ý được trả lời; một search có thể phục vụ nhiều requirement. Request quá rộng phải hỏi thu hẹp hoặc trả partial minh bạch, không âm thầm bỏ yêu cầu.

Hai lớp liên kết riêng: dẫn chiếu tài liệu (`XrefEdge`) và bằng chứng hỗ trợ kết luận (`EvidenceAssessment`/`Claim`). Có cạnh xref không chứng minh suy luận đúng.

## 6. Bất biến bảo vệ kiến trúc

1. Dữ kiện người dùng, văn bản gốc và nội dung do model sinh có nguồn gốc riêng. Câu trả lời cũ của assistant chỉ hỗ trợ giải nghĩa hội thoại, không trở thành bằng chứng pháp luật hoặc dữ kiện người dùng đã xác nhận.
2. Condense giữ cả câu gốc và dấu vết tham chiếu. Không tự chọn một đại từ/đối tượng còn mơ hồ; giữ ambiguity để hỏi lại khi cần.
3. Planner không tự thêm sự kiện hoặc số Điều. Chỉ lookup số Điều khi có từ người dùng, metadata đã xác minh hoặc span dẫn chiếu thật.
4. HyDE và generated context chỉ hỗ trợ tìm kiếm. Claim/citation luôn trỏ về nội dung nguồn gốc.
5. Bằng chứng dùng trong một run thuộc một snapshot nhất quán. Snapshot được cập nhật ở request tiếp theo.
6. Chỉ gộp khi cùng unit revision; không gộp Điều cùng số ở hai luật hoặc hai phiên bản. Legacy dùng khóa gồm corpus snapshot + document + section, không giả vờ có revision hợp lệ.
7. Điểm dense, RRF, Jev và entailment là các loại khác nhau. Không cộng điểm chéo query/round hoặc gọi điểm Jev là xác suất đáp án đúng.
8. Bằng chứng đã xác minh được giữ trong sổ bằng chứng. Candidate mới không âm thầm đẩy bằng chứng hỗ trợ yêu cầu khác ra khỏi state. Context có thể nhỏ hơn state nhưng phải đánh giá lại phần bị bỏ.
9. LLM chỉ đề xuất ID có sẵn và hành động thuộc danh sách cho phép. Output sai schema/ID/dependency bị từ chối; lỗi được ghi, không coi fallback là run đúng cấu hình thử nghiệm.
10. Toàn bộ nhánh dùng một budget ledger. Tài liệu và tool output là dữ liệu, không được thay control flow bằng chỉ dẫn bên trong.
11. Kết luận chỉ dựa trên bằng chứng generator thực sự được cung cấp. Verifier không lấy evidence trong state nhưng ngoài context để hợp thức hóa đáp án thiếu tiền đề.
12. `complete` chỉ có nghĩa đã đáp ứng rubric theo scope và bằng chứng của run. Không tuyên bố đã tìm hết tài liệu ngoài corpus.

## 7. Xref: xây offline, resolve theo scope lúc chạy

Tạo sidecar index tham chiếu gắn với manifest corpus; không cần re-embed để thử trên corpus hiện có. SQLite đủ cho adjacency và tra ID; document/unit text lấy từ kho nội dung.

`XrefEdge` lưu source unit/revision hoặc legacy scoped ID, source span, raw reference, target document/unit/clause/point nếu xác định được, loại quan hệ, parser version, checksum, trạng thái resolved/ambiguous/missing, và cách ràng buộc phiên bản đích.

- Trích xuất quy tắc cho mẫu dẫn chiếu tường minh; xử lý danh sách/khoảng Điều, khoản/điểm và “Điều này”, “Bộ luật này”.
- Resolve tên viết tắt và văn bản khác qua registry có kiểm tra danh tính. Không dùng vector similarity làm xác nhận duy nhất cho ID đích.
- “Theo quy định pháp luật” là unresolved reference; có thể đề xuất search nhưng không tạo cạnh resolved giả.
- Tham chiếu từ snapshot cũ cần phân biệt đích được chỉ đích danh theo phiên bản với đích chọn theo thời điểm áp dụng. Không tự thay bằng bản mới nhất nếu làm thay ý nghĩa dẫn chiếu; trường hợp không xác định được phải báo ambiguity.
- Quan hệ sửa đổi/thay thế không tự động hợp nhất thành toàn văn. Tận dụng amendment/effectivity guard; nội dung cần hợp nhất chưa được xác minh phải được giữ ở trạng thái chưa đủ.
- Theo chiều xuôi trước; reverse xref là policy tùy chọn sau ablation, không mở toàn bộ fan-out.
- Dedup theo target revision và span; visited theo request + requirement + revision + action signature. Dùng lại evidence đã có cho requirement khác mà không fetch lại. Chặn A→B→A.

Xref lookup lấy tài liệu gốc trực tiếp. Điểm rerank thấp theo câu gốc không được tự động loại một đích cần đọc để hoàn tất dependency; cần đánh giá vai trò của nó. Xref vẫn phải qua scope, kiểm tra nội dung và giới hạn ngân sách.

Audit offline trên nhãn hiện có: độ đúng liên kết, tỷ lệ resolve, đích thiếu, ambiguous; khả năng đi 1/2 cạnh từ các seed thực tế đến căn cứ đang thiếu. Dùng gold chỉ ở phía chấm sau retrieval. Báo riêng reachability chẩn đoán và kết quả agent thực chạy; không dùng oracle chọn seed hoặc cạnh lúc runtime.

## 8. Retrieval, rerank, coverage và context

Tách public primitive `retrieve_candidates(request, scope)` và `rank_candidates(request)` khỏi orchestration. Search primitive không condense/decompose/listwise ngầm. Giữ `HybridRetriever.retrieve()` làm facade baseline tương thích.

Không tạm đổi `retriever.decomposer=None` hoặc các thuộc tính chung theo request: UI hiện giữ một pipeline singleton và có thể chạy nhiều request. Agent state, config hiệu lực và trace nằm riêng theo request; chỉ backend/cache an toàn đồng thời mới chia sẻ.

Round đầu giữ chính sách pool baseline để có phép so sánh rõ. Các round sau chỉ tìm phần thiếu, dùng kết quả đã xác minh làm ngữ cảnh truy vấn. Kết quả nhánh lỗi không được đánh dấu nhu cầu đã giải quyết.

Mỗi score lưu query ID, backend, score type, và input hash. Chấm theo requirement để tránh mất bằng chứng phụ; câu gốc dùng để kiểm tra phạm vi. Phiên bản đầu không chế công thức cộng hai xác suất chưa được hiệu chỉnh. Dùng quota shortlist theo requirement, giữ bằng chứng trực tiếp cần thiết, rồi policy chọn bộ có kiểm tra ngữ nghĩa.

Coverage đọc nội dung/span thực: một requirement có thể cần nhiều Điều, một Điều có thể hỗ trợ nhiều requirement. Kiểm tra điều kiện áp dụng và ngoại lệ nếu chúng quyết định kết luận. Không bắt buộc mọi câu hỏi đều tìm thêm thủ tục/tố tụng khi người dùng không hỏi.

Rerank là relevance, coverage là đủ bằng chứng, verifier là claim support: ba trách nhiệm tách biệt. Listwise là strategy có thể tái sử dụng trong selector, không thêm một lượt listwise tốn phí ở mọi round chỉ vì module đã có.

Khi materialize, đọc đủ khoản/điểm và các đoạn cần thiết của Điều, có locator cho từng span; không mặc định các chunk tìm được đại diện cho toàn Điều. Có khoảng trống hoặc cắt bớt phải ghi lại. Context selector ưu tiên bộ bằng chứng bao phủ nhu cầu và giữ các tiền đề; nếu không đủ ngân sách thì giảm phạm vi kết luận hoặc partial. Không chỉ tăng top-k để tuyên bố metric tốt hơn.

## 9. Scope và lộ trình dữ liệu

Hai chế độ minh bạch cùng contract:

- `snapshot_only`: dùng corpus legacy cố định, manifest/checksum và khóa unit ổn định trong snapshot. Cho phép thử agent mà không giả nhận đã biết hiệu lực hiện hành. Kết quả nêu phạm vi snapshot; không tự tạo effective dates/revision IDs có ý nghĩa pháp lý.
- `verified_temporal`: nối identity → unit/revision → quality-approved chunks → generation index thật; resolve theo QueryScope, chất lượng và thời điểm. Cần triển khai/kiểm chứng bridge hiện còn thiếu trước khi bật chế độ này.

Reuse `ResolvedScope`/`ScopedRetriever` ở đường temporal; agent dùng wrapper `EvidenceScope` có capability và manifest của snapshot legacy. Không ép legacy chunks thành ChunkV2 bằng cách bịa metadata.

Lọc eligibility trước hoặc trong search, sau đó kiểm tra lại mọi evidence. Chỉ lọc top-N sau search có thể làm mất toàn bộ ứng viên hợp lệ; backend chưa hỗ trợ prefilter phải có scoped index hoặc overfetch/refill có quota và đánh dấu giới hạn. Refill cũng tiêu ngân sách tool/search, không tạo retry vô hạn.

Gắn index, unit map, xref và catalog vào cùng generation manifest. Kiểm tra hash/readiness rồi mới publish con trỏ active; request pin generation để không đọc lẫn dữ liệu khi ingest. Có thể dùng manifest bất biến + chuyển active pointer cho bản đầu; không cần dịch vụ phân tán. Không nhận catalog commit đơn thuần là index activation.

## 10. Compose, verify và trạng thái đầu ra

Generator nhận checklist, facts, scope, unresolved items và bundle nguyên văn. Sinh cấu trúc claims có evidence IDs trước khi render citation [n]. Quan hệ suy ra cần lưu các premise IDs. Không cần ghi private chain-of-thought; trace chỉ lưu sự kiện, căn cứ và lý do quyết định ngắn.

Verification hai tầng:

1. Code kiểm tra schema, ID/spans tồn tại, checksum/scope, citation map, dữ kiện số/ngày/phủ định có thể kiểm tra, dependency và coverage của context.
2. Model kiểm tra mỗi claim có được đoạn gốc hỗ trợ, điều kiện/ngoại lệ, kết luận quá mức và yêu cầu bị bỏ sót; input gồm facts và nguyên văn, không chỉ bản tóm tắt/nhận xét của generator.

Model verifier có thể dùng backend khác qua interface, nhưng đổi model không bảo đảm độc lập hoặc đúng. Cần rà soát thủ công mẫu và lỗi đồng thuận. Mâu thuẫn nguồn không được giải quyết bằng số đông nguồn cùng chép một nơi.

Nếu sửa câu chữ làm thay đổi nghĩa, kiểm tra lại claims liên quan trước khi render. Một lần sửa thất bại phải hạ mức kết luận hoặc trả thiếu dữ liệu; không xuất nguyên đáp án bị verifier chặn. Lỗi dịch vụ verifier có trạng thái degraded riêng và không được đánh dấu verified complete.

Phân biệt `answer`, `partial`, `clarify`, `abstain`, `error`, `cancelled`. Thiếu dữ kiện người dùng chỉ hỏi lại khi ảnh hưởng trọng yếu đến kết luận; trường hợp có thể trả lời theo điều kiện thì nêu điều kiện rõ. Corpus không có văn bản không đồng nghĩa người dùng cung cấp thiếu thông tin.

`Answer` hiện chỉ có text/citations/refused/hits nên không biểu đạt được đầy đủ các trạng thái mới. Dùng `AgentResult` riêng; public V2 trả đầy đủ trạng thái. Adapter V1 được mô tả rõ: refusal dùng câu REFUSAL đúng invariant; partial/clarify có text và metadata bổ sung ở response/trace. Không dùng `refused=False` làm bằng chứng đáp án hoàn chỉnh. Thay schema legacy cần review theo ownership trong repo, không âm thầm mở rộng ý nghĩa trường.

## 11. Một runtime cho sync và streaming

### Chọn chế độ bằng Think

- Nút Think trên composer mặc định tắt; trạng thái bật dùng chữ/icon xanh và nền xanh nhạt theo mẫu người dùng.
- Request có `think: false` (hoặc thiếu trường) đi luồng RAG hiện tại; không khởi tạo hoặc gọi agent. Condense/decomposition của baseline giữ theo cấu hình hiện tại.
- Chỉ `think: true` mới chọn agent. Backend validate boolean thật, không dùng truthiness cho chuỗi `"false"`.
- Chụp trạng thái tại lúc gửi, lưu theo lượt chat. Đổi nút giữa lúc chờ không đổi request đang chạy. Mở/tạo chat khác reset về tắt.
- Khi agent chưa sẵn sàng, trả trạng thái unavailable rõ ràng trước khi bắt đầu SSE; không fallback thành baseline mà vẫn nhận là agent.
- JSON và SSE dùng chung quyết định routing. Khi agent sẵn sàng, adapter tại điểm tích hợp UI phải dùng runtime chung bên dưới; không triển khai một agent riêng cho streaming.

Một `run_events(request)` phát event có kiểu; `run()`/CLI thu events thành result, UI chuyển events thành SSE/response. Tất cả cùng call core, prompt, budget và final result.

Events: prepared, scope_resolved, planned, round_started, evidence_added, coverage_assessed, verification_completed, final, error/cancelled. Draft không được stream như đáp án cuối. UI có thể hiển thị tiến độ và nguồn ứng viên (gắn nhãn chưa xác minh); text final được phát sau verify. Nếu muốn hiệu ứng gõ chữ, render phần text đã được duyệt.

Adapter tương thích giữ được `sources/token/done` hiện có; citation numbering chỉ chốt khi bundle final đã ổn định. Thêm trạng thái rõ ở V2; không để UI tự suy ra complete từ event done. Sequence ID đảm bảo thứ tự, final tối đa một lần, cancellation không bị convert thành complete.

Cache mới phải namespace theo model/provider, prompt/config/schema version và nội dung đầu vào; các quyết định phụ thuộc corpus cần snapshot/scope hash. Cache hit không tiêu provider request nhưng vẫn được ghi logical usage. Không dùng cache của một snapshot khác để quyết định applicability.

## 12. Ranh giới module đề xuất

```text
src/rag/agent/
  contracts.py       # request, requirement, action, result, event
  orchestrator.py    # chuyển trạng thái và một vòng lặp duy nhất
  state.py           # evidence ledger, dependency, assessment
  policy.py          # lập next actions, stop và budget admission
  planner.py         # adapter decomposer → requirements
  evidence.py        # materialize, assess, chọn bundle
  verification.py    # schema/ID checks + semantic verifier
  adapters.py        # backend hiện tại, legacy answer/trace/event
src/rag/retrieve/
  ...                # thêm public candidate/ranking primitives
src/rag/xref/
  extract.py         # offline parser + provenance
  repository.py      # sidecar adjacency và registry
  resolver.py        # resolve trong scope, không tự loop
src/rag/versioning/
  ...                # bridge thật đến chunks/index generation
```

Gộp file nhỏ nếu cần, giữ trách nhiệm trên. Các port chính: CandidateRetriever, EvidenceRepository, XrefResolver, CoverageAssessor, AnswerComposer, AnswerVerifier, EventSink. Không tạo plugin registry tổng quát hoặc agent con cho từng port khi chưa có nhu cầu.

## 13. Kế hoạch triển khai theo mốc có điều kiện nghiệm thu

| Mốc | Công việc | Nghiệm thu |
|---|---|---|
| P0 — contracts và phép đo | Chốt schema/bất biến, state transitions, profiles, status, fixture và rubric; ghi manifest baseline | Phân biệt retrieval/context/answer metrics; trace tái lập được; các yêu cầu không bị cắt âm thầm |
| P1 — một runtime + scope snapshot | Public search không decompose, adapters, event core, pin manifest và request-local state | Agent one-round tương đương đường legacy trong cấu hình parity; sync/stream cùng final; hai request không lẫn state |
| P2 — xref sidecar | Unit registry, trích xuất/resolve, đọc nội dung theo locator, audit offline | Báo cáo precision/coverage/ambiguity, chống cycle, đúng document/snapshot; giữ missing targets rõ ràng |
| P3 — adaptive evidence loop | Requirement coverage, next actions, round 2/3, dedup/budgets và context bundle | Có case thật giải quyết bằng chứng thiếu; không tìm lại cùng hành động vô ích; no-progress và hết budget dừng đúng |
| P4 — verification và UX | Structured claims, verifier, repair, partial/clarify/abstain, stream sau verify | Không xuất claim bị chặn; không tự nhận đủ khi context thiếu; final một lần và cancellation đúng |
| P5 — temporal integration | Nối catalog-quality-chunk-index-generation, eligibility ở search/xref | Fixture revision/partial amendment/as-of, activation và snapshot consistency chạy qua đường hỏi đáp thật |
| P6 — acceptance và rollout | Ablation, holdout review, chất lượng/chi phí/p95, bật theo profile | Đạt ngưỡng đã chốt trước test; có rollback profile, lỗi fallback được báo riêng |

Dependencies: P0→P1; P2 cần IDs/snapshot từ P1; P3 cần P1 và P2 cho nhánh xref; P4 cần P3; P5 có thể hoàn thiện sau snapshot pilot nhưng bắt buộc trước khi quảng bá temporal/current-law; P6 chốt chất lượng cuối. Mỗi mốc có owner/reviewer của team được chỉ định khi giao việc; không giả định nhân sự cụ thể. Thực hiện theo branch/PR policy của repo, không triển khai tất cả trong một PR.

Không bật agent thiếu verifier thành mặc định production khi mới xong P3. Có thể dùng chế độ diagnostics/retrieval-only để đo từng mốc. Code cũ vẫn là đối chứng, nhưng đường agent mới phải chỉ có một owner của decomposition và selection.

## 14. Đánh giá, tests và release gate

Bộ 64 câu và hard25 đã được xem để thiết kế nên coi là regression/dev, không coi là holdout chưa thấy. Chuẩn bị tập test mới có người review độc lập và freeze split/rubric trước tuning. Nhãn theo requirement và evidence span/unit revision, cho phép nhiều bộ căn cứ tương đương hợp lệ, nhánh có điều kiện và phần cần hỏi lại.

Ablation tối thiểu: baseline frozen; adaptive search không xref; xref giới hạn không adaptive search; adaptive search+xref; cấu hình đầy đủ có verifier. Các thay đổi model/HyDE/listwise đo riêng nếu thay đổi. Giữ snapshot/config tương thích, dùng artifact baseline đã lưu khi phù hợp; không gọi lại API baseline chỉ để đổi mốc đối chứng.

Đo:

- Retrieval: candidate recall, all-gold theo ngân sách cố định, căn cứ hữu ích mới mỗi vòng, đường đi/độ đúng xref.
- Context: coverage theo requirement, đủ premise/ngoại lệ, tỷ lệ evidence mất do selector hoặc cắt ngân sách.
- Answer: đúng, đầy đủ, claim support, citation precision và coverage; lỗi số/ngày/đối tượng/phiên bản.
- Behavior: clarify/partial/abstain phù hợp, mâu thuẫn, thiếu corpus, giới hạn và tool failure.
- Operations: rounds/depth riêng, logical/provider calls, retry/cache, usage/cost có căn cứ, p50/p95 trên điều kiện cache và concurrency xác định.

Top5 lịch sử giữ nguyên định nghĩa. Không so all-gold trên pool 50 với top5 rồi gọi đó là cải thiện ranking; báo ngân sách từng phép đo và kết quả end-to-end riêng.

Tests bắt buộc tập trung vào failure modes: nested decomposition không xảy ra; facts/negation/date không bị thêm; cùng số Điều khác luật/phiên bản; source/target xref sai hoặc không tồn tại; cycle/fan-out; nguồn mâu thuẫn; requirement cần nhiều Điều; evidence bị mất khi pack context; citation đúng ID nhưng sai nội dung; budget hết từ verifier; JSON sai; partial backend failure; timeout/retry/cancel; snapshot đổi giữa request; concurrency; sync/stream parity; legacy adapter statuses.

Semantic quality cần benchmark và review nội dung, unit test với fake model không chứng minh được chất lượng thật. Báo cáo số mẫu và paired regressions; dùng bootstrap nếu thích hợp nhưng không coi tập 25 câu là bằng chứng đủ cho mọi lĩnh vực.

Gate cấu trúc bắt buộc: zero invalid evidence/citation IDs trong output đã render, zero silent cross-snapshot evidence, zero budget bypass trong kiểm tra và trace. Đây là acceptance checks, không phải bảo đảm lỗi không thể tồn tại.

Gate chất lượng cần chốt bằng số ở P0 trước khi chấm holdout: ngưỡng correctness/completeness/citation, mức regression chấp nhận được theo nhóm, ngân sách và latency. Không bịa ngưỡng tối ưu khi chưa có generation baseline. Lỗi nặng đã có fixture phải qua review; không che bằng điểm trung bình tăng.

Artifact mỗi run: config không chứa key, corpus/generation manifest, model/prompt hashes, per-question outcomes, tool/events trace, claim/evidence mappings, usage/latency, paired regression report. Tách strict eval khỏi product degraded mode.

## 15. Điều ổn định và điều được phép thay đổi

Ổn định: state/contracts, source provenance, snapshot/scope, budget ownership, vòng lặp chung, output statuses, verifier boundary, phương pháp đo.

Điều chỉnh qua config/strategy: số rounds, query/xref quotas, model, HyDE/BM25, rerank backend, shortlist, selector, context budget và độ chặt của coverage. Thay strategy cần benchmark; không cần sửa topology.

Các bất định cần pilot giải quyết: xref cứu được bao nhiêu căn cứ thiếu; coverage assessor sai ở đâu; giới hạn số vòng đem lại lợi ích bao nhiêu; verifier có giảm lỗi mà tăng abstain quá mức không; context ngân sách hiện có có đủ cho câu nhiều luật không. Không coi các câu hỏi này đã được trả lời bởi thiết kế.

## 16. Tài liệu nội bộ đã đối chiếu

- [Pipeline](../../src/rag/pipeline.py)
- [Hybrid retriever](../../src/rag/retrieve/hybrid.py)
- [Scoped retriever contract](../../src/rag/retrieve/interfaces.py)
- [Context selection](../../src/rag/retrieve/context.py)
- [Generation và citation](../../src/rag/generate/answer.py)
- [Version repository](../../src/rag/versioning/repository.py)
- [Models và ResolvedScope](../../src/rag/models/results.py)
- [Hard25 report](../../../../evals/team-4.2/results/multihop-hard25-current-20261106-verified/REPORT.md)
- [Optimization review](../../../../evals/team-4.2/results/optimization-review-64q/proposal.md)
- [Evaluation guidelines](../../../../docs/EVALUATION.md)
- [Git workflow](../../../../docs/GIT-WORKFLOW.md)
