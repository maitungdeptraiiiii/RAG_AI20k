"""Authoring source for synthetic contract cases. Never used by a retrieval adapter.

Changing this file requires regenerating seeds and versioning the frozen benchmark.
Gold labels are proposals awaiting independent legal review, not expert judgments.
"""
import json
from pathlib import Path

B = 'bo-luat:45/2019/QH14'
N = 'nghi-dinh:145/2020/NĐ-CP'
FAMILIES = []


def group(article, quote, key=B):
    return [{'pid': f'{key}#d{article}', 'quote': quote}]


def add(fid, concept, description, category, evidence, clauses, rationale, split='test', **kwargs):
    FAMILIES.append({'family_id': fid, 'split': split, 'category': category,
        'concepts': [{'id': concept, 'description': description}],
        'context': {'assessment_date': '2025-03-01', 'date_role': 'performance_date',
            'jurisdiction': 'VN', 'employment_regime': 'labor_contract', **kwargs.pop('context', {})},
        'evidence': evidence, 'rationale': rationale,
        'variants': [{'id': f'v{i+1}', 'contract_text': c} for i, c in enumerate(clauses)], **kwargs})


add('probation-pay', 'probation.pay', 'Tiền lương trong thời gian thử việc.', 'single_rule',
    [group(26, 'Tiền lương của người lao động trong thời gian thử việc do hai bên thỏa thuận nhưng ít nhất phải bằng 85% mức lương của công việc đó.')],
    ['Trong hai tháng thử việc, người lao động nhận 70% mức lương của công việc.',
     'Lương chính thức là 12 triệu đồng/tháng. Giai đoạn đánh giá ban đầu được trả 10,2 triệu đồng/tháng.'],
    'Retrieve the full probation-pay floor; do not infer legality as part of this benchmark.', split='dev')
add('probation-duration', 'probation.duration', 'Thời hạn thử việc theo yêu cầu trình độ của công việc.', 'condition',
    [group(25, 'Thời gian thử việc do hai bên thỏa thuận căn cứ vào tính chất và mức độ phức tạp của công việc nhưng chỉ được thử việc một lần đối với một công việc và bảo đảm điều kiện sau đây:'),
     group(25, '2. Không quá 60 ngày đối với công việc có chức danh nghề nghiệp cần trình độ chuyên môn, kỹ thuật từ cao đẳng trở lên;')],
    ['Vị trí kế toán yêu cầu trình độ cao đẳng. Thời gian thử việc là 90 ngày.',
     'Ứng viên làm công việc yêu cầu bằng đại học trải qua thời gian đánh giá trước tuyển dụng kéo dài 60 ngày.'],
    'Need the applicability lead-in and the relevant education tier.', split='dev')
add('probation-repeat', 'probation.once', 'Số lần thử việc đối với cùng một công việc.', 'single_rule',
    [group(25, 'Thời gian thử việc do hai bên thỏa thuận căn cứ vào tính chất và mức độ phức tạp của công việc nhưng chỉ được thử việc một lần đối với một công việc và bảo đảm điều kiện sau đây:')],
    ['Sau khi thử việc xong, công ty được yêu cầu thử việc lần hai ở chính vị trí này.',
     'Mỗi công việc chỉ có một đợt thử việc, không tổ chức lại đợt đánh giá thử việc cho cùng công việc.'],
    'Same-work restriction rather than pay or termination notice.', split='dev')
add('short-contract', 'probation.duration', 'Điều kiện áp dụng thử việc với hợp đồng ngắn hạn.', 'exception',
    [group(24, '3. Không áp dụng thử việc đối với người lao động giao kết hợp đồng lao động có thời hạn dưới 01 tháng.')],
    ['Hợp đồng thời hạn 20 ngày, trong đó có 06 ngày thử việc.',
     'Hai bên giao kết hợp đồng 25 ngày và thực hiện công việc ngay, không có giai đoạn thử việc.'],
    'The short-contract exclusion must not be replaced by a generic six-day limit.', split='dev')
add('probation-cancel', 'probation.cancel_no_notice', 'Hủy bỏ thỏa thuận trong thời gian thử việc.', 'single_rule',
    [group(27, '2. Trong thời gian thử việc, mỗi bên có quyền hủy bỏ hợp đồng thử việc hoặc hợp đồng lao động đã giao kết mà không cần báo trước và không phải bồi thường.')],
    ['Trong thời gian thử việc, bên muốn nghỉ phải báo trước 30 ngày và bồi thường một tháng lương.',
     'Khi vẫn đang thử việc, mỗi bên có thể dừng thỏa thuận ngay mà không trả tiền bồi thường.'],
    'Probation cancellation must not be confused with regular unilateral termination.', split='dev')
add('keep-originals', 'prohibit.keep_documents', 'Giữ bản chính giấy tờ của người lao động.', 'prohibition',
    [group(17, '1. Giữ bản chính giấy tờ tùy thân, văn bằng, chứng chỉ của người lao động.')],
    ['Công ty giữ bản gốc căn cước và bằng đại học đến khi người lao động nghỉ việc.',
     'Người lao động xuất trình bản chính bằng cấp để đối chiếu và nhận lại ngay; hồ sơ lưu bản sao.'],
    'Evidence is the exact prohibited conduct, not a broad contract heading.', split='dev')
add('deposit', 'prohibit.deposit', 'Đặt cọc hoặc bảo đảm để thực hiện hợp đồng lao động.', 'prohibition',
    [group(17, '2. Yêu cầu người lao động phải thực hiện biện pháp bảo đảm bằng tiền hoặc tài sản khác cho việc thực hiện hợp đồng lao động.')],
    ['Trước ngày nhận việc, nhân viên nộp 20 triệu đồng bảo đảm thực hiện hợp đồng.',
     'Doanh nghiệp không thu tiền thế chân hoặc yêu cầu tài sản bảo đảm khi tuyển dụng.'],
    'Distinguish a recruitment security deposit from a lawful wage deduction.', split='dev')
add('disciplinary-fine', 'prohibit.fine_instead_of_discipline', 'Phạt tiền hoặc cắt lương để xử lý kỷ luật.', 'prohibition',
    [group(127, '2. Phạt tiền, cắt lương thay việc xử lý kỷ luật lao động.')],
    ['Đi muộn mỗi lần bị phạt 200.000 đồng, trừ trực tiếp vào tiền lương.',
     'Vi phạm nội quy được xử lý theo thủ tục kỷ luật, không áp dụng tiền phạt.'],
    'Disciplinary fines and compensation deductions have different legal bases.', split='dev')
add('wage-deduction', 'wage.deduction_limit', 'Căn cứ và mức giới hạn khấu trừ tiền lương.', 'multiple_evidence',
    [group(102, '1. Người sử dụng lao động chỉ được khấu trừ tiền lương của người lao động để bồi thường thiệt hại do làm hư hỏng dụng cụ, thiết bị, tài sản của người sử dụng lao động theo quy định tại Điều 129 của Bộ luật này.'),
     group(102, '3. Mức khấu trừ tiền lương hằng tháng không được quá 30% tiền lương thực trả hằng tháng của người lao động sau khi trích nộp các khoản bảo hiểm xã hội bắt buộc, bảo hiểm y tế, bảo hiểm thất nghiệp, thuế thu nhập cá nhân.')],
    ['Công ty được khấu trừ 50% lương thực trả sau bảo hiểm và thuế mỗi tháng để bồi thường thiết bị bị làm hỏng.',
     'Nếu làm hư hỏng tài sản và phát sinh trách nhiệm bồi thường, mức trừ hằng tháng tối đa 30% tiền lương sau các khoản bảo hiểm bắt buộc và thuế.'],
    'Requires both the deduction purpose and its net-wage cap; this case does not adjudicate liability.')
add('monthly-pay', 'wage.pay_period', 'Kỳ hạn trả lương cho người hưởng lương tháng.', 'single_rule',
    [group(97, '2. Người lao động hưởng lương theo tháng được trả một tháng một lần hoặc nửa tháng một lần. Thời điểm trả lương do hai bên thỏa thuận và phải được ấn định vào một thời điểm có tính chu kỳ.')],
    ['Lương tháng được cộng dồn và thanh toán ba tháng một lần.',
     'Tiền lương tháng được trả định kỳ vào ngày 05 của tháng kế tiếp.'],
    'Retrieve monthly-pay frequency rather than hourly-pay rules.')
add('late-pay', 'wage.pay_period', 'Chậm trả lương vì bất khả kháng và nghĩa vụ đền bù.', 'exception',
    [group(97, '4. Trường hợp vì lý do bất khả kháng mà người sử dụng lao động đã tìm mọi biện pháp khắc phục nhưng không thể trả lương đúng hạn thì không được chậm quá 30 ngày; nếu trả lương chậm từ 15 ngày trở lên thì người sử dụng lao động phải đền bù cho người lao động một khoản tiền ít nhất bằng số tiền lãi của số tiền trả chậm tính theo lãi suất huy động tiền gửi có kỳ hạn 01 tháng do ngân hàng nơi người sử dụng lao động mở tài khoản trả lương cho người lao động công bố tại thời điểm trả lương.')],
    ['Do bất khả kháng sau khi đã tìm mọi biện pháp khắc phục, công ty được chậm lương 45 ngày và không đền bù.',
     'Phụ lục cho phép hoãn lương khi bất khả kháng nhưng không quá 30 ngày; hoãn từ 15 ngày phải đền bù theo mức luật định.'],
    'Need the force-majeure condition, duration cap and compensation trigger together.')
add('bank-fees', 'content.wage_terms', 'Chi phí khi trả tiền lương qua tài khoản ngân hàng.', 'single_rule',
    [group(96, 'Trường hợp trả lương qua tài khoản cá nhân của người lao động được mở tại ngân hàng thì người sử dụng lao động phải trả các loại phí liên quan đến việc mở tài khoản và chuyển tiền lương.')],
    ['Người lao động chịu phí mở tài khoản và phí chuyển lương hằng tháng.',
     'Lương chuyển khoản; doanh nghiệp thanh toán phí mở tài khoản nhận lương và phí chuyển tiền lương.'],
    'Separate transfer-fee allocation from salary amount.')
add('overtime-pay', 'wage.overtime_pay', 'Tiền lương làm thêm giờ theo loại ngày.', 'multiple_evidence',
    [group(98, 'a) Vào ngày thường, ít nhất bằng 150%;'),
     group(98, 'b) Vào ngày nghỉ hằng tuần, ít nhất bằng 200%;'),
     group(98, 'c) Vào ngày nghỉ lễ, tết, ngày nghỉ có hưởng lương, ít nhất bằng 300% chưa kể tiền lương ngày lễ, tết, ngày nghỉ có hưởng lương đối với người lao động hưởng lương ngày.')],
    ['Tất cả giờ làm thêm, kể cả chủ nhật và ngày lễ, đều được trả bằng 150% đơn giá giờ làm bình thường.',
     'Làm thêm ngày thường hưởng ít nhất 150%, ngày nghỉ tuần 200%, ngày lễ 300% chưa kể tiền lương ngày lễ theo diện áp dụng.'],
    'All three day types must be retrieved, not only the normal-day percentage.')
add('night-overtime', 'wage.night_pay', 'Các thành phần tiền lương khi làm thêm vào ban đêm.', 'multiple_evidence',
    [group(98, 'a) Vào ngày thường, ít nhất bằng 150%;'),
     group(98, '2. Người lao động làm việc vào ban đêm thì được trả thêm ít nhất bằng 30% tiền lương tính theo đơn giá tiền lương hoặc tiền lương thực trả theo công việc của ngày làm việc bình thường.'),
     group(98, '3. Người lao động làm thêm giờ vào ban đêm thì ngoài việc trả lương theo quy định tại khoản 1 và khoản 2 Điều này, người lao động còn được trả thêm 20% tiền lương tính theo đơn giá tiền lương hoặc tiền lương theo công việc làm vào ban ngày của ngày làm việc bình thường hoặc của ngày nghỉ hằng tuần hoặc của ngày nghỉ lễ, tết.')],
    ['Làm thêm vào ban đêm của ngày thường chỉ được hưởng thêm 30%, không có khoản làm thêm khác.',
     'Tiền làm thêm ban đêm ngày thường gồm tiền làm thêm, khoản tăng thêm ban đêm và khoản bổ sung cho làm thêm ban đêm.'],
    'Requires the combined components; matching the word night alone is insufficient.')
add('daily-hours', 'hours.normal', 'Giới hạn giờ làm việc bình thường khi tổ chức theo ngày.', 'condition',
    [group(105, '1. Thời giờ làm việc bình thường không quá 08 giờ trong 01 ngày và không quá 48 giờ trong 01 tuần.')],
    ['Chế độ làm việc theo ngày: 10 giờ/ngày, 05 ngày/tuần, không tính là làm thêm.',
     'Thời gian làm việc bình thường theo ngày là 08 giờ, 06 ngày mỗi tuần.'],
    'Daily organization is explicit; do not silently use weekly-organization exception.', split='dev')
add('weekly-hours', 'hours.normal', 'Giới hạn giờ làm việc khi tổ chức theo tuần và nghĩa vụ thông báo.', 'condition',
    [group(105, '2. Người sử dụng lao động có quyền quy định thời giờ làm việc theo ngày hoặc tuần nhưng phải thông báo cho người lao động biết; trường hợp theo tuần thì thời giờ làm việc bình thường không quá 10 giờ trong 01 ngày và không quá 48 giờ trong 01 tuần.')],
    ['Công ty thông báo áp dụng lịch theo tuần: 10 giờ/ngày trong bốn ngày và 8 giờ ngày thứ năm.',
     'Lịch theo tuần được thông báo trước gồm 11 giờ mỗi ngày trong 04 ngày làm việc.'],
    'The weekly exception needs both daily and weekly limits.', split='dev')
add('overtime-consent', 'hours.overtime_limit', 'Điều kiện đồng ý và giới hạn làm thêm thông thường.', 'multiple_evidence',
    [group(107, 'a) Phải được sự đồng ý của người lao động;'),
     group(107, 'b) Bảo đảm số giờ làm thêm của người lao động không quá 50% số giờ làm việc bình thường trong 01 ngày; trường hợp áp dụng quy định thời giờ làm việc bình thường theo tuần thì tổng số giờ làm việc bình thường và số giờ làm thêm không quá 12 giờ trong 01 ngày; không quá 40 giờ trong 01 tháng;'),
     group(107, 'c) Bảo đảm số giờ làm thêm của người lao động không quá 200 giờ trong 01 năm, trừ trường hợp quy định tại khoản 3 Điều này.')],
    ['Người lao động bắt buộc tăng ca khi công ty yêu cầu, tối đa 60 giờ/tháng và 200 giờ/năm; không thuộc tình huống khẩn cấp.',
     'Tăng ca cần được người lao động đồng ý và tuân thủ giới hạn theo ngày, tháng, năm; cơ sở thuộc chế độ thông thường.'],
    'Requires consent plus day/month/year caps; emergency exceptions are outside these stated facts.')
add('weekly-rest', 'rest.weekly', 'Nghỉ hằng tuần và ngoại lệ do chu kỳ lao động.', 'exception',
    [group(111, '1. Mỗi tuần, người lao động được nghỉ ít nhất 24 giờ liên tục. Trong trường hợp đặc biệt do chu kỳ lao động không thể nghỉ hằng tuần thì người sử dụng lao động có trách nhiệm bảo đảm cho người lao động được nghỉ tính bình quân 01 tháng ít nhất 04 ngày.')],
    ['Theo chu kỳ sản xuất đặc biệt không thể bố trí nghỉ mỗi tuần, nhân viên chỉ được nghỉ bình quân 02 ngày/tháng.',
     'Mỗi tuần bố trí ít nhất 24 giờ nghỉ liên tục; lịch cụ thể được thông báo trong nội quy.'],
    'Both ordinary rule and cycle-based exception must be visible.')
add('shift-break', 'content.hours_rest', 'Nghỉ giữa giờ khi làm ca liên tục.', 'multiple_evidence',
    [group(109, '1. Người lao động làm việc theo thời giờ làm việc quy định tại Điều 105 của Bộ luật này từ 06 giờ trở lên trong một ngày thì được nghỉ giữa giờ ít nhất 30 phút liên tục, làm việc ban đêm thì được nghỉ giữa giờ ít nhất 45 phút liên tục.'),
     group(109, 'Trường hợp người lao động làm việc theo ca liên tục từ 06 giờ trở lên thì thời gian nghỉ giữa giờ được tính vào giờ làm việc.')],
    ['Ca đêm liên tục dài 08 giờ, nghỉ giữa ca 20 phút và không tính vào giờ làm.',
     'Ca ngày liên tục 08 giờ có ít nhất 30 phút nghỉ giữa giờ được tính vào thời gian làm việc.'],
    'Retrieve minimum break duration and whether continuous-shift breaks count as working time.')
add('annual-seniority', 'leave.annual', 'Nghỉ hằng năm và ngày tăng thêm theo thâm niên.', 'cross_article',
    [group(113, '1. Người lao động làm việc đủ 12 tháng cho một người sử dụng lao động thì được nghỉ hằng năm, hưởng nguyên lương theo hợp đồng lao động như sau:'),
     group(113, 'a) 12 ngày làm việc đối với người làm công việc trong điều kiện bình thường;'),
     group(114, 'Cứ đủ 05 năm làm việc cho một người sử dụng lao động thì số ngày nghỉ hằng năm của người lao động theo quy định tại khoản 1 Điều 113 của Bộ luật này được tăng thêm tương ứng 01 ngày.')],
    ['Nhân viên làm công việc bình thường, đã đủ 05 năm tại công ty, được nghỉ phép năm cố định 12 ngày.',
     'Với công việc bình thường và đủ 05 năm làm tại cùng doanh nghiệp, số ngày phép năm là 13 ngày hưởng nguyên lương.'],
    'Finding only annual-leave base days misses the seniority addition.')
add('annual-prorata', 'leave.annual', 'Tính nghỉ hằng năm khi chưa làm đủ năm.', 'cross_document',
    [group(113, '2. Người lao động làm việc chưa đủ 12 tháng cho một người sử dụng lao động thì số ngày nghỉ hằng năm theo tỷ lệ tương ứng với số tháng làm việc.'),
     group(66, '1. Số ngày nghỉ hằng năm của người lao động làm việc chưa đủ 12 tháng theo quy định tại khoản 2 Điều 113 của Bộ luật Lao động được tính như sau: lấy số ngày nghỉ hàng năm cộng với số ngày được nghỉ tăng thêm theo thâm niên (nếu có), chia cho 12 tháng, nhân với số tháng làm việc thực tế trong năm để tính thành số ngày được nghỉ hằng năm.', N)],
    ['Người làm công việc bình thường mới làm đủ 06 tháng không có phép năm vì chưa đủ một năm làm việc.',
     'Nhân viên công việc bình thường đã làm đủ 06 tháng được tính phép theo tỷ lệ số tháng làm việc thực tế.'],
    'Need both Labor Code entitlement and the implementing calculation, not a scope-only decree citation.')
add('annual-payout', 'leave.annual', 'Thanh toán phép chưa nghỉ khi thôi việc và tiền lương làm căn cứ.', 'cross_document',
    [group(113, '3. Trường hợp do thôi việc, bị mất việc làm mà chưa nghỉ hằng năm hoặc chưa nghỉ hết số ngày nghỉ hằng năm thì được người sử dụng lao động thanh toán tiền lương cho những ngày chưa nghỉ.'),
     group(67, '3. Tiền lương làm căn cứ trả cho người lao động những ngày chưa nghỉ hằng năm hoặc chưa nghỉ hết số ngày nghỉ hằng năm theo khoản 3 Điều 113 của Bộ luật Lao động là tiền lương theo hợp đồng lao động của tháng trước liền kề tháng người lao động thôi việc, bị mất việc làm.', N)],
    ['Khi thôi việc, ngày phép chưa dùng tự động hết giá trị và không được quy đổi thành tiền.',
     'Khi thôi việc, phép chưa nghỉ được thanh toán theo tiền lương hợp đồng của tháng trước liền kề tháng thôi việc.'],
    'Need the termination entitlement and the exact wage base.')
add('personal-leave', 'leave.personal_paid', 'Nghỉ việc riêng có hưởng lương khi kết hôn.', 'condition',
    [group(115, '1. Người lao động được nghỉ việc riêng mà vẫn hưởng nguyên lương và phải thông báo với người sử dụng lao động trong trường hợp sau đây:'),
     group(115, 'a) Kết hôn: nghỉ 03 ngày;')],
    ['Người lao động kết hôn được nghỉ 01 ngày không lương dù đã báo cho công ty.',
     'Khi bản thân kết hôn, nhân viên thông báo cho công ty và được nghỉ 03 ngày hưởng nguyên lương.'],
    'The paid-leave lead-in matters; a bare number is insufficient.')
add('employee-notice', 'termination.employee_unilateral', 'Báo trước khi người lao động chấm dứt hợp đồng và ngoại lệ.', 'exception',
    [group(35, 'a) Ít nhất 45 ngày nếu làm việc theo hợp đồng lao động không xác định thời hạn;'),
     group(35, 'b) Không được trả đủ lương hoặc trả lương không đúng thời hạn, trừ trường hợp quy định tại khoản 4 Điều 97 của Bộ luật này;'),
     group(97, '4. Trường hợp vì lý do bất khả kháng mà người sử dụng lao động đã tìm mọi biện pháp khắc phục nhưng không thể trả lương đúng hạn thì không được chậm quá 30 ngày; nếu trả lương chậm từ 15 ngày trở lên thì người sử dụng lao động phải đền bù cho người lao động một khoản tiền ít nhất bằng số tiền lãi của số tiền trả chậm tính theo lãi suất huy động tiền gửi có kỳ hạn 01 tháng do ngân hàng nơi người sử dụng lao động mở tài khoản trả lương cho người lao động công bố tại thời điểm trả lương.')],
    ['Hợp đồng không xác định thời hạn buộc người lao động báo trước 90 ngày trong mọi trường hợp, kể cả công ty cố ý không trả lương.',
     'Hợp đồng không xác định thời hạn quy định báo trước 45 ngày khi nghỉ thông thường, đồng thời bảo lưu quyền nghỉ không báo trước khi bị nợ lương theo luật.'],
    'Retrieve ordinary notice, unpaid-wage exception and its force-majeure carve-out; three linked provisions.')
add('pregnancy-exit', 'maternity.terminate_or_suspend', 'Nghỉ việc do tiếp tục làm việc ảnh hưởng xấu tới thai nhi.', 'cross_article',
    [group(35, 'đ) Lao động nữ mang thai phải nghỉ việc theo quy định tại khoản 1 Điều 138 của Bộ luật này;'),
     group(138, '1. Lao động nữ mang thai nếu có xác nhận của cơ sở khám bệnh, chữa bệnh có thẩm quyền về việc tiếp tục làm việc sẽ ảnh hưởng xấu tới thai nhi thì có quyền đơn phương chấm dứt hợp đồng lao động hoặc tạm hoãn thực hiện hợp đồng lao động.'),
     group(138, 'Trường hợp đơn phương chấm dứt hợp đồng lao động hoặc tạm hoãn thực hiện hợp đồng lao động thì phải thông báo cho người sử dụng lao động kèm theo xác nhận của cơ sở khám bệnh, chữa bệnh có thẩm quyền về việc tiếp tục làm việc sẽ ảnh hưởng xấu tới thai nhi.')],
    ['Dù có xác nhận y tế rằng công việc ảnh hưởng xấu tới thai nhi, lao động nữ vẫn phải báo trước 45 ngày mới được nghỉ.',
     'Khi có xác nhận y tế hợp lệ về ảnh hưởng xấu tới thai nhi, lao động nữ thông báo kèm xác nhận để thực hiện quyền nghỉ theo luật.'],
    'Requires the cross-reference, medical condition and notification evidence.')
add('settlement', 'termination.settlement_deadline', 'Thời hạn thanh toán quyền lợi sau chấm dứt hợp đồng.', 'condition',
    [group(48, '1. Trong thời hạn 14 ngày làm việc kể từ ngày chấm dứt hợp đồng lao động, hai bên có trách nhiệm thanh toán đầy đủ các khoản tiền có liên quan đến quyền lợi của mỗi bên, trừ trường hợp sau đây có thể kéo dài nhưng không được quá 30 ngày:')],
    ['Sau khi chấm dứt trong điều kiện thông thường, công ty thanh toán các khoản liên quan sau 60 ngày.',
     'Trong điều kiện thông thường, hai bên thanh toán đầy đủ quyền lợi trong 14 ngày làm việc từ khi chấm dứt hợp đồng.'],
    'Ordinary conditions are stated; extension applicability is not being adjudicated.')
add('maternity-night', 'maternity.no_night_overtime_travel', 'Hạn chế làm đêm, làm thêm và công tác xa khi mang thai.', 'condition',
    [group(137, '1. Người sử dụng lao động không được sử dụng người lao động làm việc ban đêm, làm thêm giờ và đi công tác xa trong trường hợp sau đây:'),
     group(137, 'a) Mang thai từ tháng thứ 07 hoặc từ tháng thứ 06 nếu làm việc ở vùng cao, vùng sâu, vùng xa, biên giới, hải đảo;')],
    ['Nhân viên mang thai tháng thứ 07 vẫn phải làm ca đêm theo lịch bắt buộc.',
     'Từ tháng thứ 07 của thai kỳ, người lao động không bị bố trí làm đêm, tăng ca hoặc công tác xa.'],
    'Retrieve the pregnancy threshold and prohibited assignments together.')
add('maternity-break', 'maternity.breaks', 'Nghỉ trong giờ làm khi nuôi con dưới mười hai tháng tuổi.', 'cross_document',
    [group(137, '4. Lao động nữ trong thời gian hành kinh được nghỉ mỗi ngày 30 phút, trong thời gian nuôi con dưới 12 tháng tuổi được nghỉ mỗi ngày 60 phút trong thời gian làm việc. Thời gian nghỉ vẫn được hưởng đủ tiền lương theo hợp đồng lao động.'),
     group(80, 'a) Lao động nữ trong thời gian nuôi con dưới 12 tháng tuổi có quyền được nghỉ mỗi ngày 60 phút trong thời gian làm việc để cho con bú, vắt, trữ sữa, nghỉ ngơi. Thời gian nghỉ vẫn được hưởng đủ tiền lương theo hợp đồng lao động;', N)],
    ['Lao động nữ đang nuôi con 08 tháng tuổi được nghỉ 30 phút/ngày, số phút nghỉ bị trừ lương.',
     'Người lao động nữ nuôi con dưới một tuổi được nghỉ mỗi ngày 60 phút trong giờ làm và vẫn hưởng đủ lương.'],
    'Must find both primary and implementing text, rather than unrelated maternity-leave duration.')
add('return-job', 'maternity.job_guarantee', 'Bảo đảm việc làm khi trở lại sau nghỉ thai sản.', 'single_rule',
    [group(140, 'Lao động được bảo đảm việc làm cũ khi trở lại làm việc sau khi nghỉ hết thời gian theo quy định tại các khoản 1, 3 và 5 Điều 139 của Bộ luật này mà không bị cắt giảm tiền lương và quyền, lợi ích so với trước khi nghỉ thai sản; trường hợp việc làm cũ không còn thì người sử dụng lao động phải bố trí việc làm khác cho họ với mức lương không thấp hơn mức lương trước khi nghỉ thai sản.')],
    ['Sau nghỉ thai sản, nếu vị trí cũ không còn, công ty chuyển nhân viên sang việc mới với lương bằng 80% trước khi nghỉ.',
     'Khi quay lại sau nghỉ thai sản, nhân viên được giữ việc cũ; nếu việc đó không còn thì bố trí việc khác với lương không thấp hơn trước nghỉ.'],
    'The fallback job and wage protection must both be present.')
add('training-costs', 'training.cost_repayment', 'Chi phí đào tạo và nghĩa vụ hoàn trả khi nghỉ trái pháp luật.', 'cross_article',
    [group(40, '3. Phải hoàn trả cho người sử dụng lao động chi phí đào tạo quy định tại Điều 62 của Bộ luật này.'),
     group(62, 'd) Chi phí đào tạo và trách nhiệm hoàn trả chi phí đào tạo;')],
    ['Điều 5: Người lao động được doanh nghiệp tài trợ đào tạo theo hợp đồng đào tạo riêng. Điều 9: Nếu đơn phương chấm dứt trái pháp luật, người lao động không có nghĩa vụ hoàn trả bất kỳ chi phí đào tạo nào.',
     'Phụ lục đào tạo quy định chi phí và trách nhiệm hoàn trả; nếu người lao động đơn phương chấm dứt trái pháp luật thì xử lý khoản đào tạo theo quy định pháp luật.'],
    'A deliberately narrow evidence requirement about cross-reference and agreed repayment terms, not an exhaustive training-cost dispute analysis.')

# Identical concept across dates deliberately stays within one family/split.
wage_variants = []
for suffix, day, key, quote in [
    ('2024-before', '2024-06-30', 'nghi-dinh:38/2022/NĐ-CP', '4.680.000'),
    ('2024-start', '2024-07-01', 'nghi-dinh:74/2024/NĐ-CP', '4.960.000'),
    ('2025-end', '2025-12-31', 'nghi-dinh:74/2024/NĐ-CP', '4.960.000'),
    ('2026-start', '2026-01-01', 'nghi-dinh:293/2025/NĐ-CP', '5.310.000'),
]:
    wage_variants.append({'id': suffix,
        'contract_text': 'Mức lương theo công việc cho lao động làm đủ giờ bình thường tại cơ sở thuộc vùng I là 4.800.000 đồng/tháng. Cần xác định căn cứ mức tối thiểu tháng tại thời điểm thực hiện.',
        'context': {'assessment_date': day, 'minimum_wage_region': 'I', 'pay_basis': 'monthly'},
        'evidence': [group(3, quote, key)]})
FAMILIES.append({'family_id': 'minimum-wage-time', 'split': 'test', 'category': 'temporal_boundary',
    'concepts': [{'id': 'wage.minimum_regional', 'description': 'Mức lương tối thiểu tháng theo vùng và thời điểm.'}],
    'context': {'jurisdiction': 'VN', 'employment_regime': 'labor_contract', 'date_role': 'performance_date'},
    'variants': wage_variants,
    'rationale': 'Region I is supplied as a fact; administrative-region mapping is not tested. The numeric quote tests the correctly dated wage table, not complete legal reasoning.'})
FAMILIES.append({'family_id': 'missing-assessment-date', 'split': 'dev', 'category': 'insufficient_context',
    'concepts': [{'id': 'wage.minimum_regional', 'description': 'Mức lương tối thiểu tháng theo vùng và thời điểm.'}],
    'context': {'jurisdiction': 'VN', 'minimum_wage_region': 'I'}, 'decision': 'insufficient_context',
    'required_context': ['assessment_date'], 'evidence': [],
    'variants': [{'id': 'v1', 'contract_text': 'Lương theo công việc là 4,8 triệu đồng/tháng cho lao động vùng I; hồ sơ không ghi thời điểm thực hiện hoặc thời điểm cần kiểm tra.'},
                 {'id': 'v2', 'contract_text': 'Phụ lục lương vùng I để trống ngày có hiệu lực và không có ngày áp dụng để đánh giá.'}],
    'rationale': 'No default to today: a time-sensitive wage case needs an assessment date.'})
FAMILIES.append({'family_id': 'regional-wage-boundaries', 'split': 'test', 'category': 'temporal_boundary',
    'concepts': [{'id': 'wage.minimum_regional',
                  'description': 'Mức lương tối thiểu tháng theo vùng tại thời điểm thực hiện hợp đồng.'}],
    'context': {'jurisdiction': 'VN', 'employment_regime': 'labor_contract',
                'date_role': 'wage_period_date', 'wage_region': 'I',
                'region_assignment': 'provided_as_fixture_not_inferred_from_address'},
    'variants': [
        {'id': day, 'contract_text': clause, 'context': {'assessment_date': day},
         'evidence': [[{'pid': f'nghi-dinh:{number}/NĐ-CP#d3',
                       'quote': f'Vùng I\n{amount}\n{hourly}'}]]}
        for day, number, amount, hourly, clause in [
            ('2024-06-30', '38/2022', '4.680.000', '22.500', 'Lương theo công việc cho lao động hưởng lương tháng vùng I là 4,7 triệu đồng; kiểm tra kỳ lương cuối tháng 6 năm 2024.'),
            ('2024-07-01', '74/2024', '4.960.000', '23.800', 'Điều khoản lương theo công việc vùng I vẫn là 4,7 triệu đồng cho kỳ lương bắt đầu tháng 7 năm 2024.'),
            ('2025-06-30', '74/2024', '4.960.000', '23.800', 'Mức lương theo công việc tháng của lao động vùng I là 5 triệu đồng vào cuối tháng 6 năm 2025.'),
            ('2025-07-01', '74/2024', '4.960.000', '23.800', 'Sau thay đổi địa giới tháng 7 năm 2025, địa bàn làm việc đã được xác định thuộc vùng I; lương theo công việc là 5 triệu đồng/tháng.'),
            ('2025-12-31', '74/2024', '4.960.000', '23.800', 'Mức lương theo công việc vùng I là 5 triệu đồng/tháng, kiểm tra kỳ lương ngày cuối năm 2025.'),
            ('2026-01-01', '293/2025', '5.310.000', '25.500', 'Công ty tiếp tục trả lương theo công việc vùng I là 5 triệu đồng/tháng từ đầu năm 2026.')]],
    'rationale': 'Known region I: retrieve the correct table row across decree boundaries. Geographic classification and overall wage compliance are separate tasks.'})
FAMILIES.append({'family_id': 'outside-employment', 'split': 'test', 'category': 'out_of_scope',
    'concepts': [], 'context': {'jurisdiction': 'VN', 'assessment_date': '2025-03-01', 'contract_type': 'residential_lease'},
    'decision': 'out_of_scope', 'evidence': [],
    'variants': [{'id': 'v1', 'contract_text': 'Bên thuê căn hộ đặt cọc hai tháng tiền thuê; đây là hợp đồng thuê nhà ở, không có quan hệ lao động.'},
                 {'id': 'v2', 'contract_text': 'Bên cho thuê nhà giữ khoản bảo đảm thanh toán tiền thuê. Các bên xác nhận giao dịch chỉ là thuê nhà, không phải tuyển dụng.'}],
    'rationale': 'Security-deposit keyword is a hard negative for employment-deposit retrieval.'})


if __name__ == '__main__':
    result = {'version': 'contract-evidence-v1.0-draft',
        'corpus_documents': [B, N, 'thong-tu:10/2020/TT-BLĐTBXH',
            'nghi-dinh:38/2022/NĐ-CP', 'nghi-dinh:74/2024/NĐ-CP', 'nghi-dinh:293/2025/NĐ-CP'],
        'families': FAMILIES}
    Path(__file__).with_name('seeds.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
