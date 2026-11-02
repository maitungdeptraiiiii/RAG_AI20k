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
]


def main() -> None:
    s = Settings.load()
    store = ChunkStore(s.chunks_path)
    chunks = store.all()
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "evals/team-4.2/datasets/benchmark_6_bo_luat.jsonl")
    with out.open("w", encoding="utf-8") as f:
        for qid, typ, question, arts, ref in Q:
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
            f.write(json.dumps({"id": qid, "question": question, "type": typ, "author": "claude",
                                "gold": gold, "reference": ref, "gold_articles": labels,
                                "gold_chunk_ids": ids}, ensure_ascii=False) + "\n")
    print("wrote", len(Q), "questions ->", out)


if __name__ == "__main__":
    main()
