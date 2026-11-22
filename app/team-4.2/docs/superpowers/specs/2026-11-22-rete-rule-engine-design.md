# Rule engine v2: lõi đa luật + mạng phụ thuộc tăng dần ba trị (join kiểu TREAT) — thiết kế

Ngày: 2026-11-22 · **Bản 2** (sau khi khảo sát các biến thể của Rete) · Người quyết định: Tùng (A) ·
Trạng thái: **đã duyệt** (Tùng, 2026-11-22); bước tiếp theo là kế hoạch triển khai

Thay đổi so với bản 1: (1) không còn "Rete mệnh đề không join": mạng gồm phần điều kiện (mệnh đề, tăng dần) và phần
join/đếm/phủ định trên đối tượng kiểu TREAT (§6.1); (2) thêm ngữ nghĩa ba trị cho đối tượng, đếm, phủ định (§5.6);
(3) thêm bảng các biến thể đã xét và lý do (§4.2); (4) `ReteEvaluator` đổi tên `NetworkEvaluator`; (5) benchmark thêm
trục "số đối tượng mỗi hồ sơ" (§9); (6) bỏ cách gọi "TMS" của Drools (§6.3); (7) thêm giai đoạn 7 (§11).

Liên quan: `2026-11-14-contract-concept-check-design.md` §5 (danh mục), §8 (engine hiện tại).
Code hiện tại: `src/rag/bridge/engine.py`, `catalog.py`, `concepts.yaml`, `check.py`, `recheck.py`,
`src/rag/contracts/graph/tools.py` (`check_concept`).

## 1. Mục đích và lý do

Dự án sang W04 chuyển từ "soát hợp đồng lao động" sang "soát nhiều loại hợp đồng". Engine hiện tại đúng cho 44 rule
lao động nhưng có ba chỗ chặn việc mở rộng:

1. Dữ kiện, đơn vị, finding viết cứng cho lao động (`CONTRACT_FACTS`, `USER_FACTS`, `employee_impact`,
   `_BASE` coi tháng = 720 giờ, hai hook `_contract_level_check`, `_unstated_restriction` nằm trong lõi).
2. Không có ngoại lệ giữa các rule / giữa các luật (BLDS là luật chung, BLLĐ / LTM là luật chuyên ngành ghi đè).
   `cases` chỉ là "case đầu tiên khớp" bên trong một rule.
3. Không có kết luận trung gian (rule sinh dữ kiện cho rule khác), ví dụ BLLĐ Đ20.2: HĐ xác định thời hạn hết hạn,
   NLĐ vẫn làm việc, quá 30 ngày không ký mới → trở thành HĐ không xác định thời hạn.

Người dùng muốn có một engine **dựa trên Rete** để chứng minh nó chịu được khi số rule tăng (ước tính 160–250 rule
khi đủ 7 gói, benchmark tới 10.000 rule tổng hợp) và để có phần "phương pháp nâng cao" trình bày với mentor.
Các ca demo (phụ lục theo thời gian, nhiều hợp đồng của một người lao động) cần join, đếm, phủ định trên nhiều
văn bản.

Thiết kế ghép các hệ thống đã khảo sát: ngữ nghĩa ngoại lệ của Catala; dữ kiện suy ra có justification (tính lại
theo phụ thuộc, không phải truth maintenance của Drools); mạng mệnh đề ba trị (US 7418434); join kiểu TREAT; vòng hỏi
theo mục tiêu của Oracle Intelligent Advisor; cây giải thích kiểu s(CASP). Phần riêng của dự án: dữ kiện do LLM trích
kèm trích dẫn nguyên văn, đi vào justification; ngữ nghĩa ba trị cho đối tượng/đếm/phủ định (§5.6).

## 2. Mục tiêu / không mục tiêu / phản mục tiêu

**Mục tiêu**
- G1. Lõi engine không biết gì về lao động; mỗi luật là một *domain pack* (YAML) tự khai báo dữ kiện, đơn vị,
  finding, vai trò.
- G2. Ngoại lệ có ưu tiên giữa rule và giữa pack; kết luận trung gian (dữ kiện suy ra).
- G3. Hai evaluator cùng ngữ nghĩa sau interface `Evaluator`: `ReferenceEvaluator` (tính toàn bộ, theo thứ tự topo)
  và `NetworkEvaluator` (mạng biên dịch một lần, phiên theo hồ sơ, cập nhật tăng dần, §6).
- G4. `explain()` (cây giải thích tới câu trích trong hợp đồng) và `next_questions()` (dữ kiện nên hỏi người dùng).
- G5. Benchmark tái lập được, báo trung thực ba kịch bản (§9).
- G6. Gói `labor` cho kết quả **giống hệt** engine cũ trên toàn bộ test + eval hiện có.
- G7. Gói thứ hai `civil_general` + `civil_loan` (BLDS phần chung hợp đồng + vay tài sản) chạy mà không sửa lõi.
- G8. Rule xuyên đối tượng: đếm, ghép cặp, phủ định trên nhiều hợp đồng / phụ lục của một người lao động, có soát
  theo ngày hiệu lực (§5.6). Phục vụ các hồ sơ a1, b1–b5.

**Không mục tiêu**
- Tự nhận diện loại hợp đồng (người gọi truyền danh sách pack; mặc định `labor`). Spec riêng sau.
- Tự gom văn bản về cùng một người lao động bằng CCCD/tên: bản đầu dùng khai báo tay trong `dossier.yaml`.
- Phreak / LEAPS / Rete/UL và các biến thể tối ưu khác: hoãn, lý do ở §4.2. Chỉ làm khi benchmark chỉ ra mạng chậm.
- Join nhiều bảng với thứ tự tối ưu theo ước lượng số bản ghi (Hiperfact): join ở đây chỉ vài đối tượng.
- LLM sinh rule.

**Phản mục tiêu** (xảy ra là thất bại dù code chạy)
- Kết quả soát gói lao động đổi so với engine cũ mà không có lý do được ghi.
- Network và Reference cho kết quả khác nhau trên bất kỳ đầu vào nào (kể cả có đối tượng).
- Thiếu dữ kiện thành vi phạm (bất biến cũ, giữ nguyên, kể cả qua ngoại lệ, dữ kiện suy ra, đếm và phủ định).
- Benchmark chỉ khoe kịch bản mạng thắng, hoặc chỉ đo trục số rule mà bỏ trục số đối tượng.
- Gọi thuật toán là "Rete đầy đủ" khi không có bộ nhớ beta; tên đúng ở §6.1.

## 3. Ràng buộc

- Thuần Python, không I/O trong lõi (như `engine.py` hiện tại). Không thêm dependency.
- YAML hiện có (`concepts.yaml` v0.2) nạp được không cần sửa tay; trường mới đều tùy chọn.
- API cũ giữ làm lớp tương thích: `evaluate()`, `evaluate_concept()`, `RuleResult` (kể cả `legality`,
  `employee_impact`), `Fact`, `CONFLICT`, `Facts` — các module `facts_map`, `graph_facts`, `tools`, `check` không bắt
  buộc sửa ở giai đoạn 1.
- File `concepts.yaml` còn được LU (đồ thị luật) đọc các trường `roles`, `id`, `label`, `scope`, `phase`,
  `applies_to`, `anchors`, `value_sources` — không đổi tên / vị trí các trường này.

## 4. Phương án đã xét

### 4.1 Cách xây

| | Cách | Đánh đổi | Kết luận |
|---|---|---|---|
| A | Tự viết: mạng phụ thuộc tăng dần ba trị (điều kiện, chia sẻ node) + join kiểu TREAT cho rule xuyên đối tượng | Ngữ nghĩa đúng ý (ba trị, ngoại lệ, giải thích); tự chịu lỗi lan truyền | **Chọn**, làm `NetworkEvaluator` |
| B | Thư viện Rete có sẵn (`clipspy`, `experta`, `durable_rules`) | Có Rete + TMS sẵn; không có ba trị / ngoại lệ ưu tiên, phải mô phỏng U bằng dữ kiện phụ; hai thư viện gần như ngừng bảo trì | Loại |
| C | Đồ thị phụ thuộc kiểu Catala, tính toàn bộ theo thứ tự topo | Đơn giản, đủ dùng ở quy mô thật | **Chọn**, làm `ReferenceEvaluator` và chuẩn đối chiếu |

C giữ vai trò chuẩn đúng và phương án dự phòng; A là chiến lược tối ưu đặt sau cùng interface. Ngữ nghĩa và định dạng
YAML được chốt kỹ (khó sửa về sau); chiến lược chạy được phép tối ưu dần (dễ sửa).

### 4.2 Các biến thể của Rete đã xét

| Biến thể | Ý chính | Quyết định | Lý do |
|---|---|---|---|
| Rete gốc (Forgy) | Bộ nhớ alpha + beta (lưu kết quả nối từng phần) | **Lấy ý tưởng**: chia sẻ node alpha, lan truyền thay đổi. **Không lấy** bộ nhớ beta | Điều kiện trên bảng dữ kiện không có phép nối; hồ sơ chỉ vài đối tượng |
| **TREAT** (Miranker 1987) | Bỏ bộ nhớ beta, nối tính lại từ bộ nhớ alpha, bắt đầu từ đối tượng đổi | **Dùng cho join/đếm/phủ định** | Hồ sơ nhỏ nên nối rẻ; xóa đơn giản (b4); ít trạng thái; dễ đối chiếu. Độ phức tạp tiệm cận như Rete, khác nhau ở hằng số (theo chính tác giả) |
| LEAPS | Đánh giá lười, bỏ bớt trạng thái | Hoãn | Trạng thái không phải vấn đề khi mỗi phiên chỉ một hồ sơ |
| Phreak (Drools) | Lười, theo mục tiêu, bộ nhớ ba tầng, lan truyền theo tập | Hoãn | Có ích khi mỗi phiên có hàng nghìn rule và chỉ vài rule liên quan; số liệu chỉ từ nhà cung cấp. Xem lại nếu benchmark cho thấy mạng chậm |
| Rete/UL (Doorenbos) | "Left unlinking" tránh đánh giá node chờ dữ liệu | Hoãn | Lợi ích ở hàng chục nghìn rule, lớn hơn quy mô benchmark |
| Rete II / III / NT (Forgy) | Cải tiến thương mại | Loại | Cách triển khai không được công bố, không có gì để hiện thực |
| Hiperfact | Thứ tự nối theo ước lượng số bản ghi, cấu trúc dữ liệu thân thiện bộ nhớ đệm | Loại | Tối ưu nối lớn; nối ở đây chỉ vài đối tượng; một nguồn |
| DBSP / Differential Dataflow | Khung hình thức bảo trì view tăng dần, có đệ quy và tổng hợp | Loại (nhắc như nền lý thuyết) | Hướng hệ dữ liệu lớn; nguồn đã đọc không so sánh trực tiếp với Rete |

Điều chưa xác minh / giới hạn (phải nói rõ khi trình bày):
- Chưa kiểm với bài gốc việc TREAT gốc xử lý điều kiện phủ định; phép đếm trên bộ nhớ alpha là phần mở rộng do
  nhóm thiết kế. Không tìm thấy tài liệu công bố về TREAT/Rete ba trị cho nối và đếm: ngữ nghĩa §5.6 là thiết kế
  của nhóm.
- Tuyên bố "chịu được khi số rule tăng" chỉ đúng cho phần mạng điều kiện. Phần join phụ thuộc **số đối tượng mỗi
  hồ sơ**, nên benchmark có hai trục (§9).
- So sánh TREAT / Rete / LEAPS lấy từ bài của chính Miranker và một luận án; chưa đọc toàn văn.

Nguồn: Miranker, AAAI 1987 (cdn.aaai.org/AAAI/1987/AAAI87-008.pdf); Miranker, TREAT vs Rete
(cs.utexas.edu/~miranker/treat-vs-rete-bib.html); Brant et al., VLDB 1991 (vldb.org/dblp/db/conf/vldb/BrantGLM91.html);
Doorenbos, CMU-CS-95-113; Red Hat, Phreak; JBoss DOC-12695 (Rete III); Hiperfact, arXiv 2012.02710; DBSP, arXiv
2203.16684; US 7418434.

## 5. Ngữ nghĩa (phần chuẩn, cả hai evaluator phải tuân theo)

### 5.1 Giá trị

- Dữ kiện: `Fact(value, unit, source, uid, quote, ...)` như hiện tại; `source` thêm `"derived"`.
- Trạng thái đặc biệt: thiếu (`None`), `CONFLICT` (đã có), **`UNKNOWN`** (mới — dữ kiện suy ra mà chưa xác định được).
  `UNKNOWN` xử lý như `CONFLICT` ở lá: mọi phép so sánh → U; `present`/`absent` → U.
- Logic ba trị Kleene cho `all`/`any`/`not` — giữ nguyên `eval_cond`.
- `compare`/`convert` giữ nguyên, nhưng bảng quy đổi lấy từ pack (§7). Gói `labor` khai báo đúng bảng `_BASE` hiện tại.

### 5.2 Đánh giá một rule

Giữ nguyên toàn bộ bảng trạng thái của `_evaluate_rule` hiện tại (applicability → resolve_law → present →
check → on_silence). Hai hook được chuyển khỏi lõi thành ngữ nghĩa khai báo:

- `_contract_level_check` → pack khai báo `document_facts` (với `labor`: đúng tập `CONTRACT_FACTS`). Quy tắc chung:
  rule mà `check` chỉ dùng `document_facts`, và có ít nhất một dữ kiện đó, được coi là `present`.
- `_unstated_restriction` → thuộc tính rule `unstated_false: bool`. Bộ nạp tự đặt `true` khi `check` có dạng
  `{fact: <slot bool>, op: eq, value: false}` không có `law` (đúng điều kiện cũ), để YAML cũ không phải sửa; rule mới
  có thể ghi rõ. Ý nghĩa chung: khái niệm có mặt nhưng không nói tới hạn chế → coi như không có hạn chế.
- `outcome` truyền nguyên dạng (dict) vào `RuleResult.outcome`; `legality`, `employee_impact` giữ làm thuộc tính đọc
  từ `outcome` để tương thích.

### 5.3 Dữ kiện suy ra (mới)

Khai báo trong pack:

```yaml
derived:
  - fact: contract_kind_effective
    unit: null
    definitions:
      - id: base
        when: null                       # luôn áp dụng
        from: contract_kind              # lấy giá trị dữ kiện khác ...
      - id: d20k2a
        exception_of: base
        when: {all: [{fact: contract_kind, op: eq, value: xac_dinh_thoi_han},
                     {fact: worked_after_expiry_days, op: gt, value: 30, unit: day},
                     {fact: new_contract_signed, op: eq, value: false}]}
        value: khong_xac_dinh_thoi_han   # ... hoặc hằng
        anchors: [{pid: "bo-luat:45/2019/QH14#d20.k2.a", role: basis}]
```

(Ví dụ minh họa; điều kiện Đ20.2 phải được kiểm lại theo văn bản trước khi đưa vào pack.)

Ngữ nghĩa cây ngoại lệ (theo Catala, thêm U):

Với một node định nghĩa `n` có các ngoại lệ con `E(n)`:
1. Tính mọi con. Nếu ≥1 con cho giá trị: tất cả cùng giá trị → giá trị đó; khác nhau → `CONFLICT`.
2. Không con nào cho giá trị nhưng ≥1 con là `UNKNOWN` → `UNKNOWN` (không được bỏ qua ngoại lệ chưa biết).
3. Mọi con "không áp dụng": `when(n)` = T → giá trị của `n` (`value`, hoặc dữ kiện `from` — nếu `from` thiếu thì
   *không áp dụng*, nếu `CONFLICT`/`UNKNOWN` thì giữ nguyên); F → *không áp dụng*; U → `UNKNOWN`.

Các gốc (định nghĩa không có `exception_of`) kết hợp như anh em theo bước 1–2. Kết quả cuối "không áp dụng" →
dữ kiện thiếu (`None`). Dữ kiện suy ra mang justification: định nghĩa thắng + các dữ kiện đầu vào (§8).

`RuleResult.missing_facts` chỉ liệt kê dữ kiện *đầu vào*: dữ kiện suy ra đang thiếu / UNKNOWN được mở ra thành các
dữ kiện đầu vào còn thiếu của những định nghĩa chưa quyết định được (để `next_questions()` và UI hỏi đúng thứ người
dùng trả lời được); tên dữ kiện suy ra ghi vào `reasons` (`derived_unknown:<tên>`).

Bộ nạp từ chối: phụ thuộc vòng giữa dữ kiện suy ra; `exception_of` trỏ tới định nghĩa không tồn tại; dữ kiện suy ra
trùng tên dữ kiện đầu vào.

*Chốt khi triển khai (giai đoạn 3, `rules/derived.py`):*
- Con `CONFLICT` của một nút thắng mọi giá trị anh em (spec không nói; chọn thận trọng). Con `UNKNOWN` thua giá trị
  (đúng chữ bước 1: một ngoại lệ đã cho giá trị thì dùng giá trị đó dù ngoại lệ anh em chưa biết).
- Ngoại lệ cho giá trị hay `UNKNOWN` đều thắng gốc kể cả khi `when` của gốc là F (ngoại lệ không phụ thuộc điều kiện gốc).
- Dữ kiện đầu vào truyền vào mà trùng tên dữ kiện suy ra bị bỏ qua ở cả hai evaluator; dữ kiện suy ra luôn do định nghĩa
  quyết định. `Fact.derived_by` ghi id định nghĩa thắng; `facts_used[<tên>].derived_by` đưa nó ra kết quả.
- `missing_facts` mở dữ kiện suy ra thiếu / `UNKNOWN` thành dữ kiện đầu vào thiếu của định nghĩa có `when` khác F: tên
  thiếu trong lá `when` (chỉ khi `when` = U) và `from` thiếu; mở đệ quy qua dữ kiện suy ra khác. `reasons` thêm
  `derived_unknown:<tên>`.

### 5.4 Ngoại lệ giữa rule (mới)

Rule có thể khai báo `exception_of: <concept_id>/<rule_id>` (được trỏ sang pack khác). Rule ngoại lệ thay thế
rule gốc khi nó *áp dụng*:

| Trạng thái applicability của ngoại lệ | Kết quả rule gốc |
|---|---|
| T | `NOT_APPLICABLE`, reason `overridden_by:<id>`; rule ngoại lệ tự cho kết quả của nó |
| F | rule gốc giữ nguyên kết quả |
| U | nếu rule gốc là `FAIL`: hạ thành `UNKNOWN` / `needs_facts`, reason `exception_unknown:<id>`; trạng thái khác giữ nguyên, thêm reason `exception_unknown:<id>` |

Lý do hàng U: giữ bất biến "thiếu dữ kiện không thành vi phạm"; PASS giữ nguyên để không làm ngập UNKNOWN (*quyết
định của người viết spec*, xem §12).

Nhiều ngoại lệ cùng T cho một rule gốc: cả hai đều cho kết quả; rule gốc `NOT_APPLICABLE` với reason liệt kê cả hai.
Ngoại lệ lồng nhau (ngoại lệ của ngoại lệ) được phép; không vòng.

*Chốt khi triển khai (giai đoạn 3, `rules/exceptions.py`):*
- Rule ngoại lệ "áp dụng" khi applicability T **và** giá trị luật chọn được (không case nào khớp thì F; case chưa quyết
  định thì U). Một rule coi là áp dụng nếu chính nó hoặc bất kỳ ngoại lệ (kể cả gián tiếp) của nó áp dụng, như cây ngoại lệ
  của Catala: R2 là ngoại lệ của R, R là ngoại lệ của X, R2 áp dụng thì cả R lẫn X đều bị thay thế.
- Hàng U khi rule gốc `FAIL`: hạ thành `UNKNOWN` / `needs_facts`, `legality` / `employee_impact` = None, `missing_facts`
  thêm dữ kiện đầu vào còn thiếu của cả cây ngoại lệ đang U. Có ngoại lệ T thì ngoại lệ U bị bỏ qua.
- `reasons`: `overridden_by:<concept>/<rule>` (mỗi ngoại lệ T một dòng, theo thứ tự trong catalog) hoặc
  `exception_unknown:<concept>/<rule>`.
- `evaluate_concept` (từng concept, lớp tương thích) chỉ áp dụng ngoại lệ giữa các rule cùng concept; ngoại lệ chéo
  concept chỉ có ở `evaluate_all` và ở phiên. Đích `exception_of` ở gói khác chỉ kiểm tồn tại ở `load_packs` (sau khi gộp).

### 5.5 Pack và hợp nhất

```
src/rag/rules/packs/<pack_id>/
  pack.yaml       # id, version, extends: [..], document_kinds, units, conversions, document_facts,
                  # user_facts (kèm câu hỏi + kiểu), findings, roles, derived
  concepts.yaml   # định dạng hiện tại + trường tùy chọn mới (kind, exception_of, unstated_false)
```

- `extends`: pack con thấy dữ kiện / dữ kiện suy ra / rule của pack cha (vd. `civil_loan` extends `civil_general`).
- Id concept phải duy nhất trên mọi pack được nạp cùng lúc; trùng → lỗi nạp (không namespace, để không đổi khóa
  `concept_id` mà đồ thị luật và UI đang dùng).
- `findings`: tập finding hợp lệ của pack; lõi chỉ biết các finding chung (`ok`, `violation`, `needs_facts`,
  `conflict`, `missing_content`) và những gì pack khai báo thêm (`labor` khai báo `hidden_right`, `possible_right`).
- Gói `labor`: chuyển `bridge/concepts.yaml` sang `rules/packs/labor/concepts.yaml`; `catalog.DEFAULT_PATH` trỏ tới
  đó; `CONTRACT_FACTS`, `USER_FACTS` giữ làm hằng tương thích, được đọc ra từ `pack.yaml`. Báo LU đường dẫn mới.
- `kind` (payment, time_limit, notice, rate_cap, termination, penalty, …): trường nhãn trên concept, khai báo slot
  chung; engine không dùng. Dùng cho tagger/prompt trích (ngoài phạm vi engine, chỉ cần bộ nạp chấp nhận và kiểm
  slot của concept khớp slot của kind).

### 5.6 Đối tượng, join, đếm, phủ định (mới; thiết kế của nhóm)

**Đối tượng.** Ngoài bảng dữ kiện phẳng, phiên nhận các `WorkingObject` có kiểu (`Employee`, `Contract`,
`Amendment`): `{id, type, attrs: {tên: Fact}, valid_from, valid_to, refs: {tên: id}}`, do `rag.contracts.dossier` cấp.
Bảng dữ kiện phẳng hiện tại là trường hợp một hợp đồng không có đối tượng; rule cũ không đổi.

**Thành viên tại ngày soát.** Đối tượng thuộc bộ nhớ của kiểu nó tại ngày `day` khi `valid_from ≤ day` và (`valid_to`
rỗng hoặc `day ≤ valid_to`). `valid_from` chưa biết → thành viên *có thể* (trị U).

**Ba trị của ứng viên.** Với một rule xuyên đối tượng, mỗi ứng viên (một đối tượng hoặc một bộ đối tượng) có một trị:
T = chắc chắn thỏa điều kiện lọc / nối (AND Kleene của các điều kiện và tư cách thành viên), U = có thể thỏa,
F = không thỏa (loại bỏ).

**Đếm.** Gọi `n_T` là số ứng viên T và `n_U` là số ứng viên U; số đếm thật nằm trong khoảng `[n_T, n_T + n_U]`. So
khoảng đó với ngưỡng `k` bằng toán tử của rule: T nếu mọi giá trị trong khoảng thỏa; F nếu không giá trị nào thỏa;
còn lại U. Ví dụ `count > 2`: T nếu `n_T > 2`; F nếu `n_T + n_U ≤ 2`; còn lại U.

**Tồn tại / không tồn tại.** `exists` = đếm `≥ 1`. `not exists` = NOT ba trị của `exists`: T nếu `n_T + n_U = 0`;
F nếu `n_T ≥ 1`; U nếu `n_T = 0` và `n_U ≥ 1`.

**Nhóm.** Rule khai báo khóa nhóm (vd. `employee`); kết quả là một `RuleResult` cho mỗi nhóm, có thêm trường `object`
(id của nhóm; `None` với rule cũ). Ứng viên có khóa nhóm chưa biết được tính là U cho mọi nhóm cùng kiểu.

**Dữ kiện suy ra theo đối tượng.** `derived` (§5.3) có thể khai báo cho một kiểu đối tượng; mỗi đối tượng có giá trị
riêng (vd. `Contract.kind_effective`); ngữ nghĩa cây ngoại lệ giữ nguyên.

**Cú pháp YAML** (phác thảo, chốt khi làm việc D24):

```yaml
- id: fixed_term_limit/r1
  over: {c: {type: Contract, where: {fact: kind_effective, op: eq, value: xac_dinh_thoi_han}}}
  group_by: {employee: c.refs.employee}
  check: {count: {of: c, op: lte, value: 2}}
```

Bộ nạp kiểm: biến đã khai báo, kiểu tồn tại, không nối vòng.

## 6. Mạng phụ thuộc tăng dần ba trị (join kiểu TREAT)

### 6.1 Hai phần

1. **Mạng điều kiện (mệnh đề).** Điều kiện trên bảng dữ kiện: node alpha **chia sẻ** giữa các rule, node kết hợp ba
   trị có **bộ đếm** T/F/U, **lan truyền phần thay đổi** theo rank, dữ kiện suy ra đưa ngược vào mạng. Không có bộ
   nhớ beta vì không có phép nối trong phần này. Phần này lấy ý tưởng chia sẻ node và lan truyền thay đổi của Rete;
   vì vậy không gọi là "Rete đầy đủ".
2. **Join / đếm / phủ định trên đối tượng (§5.6) kiểu TREAT.** Chỉ lưu bộ nhớ theo kiểu đối tượng (bộ nhớ alpha).
   Khi đối tượng được thêm / xóa / đổi, tính lại tập ứng viên của các nhóm bị ảnh hưởng, bắt đầu từ đối tượng đổi,
   **không lưu kết quả nối trung gian**; ra `(n_T, n_U)` rồi thành một trị đưa vào mạng điều kiện như một lá.

Lý do dùng TREAT cho phần 2: mỗi hồ sơ chỉ có vài hợp đồng / phụ lục nên nối rẻ; xóa đơn giản (b4: thêm hợp đồng bị
sót thì kết luận trung gian rút lại, không có kết quả nối từng phần phải dọn); ít trạng thái; dễ chứng minh bằng
Reference. Hai phần nối với nhau qua lá `ObjectLeaf` và qua dữ kiện suy ra theo đối tượng.

Quy mô: nhiều rule → phần 1; nhiều đối tượng mỗi hồ sơ → phần 2. Benchmark đo hai trục (§9).

### 6.2 Biên dịch

`Network.compile(packs) -> Network` — một lần cho một tập pack, bất biến, dùng chung cho mọi phiên. Ngày soát không
nằm trong mạng mà là đầu vào của phiên (LawNode đọc nó), nên một mạng phục vụ hợp đồng ở mọi ngày ký.

| Node | Đầu vào | Đầu ra (theo phiên) |
|---|---|---|
| `FactNode(name)` | dữ kiện đầu vào hoặc suy ra | Fact / None / CONFLICT / UNKNOWN |
| `AlphaNode(fact, op, value, unit)` — **chia sẻ** giữa mọi rule có cùng khóa | 1 FactNode | Tri |
| `AndNode` / `OrNode` / `NotNode` | các node con | Tri, giữ **bộ đếm** (#T, #F, #U) để cập nhật O(1) khi một con đổi |
| `LawNode(rule)` | các node của `cases.when` + FactNode của `by` + ngày phiên | giá trị luật đã chọn + trạng thái + reasons |
| `LawLeafNode(fact, op, law_name)` | FactNode + LawNode | Tri |
| `DefinitionNode` (cây ngoại lệ dữ kiện suy ra) | node `when` + node con | giá trị / không áp dụng / UNKNOWN / CONFLICT |
| `DerivedFactNode` | các DefinitionNode gốc | ghi vào FactNode cùng tên → chaining |
| `PresenceNode(concept)` | đầu vào phiên (`present`, `evidence`) | bool |
| `ObjectMemory(type)` | đối tượng của phiên, đã lọc theo ngày soát (bộ nhớ alpha kiểu TREAT) | tập đối tượng |
| `GroupMatchNode(rule)` | `ObjectMemory` + điều kiện lọc / nối | `(n_T, n_U)` theo nhóm, tính theo yêu cầu từ đối tượng đổi; không lưu kết quả nối trung gian |
| `ObjectLeaf(rule, op, k)` | `GroupMatchNode` | Tri (so khoảng `[n_T, n_T + n_U]` với `k`, §5.6) |
| `RuleNode(rule)` | applicability, LawNode, check, PresenceNode, các RuleNode ngoại lệ, ObjectLeaf | `RuleResult` |

Mỗi node có `rank` = độ sâu topo. Bộ biên dịch dùng chung các hàm ngữ nghĩa của §5 (một module `semantics.py`);
node chỉ là cách *lập lịch* gọi các hàm đó.

### 6.3 Phiên

```python
session = network.session(day=date, facts=Facts, present=set[str], evidence=dict,
                          objects: Sequence[WorkingObject] = ())
session.results() -> list[RuleResult]
session.update(changes: dict[str, Fact | None], present=..., evidence=...,
               objects: ObjectChanges | None = None) -> Diff   # ObjectChanges = {added, removed, changed}; Diff = rule đổi trạng thái
session.fork() -> Session        # sao chép bộ nhớ, dùng cho next_questions
```

Lan truyền: hàng đợi ưu tiên theo `rank`; mỗi node tính lại tối đa một lần trong một lần `update`; node chỉ đẩy tiếp
khi đầu ra thực sự đổi. Đảm bảo không có trạng thái trung gian sai (glitch) và kết quả không phụ thuộc thứ tự
`changes`. Dữ kiện suy ra đổi → FactNode đổi → lan tiếp (cùng hàng đợi, rank lớn hơn). Đối tượng đổi → chỉ
`GroupMatchNode` của các nhóm bị ảnh hưởng tính lại, rồi lan tiếp như trên.

Rút lại (đây là tính lại theo phụ thuộc, không phải truth maintenance của Drools): giá trị dữ kiện suy ra hoàn toàn do
node định nghĩa quyết định, nên "rút lại" = node tính lại ra "không áp dụng" và lan truyền như mọi thay đổi khác;
justification luôn là định nghĩa đang thắng. Khác biệt với Drools TMS: không có bộ đếm justification riêng.

## 7. Interface và module

```
src/rag/rules/
  semantics.py   # Tri, UNKNOWN, CONFLICT, Fact, compare, convert(units), eval_cond, resolve_law,
                 # evaluate_rule (bảng trạng thái §5.2), resolve_definitions (§5.3), apply_exceptions (§5.4)
  model.py       # Pack, Rule, Concept, Derived, Definition, Units (dataclass bất biến)
  loader.py      # nạp + kiểm pack, extends, hợp nhất, báo hết lỗi một lần (như CatalogError)
  evaluator.py   # Protocol Evaluator: session(day, facts, present, evidence, objects=()) -> Session
  reference.py   # ReferenceEvaluator: mỗi lần results() tính toàn bộ theo thứ tự topo, kể cả §5.6
  network/nodes.py, network/objects.py (ObjectMemory, GroupMatchNode), network/network.py, network/session.py
  explain.py     # explain(session, concept_id, rule_id) -> ExplanationTree
  questions.py   # next_questions(session, pack) -> list[Question]
  packs/labor/, packs/civil_general/, packs/civil_loan/
```

`rag.bridge.engine` và `rag.bridge.catalog` trở thành lớp mỏng gọi `rag.rules` (giữ tên công khai hiện có).
Chọn pack: tham số `packs=` ở `check_contract` / `ask_contract_graph` (mặc định `["labor"]`), mạng biên dịch được
cache theo (danh sách pack, version). Chọn evaluator: tham số `evaluator=` ở `check_contract`, mặc định `network`;
biến môi trường `RAG_RULE_EVALUATOR=reference` để chuyển nhanh khi nghi lỗi.

## 8. Giải thích và câu hỏi

**`explain()`** trả cây: RuleResult → (applicability | case đã chọn | law value + nguồn `periods.source` | check)
→ lá (điều kiện, Tri) → dữ kiện (`source`, `uid`, `quote`, `amended_from`) → nếu là dữ kiện suy ra thì mở tiếp:
định nghĩa thắng (anchors) + các ngoại lệ bị loại và vì sao (F / không áp dụng). Ngoại lệ giữa rule hiện là nút
`overridden_by` / `exception_unknown`. Định dạng JSON để UI vẽ; markdown ngắn để đưa vào báo cáo.

**`next_questions()`**: ứng viên = dữ kiện `user_facts` của pack (bool / enum / số có miền rời rạc) đang thiếu và nằm
trong `missing_facts` của ít nhất một kết quả UNKNOWN. Với mỗi ứng viên và mỗi giá trị khả dĩ: `session.fork()` +
`update` → đếm số kết quả UNKNOWN trở thành xác định. Điểm = giá trị nhỏ nhất qua các giá trị khả dĩ (chắc chắn giải
quyết được bao nhiêu). Trả danh sách xếp hạng kèm câu hỏi (`user_facts[].question`). Đây là chỗ cập nhật tăng dần
của mạng có ích trực tiếp (nhiều lần fork + update trên một hợp đồng).

## 9. Benchmark

`scripts/bench_rule_engine.py` — sinh pack tổng hợp có tham số, chạy cả hai evaluator, ghi JSON + bảng markdown.

- **Trục 1, số rule:** 44 (pack thật), 500, 2.000, 10.000; tỉ lệ điều kiện dùng chung (0.2 / 0.5); độ sâu dữ kiện
  suy ra (0 / 3); 50–500 dữ kiện đầu vào.
- **Trục 2, số đối tượng mỗi hồ sơ:** 1 / 5 / 20 / 100 hợp đồng+phụ lục của một người, với 5–50 rule xuyên đối tượng
  (đếm, ghép cặp, phủ định).
- Kịch bản:
  1. **Biên dịch** mạng (một lần cho cả catalog).
  2. **Lần đánh giá đầu** của một hợp đồng (Reference vs Network) — dự kiến mạng *không* thắng, phải báo đúng như vậy.
  3. **Cập nhật tăng dần** 1 / 5 / 20 dữ kiện (recheck, người dùng trả lời) — dự kiến mạng thắng rõ.
  4. **Nhiều hợp đồng** (100) dùng chung một mạng — chi phí biên dịch chia đều.
  5. **`next_questions()`** trên hợp đồng nhiều UNKNOWN.
  6. **Thêm / xóa một đối tượng** trong hồ sơ nhiều đối tượng (trục 2).
- Đo: thời gian trung vị / p95 (lặp ≥ 20 lần, bỏ lần khởi động), số node được tính lại, bộ nhớ đỉnh (`tracemalloc`).
- Mọi lần chạy benchmark đồng thời kiểm hai evaluator ra kết quả bằng nhau.
- Mục tiêu trình bày (không phải điều kiện nghiệm thu cứng): ở 10.000 rule, cập nhật 1 dữ kiện < 5 ms p95.
- *Could:* biến thể `network+beta` (join lưu bộ nhớ beta kiểu Rete) làm evaluator thứ ba chỉ để so với TREAT trên
  trục 2, nếu còn thời gian.

## 10. Kiểm thử

- **Tương đương với engine cũ**: toàn bộ `tests/test_bridge_*.py`, `test_contract_graph_tools.py` chạy qua lớp tương
  thích với cả hai evaluator, không sửa kỳ vọng. Thêm test golden: đóng băng kết quả engine cũ trên các fixture hợp
  đồng hiện có trước khi refactor, so từng `RuleResult`.
- **Đối chiếu ngẫu nhiên** Network vs Reference: sinh pack + dữ kiện + đối tượng + chuỗi `update` ngẫu nhiên (thêm /
  xóa / đổi dữ kiện và đối tượng; seed cố định, vài nghìn ca), so kết quả sau mỗi bước.
- **Ngữ nghĩa mới**: bảng chân lý cho §5.3 (mọi tổ hợp T/F/U của ngoại lệ, CONFLICT, `from` thiếu), §5.4 (ba hàng),
  §5.6 (đếm theo khoảng `[n_T, n_T + n_U]` với từng toán tử, `exists` / `not exists` với ứng viên U, `valid_from`
  chưa biết, khóa nhóm chưa biết), phát hiện vòng, `extends`, trùng id.
- **Bất biến**: không đầu vào nào mà một dữ kiện chuyển từ có giá trị sang thiếu lại làm một rule chuyển sang `FAIL`
  (thiếu dữ kiện không thành vi phạm) — kiểm bằng đối chiếu ngẫu nhiên.
- **Pack thứ hai**: vài hợp đồng vay mẫu (tự soạn, có cả lãi vượt trần 20%/năm và lãi hợp lệ), chạy không sửa lõi.

## 11. Giai đoạn (mỗi giai đoạn tự demo được)

1. Tách `semantics.py`, `model.py`, `loader.py`, `ReferenceEvaluator`; gói `labor` (pack.yaml + chuyển concepts.yaml);
   lớp tương thích. Nghiệm thu: test cũ + golden xanh.
2. Mạng điều kiện (mệnh đề, §6.1 phần 1): biên dịch, phiên, `update`, diff; đối chiếu ngẫu nhiên; nối vào
   `check_contract` (sau recheck chỉ `update` dữ kiện mới) và `tools.check_concept` (dùng phiên). Nghiệm thu: test cũ
   xanh với `network`.
3. Dữ kiện suy ra + ngoại lệ giữa rule (§5.3–5.4), ở cả hai evaluator; một rule thật (Đ20.2) sau khi đọc văn bản.
4. `explain()`, `next_questions()`; sự kiện stream `evaluation_diff` cho UI.
5. Pack `civil_general` + `civil_loan` (rule chỉ viết sau khi đọc BLDS 2015 phần chung hợp đồng và Đ463–471).
6. Benchmark + biểu đồ cho bài trình bày.
7. Đối tượng / join / đếm / phủ định (§5.6), làm hai bước:
   - **7a** (có thể bắt đầu ngay sau giai đoạn 1, song song giai đoạn 2): ngữ nghĩa §5.6 và bảng chân lý trong
     `ReferenceEvaluator` + `dossier_objects` của Huy. Reference là chuẩn đúng nên phải có trước mạng.
   - **7b** (sau giai đoạn 3): `ObjectMemory`, `GroupMatchNode`, `ObjectLeaf` trong mạng; đối chiếu ngẫu nhiên với
     Reference; rule xuyên văn bản cho b1–b5 và đếm phụ lục ở a1.
   Giai đoạn 7 phải xong trước khi nối endpoint demo cho các hồ sơ b.

## 12. Quyết định của người viết spec (cần người dùng xem lại)

- Hai phần: mạng điều kiện mệnh đề tăng dần + join kiểu TREAT cho rule xuyên đối tượng (§6.1). Không gọi là "Rete
  đầy đủ" vì không có bộ nhớ beta.
- Ngữ nghĩa ba trị cho đối tượng: đếm theo khoảng `[n_T, n_T + n_U]`, `not exists` gặp ứng viên U thì ra U (§5.6).
  Đây là thiết kế của nhóm, không có tài liệu công bố để đối chiếu.
- Ngoại lệ U: chỉ hạ `FAIL` thành `UNKNOWN`, giữ `PASS` (§5.4).
- Id concept toàn cục, không namespace (§5.5).
- Cây ngoại lệ dữ kiện suy ra và ngoại lệ giữa rule: các chi tiết đã chốt khi triển khai nằm ở cuối §5.3 và §5.4.
- Chuyển `concepts.yaml` sang `rules/packs/labor/` (ảnh hưởng LU).
- Evaluator mặc định là `network` sau giai đoạn 2, có công tắc về `reference`.
- Bỏ cách gọi "TMS" của Drools; dùng "tính lại theo phụ thuộc" (§6.3).
- Hoãn Phreak / LEAPS / Rete/UL; loại Rete II/III/NT, Hiperfact, DBSP (§4.2).

## 13. Để lại cho người triển khai

- Cấu trúc dữ liệu cụ thể của bộ nhớ node và hàng đợi.
- Định dạng JSON chi tiết của `ExplanationTree` (miễn đủ thông tin §8).
- Cách sinh pack tổng hợp cho benchmark (miễn dùng đúng loader thật và đủ tham số §9).
- Tên sự kiện stream phụ (miễn giữ các sự kiện hiện có).
