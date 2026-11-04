"""Sinh evals/team-4.2/datasets/benchmark_doi_thuong.jsonl: 64 câu hỏi kiểu người dân thật hỏi.

Đợt 1: d01-d20. Đợt 2 (11/2026): d21-d64, phủ đều 6 bộ luật. Giữ nguyên id đợt 1 để so được với kết quả cũ
(lọc id <= d20 trong retrieval_per_question.csv).

Đặc điểm: văn nói, mơ hồ, thiếu dữ kiện (không nói rõ hậu quả, số tiền, tuổi...), không dùng thuật ngữ
luật, nhiều câu gộp 2 vấn đề (hình sự + dân sự). Gold = các Điều mà luật sư sẽ viện dẫn để trả lời.

type: "paraphrase" nếu 1 vấn đề, "multi" nếu gold trải trên nhiều vấn đề/bộ luật. Mọi câu có
style = "colloquial_vague" để tách khỏi bộ benchmark_6_bo_luat.

Chạy tại gốc repo sau khi ingest data/team-4.2/raw/:
    python evals/team-4.2/runners/build_benchmark_doi_thuong.py
"""
import json, re, sys
from pathlib import Path

from rag.config import Settings
from rag.index.store import ChunkStore

HS, TTHS, LD = "bo_luat_hinh_su_2015.txt", "bo_luat_to_tung_hinh_su_2015.txt", "bo_luat_lao_dong_2019.txt"
DS, TTDS, HH = "bo_luat_dan_su_2015.txt", "bo_luat_to_tung_dan_su_2015.txt", "bo_luat_hang_hai_2015.txt"

Q = [
    # --- tai nạn, xô xát ---
    ("d01", "multi", "hôm nay tôi lỡ tông phải một ông già lúc sang đường, không biết có bị sao không",
     [(HS, 260), (DS, 601), (DS, 590)],
     "Nếu vi phạm quy định giao thông mà làm chết người hoặc gây tổn thương cơ thể từ 61% trở lên có thể bị truy cứu "
     "TNHS theo Điều 260 BLHS (phạt tiền 30-100 triệu, cải tạo không giam giữ đến 3 năm hoặc tù 1-5 năm). Về dân sự, "
     "xe cơ giới là nguồn nguy hiểm cao độ nên chủ xe/người sử dụng phải bồi thường kể cả khi không có lỗi (Điều 601), "
     "thiệt hại về sức khỏe tính theo Điều 590 BLDS."),
    ("d02", "multi", "tôi lỡ tay đẩy người ta xuống vực, có đến nhà bố mẹ họ xin lỗi rồi có sao không",
     [(HS, 128), (HS, 51), (HS, 29)],
     "Vô ý làm chết người bị xử lý theo Điều 128 BLHS (cải tạo không giam giữ đến 3 năm hoặc tù 1-5 năm). Xin lỗi, "
     "bồi thường, được gia đình bị hại xin giảm nhẹ là tình tiết giảm nhẹ (Điều 51), không làm mất trách nhiệm; "
     "có thể được miễn TNHS nếu tội ít nghiêm trọng do vô ý và người đại diện bị hại tự nguyện hòa giải, đề nghị miễn (Điều 29 khoản 3)."),
    ("d03", "multi", "thằng em tôi nhậu xong đánh nhau ngoài quán, bên kia phải khâu mấy mũi, giờ công an gọi lên làm việc",
     [(HS, 134), (HS, 13)],
     "Có thể bị xử lý về tội cố ý gây thương tích (Điều 134 BLHS) tùy tỷ lệ tổn thương cơ thể và tình tiết (hung khí...). "
     "Say rượu không phải lý do được miễn trách nhiệm hình sự (Điều 13)."),
    # --- lao động ---
    ("d04", "multi", "công ty tự nhiên bảo mai khỏi đi làm nữa, thế có được không",
     [(LD, 36), (LD, 39), (LD, 41)],
     "Công ty chỉ được đơn phương chấm dứt HĐLĐ trong các trường hợp ở Điều 36 và phải báo trước; làm sai là chấm dứt "
     "trái pháp luật (Điều 39), phải nhận lại người lao động, trả lương, đóng bảo hiểm những ngày không được làm và trả "
     "thêm ít nhất 02 tháng lương (Điều 41)."),
    ("d05", "paraphrase", "công ty nợ lương mấy tháng rồi, giờ em nghỉ ngang luôn có bị sao không",
     [(LD, 35)],
     "Không được trả đủ lương hoặc trả không đúng thời hạn thì người lao động được đơn phương chấm dứt HĐLĐ không cần báo trước (Điều 35 khoản 2 điểm b BLLĐ)."),
    ("d06", "multi", "đang bầu mà bị công ty cho nghỉ việc, chị có làm gì được không",
     [(LD, 37), (LD, 137)],
     "Người sử dụng lao động không được đơn phương chấm dứt HĐLĐ với lao động nữ mang thai, đang nghỉ thai sản hoặc nuôi "
     "con dưới 12 tháng tuổi (Điều 37), và không được sa thải/chấm dứt HĐLĐ vì lý do mang thai (Điều 137)."),
    ("d07", "multi", "tháng nào cũng phải ở lại làm tới 9-10h tối mà chẳng thấy thêm đồng nào",
     [(LD, 107), (LD, 98)],
     "Làm thêm giờ phải được người lao động đồng ý và không vượt giới hạn (50% giờ làm bình thường/ngày, 40 giờ/tháng) "
     "(Điều 107); phải trả ít nhất 150% lương ngày thường, cộng thêm phụ cấp làm việc ban đêm nếu có (Điều 98)."),
    # --- tiền bạc, tài sản ---
    ("d08", "multi", "cho đứa bạn mượn 50 triệu giờ nó chặn hết liên lạc rồi",
     [(DS, 466), (HS, 175)],
     "Bên vay phải trả đủ khi đến hạn, có thể khởi kiện đòi nợ (Điều 466 BLDS). Nếu vay rồi bỏ trốn, dùng thủ đoạn gian "
     "dối hoặc cố tình không trả để chiếm đoạt từ 4 triệu đồng trở lên có thể bị xử lý tội lạm dụng tín nhiệm chiếm đoạt tài sản (Điều 175 BLHS)."),
    ("d09", "paraphrase", "chuyển khoản cọc mua hàng trên mạng xong bị block luôn",
     [(HS, 174)],
     "Dùng thủ đoạn gian dối chiếm đoạt tài sản từ 2 triệu đồng trở lên là tội lừa đảo chiếm đoạt tài sản (Điều 174 BLHS); khoản 1: cải tạo không giam giữ đến 3 năm hoặc tù 6 tháng-3 năm."),
    ("d10", "multi", "mẹ mất rồi mà sổ đỏ vẫn đứng tên mẹ, mấy anh em đang cãi nhau",
     [(DS, 650), (DS, 651)],
     "Không có di chúc thì chia thừa kế theo pháp luật (Điều 650); hàng thừa kế thứ nhất gồm vợ/chồng, cha mẹ đẻ/nuôi, con đẻ/nuôi của người chết, được hưởng phần bằng nhau (Điều 651)."),
    ("d16", "multi", "nhặt được cái ví ngoài đường, giữ luôn có sao không",
     [(DS, 230), (HS, 176)],
     "Phải trả lại cho người đánh rơi nếu biết địa chỉ, không thì giao nộp UBND hoặc công an cấp xã (Điều 230 BLDS). "
     "Cố tình không trả lại tài sản trị giá từ 10 triệu đồng có thể bị xử lý tội chiếm giữ trái phép tài sản (Điều 176 BLHS)."),
    ("d17", "multi", "tối qua say quá đập vỡ đồ của quán, sáng ra họ đòi đền",
     [(DS, 589), (HS, 178)],
     "Phải bồi thường thiệt hại tài sản bị hư hỏng (Điều 589 BLDS). Cố ý làm hư hỏng tài sản từ 2 triệu đồng trở lên có thể bị xử lý theo Điều 178 BLHS."),
    # --- gia đình, hàng xóm ---
    ("d12", "multi", "con tôi mới 13 tuổi, đi lấy trộm xe đạp bị người ta bắt được",
     [(HS, 12), (DS, 586)],
     "Chưa đủ 14 tuổi thì không phải chịu trách nhiệm hình sự (Điều 12 BLHS). Người chưa đủ 15 tuổi gây thiệt hại thì cha mẹ phải bồi thường (Điều 586 khoản 2 BLDS)."),
    ("d13", "multi", "nhà bên cạnh đang xây, tường nhà tôi nứt hết cả rồi",
     [(DS, 174), (DS, 584)],
     "Khi xây dựng phải bảo đảm an toàn, không xâm phạm bất động sản liền kề (Điều 174 BLDS); gây thiệt hại thì phải bồi thường (Điều 584)."),
    ("d14", "paraphrase", "con chó nhà tôi sổng ra cắn đứa nhỏ hàng xóm",
     [(DS, 603)],
     "Chủ sở hữu phải bồi thường thiệt hại do súc vật gây ra (Điều 603 BLDS), trừ khi người bị hại hoàn toàn có lỗi."),
    ("d15", "multi", "bị đứa kia lên facebook bịa chuyện nói xấu, nhục không chịu được",
     [(DS, 34), (HS, 156), (HS, 155)],
     "Có quyền yêu cầu gỡ bỏ, cải chính và bồi thường (Điều 34 BLDS). Bịa đặt, loan truyền điều sai sự thật xúc phạm danh dự có thể bị xử lý tội vu khống (Điều 156), xúc phạm nghiêm trọng nhân phẩm là tội làm nhục người khác (Điều 155)."),
    # --- tố tụng ---
    ("d11", "paraphrase", "tối qua chồng tôi bị công an đến nhà bắt đi, giờ chẳng ai báo gì cho gia đình cả",
     [(TTHS, 116)],
     "Người ra lệnh bắt phải thông báo ngay cho gia đình; Cơ quan điều tra nhận người phải thông báo cho gia đình trong 24 giờ (Điều 116 BLTTHS)."),
    ("d18", "paraphrase", "tòa gửi giấy gọi lên mà tôi bận không đi được thì sao",
     [(TTDS, 227)],
     "Triệu tập lần 1 vắng mặt thì hoãn phiên tòa; lần 2 vắng không lý do chính đáng: nguyên đơn bị coi là từ bỏ khởi kiện, bị đơn bị xét xử vắng mặt (Điều 227 BLTTDS)."),
    ("d19", "multi", "vợ ôm con về ngoại cả năm nay rồi, giờ muốn làm đơn ly hôn thì nộp ở đâu",
     [(TTDS, 35), (TTDS, 39)],
     "Ly hôn thuộc thẩm quyền Tòa án nhân dân cấp huyện (Điều 35); nộp tại Tòa nơi bị đơn (vợ) cư trú, làm việc, hoặc thỏa thuận nộp nơi nguyên đơn (Điều 39 BLTTDS)."),
    ("d20", "paraphrase", "chồng tôi đi làm trên tàu, hết hợp đồng mà chủ tàu bỏ ở nước ngoài không lo cho về",
     [(HH, 66)],
     "Chủ tàu phải bố trí cho thuyền viên hồi hương và thanh toán chi phí khi hợp đồng lao động hết hạn (Điều 66 Bộ luật Hàng hải)."),

    # ===== Đợt 2 (d21-d64), 11/2026 =====
    # --- hình sự ---
    ("d21", "paraphrase", "thằng con trai tôi 18 tuổi yêu đứa con gái 15 tuổi, hai đứa tự nguyện ngủ với nhau, giờ bố mẹ bé gái đòi báo công an",
     [(HS, 145)],
     "Người từ đủ 18 tuổi giao cấu với người từ đủ 13 đến dưới 16 tuổi là phạm tội dù hai bên tự nguyện (Điều 145 BLHS), khoản 1: tù 01-05 năm."),
    ("d22", "multi", "ông hàng xóm say rượu cầm dao sang chửi, tôi lấy gậy đánh lại gãy tay ông ấy, giờ ổng đòi kiện",
     [(HS, 22), (HS, 134)],
     "Chống trả cần thiết để bảo vệ mình trước hành vi tấn công là phòng vệ chính đáng, không phải tội phạm (Điều 22 BLHS). "
     "Nếu chống trả rõ ràng quá mức cần thiết thì là vượt quá giới hạn phòng vệ (Điều 136); không có yếu tố phòng vệ thì xét theo tội cố ý gây thương tích (Điều 134)."),
    ("d23", "paraphrase", "đi đường thấy người ta bị tai nạn nằm đó mà sợ liên lụy nên đi luôn, có sao không",
     [(HS, 132)],
     "Thấy người đang ở tình trạng nguy hiểm đến tính mạng, có điều kiện mà không cứu giúp dẫn đến người đó chết thì phạm tội theo Điều 132 BLHS "
     "(cảnh cáo, cải tạo không giam giữ đến 02 năm hoặc tù 03 tháng-02 năm)."),
    ("d24", "paraphrase", "tối nào mấy ông trong xóm cũng tụ tập đánh bài ăn tiền, công an ập vào thì có bị gì không",
     [(HS, 321)],
     "Đánh bạc trái phép được thua bằng tiền/hiện vật từ 5 đến dưới 50 triệu đồng (hoặc dưới 5 triệu nhưng đã bị xử phạt hành chính, đã bị kết án mà còn vi phạm) "
     "phạm tội đánh bạc (Điều 321 BLHS): cải tạo không giam giữ đến 03 năm hoặc tù 06 tháng-03 năm; dưới mức đó thì xử phạt hành chính."),
    ("d25", "paraphrase", "đang đi thì bị thằng kia rút dao kề cổ bắt đưa điện thoại",
     [(HS, 168)],
     "Dùng vũ lực hoặc đe dọa dùng vũ lực ngay tức khắc làm người bị tấn công không thể chống cự để chiếm tài sản là tội cướp tài sản (Điều 168 BLHS), "
     "khoản 1: tù 03-10 năm; dùng hung khí nguy hiểm là tình tiết định khung tăng nặng."),
    ("d26", "multi", "cháu tôi 17 tuổi đi trộm điện thoại của người ta bị bắt, liệu có phải đi tù không",
     [(HS, 173), (HS, 91)],
     "Lén lút chiếm tài sản từ 2 triệu đồng trở lên là tội trộm cắp tài sản (Điều 173 BLHS). Người dưới 18 tuổi phạm tội được xử lý chủ yếu nhằm giáo dục, "
     "có thể được miễn TNHS, áp dụng biện pháp giám sát giáo dục, chỉ phạt tù khi các biện pháp khác không đủ tác dụng và mức tù nhẹ hơn người lớn (Điều 91)."),
    ("d27", "paraphrase", "chồng tôi cứ say là về đánh chửi vợ con, mấy năm nay rồi",
     [(HS, 185)],
     "Thường xuyên làm nhục, gây đau đớn về thể xác, tinh thần cho vợ, con là tội ngược đãi hoặc hành hạ (Điều 185 BLHS): cảnh cáo, "
     "cải tạo không giam giữ đến 03 năm hoặc tù 03 tháng-02 năm."),
    ("d28", "paraphrase", "uống mấy lon bia xong chạy xe va vào người ta, hoảng quá nên bỏ chạy luôn",
     [(HS, 260)],
     "Vi phạm quy định giao thông gây hậu quả nghiêm trọng thì phạm tội theo Điều 260 BLHS; có nồng độ cồn vượt mức quy định hoặc bỏ chạy để trốn tránh "
     "trách nhiệm, cố ý không cứu giúp người bị nạn là tình tiết định khung khoản 2 (tù 03-10 năm)."),
    ("d29", "paraphrase", "bạn rủ chở hộ một bọc hàng lên biên giới trả 5 triệu, đến nơi mới biết là ma túy",
     [(HS, 250)],
     "Vận chuyển trái phép chất ma túy là tội theo Điều 250 BLHS (khoản 1: tù 02-07 năm). Tội này đòi hỏi lỗi cố ý; nếu thật sự không biết bọc hàng là ma túy "
     "thì không đủ yếu tố cấu thành, nhưng cơ quan điều tra sẽ xem xét các dấu hiệu (giá công bất thường...)."),
    ("d30", "paraphrase", "bố tôi gần 80 tuổi, bệnh nặng, vừa bị tòa tuyên án tù, có xin lùi ngày đi tù được không",
     [(HS, 67)],
     "Người bị phạt tù đang bị bệnh nặng được hoãn chấp hành hình phạt tù cho đến khi sức khỏe hồi phục (Điều 67 khoản 1 điểm a BLHS)."),
    ("d31", "paraphrase", "lần đầu vi phạm, tội cũng nhẹ, nhà có con nhỏ, có xin được không phải ngồi tù không",
     [(HS, 65)],
     "Người bị phạt tù không quá 03 năm, có nhân thân tốt, có nhiều tình tiết giảm nhẹ và xét thấy không cần bắt chấp hành hình phạt tù thì có thể được hưởng "
     "án treo, thời gian thử thách 01-05 năm (Điều 65 BLHS)."),
    ("d32", "multi", "cho vay lấy lãi 5 nghìn một triệu một ngày thì có bị sao không",
     [(DS, 468), (HS, 201)],
     "Lãi suất thỏa thuận không được vượt 20%/năm, phần vượt không có hiệu lực (Điều 468 BLDS). 5.000đ/1 triệu/ngày ≈ 182%/năm, vượt 5 lần mức cao nhất; "
     "nếu thu lợi bất chính từ 30 triệu đồng thì phạm tội cho vay lãi nặng (Điều 201 BLHS): phạt tiền 50-200 triệu hoặc cải tạo không giam giữ đến 03 năm."),
    # --- tố tụng hình sự ---
    ("d33", "paraphrase", "anh trai bị công an bắt, nhà muốn thuê luật sư thì lúc nào luật sư mới được vào",
     [(TTHS, 74)],
     "Người bào chữa tham gia từ khi khởi tố bị can; trường hợp bắt, tạm giữ thì từ khi người bị bắt có mặt tại trụ sở Cơ quan điều tra hoặc từ khi có quyết định tạm giữ (Điều 74 BLTTHS)."),
    ("d34", "paraphrase", "em tôi bị tạm giam mấy tháng rồi vẫn chưa thấy đưa ra xử, giam vậy tối đa bao lâu",
     [(TTHS, 173)],
     "Tạm giam để điều tra không quá 02 tháng với tội ít nghiêm trọng, 03 tháng với tội nghiêm trọng, 04 tháng với tội rất nghiêm trọng, đặc biệt nghiêm trọng; "
     "có thể được gia hạn theo Điều 173 BLTTHS."),
    ("d35", "paraphrase", "đánh nhau bị thương nhẹ, giờ hai bên làm lành rồi, tôi rút đơn thì vụ án có dừng không",
     [(TTHS, 155)],
     "Một số tội (vd. khoản 1 Điều 134 BLHS) chỉ khởi tố khi bị hại yêu cầu; bị hại rút yêu cầu thì vụ án được đình chỉ, trừ khi việc rút yêu cầu do bị ép buộc (Điều 155 BLTTHS)."),
    ("d36", "multi", "tòa vừa xử bố tôi 3 năm tù mà gia đình thấy nặng quá, giờ làm sao",
     [(TTHS, 331), (TTHS, 333)],
     "Bị cáo và người đại diện của bị cáo có quyền kháng cáo bản án sơ thẩm (Điều 331 BLTTHS); thời hạn kháng cáo là 15 ngày kể từ ngày tuyên án (Điều 333)."),
    # --- dân sự ---
    ("d37", "paraphrase", "đặt cọc 100 triệu mua nhà rồi mà bên bán lại đổi ý không bán nữa",
     [(DS, 328)],
     "Bên nhận đặt cọc từ chối giao kết, thực hiện hợp đồng thì phải trả lại tiền cọc và một khoản tiền tương đương giá trị cọc, trừ khi có thỏa thuận khác (Điều 328 BLDS)."),
    ("d38", "paraphrase", "bố mất để di chúc cho hết người tình, mẹ con tôi không được đồng nào, mà tôi mới 16 tuổi",
     [(DS, 644)],
     "Vợ và con chưa thành niên của người lập di chúc vẫn được hưởng phần di sản bằng 2/3 suất của một người thừa kế theo pháp luật dù không được di chúc cho hưởng (Điều 644 BLDS)."),
    ("d39", "multi", "ông nội trước khi mất có nói miệng là cho tôi mảnh đất, mấy chú có cãi được không",
     [(DS, 629), (DS, 630)],
     "Di chúc miệng chỉ được lập khi tính mạng bị cái chết đe dọa và không thể lập di chúc bằng văn bản (Điều 629 BLDS); để hợp pháp phải có ít nhất 2 người làm chứng, "
     "được ghi chép lại, ký tên và công chứng/chứng thực trong 05 ngày làm việc (Điều 630 khoản 5)."),
    ("d40", "multi", "mua điện thoại về được 3 hôm thì hỏng, cửa hàng không chịu đổi cũng không sửa",
     [(DS, 445), (DS, 446)],
     "Bên bán phải bảo đảm chất lượng vật bán đúng thỏa thuận/tiêu chuẩn (Điều 445 BLDS) và có nghĩa vụ bảo hành trong thời hạn bảo hành (Điều 446): sửa chữa, đổi, hoặc trả lại tiền."),
    ("d41", "paraphrase", "cây nhà hàng xóm mọc lấn sang nhà tôi, rễ đâm nứt cả sân",
     [(DS, 175)],
     "Người sử dụng đất chỉ được sử dụng không gian, lòng đất theo chiều thẳng đứng từ ranh giới thửa đất và không được ảnh hưởng đến việc sử dụng đất của người khác (Điều 175 BLDS); gây thiệt hại thì phải bồi thường."),
    ("d42", "paraphrase", "nhà tôi ở trong ngõ, nhà phía ngoài xây tường chặn mất lối đi ra đường",
     [(DS, 254)],
     "Chủ sở hữu bất động sản bị vây bọc không có lối đi ra đường công cộng có quyền yêu cầu chủ bất động sản vây bọc dành một lối đi hợp lý, và phải đền bù nếu không có thỏa thuận khác (Điều 254 BLDS)."),
    ("d43", "paraphrase", "con tôi 16 tuổi tự ý đi mua xe máy trả góp, giờ tôi muốn trả lại được không",
     [(DS, 21)],
     "Người từ đủ 15 đến chưa đủ 18 tuổi tự xác lập giao dịch, trừ giao dịch liên quan đến bất động sản, động sản phải đăng ký và giao dịch khác theo luật phải được người đại diện đồng ý (Điều 21 BLDS); xe máy là tài sản phải đăng ký."),
    ("d44", "multi", "chồng mất không để lại di chúc, nhà hai vợ chồng mua chung thì chia thế nào",
     [(DS, 213), (DS, 651)],
     "Nhà là tài sản chung của vợ chồng (Điều 213 BLDS) nên một nửa thuộc về vợ; nửa còn lại là di sản, chia theo pháp luật cho hàng thừa kế thứ nhất gồm vợ, cha mẹ, con của người chết, mỗi người phần bằng nhau (Điều 651)."),
    ("d45", "paraphrase", "bị cửa hàng lấy ảnh mình đăng quảng cáo trên facebook mà không xin phép",
     [(DS, 32)],
     "Sử dụng hình ảnh của cá nhân phải được người đó đồng ý; dùng vì mục đích thương mại thì phải trả thù lao. Người bị xâm phạm có quyền yêu cầu thu hồi, gỡ bỏ, bồi thường (Điều 32 BLDS)."),
    ("d46", "paraphrase", "ký hợp đồng thi công mà chậm mấy ngày bị đòi phạt 30% giá trị, vậy có đúng luật không",
     [(DS, 418)],
     "Mức phạt vi phạm do các bên thỏa thuận, BLDS không giới hạn mức (Điều 418); luật khác có thể quy định trần (vd. Luật Thương mại)."),
    ("d47", "paraphrase", "nhặt được con chó lạc giữ nuôi cả năm, giờ chủ cũ đến đòi",
     [(DS, 231)],
     "Người bắt được gia súc thất lạc phải báo UBND cấp xã; sau 06 tháng kể từ ngày thông báo công khai (01 năm với gia súc thả rông) thì thuộc sở hữu người bắt được. "
     "Chủ được nhận lại thì phải trả công nuôi giữ, chi phí (Điều 231 BLDS)."),
    # --- lao động ---
    ("d48", "paraphrase", "đi xin việc công ty bắt nộp bằng đại học bản gốc, nghỉ mới trả",
     [(LD, 17)],
     "Người sử dụng lao động không được giữ bản chính giấy tờ tùy thân, văn bằng, chứng chỉ của người lao động (Điều 17 BLLĐ)."),
    ("d49", "multi", "thử việc 3 tháng mà công ty chỉ trả có 70% lương",
     [(LD, 25), (LD, 26)],
     "Thử việc tối đa 180 ngày (quản lý doanh nghiệp), 60 ngày (cao đẳng trở lên), 30 ngày (trung cấp), 06 ngày làm việc (công việc khác) (Điều 25 BLLĐ); lương thử việc ít nhất 85% lương công việc đó (Điều 26)."),
    ("d50", "multi", "làm cho công ty 5 năm rồi giờ xin nghỉ, công ty có phải trả khoản gì không",
     [(LD, 46), (LD, 48)],
     "Làm thường xuyên từ đủ 12 tháng thì được trợ cấp thôi việc, mỗi năm nửa tháng lương (trừ thời gian đã đóng bảo hiểm thất nghiệp) (Điều 46 BLLĐ); "
     "trong 14 ngày làm việc công ty phải thanh toán đủ các khoản và trả lại sổ bảo hiểm xã hội, giấy tờ (Điều 48)."),
    ("d51", "paraphrase", "đi muộn mấy lần bị công ty trừ thẳng vào lương",
     [(LD, 127)],
     "Nghiêm cấm phạt tiền, cắt lương thay việc xử lý kỷ luật lao động (Điều 127 BLLĐ)."),
    ("d52", "multi", "em 15 tuổi muốn đi làm phụ quán cà phê dịp hè được không",
     [(LD, 143), (LD, 146)],
     "Người dưới 18 tuổi là lao động chưa thành niên, được làm những công việc phù hợp (Điều 143 BLLĐ); từ đủ 15 đến dưới 18 tuổi làm không quá 08 giờ/ngày, 40 giờ/tuần (Điều 146)."),
    ("d53", "multi", "sếp hay sờ mó, nói chuyện bậy với em ở công ty, em muốn nghỉ luôn",
     [(LD, 8), (LD, 35)],
     "Quấy rối tình dục tại nơi làm việc là hành vi bị nghiêm cấm (Điều 8 BLLĐ); người lao động bị quấy rối tình dục được đơn phương chấm dứt HĐLĐ không cần báo trước (Điều 35 khoản 2)."),
    ("d54", "paraphrase", "vợ sắp đẻ, công ty cho nghỉ được mấy tháng",
     [(LD, 139)],
     "Lao động nữ được nghỉ thai sản trước và sau khi sinh 06 tháng, thời gian nghỉ trước sinh không quá 02 tháng; sinh đôi trở lên thì từ con thứ hai mỗi con thêm 01 tháng (Điều 139 BLLĐ)."),
    ("d55", "paraphrase", "mẹ mất, xin nghỉ mấy ngày mà công ty bảo phải nghỉ không lương",
     [(LD, 115)],
     "Cha đẻ, mẹ đẻ, vợ/chồng, con chết thì người lao động được nghỉ 03 ngày hưởng nguyên lương (Điều 115 BLLĐ)."),
    # --- tố tụng dân sự ---
    ("d56", "paraphrase", "muốn kiện mà không có tiền, đi kiện có phải đóng tiền trước không",
     [(TTDS, 146)],
     "Nguyên đơn phải nộp tiền tạm ứng án phí sơ thẩm, trừ trường hợp được miễn hoặc không phải nộp theo quy định (Điều 146 BLTTDS)."),
    ("d57", "paraphrase", "người nợ tiền tôi đang sống ở nước ngoài, giờ muốn kiện thì nộp đơn ở đâu",
     [(TTDS, 37)],
     "Tranh chấp có đương sự ở nước ngoài không thuộc Tòa cấp huyện mà thuộc thẩm quyền sơ thẩm của Tòa án nhân dân cấp tỉnh (Điều 37 BLTTDS)."),
    ("d58", "paraphrase", "nộp đơn kiện lên tòa rồi mà tòa trả lại đơn",
     [(TTDS, 192)],
     "Tòa trả lại đơn khi người khởi kiện không có quyền khởi kiện, chưa đủ điều kiện khởi kiện, sự việc đã được giải quyết bằng bản án có hiệu lực, không nộp tạm ứng án phí... "
     "(Điều 192 BLTTDS); người khởi kiện có thể khiếu nại việc trả lại đơn."),
    ("d59", "multi", "bản án phúc thẩm có hiệu lực rồi nhưng tôi vẫn thấy xử sai, còn cách nào không",
     [(TTDS, 326), (TTDS, 327)],
     "Bản án có hiệu lực bị kháng nghị giám đốc thẩm khi có căn cứ: kết luận không phù hợp tình tiết khách quan, vi phạm nghiêm trọng thủ tục, sai lầm áp dụng pháp luật (Điều 326 BLTTDS); "
     "đương sự gửi đơn đề nghị người có thẩm quyền kháng nghị trong 01 năm kể từ ngày bản án có hiệu lực (Điều 327)."),
    ("d60", "paraphrase", "tòa xử sơ thẩm xong tôi không đồng ý thì được kháng cáo trong bao lâu",
     [(TTDS, 273)],
     "Thời hạn kháng cáo bản án sơ thẩm là 15 ngày kể từ ngày tuyên án; người vắng mặt tại phiên tòa thì tính từ ngày nhận được hoặc niêm yết bản án (Điều 273 BLTTDS)."),
    # --- hàng hải ---
    ("d61", "paraphrase", "chồng tôi làm thuyền viên bị tai nạn trên tàu, chủ tàu có phải lo không",
     [(HH, 69)],
     "Chủ tàu chịu trách nhiệm đối với thuyền viên bị tai nạn lao động hàng hải, bệnh nghề nghiệp (Điều 69 Bộ luật Hàng hải)."),
    ("d62", "multi", "đi tàu ra đảo bị mất vali hành lý, hãng tàu có phải đền không",
     [(HH, 209), (HH, 213)],
     "Người vận chuyển phải bồi thường mất mát, hư hỏng hành lý trong giới hạn trách nhiệm theo Điều 209 Bộ luật Hàng hải (mức riêng cho hành lý xách tay, "
     "hành lý khác); hành khách phải thông báo bằng văn bản cho người vận chuyển về mất mát, hư hỏng hành lý theo Điều 213."),
    ("d63", "paraphrase", "tàu cá nhà tôi cứu được một tàu bị nạn ngoài khơi, có được đòi tiền công không",
     [(HH, 266)],
     "Hoạt động cứu hộ mang lại kết quả có ích thì người cứu hộ có quyền hưởng tiền công cứu hộ (Điều 266 Bộ luật Hàng hải)."),
    ("d64", "paraphrase", "hai tàu đâm vào nhau ngoài biển thì bên nào phải đền",
     [(HH, 287)],
     "Tai nạn đâm va do lỗi của các bên thì mỗi tàu bồi thường theo mức độ lỗi của mình; lỗi ngang nhau hoặc không xác định được mức độ lỗi thì chia đều (Điều 287 Bộ luật Hàng hải)."),
]


def main() -> None:
    s = Settings.load()
    chunks = ChunkStore(s.chunks_path).all()
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "evals/team-4.2/datasets/benchmark_doi_thuong.jsonl")
    rows = []
    for qid, typ, question, arts, ref in sorted(Q):
        assert (typ == "multi") == (len(arts) > 1), (qid, typ, arts)
        gold, ids, labels = [], [], []
        for src, n in arts:
            pat = re.compile(rf"(^| > )Điều {n}\. ")
            secs = {c.section for c in chunks if c.source == src and c.section and pat.search(c.section)
                    and c.section.rsplit(" > ", 1)[-1].startswith(f"Điều {n}.")}
            assert len(secs) == 1, (qid, src, n, secs)
            sec = secs.pop()
            gold.append({"source": src, "section": sec})
            ids += [c.chunk_id for c in chunks if c.source == src and c.section == sec]
            labels.append(f"{src.removesuffix('.txt')} Điều {n}")
        rows.append({"id": qid, "question": question, "type": typ, "author": "claude", "style": "colloquial_vague",
                     "gold": gold, "reference": ref, "gold_articles": labels, "gold_chunk_ids": ids})
    assert len({r["id"] for r in rows}) == len(rows) == len(Q)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote", len(rows), "questions ->", out)


if __name__ == "__main__":
    main()
