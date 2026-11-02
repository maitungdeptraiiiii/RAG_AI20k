"""Sinh evals/team-4.2/datasets/benchmark_6_bo_luat.jsonl (chạy tại gốc repo sau khi ingest data/team-4.2/raw/): gold = section của Điều (tra từ chunk store).

Ghi thêm gold_chunk_ids (thông tin, runner không dùng) và gold_articles để người đọc kiểm tra.
"""
import json, re, sys
from pathlib import Path

from rag.config import Settings
from rag.index.store import ChunkStore

HS, TTHS, LD = "bo_luat_hinh_su_2015.txt", "bo_luat_to_tung_hinh_su_2015.txt", "bo_luat_lao_dong_2019.txt"
DS, TTDS, HH = "bo_luat_dan_su_2015.txt", "bo_luat_to_tung_dan_su_2015.txt", "bo_luat_hang_hai_2015.txt"

Q = [
    # --- lookup: hỏi gần đúng câu chữ trong luật ---
    ("q01", "lookup", "Thời giờ làm việc bình thường của người lao động không quá bao nhiêu giờ trong một ngày và một tuần?",
     [(LD, 105)], "Không quá 08 giờ trong 01 ngày và không quá 48 giờ trong 01 tuần (theo tuần thì không quá 10 giờ/ngày, 48 giờ/tuần)."),
    ("q02", "lookup", "Người lao động làm việc đủ 12 tháng trong điều kiện bình thường được nghỉ hằng năm bao nhiêu ngày?",
     [(LD, 113)], "12 ngày làm việc, hưởng nguyên lương."),
    ("q03", "lookup", "Người thành niên là người từ đủ bao nhiêu tuổi trở lên?",
     [(DS, 20)], "Người từ đủ mười tám tuổi trở lên."),
    ("q04", "lookup", "Thời hạn tạm giữ tối đa là bao nhiêu ngày và được gia hạn mấy lần?",
     [(TTHS, 118)], "Không quá 03 ngày; có thể gia hạn không quá 03 ngày, trường hợp đặc biệt gia hạn lần hai không quá 03 ngày, phải được Viện kiểm sát phê chuẩn."),
    ("q05", "lookup", "Thời hạn kháng cáo đối với bản án sơ thẩm trong vụ án dân sự là bao lâu?",
     [(TTDS, 273)], "15 ngày kể từ ngày tuyên án (đương sự vắng mặt có lý do chính đáng thì tính từ ngày nhận/niêm yết bản án)."),
    ("q06", "lookup", "Thời hiệu khởi kiện đối với vụ việc liên quan đến hợp đồng thuê tàu là bao lâu?",
     [(HH, 219)], "02 năm kể từ ngày chấm dứt hợp đồng."),
    ("q07", "lookup", "Thời hiệu để người thừa kế yêu cầu chia di sản là bao nhiêu năm?",
     [(DS, 623)], "30 năm đối với bất động sản, 10 năm đối với động sản, kể từ thời điểm mở thừa kế."),
    ("q08", "lookup", "Tội phạm được phân thành mấy loại theo Bộ luật Hình sự?",
     [(HS, 9)], "Bốn loại: ít nghiêm trọng, nghiêm trọng, rất nghiêm trọng, đặc biệt nghiêm trọng."),
    # --- paraphrase: diễn đạt đời thường, khác câu chữ luật ---
    ("q09", "paraphrase", "Tôi ký hợp đồng lao động không thời hạn, muốn nghỉ việc thì phải báo trước cho công ty bao lâu?",
     [(LD, 35)], "Ít nhất 45 ngày."),
    ("q10", "paraphrase", "Chị em công nhân sinh con được nghỉ bao lâu, nếu sinh đôi thì sao?",
     [(LD, 139)], "06 tháng (trước sinh không quá 02 tháng); sinh đôi trở lên thì từ con thứ hai mỗi con được nghỉ thêm 01 tháng."),
    ("q11", "paraphrase", "Cho bạn vay tiền thì được lấy lãi tối đa bao nhiêu phần trăm một năm?",
     [(DS, 468)], "Lãi suất thỏa thuận không vượt quá 20%/năm của khoản tiền vay; phần vượt không có hiệu lực."),
    ("q12", "paraphrase", "Bố mẹ mất không để lại di chúc thì những ai được hưởng tài sản đầu tiên?",
     [(DS, 651)], "Hàng thừa kế thứ nhất: vợ, chồng, cha đẻ, mẹ đẻ, cha nuôi, mẹ nuôi, con đẻ, con nuôi của người chết."),
    ("q13", "paraphrase", "Kỹ sư mới tốt nghiệp đại học đi làm thì công ty được cho thử việc tối đa bao lâu?",
     [(LD, 25)], "Không quá 60 ngày (công việc cần trình độ từ cao đẳng trở lên); chỉ thử việc một lần."),
    ("q14", "paraphrase", "Đàn ông đi làm bình thường thì đến mấy tuổi mới được về hưu?",
     [(LD, 169)], "Điều chỉnh theo lộ trình đến đủ 62 tuổi với lao động nam vào năm 2028 (nữ 60 tuổi vào năm 2035)."),
    ("q15", "paraphrase", "Lái xe gây tai nạn làm chết một người thì bị xử lý hình sự thế nào?",
     [(HS, 260)], "Phạt tiền 30-100 triệu đồng, cải tạo không giam giữ đến 03 năm hoặc phạt tù 01-05 năm (khoản 1)."),
    ("q16", "paraphrase", "Muốn kiện người khác về chuyện dân sự thì nộp đơn ở tòa nơi nào?",
     [(TTDS, 39)], "Tòa án nơi bị đơn cư trú, làm việc (cá nhân) hoặc nơi bị đơn có trụ sở (cơ quan, tổ chức)."),
    # --- multi: cần suy luận / nối nhiều Điều, có câu nối hai bộ luật ---
    ("q17", "multi", "Một thiếu niên 15 tuổi lần đầu trộm chiếc xe máy trị giá 10 triệu đồng thì có phải chịu trách nhiệm hình sự không?",
     [(HS, 12), (HS, 173), (HS, 9)],
     "Không. Trộm 10 triệu thuộc khoản 1 Điều 173 (tối đa 03 năm tù) là tội ít nghiêm trọng (Điều 9); người 14-16 tuổi chỉ chịu TNHS về tội rất nghiêm trọng/đặc biệt nghiêm trọng tại Điều 173 (Điều 12 khoản 2)."),
    ("q18", "multi", "A cho B vay tiền với lãi 30%/năm. B không trả, 4 năm sau A mới khởi kiện. Phần lãi có được tính đủ không và A còn quyền khởi kiện không?",
     [(DS, 468), (DS, 429)],
     "Phần lãi vượt 20%/năm không có hiệu lực (Điều 468); thời hiệu khởi kiện tranh chấp hợp đồng là 03 năm (Điều 429) nên sau 4 năm đã hết thời hiệu."),
    ("q19", "multi", "Tôi bị công ty đuổi việc trái luật cách đây 10 tháng. Giờ tôi còn kiện ra tòa được không, và nếu thắng thì công ty phải bồi thường những gì?",
     [(LD, 190), (LD, 41)],
     "Còn: thời hiệu yêu cầu Tòa án là 01 năm (Điều 190). Công ty phải nhận lại làm việc, trả lương, đóng BHXH/BHYT/BHTN những ngày không được làm việc và trả thêm ít nhất 02 tháng lương (Điều 41)."),
    ("q20", "multi", "Bị can bị khởi tố về tội trộm cắp tài sản trị giá 10 triệu đồng thì có thể bị tạm giam để điều tra tối đa bao lâu (chưa gia hạn)?",
     [(HS, 173), (HS, 9), (TTHS, 173)],
     "Trộm 10 triệu thuộc khoản 1 Điều 173 BLHS (tối đa 03 năm tù) là tội ít nghiêm trọng (Điều 9 BLHS), nên tạm giam để điều tra không quá 02 tháng (Điều 173 BLTTHS)."),
    # ===== Đợt 2 (q21-q40): 8 lookup, 8 paraphrase, 4 multi =====
    # --- lookup ---
    ("q21", "lookup", "Người lao động làm thêm giờ vào ngày nghỉ hằng tuần được trả lương ít nhất bằng bao nhiêu phần trăm?",
     [(LD, 98)], "Ít nhất bằng 200% (ngày thường 150%, ngày lễ tết 300%)."),
    ("q22", "lookup", "Người lao động được nghỉ Tết Âm lịch bao nhiêu ngày hưởng nguyên lương?",
     [(LD, 112)], "05 ngày."),
    ("q23", "lookup", "Thời hiệu truy cứu trách nhiệm hình sự đối với tội phạm nghiêm trọng là bao nhiêu năm?",
     [(HS, 27)], "10 năm (ít nghiêm trọng 05 năm, rất nghiêm trọng 15 năm, đặc biệt nghiêm trọng 20 năm)."),
    ("q24", "lookup", "Hình phạt chính đối với người phạm tội bao gồm những hình phạt nào?",
     [(HS, 32)], "Cảnh cáo, phạt tiền, cải tạo không giam giữ, trục xuất, tù có thời hạn, tù chung thân, tử hình."),
    ("q25", "lookup", "Thời hạn giải quyết tố giác, tin báo về tội phạm, kiến nghị khởi tố là bao nhiêu ngày?",
     [(TTHS, 147)], "20 ngày kể từ ngày nhận được tố giác, tin báo, kiến nghị khởi tố."),
    ("q26", "lookup", "Thời hạn chuẩn bị xét xử đối với vụ án tranh chấp dân sự, hôn nhân và gia đình là bao lâu?",
     [(TTDS, 203)], "04 tháng kể từ ngày thụ lý vụ án (vụ án tại Điều 26 và Điều 28)."),
    ("q27", "lookup", "Ai là người có quyền chỉ huy cao nhất trên tàu biển?",
     [(HH, 52)], "Thuyền trưởng; mọi người trên tàu phải chấp hành mệnh lệnh của thuyền trưởng."),
    ("q28", "lookup", "Người từ đủ mười lăm tuổi đến chưa đủ mười tám tuổi có được lập di chúc không?",
     [(DS, 625)], "Được, nếu được cha, mẹ hoặc người giám hộ đồng ý về việc lập di chúc."),
    # --- paraphrase ---
    ("q29", "paraphrase", "Tôi sắp cưới vợ thì được công ty cho nghỉ mấy ngày mà vẫn có lương?",
     [(LD, 115)], "03 ngày nghỉ việc riêng hưởng nguyên lương (phải thông báo với người sử dụng lao động)."),
    ("q30", "paraphrase", "Làm cho công ty được 4 năm rồi nghỉ thì công ty có phải trả thêm khoản tiền nào không, tính thế nào?",
     [(LD, 46)], "Trợ cấp thôi việc: mỗi năm làm việc được một nửa tháng tiền lương (trừ thời gian đã đóng bảo hiểm thất nghiệp)."),
    ("q31", "paraphrase", "Lừa người ta lấy 30 triệu đồng thì có thể bị đi tù bao lâu?",
     [(HS, 174)], "Cải tạo không giam giữ đến 03 năm hoặc phạt tù từ 06 tháng đến 03 năm (khoản 1 Điều 174)."),
    ("q32", "paraphrase", "Tôi cho bạn mượn ô tô, bạn lái gây tai nạn thì ai phải đền tiền cho người bị nạn?",
     [(DS, 601)], "Người được giao chiếm hữu, sử dụng (người mượn) phải bồi thường, trừ khi có thỏa thuận khác; bồi thường cả khi không có lỗi."),
    ("q33", "paraphrase", "Con tôi 17 tuổi bị bắt mà gia đình không thuê được luật sư thì có ai bào chữa cho cháu không?",
     [(TTHS, 76)], "Có: cơ quan có thẩm quyền tiến hành tố tụng phải chỉ định người bào chữa cho người dưới 18 tuổi."),
    ("q34", "paraphrase", "Tàu chở hàng gặp bão làm hỏng hết hàng thì hãng tàu có phải bồi thường không?",
     [(HH, 151)], "Người vận chuyển được miễn hoàn toàn trách nhiệm khi tổn thất do thiên tai, thảm họa hoặc tai nạn hàng hải."),
    ("q35", "paraphrase", "Tàu nước ngoài có được chở hàng từ Hải Phòng vào TP.HCM không?",
     [(HH, 8)], "Về nguyên tắc không: hàng vận chuyển nội địa bằng đường biển phải chở bằng tàu biển Việt Nam, trừ các trường hợp ngoại lệ ở khoản 2."),
    ("q36", "paraphrase", "Đi kiện mà bị tòa bác đơn thì có phải trả tiền án phí không?",
     [(TTDS, 147)], "Có: đương sự phải chịu án phí sơ thẩm nếu yêu cầu không được Tòa án chấp nhận, trừ trường hợp được miễn."),
    # --- multi ---
    ("q37", "multi", "Công ty bắt tôi làm thêm 60 giờ trong một tháng, toàn vào Chủ nhật là ngày nghỉ hằng tuần. Như vậy có đúng luật không và tiền làm thêm phải trả ít nhất bao nhiêu?",
     [(LD, 107), (LD, 98)],
     "Không đúng: làm thêm không quá 40 giờ/tháng (Điều 107). Tiền làm thêm vào ngày nghỉ hằng tuần ít nhất 200% (Điều 98)."),
    ("q38", "multi", "Một người lừa đảo chiếm đoạt 100 triệu đồng cách đây 8 năm, không có tình tiết tăng nặng khác. Đến nay họ còn bị truy cứu trách nhiệm hình sự không?",
     [(HS, 174), (HS, 9), (HS, 27)],
     "Còn: 100 triệu thuộc khoản 2 Điều 174 (02-07 năm tù) là tội nghiêm trọng (Điều 9), thời hiệu truy cứu 10 năm (Điều 27) nên sau 8 năm vẫn còn."),
    ("q39", "multi", "Cậu con trai 16 tuổi tự lập di chúc để toàn bộ tài sản cho bạn thân mà không hỏi bố mẹ, rồi qua đời. Tài sản của cậu sẽ được chia cho ai?",
     [(DS, 625), (DS, 650), (DS, 651)],
     "Di chúc của người 15-18 tuổi cần cha mẹ đồng ý (Điều 625) nên không hợp pháp; khi đó áp dụng thừa kế theo pháp luật (Điều 650): hàng thứ nhất là cha, mẹ (Điều 651)."),
    ("q40", "multi", "Hàng hóa gửi theo tàu biển bị mất, 2 năm sau chủ hàng mới khởi kiện và viện dẫn thời hiệu 3 năm về hợp đồng của Bộ luật Dân sự. Chủ hàng còn kiện được không?",
     [(HH, 169), (DS, 4), (DS, 429)],
     "Không: BLDS là luật chung, chỉ áp dụng khi luật chuyên ngành không quy định (Điều 4); Bộ luật Hàng hải quy định thời hiệu về mất mát hàng hóa là 01 năm (Điều 169), nên không áp dụng mức 03 năm của Điều 429."),
    # ===== Đợt 3 (q41-q100): 24 lookup, 24 paraphrase, 12 câu khó (multi, có hard_kind) =====
    # --- lookup: 4 câu mỗi bộ luật ---
    ("q41", "lookup", "Người lao động làm việc từ 06 giờ trở lên trong một ngày được nghỉ giữa giờ ít nhất bao nhiêu phút?",
     [(LD, 109)], "Ít nhất 30 phút liên tục; làm việc ban đêm thì ít nhất 45 phút liên tục."),
    ("q42", "lookup", "Mỗi tuần người lao động được nghỉ ít nhất bao nhiêu giờ liên tục?",
     [(LD, 111)], "Ít nhất 24 giờ liên tục."),
    ("q43", "lookup", "Giờ làm việc ban đêm được tính từ mấy giờ đến mấy giờ?",
     [(LD, 106)], "Từ 22 giờ đến 06 giờ sáng ngày hôm sau."),
    ("q44", "lookup", "Hợp đồng lao động xác định thời hạn có thời hạn tối đa bao nhiêu tháng?",
     [(LD, 20)], "Không quá 36 tháng kể từ thời điểm có hiệu lực của hợp đồng."),
    ("q45", "lookup", "Người chưa thành niên là người chưa đủ bao nhiêu tuổi?",
     [(DS, 21)], "Người chưa đủ mười tám tuổi."),
    ("q46", "lookup", "Giao dịch dân sự có hiệu lực khi có đủ những điều kiện nào?",
     [(DS, 117)], "Chủ thể có năng lực pháp luật và năng lực hành vi phù hợp; hoàn toàn tự nguyện; mục đích, nội dung không vi phạm điều cấm của luật, không trái đạo đức xã hội; hình thức đúng quy định nếu luật có quy định."),
    ("q47", "lookup", "Di chúc phải được lập dưới hình thức nào?",
     [(DS, 627)], "Phải lập thành văn bản; nếu không thể lập bằng văn bản thì có thể di chúc miệng."),
    ("q48", "lookup", "Thừa kế thế vị được áp dụng trong trường hợp nào?",
     [(DS, 652)], "Khi con của người để lại di sản chết trước hoặc cùng thời điểm với người để lại di sản thì cháu được hưởng phần di sản mà cha hoặc mẹ của cháu được hưởng nếu còn sống."),
    ("q49", "lookup", "Tù có thời hạn đối với người phạm một tội có mức tối thiểu và tối đa là bao nhiêu?",
     [(HS, 38)], "Tối thiểu 03 tháng, tối đa 20 năm."),
    ("q50", "lookup", "Án treo được áp dụng khi xử phạt tù không quá bao nhiêu năm và thời gian thử thách là bao lâu?",
     [(HS, 65)], "Phạt tù không quá 03 năm; thời gian thử thách từ 01 năm đến 05 năm."),
    ("q51", "lookup", "Không áp dụng hình phạt tử hình đối với những người nào?",
     [(HS, 40)], "Người dưới 18 tuổi khi phạm tội, phụ nữ có thai, phụ nữ đang nuôi con dưới 36 tháng tuổi, người đủ 75 tuổi trở lên khi phạm tội hoặc khi xét xử."),
    ("q52", "lookup", "Tội phạm là gì theo Bộ luật Hình sự?",
     [(HS, 8)], "Hành vi nguy hiểm cho xã hội được quy định trong Bộ luật hình sự, do người có năng lực trách nhiệm hình sự hoặc pháp nhân thương mại thực hiện một cách cố ý hoặc vô ý."),
    ("q53", "lookup", "Các biện pháp ngăn chặn trong tố tụng hình sự gồm những biện pháp nào?",
     [(TTHS, 109)], "Giữ người trong trường hợp khẩn cấp, bắt, tạm giữ, tạm giam, bảo lĩnh, đặt tiền để bảo đảm, cấm đi khỏi nơi cư trú, tạm hoãn xuất cảnh."),
    ("q54", "lookup", "Thời hạn điều tra vụ án hình sự đối với tội phạm nghiêm trọng là bao lâu?",
     [(TTHS, 172)], "Không quá 03 tháng (ít nghiêm trọng 02 tháng, rất nghiêm trọng và đặc biệt nghiêm trọng 04 tháng)."),
    ("q55", "lookup", "Viện kiểm sát phải quyết định việc truy tố trong thời hạn bao lâu đối với tội phạm rất nghiêm trọng?",
     [(TTHS, 240)], "30 ngày kể từ ngày nhận hồ sơ vụ án và bản kết luận điều tra (ít nghiêm trọng và nghiêm trọng là 20 ngày)."),
    ("q56", "lookup", "Thời hạn kháng nghị của Viện kiểm sát cùng cấp đối với bản án hình sự sơ thẩm là bao nhiêu ngày?",
     [(TTHS, 337)], "15 ngày; Viện kiểm sát cấp trên trực tiếp là 30 ngày, kể từ ngày tuyên án."),
    ("q57", "lookup", "Người khởi kiện vụ án dân sự phải nộp tiền tạm ứng án phí trong thời hạn bao nhiêu ngày?",
     [(TTDS, 195)], "07 ngày kể từ ngày nhận được giấy báo của Tòa án về việc nộp tiền tạm ứng án phí."),
    ("q58", "lookup", "Tòa án giải quyết vụ án dân sự theo thủ tục rút gọn khi có đủ những điều kiện nào?",
     [(TTDS, 317)], "Tình tiết đơn giản, quan hệ pháp luật rõ ràng, đương sự đã thừa nhận nghĩa vụ, chứng cứ đầy đủ; các đương sự có địa chỉ rõ ràng; không có đương sự cư trú hoặc tài sản tranh chấp ở nước ngoài (trừ trường hợp luật định)."),
    ("q59", "lookup", "Tòa án nhân dân cấp huyện có thẩm quyền giải quyết theo thủ tục sơ thẩm những tranh chấp nào?",
     [(TTDS, 35)], "Tranh chấp dân sự, hôn nhân và gia đình (Điều 26, 28, trừ khoản 7 Điều 26), kinh doanh thương mại và lao động theo quy định của Điều này."),
    ("q60", "lookup", "Tòa án có tự áp dụng thời hiệu khởi kiện trong vụ án dân sự không?",
     [(TTDS, 184)], "Không: Tòa án chỉ áp dụng thời hiệu theo yêu cầu của một bên hoặc các bên, đưa ra trước khi Tòa án cấp sơ thẩm ra bản án, quyết định giải quyết vụ việc."),
    ("q61", "lookup", "Tàu biển theo Bộ luật Hàng hải được định nghĩa như thế nào?",
     [(HH, 13)], "Phương tiện nổi di động chuyên dùng hoạt động trên biển; không bao gồm tàu quân sự, tàu công vụ, tàu cá, phương tiện thủy nội địa, tàu ngầm, tàu lặn, thủy phi cơ, kho chứa nổi, giàn di động, ụ nổi."),
    ("q62", "lookup", "Chủ tàu là ai theo Bộ luật Hàng hải?",
     [(HH, 15)], "Chủ tàu là người sở hữu tàu biển."),
    ("q63", "lookup", "Người vận chuyển có nghĩa vụ ký phát vận đơn cho ai?",
     [(HH, 159)], "Theo yêu cầu của người giao hàng, người vận chuyển ký phát cho người giao hàng một bộ vận đơn."),
    ("q64", "lookup", "Tổn thất chung được phân bổ theo nguyên tắc nào?",
     [(HH, 293)], "Phân bổ theo tỷ lệ trên cơ sở giá trị phần tổn thất và phần cứu được tại thời điểm và nơi tàu kết thúc hành trình ngay sau khi xảy ra tổn thất chung."),
    # --- paraphrase: 4 câu mỗi bộ luật ---
    ("q65", "paraphrase", "Tôi đang bầu tháng thứ 7 thì sếp có được bắt tôi làm ca đêm hay tăng ca không?",
     [(LD, 137)], "Không: người sử dụng lao động không được sử dụng lao động nữ mang thai từ tháng thứ 07 làm việc ban đêm, làm thêm giờ, đi công tác xa."),
    ("q66", "paraphrase", "Nghỉ việc rồi thì công ty phải trả hết tiền lương, các khoản cho tôi trong bao lâu?",
     [(LD, 48)], "Trong 14 ngày làm việc kể từ ngày chấm dứt hợp đồng (một số trường hợp đặc biệt có thể kéo dài)."),
    ("q67", "paraphrase", "Thuê em bé 13 tuổi làm việc thì phải ký hợp đồng thế nào?",
     [(LD, 145)], "Phải giao kết hợp đồng lao động bằng văn bản với người chưa đủ 15 tuổi và người đại diện theo pháp luật của người đó; bố trí giờ làm không ảnh hưởng thời gian học tập."),
    ("q68", "paraphrase", "Nhân viên nghỉ không phép mấy ngày thì công ty được đuổi việc?",
     [(LD, 125)], "Tự ý bỏ việc 05 ngày cộng dồn trong 30 ngày hoặc 20 ngày cộng dồn trong 365 ngày mà không có lý do chính đáng thì có thể bị sa thải."),
    ("q69", "paraphrase", "Nhặt được ví tiền ngoài đường mà không biết của ai thì phải làm gì?",
     [(DS, 230)], "Thông báo hoặc giao nộp cho UBND cấp xã hoặc công an cấp xã nơi gần nhất để thông báo công khai cho chủ sở hữu nhận lại."),
    ("q70", "paraphrase", "Chó nhà hàng xóm cắn con tôi thì ai phải đền?",
     [(DS, 603)], "Chủ sở hữu súc vật phải bồi thường; người đang chiếm hữu, sử dụng súc vật bồi thường trong thời gian chiếm hữu, sử dụng."),
    ("q71", "paraphrase", "Người ta nợ tiền tôi mà trả trễ thì tôi có được đòi thêm tiền lãi không?",
     [(DS, 357)], "Có: bên chậm trả tiền phải trả lãi trên số tiền chậm trả tương ứng thời gian chậm trả, lãi suất theo thỏa thuận nhưng không vượt mức khoản 1 Điều 468."),
    ("q72", "paraphrase", "Bị người khác đánh phải nằm viện thì được đòi bồi thường những khoản gì?",
     [(DS, 590)], "Chi phí cứu chữa, bồi dưỡng, phục hồi sức khỏe; thu nhập thực tế bị mất hoặc giảm; chi phí và thu nhập bị mất của người chăm sóc; và tiền bù đắp tổn thất tinh thần."),
    ("q73", "paraphrase", "Đánh bạc thua được 10 triệu thì có bị đi tù không?",
     [(HS, 321)], "Có thể: đánh bạc trái phép trị giá từ 5 triệu đến dưới 50 triệu đồng bị phạt cải tạo không giam giữ đến 03 năm hoặc phạt tù từ 06 tháng đến 03 năm."),
    ("q74", "paraphrase", "Đánh nhau làm người ta bị thương 15% thì bị xử thế nào?",
     [(HS, 134)], "Tội cố ý gây thương tích: tỷ lệ tổn thương 11%-30% bị phạt cải tạo không giam giữ đến 03 năm hoặc phạt tù từ 06 tháng đến 03 năm."),
    ("q75", "paraphrase", "Dùng dao dọa người đi đường để lấy điện thoại thì bị phạt tù bao nhiêu năm?",
     [(HS, 168)], "Tội cướp tài sản: phạt tù từ 03 năm đến 10 năm (khoản 1), cao hơn nếu có tình tiết tăng nặng."),
    ("q76", "paraphrase", "Kế toán công ty nhà nước lấy 50 triệu tiền quỹ mình quản lý thì phạm tội gì, đi tù bao lâu?",
     [(HS, 353)], "Tội tham ô tài sản: chiếm đoạt từ 2 triệu đến dưới 100 triệu đồng bị phạt tù từ 02 năm đến 07 năm."),
    ("q77", "paraphrase", "Người nhà có thể đứng ra bảo lãnh cho bị can được tại ngoại không?",
     [(TTHS, 121)], "Có: bảo lĩnh là biện pháp thay thế tạm giam; cá nhân đủ 18 tuổi, nhân thân tốt, thu nhập ổn định có thể nhận bảo lĩnh cho bị can, bị cáo là người thân thích."),
    ("q78", "paraphrase", "Biết có người sắp gây ra một tội rất nghiêm trọng thì công an có được giữ người đó trước không?",
     [(TTHS, 110)], "Được: giữ người trong trường hợp khẩn cấp khi có đủ căn cứ xác định người đó đang chuẩn bị thực hiện tội phạm rất nghiêm trọng hoặc đặc biệt nghiêm trọng."),
    ("q79", "paraphrase", "Nạn nhân trong vụ án hình sự có được kháng cáo bản án không?",
     [(TTHS, 331)], "Có: bị cáo, bị hại và người đại diện của họ có quyền kháng cáo bản án, quyết định sơ thẩm."),
    ("q80", "paraphrase", "Có thể nộp tiền để được tại ngoại thay vì bị tạm giam không?",
     [(TTHS, 122)], "Có: đặt tiền để bảo đảm là biện pháp ngăn chặn thay thế tạm giam, cơ quan có thẩm quyền quyết định căn cứ tính chất hành vi, nhân thân, tài sản của bị can, bị cáo."),
    ("q81", "paraphrase", "Đi kiện thì ai phải đưa ra bằng chứng, tôi hay bên bị kiện?",
     [(TTDS, 91)], "Đương sự có yêu cầu phải cung cấp tài liệu, chứng cứ chứng minh yêu cầu của mình là có căn cứ (trừ một số trường hợp, vd. người tiêu dùng không phải chứng minh lỗi của bên kinh doanh)."),
    ("q82", "paraphrase", "Tòa gọi lần thứ hai mà người đi kiện vẫn không đến thì vụ kiện thế nào?",
     [(TTDS, 227)], "Nguyên đơn vắng mặt lần thứ hai không có người đại diện thì bị coi là từ bỏ việc khởi kiện, Tòa án đình chỉ giải quyết yêu cầu khởi kiện (trừ khi có đơn xin xét xử vắng mặt)."),
    ("q83", "paraphrase", "Trước khi xử, tòa có cho hai bên ngồi thương lượng với nhau không?",
     [(TTDS, 205)], "Có: trong thời hạn chuẩn bị xét xử sơ thẩm, Tòa án tiến hành hòa giải, trừ vụ án không được hòa giải hoặc không tiến hành hòa giải được."),
    ("q84", "paraphrase", "Muốn kiện ra tòa thì có thể nói miệng hay bắt buộc phải viết đơn?",
     [(TTDS, 189)], "Phải làm đơn khởi kiện."),
    ("q85", "paraphrase", "Tàu gặp nạn trên biển thì thuyền trưởng phải báo cho ai?",
     [(HH, 58)], "Thông báo ngay cho cơ quan nhà nước có thẩm quyền và báo cáo tai nạn hàng hải theo quy định."),
    ("q86", "paraphrase", "Cứu được tàu bị nạn thì có được trả công không, gồm những khoản gì?",
     [(HH, 266)], "Có nếu cứu hộ mang lại kết quả có ích; tiền công gồm tiền trả công, chi phí cứu hộ, chi phí vận chuyển, bảo quản tài sản được cứu và tiền thưởng."),
    ("q87", "paraphrase", "Hai tàu đâm nhau vì sương mù mà không rõ lỗi của ai thì thiệt hại tính sao?",
     [(HH, 288)], "Đâm va do bất khả kháng, ngẫu nhiên hoặc không xác định được lỗi thì thiệt hại của tàu nào tàu đó chịu."),
    ("q88", "paraphrase", "Được tàu khác cứu sống thì tôi có phải trả tiền cho họ không?",
     [(HH, 270)], "Không: người được cứu tính mạng không phải trả tiền; người cứu được hưởng tiền thưởng hợp lý trong tiền công cứu hộ nếu liên quan cùng tai nạn có cứu hộ tài sản."),
    # --- câu khó (multi): 12 câu, 6 kiểu x 2 ---
    ("q89", "multi", "Tôi đang mang thai tháng thứ 8. Công ty có được bắt tôi làm thêm giờ không, và tôi được nghỉ thai sản tổng cộng bao lâu?",
     [(LD, 137), (LD, 139)],
     "Không được làm thêm giờ, làm đêm khi mang thai từ tháng thứ 07 (Điều 137). Nghỉ thai sản 06 tháng, trước sinh không quá 02 tháng (Điều 139).", "compose"),
    ("q90", "multi", "Sau khi nộp đơn khởi kiện dân sự, tòa thụ lý vụ án khi nào và trong bao lâu phải báo cho bên bị kiện biết?",
     [(TTDS, 195), (TTDS, 196)],
     "Tòa thụ lý khi người khởi kiện nộp biên lai tạm ứng án phí (nộp trong 07 ngày) (Điều 195); trong 03 ngày làm việc kể từ ngày thụ lý phải thông báo bằng văn bản cho bị đơn (Điều 196).", "compose"),
    ("q91", "multi", "Bị can lừa đảo chiếm đoạt 30 triệu đồng (lần đầu, không có tình tiết khác). Sau khi nhận hồ sơ, Viện kiểm sát có tối đa bao lâu để quyết định truy tố (chưa gia hạn)?",
     [(HS, 174), (HS, 9), (TTHS, 240)],
     "30 triệu thuộc khoản 1 Điều 174 (tối đa 03 năm tù) là tội ít nghiêm trọng (Điều 9 BLHS), nên thời hạn quyết định truy tố là 20 ngày (Điều 240 BLTTHS).", "bridge"),
    ("q92", "multi", "Con tôi 12 tuổi dắt chó của nhà đi dạo, chó cắn người qua đường. Ai phải bồi thường?",
     [(DS, 603), (DS, 586)],
     "Người chiếm hữu, sử dụng súc vật phải bồi thường (Điều 603); con dưới 15 tuổi gây thiệt hại thì cha, mẹ phải bồi thường toàn bộ (Điều 586).", "bridge"),
    ("q93", "multi", "Nhân viên nữ đang mang thai thường xuyên không hoàn thành công việc. Công ty có được đơn phương chấm dứt hợp đồng với chị ấy không?",
     [(LD, 36), (LD, 37)],
     "Không: dù thường xuyên không hoàn thành công việc là căn cứ đơn phương chấm dứt (Điều 36), người sử dụng lao động không được đơn phương chấm dứt với lao động nữ mang thai (Điều 37).", "exception"),
    ("q94", "multi", "Ông A lập di chúc để toàn bộ tài sản cho con trai cả. Vợ ông A và con út 10 tuổi có được hưởng gì không?",
     [(DS, 644), (DS, 651)],
     "Có: vợ và con chưa thành niên vẫn được hưởng hai phần ba suất của một người thừa kế theo pháp luật (Điều 644); suất tính theo hàng thừa kế thứ nhất gồm vợ, con (Điều 651).", "exception"),
    ("q95", "multi", "Lương của tôi tính theo giờ là 50.000 đồng. Hôm thứ Tư tôi làm 10 tiếng. Tiền làm thêm giờ hôm đó ít nhất là bao nhiêu?",
     [(LD, 105), (LD, 98)],
     "Giờ làm bình thường không quá 08 giờ/ngày (Điều 105) nên làm thêm 2 giờ; ngày thường trả ít nhất 150% (Điều 98): 2 x 50.000 x 150% = 150.000 đồng.", "numeric"),
    ("q96", "multi", "Tôi làm việc trong điều kiện bình thường cho một công ty được 11 năm. Mỗi năm tôi được nghỉ phép bao nhiêu ngày?",
     [(LD, 113), (LD, 114)],
     "12 ngày (Điều 113) cộng thêm 1 ngày cho mỗi đủ 5 năm làm việc (Điều 114): 11 năm được thêm 2 ngày, tổng 14 ngày.", "numeric"),
    ("q97", "multi", "Thời hạn kháng cáo bản án sơ thẩm trong vụ án hình sự và trong vụ án dân sự có giống nhau không?",
     [(TTHS, 333), (TTDS, 273)],
     "Giống nhau: đều 15 ngày kể từ ngày tuyên án (Điều 333 BLTTHS, Điều 273 BLTTDS); người vắng mặt thì tính từ ngày nhận hoặc niêm yết bản án.", "comparison"),
    ("q98", "multi", "Thời hiệu khởi kiện ra Tòa đối với tranh chấp hợp đồng dân sự thông thường và tranh chấp lao động cá nhân khác nhau thế nào?",
     [(DS, 429), (LD, 190)],
     "Tranh chấp hợp đồng dân sự: 03 năm (Điều 429 BLDS); tranh chấp lao động cá nhân yêu cầu Tòa án: 01 năm (Điều 190 BLLĐ).", "comparison"),
    ("q99", "multi", "Công ty cho tôi thử việc lần hai cho cùng vị trí với lương bằng 70% lương chính thức, họ bảo luật cho phép. Có đúng không?",
     [(LD, 25), (LD, 26)],
     "Không đúng: chỉ được thử việc một lần đối với một công việc (Điều 25), và lương thử việc ít nhất phải bằng 85% mức lương của công việc đó (Điều 26).", "false_premise"),
    ("q100", "multi", "Con tôi 17 tuổi đã là người thành niên nên được tự lập di chúc mà không cần hỏi ai, đúng không?",
     [(DS, 20), (DS, 625)],
     "Không đúng: người thành niên là người từ đủ 18 tuổi (Điều 20); người từ đủ 15 đến chưa đủ 18 tuổi chỉ được lập di chúc nếu cha, mẹ hoặc người giám hộ đồng ý (Điều 625).", "false_premise"),
]

# Kiểu câu khó cho 8 câu multi của đợt 1-2 (đợt 3 ghi trực tiếp trong tuple)
HARD_KIND = {
    "q17": "bridge", "q18": "compose", "q19": "compose", "q20": "bridge",
    "q37": "compose", "q38": "bridge", "q39": "bridge", "q40": "conflict",
}


def main() -> None:
    s = Settings.load()
    store = ChunkStore(s.chunks_path)
    chunks = store.all()
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "evals/team-4.2/datasets/benchmark_6_bo_luat.jsonl")
    with out.open("w", encoding="utf-8") as f:
        for qid, typ, question, arts, ref, *rest in Q:
            hard_kind = rest[0] if rest else HARD_KIND.get(qid)
            assert (typ == "multi") == (hard_kind is not None), (qid, typ, hard_kind)
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
            row = {"id": qid, "question": question, "type": typ, "author": "claude",
                   "gold": gold, "reference": ref, "gold_articles": labels, "gold_chunk_ids": ids}
            if hard_kind:
                row["hard_kind"] = hard_kind
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("wrote", len(Q), "questions ->", out)


if __name__ == "__main__":
    main()
