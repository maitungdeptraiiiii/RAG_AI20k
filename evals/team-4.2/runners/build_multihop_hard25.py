"""Author a separate corpus-grounded challenge set; never derive questions from old evals.

Run from repository root. Old questions are read ONLY by the subsequent novelty audit.
Every tuple links (source alias, article number, necessary reasoning step).
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path('evals/team-4.2')
OUT = ROOT / 'datasets/benchmark_multihop_hard25.jsonl'
CORPUS = Path('data/team-4.2/jina/processed/chunks.jsonl')
SOURCES = {k: f'bo_luat_{v}_{2019 if k == "ld" else 2015}.txt' for k, v in {
    'ds': 'dan_su', 'ttds': 'to_tung_dan_su', 'ld': 'lao_dong',
    'hs': 'hinh_su', 'tths': 'to_tung_hinh_su', 'hh': 'hang_hai'}.items()}

# Entirely new fact patterns, authored before retrieval. References are conditional,
# limited to the repository snapshot rather than a claim about law currently in force.
CASES = [
('nguoi_bi_tuyen_chet_tro_ve',
 'tôi đi biệt tích lâu quá nên tòa đã tuyên là chết, giờ về mới biết người nhận thừa kế biết tôi còn sống nhưng cố tình giấu tin để hưởng tài sản và tiền cho thuê căn kho; tôi phải xin tòa xử lý quyết định cũ thế nào rồi đòi lại kho và khoản tiền đó ra sao?',
 [('ttds',394,'Xác định người trở về có quyền yêu cầu hủy quyết định tuyên chết.'),('ds',73,'Xác định quyền đòi tài sản và hoa lợi khi người nhận biết người bị tuyên chết còn sống.'),('ttds',395,'Nối việc hủy quyết định tuyên chết với giải quyết hậu quả tài sản.')],
 'Phải yêu cầu hủy quyết định tuyên chết; quyết định hủy giải quyết cả hậu quả pháp lý. Người trở về được yêu cầu hoàn trả tài sản còn lại; người thừa kế biết người đó còn sống mà cố tình giấu để hưởng thừa kế phải hoàn trả toàn bộ tài sản đã nhận, kể cả hoa lợi, lợi tức và bồi thường nếu gây thiệt hại.'),
('giam_ho_tu_mua_tai_san',
 'cậu tôi là người giám hộ của chị bị mất năng lực hành vi, tự ký bán bộ máy làm nghề của chị cho chính mình rồi lại đòi đứng ra đại diện chị khi gia đình kiện; giao dịch ấy có được giữ không, máy và tiền xử lý sao, ai có thể đại diện khi hai bên đang đối đầu?',
 [('ds',59,'Nhận diện giao dịch giữa người giám hộ với người được giám hộ và ngoại lệ vì lợi ích, có giám sát đồng ý.'),('ds',131,'Suy ra hoàn trả tài sản khi giao dịch vô hiệu.'),('ttds',87,'Loại người đại diện có lợi ích đối lập trong cùng vụ việc.')],
 'Giao dịch liên quan tài sản giữa người giám hộ và người được giám hộ vô hiệu, trừ giao dịch vì lợi ích người được giám hộ và có sự đồng ý của người giám sát. Nếu vô hiệu, các bên hoàn trả những gì đã nhận, bên có lỗi bồi thường. Người giám hộ có lợi ích đối lập không được đại diện trong vụ việc này.'),
('vuot_uy_quyen_mua_may',
 'tôi chỉ ủy quyền cho quản lý mua máy tối đa 200 triệu, anh ấy ký 350 triệu; tôi biết việc rồi phản đối ngay, bên bán nói tôi đã đồng ý qua điện thoại nhưng chỉ có một đoạn ghi âm không rõ người nói; phần vượt có buộc tôi trả không và ra tòa bên nào phải đưa chứng cứ cho chuyện đồng ý ấy?',
 [('ds',143,'Kiểm tra phần vượt và ngoại lệ công nhận, biết mà không phản đối hoặc lỗi làm đối tác không biết.'),('ttds',91,'Gắn người viện dẫn việc chấp nhận với nghĩa vụ chứng minh.'),('ttds',94,'Phân loại bản ghi âm là nguồn chứng cứ, không tự coi lời khẳng định là sự thật.')],
 'Phần vượt không mặc nhiên ràng buộc người được đại diện; phải kiểm tra các ngoại lệ tại Điều 143. Bên viện dẫn việc chấp nhận phải cung cấp chứng cứ theo nghĩa vụ chứng minh; ghi âm là một nguồn chứng cứ cần được đánh giá, không tự đủ để kết luận đã đồng ý.'),
('tang_cho_gia_tao_tron_nghia_vu',
 'bên phải trả tiền mua nguyên liệu cho tôi làm giấy tặng toàn bộ máy xưởng cho em ruột nhưng vẫn tự dùng máy, họ còn rao bán tiếp; nếu giấy tặng chỉ để né nghĩa vụ thì tôi xin xử lý giao dịch, lấy lại hiện trạng và ngăn họ tẩu tán máy trong lúc kiện bằng cách nào?',
 [('ds',124,'Nhận diện giả tạo nhằm trốn nghĩa vụ với người thứ ba.'),('ds',131,'Nối vô hiệu với khôi phục tình trạng ban đầu, hoàn trả.'),('ttds',126,'Xác định điều kiện phong tỏa tài sản của người có nghĩa vụ khi có nguy cơ tẩu tán.')],
 'Giao dịch giả tạo để trốn tránh nghĩa vụ với người thứ ba bị vô hiệu; hậu quả là khôi phục tình trạng ban đầu, hoàn trả. Có thể yêu cầu phong tỏa tài sản người có nghĩa vụ nếu có căn cứ cho thấy họ có tài sản và biện pháp cần thiết để bảo đảm giải quyết hoặc thi hành án; việc rao bán là dữ kiện cần xem xét, không tự động chấp nhận chỉ vì có tranh chấp.'),
('nguoi_mua_ngay_tinh_do_bi_mat_cap',
 'máy ảnh của tôi bị lấy trộm rồi bán qua hai người, người đang giữ đưa hóa đơn mua đồ cũ và bảo mua ngay tình nên tôi hết quyền đòi; máy không phải loại đăng ký sở hữu, vậy tôi có đòi chính cái máy từ họ được không và khi kiện phải chứng minh những chuyện gì?',
 [('ds',166,'Xác lập quyền chủ sở hữu đòi lại tài sản.'),('ds',167,'Phân biệt mua có đền bù với ngoại lệ tài sản bị lấy cắp, mất, ngoài ý chí chủ.'),('ttds',91,'Nối điều kiện đòi tài sản với chứng cứ sở hữu và nguồn gốc mất máy.')],
 'Chủ sở hữu có quyền đòi lại tài sản theo luật. Với động sản không phải đăng ký, dù người giữ mua có đền bù và ngay tình, tài sản bị lấy cắp vẫn thuộc ngoại lệ cho phép đòi lại. Người kiện cần chứng minh quyền của mình, đặc điểm nhận dạng máy và việc máy bị lấy cắp; hóa đơn mua đồ cũ không tự loại trừ quyền đó.'),
('chuyen_quyen_yeu_cau_khong_thong_bao',
 'xưởng tôi còn nợ tiền vải, chủ hàng âm thầm chuyển quyền thu tiền cho người khác mà không báo; tôi đã thanh toán đủ cho chủ cũ, giờ người mới kiện đòi lần nữa, tôi dùng việc đã trả và chuyện không được báo để chống yêu cầu đó thế nào, phải lưu giấy tờ gì?',
 [('ds',365,'Xác định chuyển giao quyền yêu cầu và nghĩa vụ thông báo bằng văn bản.'),('ds',369,'Nối thiếu thông báo, đã trả người cũ với quyền từ chối người thế quyền.'),('ttds',91,'Xác định chứng cứ thanh toán và thông báo cần xuất trình.')],
 'Chuyển giao quyền yêu cầu không cần bên có nghĩa vụ đồng ý nhưng phải thông báo bằng văn bản, trừ thỏa thuận khác. Nếu vì không được thông báo mà đã thực hiện nghĩa vụ với người chuyển giao, người thế quyền không được yêu cầu thực hiện lại. Cần chứng minh việc thanh toán, thời điểm và thông tin thông báo liên quan.'),
('bao_lanh_tra_thay_truoc_han',
 'tôi bảo lãnh khoản tiền mua thiết bị cho bạn, giấy chỉ nói trả thay khi bạn đến hạn không trả; bên bán đòi tôi trước hạn nên tôi chưa trả, sau đó đến hạn bạn không trả thì tôi đã trả thay đủ; giờ tôi đòi bạn khoản nào và nếu kiện thì phải chứng minh hai mốc đó ra sao?',
 [('ds',335,'Xác định phạm vi cam kết bảo lãnh và điều kiện thực hiện.'),('ds',339,'Phân biệt đòi bên bảo lãnh trước hạn với khi bên được bảo lãnh không thực hiện.'),('ds',340,'Nối thực hiện thay với quyền yêu cầu hoàn trả trong phạm vi đã thực hiện.'),('ttds',91,'Gắn quyền truy hoàn với giấy bảo lãnh, hạn nghĩa vụ, chứng từ trả thay.')],
 'Không phải thực hiện bảo lãnh khi nghĩa vụ chưa đến hạn. Sau khi thực hiện nghĩa vụ bảo lãnh, có quyền yêu cầu người được bảo lãnh thực hiện nghĩa vụ đối với mình trong phạm vi đã trả thay, trừ thỏa thuận khác. Phải chứng minh cam kết, ngày đến hạn và số tiền thực trả thay.'),
('thoi_hieu_dich_vu_thua_nhan_lai',
 'tôi đòi tiền thiết kế đã quá ba năm từ ngày khách không thanh toán, nhưng sáu tháng trước họ ký xác nhận còn thiếu và trả một phần; giờ họ yêu cầu tòa áp dụng hết thời hiệu, tòa phải nối ngày xác nhận với hạn kiện và thời điểm họ nêu yêu cầu thế nào?',
 [('ds',429,'Xác định thời hiệu tranh chấp hợp đồng từ lúc biết hoặc phải biết quyền bị xâm phạm.'),('ds',157,'Kiểm tra thừa nhận hoặc trả một phần làm thời hiệu bắt đầu lại từ ngày tiếp theo.'),('ttds',184,'Xác định chỉ áp dụng thời hiệu theo yêu cầu trước bản án, quyết định sơ thẩm.')],
 'Mốc ba năm của tranh chấp hợp đồng phải được xem cùng việc bắt đầu lại thời hiệu khi bên có nghĩa vụ thừa nhận hoặc thực hiện một phần nghĩa vụ; thời hiệu mới tính từ ngày tiếp theo. Tòa chỉ áp dụng thời hiệu nếu có yêu cầu hợp lệ trước khi ra bản án hoặc quyết định sơ thẩm; cần kiểm tra chứng cứ và các mốc cụ thể.'),
('ban_phan_so_huu_chung_khong_bao',
 'tôi với bạn góp tiền mua chung một máy in công nghiệp theo phần, bạn lén bán phần của mình cho người ngoài mà không cho tôi cơ hội mua, tôi mới biết được một tháng và người mua đang rao bán tiếp phần ấy; tôi còn cách yêu cầu thay người mua và giữ phần máy đang tranh chấp đến lúc tòa xử không?',
 [('ds',218,'Nối quyền ưu tiên mua với thời hạn ba tháng từ khi phát hiện vi phạm và yêu cầu chuyển quyền, nghĩa vụ người mua.'),('ttds',121,'Nối nguy cơ chuyển tiếp quyền với cấm chuyển dịch quyền tài sản đang tranh chấp.'),('ttds',136,'Kiểm tra nghĩa vụ thực hiện biện pháp bảo đảm khi yêu cầu cấm chuyển dịch quyền.')],
 'Chủ sở hữu chung theo phần có quyền ưu tiên mua; nếu vi phạm, trong ba tháng từ ngày phát hiện có thể yêu cầu tòa chuyển quyền và nghĩa vụ người mua cho mình. Khi có căn cứ người giữ tài sản đang chuyển dịch quyền, có thể yêu cầu cấm chuyển dịch quyền đối với tài sản đang tranh chấp và phải thực hiện biện pháp bảo đảm theo Điều 136. Cần xác định phần quyền và điều kiện giao dịch cụ thể.'),
('chuyen_nham_tien_sinh_loi_ngan_hang',
 'kế toán chuyển nhầm tiền công ty tôi vào tài khoản người lạ, họ biết nhầm nhưng đem gửi lấy lãi và không trả; tôi có thể đòi cả gốc lẫn phần lãi ấy không, nếu không tự lấy được sao kê thì nhờ tòa thu thập thế nào và có chặn tiền trong tài khoản lúc kiện được không?',
 [('ds',579,'Xác định được lợi không có căn cứ phải hoàn trả.'),('ds',581,'Nối biết không có căn cứ với hoàn trả hoa lợi, lợi tức.'),('ttds',106,'Xác định yêu cầu cung cấp chứng cứ và hỗ trợ của tòa khi không tự thu thập được.'),('ttds',124,'Xác định điều kiện phong tỏa tài khoản để bảo đảm giải quyết hoặc thi hành án.')],
 'Người được lợi không có căn cứ phải hoàn trả; người không ngay tình phải hoàn trả hoa lợi, lợi tức từ thời điểm chiếm hữu, sử dụng, được lợi không có căn cứ. Cần chứng cứ giao dịch và lợi tức thực tế; có thể yêu cầu tòa hỗ trợ thu thập khi đủ điều kiện và yêu cầu phong tỏa tài khoản khi có căn cứ luật định.'),
('gui_giu_hang_dung_sai_muc_dich',
 'tôi gửi mười máy pha cà phê cho kho giữ có trả phí, kho tự đem cho thuê rồi làm mất hai máy, họ đổ do bão nhưng không đưa chứng cứ; tôi ở Huế còn kho đặt trụ sở Đà Nẵng, muốn đòi máy và bồi thường thì dựa vào nghĩa vụ nào, ai phải làm rõ bất khả kháng và thường nộp đơn ở đâu?',
 [('ds',554,'Nhận diện quan hệ gửi giữ có nghĩa vụ bảo quản và hoàn trả.'),('ds',557,'Nối sử dụng trái phép, mất tài sản với trách nhiệm bồi thường và ngoại lệ bất khả kháng.'),('ttds',91,'Phân bổ nghĩa vụ chứng minh yêu cầu và phản đối.'),('ttds',39,'Nối bị đơn là tổ chức với thẩm quyền lãnh thổ theo trụ sở, xét ngoại lệ hoặc thỏa thuận hợp lệ.')],
 'Bên giữ phải bảo quản, trả tài sản và không được sử dụng nếu không được đồng ý; mất, hư hỏng phải bồi thường trừ bất khả kháng. Bên yêu cầu và bên phản đối phải chứng minh căn cứ tương ứng; không chỉ nói có bão là đủ. Theo quy tắc thông thường, tòa nơi bị đơn có trụ sở giải quyết, trừ thỏa thuận hoặc căn cứ thẩm quyền khác hợp lệ.'),
('so_suat_lam_hong_dung_cu',
 'tôi sơ suất làm hỏng dụng cụ của xưởng, thiệt hại không nghiêm trọng và dưới mười tháng lương tối thiểu vùng, công ty bắt đền nguyên giá máy mới dù dụng cụ đã cũ; nhà tôi đang khó khăn, biên bản định giá công ty giữ, mức đền phải nối lỗi, thiệt hại thực tế với hoàn cảnh của tôi thế nào và ai phải đưa chứng cứ?',
 [('ld',129,'Kiểm tra điều kiện sơ suất, thiệt hại không nghiêm trọng dưới ngưỡng và mức bồi thường tối đa ba tháng tiền lương.'),('ld',130,'Nối mức bồi thường với lỗi, thiệt hại thực tế, hoàn cảnh gia đình, nhân thân, tài sản.'),('ttds',91,'Xác định nghĩa vụ chứng minh và cung cấp biên bản định giá do công ty giữ.')],
 'Nếu đủ điều kiện sơ suất gây thiệt hại không nghiêm trọng với giá trị không quá mười tháng lương tối thiểu vùng thì mức bồi thường nhiều nhất ba tháng tiền lương theo Điều 129. Việc quyết định phải xét lỗi, thiệt hại thực tế và hoàn cảnh theo Điều 130; không tự lấy giá máy mới. Công ty phải chứng minh yêu cầu và cung cấp tài liệu mình quản lý theo Điều 91.'),
('hop_dong_het_han_lam_tiep',
 'tôi làm văn phòng theo hợp đồng một năm, hết hạn rồi vẫn làm thêm 45 ngày mà chưa ký gì mới, giờ hai bên cãi nhau hợp đồng đã thành không xác định thời hạn chưa; nếu tôi chỉ yêu cầu xác định loại hợp đồng thì phải đi hòa giải trước và tính hạn yêu cầu hòa giải, kiện từ đâu?',
 [('ld',20,'Nối làm tiếp quá ba mươi ngày với chuyển loại hợp đồng, kiểm tra trường hợp ngoại lệ.'),('ld',188,'Xác định tranh chấp về loại hợp đồng không đương nhiên thuộc ngoại lệ hòa giải.'),('ld',190,'Tách thời hiệu hòa giải sáu tháng và khởi kiện một năm từ khi phát hiện vi phạm.'),('ttds',32,'Nhận diện tranh chấp lao động cá nhân thuộc thẩm quyền tòa khi đủ điều kiện.')],
 'Thông thường sau ba mươi ngày tiếp tục làm mà không ký mới, hợp đồng xác định thời hạn chuyển thành không xác định thời hạn; cần loại trừ các trường hợp luật quy định riêng. Tranh chấp chỉ về loại hợp đồng thường phải hòa giải trước. Thời hiệu yêu cầu hòa giải là sáu tháng, yêu cầu tòa là một năm từ khi phát hiện hành vi bị cho là xâm phạm quyền, không tự lấy ngày hết hợp đồng cho mọi trường hợp.'),
('dieu_chuyen_vuot_60_ngay',
 'tôi được tuyển làm kế toán, xưởng chuyển sang đóng gói cộng dồn 70 ngày làm việc trong năm mà tôi không đồng ý bằng văn bản; tôi không nhận phần ngày vượt nên họ cho ngồi chờ không lương, tôi cần nối giới hạn điều chuyển với tiền ngừng việc ra sao, hồ sơ chấm công họ giữ thì ai phải đưa ra?',
 [('ld',29,'Xác định vượt sáu mươi ngày cần đồng ý bằng văn bản, từ chối dẫn đến ngừng việc thì dẫn chiếu Điều 99.'),('ld',99,'Tính lương ngừng việc theo nguyên nhân thay vì tự động bằng không.'),('ttds',91,'Nối chấm công, điều chuyển do người sử dụng lao động quản lý với nghĩa vụ cung cấp.')],
 'Điều chuyển quá sáu mươi ngày làm việc cộng dồn trong năm cần đồng ý bằng văn bản; nếu không đồng ý và phải ngừng việc thì áp dụng lương ngừng việc theo Điều 99, căn cứ nguyên nhân. Công ty phải cung cấp tài liệu chấm công, điều chuyển do mình quản lý khi người lao động không thể cung cấp theo quy định về chứng minh.'),
('tam_dinh_chi_khong_ky_luat',
 'kho bị thiếu hàng nên tôi bị tạm đình chỉ 20 ngày, lúc đó công ty ứng nửa lương; hết xác minh họ xác nhận tôi không vi phạm nhưng vẫn bắt trả tiền ứng và không thanh toán nửa còn lại, nếu tôi kiện đòi phần thiếu thì được tính thế nào, có phải hòa giải và công ty phải nộp hồ sơ xác minh không?',
 [('ld',128,'Nối kết quả không bị xử lý kỷ luật với trả đủ lương thời gian đình chỉ, không thu hồi khoản ứng.'),('ld',188,'Phân biệt đòi lương đình chỉ với tranh chấp sa thải được miễn hòa giải.'),('ttds',91,'Nối kết quả xác minh, bảng lương do công ty giữ với nghĩa vụ cung cấp chứng cứ.')],
 'Nếu không bị xử lý kỷ luật thì phải trả đủ lương thời gian tạm đình chỉ; ngay cả khi bị kỷ luật cũng không phải hoàn lại khoản đã tạm ứng. Tranh chấp đòi lương này không tự thuộc ngoại lệ hòa giải dành cho sa thải. Cần hồ sơ đình chỉ, xác minh và bảng lương; công ty có nghĩa vụ cung cấp tài liệu mình quản lý theo luật.'),
('hop_dong_nguoi_ky_khong_du_quyen',
 'người ký hợp đồng tuyển tôi bên công ty hóa ra không có quyền ký, công ty muốn coi toàn bộ thời gian đã làm như không tồn tại để khỏi thanh toán; tôi có thể tự coi hợp đồng vô hiệu không, cơ quan nào tuyên và quyền lợi công việc đã làm xử lý thế nào?',
 [('ld',49,'Xác định người giao kết không đúng thẩm quyền là căn cứ vô hiệu toàn bộ.'),('ld',50,'Xác định tòa án có quyền tuyên hợp đồng vô hiệu.'),('ld',51,'Nối căn cứ ký sai thẩm quyền với quyền lợi trong thời gian thực hiện và ký lại.'),('ttds',401,'Xác định thủ tục yêu cầu tòa tuyên hợp đồng lao động vô hiệu.')],
 'Ký không đúng thẩm quyền có thể làm hợp đồng vô hiệu toàn bộ nhưng thẩm quyền tuyên thuộc tòa. Với trường hợp vô hiệu toàn bộ này, quyền và lợi ích người lao động được giải quyết theo pháp luật, đồng thời hai bên ký lại đúng thẩm quyền; không tự xóa quyền lợi của thời gian đã làm.'),
('co_cau_cat_giam_hang_loat',
 'xưởng thay dây chuyền tự động nên dự tính cho cả tổ nghỉ, không làm phương án sử dụng lao động hay xem có thể đào tạo lại, họ bảo chỉ cần trả trợ cấp là xong; việc cắt giảm phải qua những bước nào, trợ cấp mất việc gắn với thời gian làm ra sao và nếu tôi kiện riêng khoản trợ cấp thì có bắt buộc hòa giải không?',
 [('ld',42,'Kiểm tra nghĩa vụ khi thay đổi cơ cấu, công nghệ, đào tạo lại và thủ tục cho thôi việc.'),('ld',44,'Nối cắt giảm với nội dung và công khai phương án sử dụng lao động.'),('ld',47,'Xác định điều kiện, thời gian tính trợ cấp mất việc, loại thời gian bảo hiểm thất nghiệp.'),('ld',188,'Phân loại tranh chấp trợ cấp khi chấm dứt thuộc ngoại lệ hòa giải.'),('ttds',32,'Nối ngoại lệ hòa giải với thẩm quyền giải quyết tranh chấp lao động cá nhân của tòa.')],
 'Trả trợ cấp không thay nghĩa vụ lập phương án, xem xét đào tạo lại và các thủ tục theo Điều 42, 44. Người đủ điều kiện được trợ cấp mất việc theo Điều 47, thời gian tính phải trừ thời gian tham gia bảo hiểm thất nghiệp và thời gian đã được trả trợ cấp theo luật. Tranh chấp riêng về trợ cấp khi chấm dứt không bắt buộc qua hòa giải viên.'),
('dong_pham_hanh_vi_vuot_qua',
 'em tôi chỉ nhận canh cửa cho nhóm đột nhập phá một máy chủ, người trực tiếp vào lại tự ý làm thêm chuyện khác mà em không biết và không cùng ý định; nếu bị xử chung vụ thì phải tách phần vượt quá với vai trò canh cửa thế nào, tòa có được lấy tình tiết riêng của người kia áp hết cho em không?',
 [('hs',17,'Xác định cố ý cùng thực hiện và giới hạn trách nhiệm với hành vi vượt quá người thực hành.'),('hs',58,'Cá thể hóa vai trò và tình tiết riêng từng người đồng phạm.'),('tths',85,'Nối phạm vi cố ý, lỗi và tình tiết với những vấn đề phải chứng minh.')],
 'Canh cửa có thể là giúp sức nếu cố ý cùng thực hiện; không chịu trách nhiệm về hành vi vượt quá của người thực hành. Phải chứng minh lỗi và phạm vi tham gia, không chỉ dựa có mặt trong nhóm. Hình phạt xét vai trò từng người, tình tiết riêng của ai chỉ áp dụng cho người đó.'),
('tu_y_dung_hay_chua_dat',
 'tôi định đầu độc đàn cá của trại đối thủ, mới mang chai hóa chất đến bể thì tự thấy sai nên cất đi, không ai phát hiện hay cản; người cùng đi lại khai tôi chỉ dừng vì thấy bảo vệ, chưa con cá nào chết, hai cách dừng ấy ảnh hưởng trách nhiệm và cách xác minh ra sao?',
 [('hs',16,'Phân biệt tự nguyện chấm dứt khi không bị ngăn cản với dừng do trở ngại.'),('hs',15,'Xác định phạm tội chưa đạt cần đã cố ý thực hiện nhưng không đến cùng vì nguyên nhân ngoài ý muốn.'),('hs',57,'Nối phân loại giai đoạn với giới hạn quyết định hình phạt, không tự kết luận mới mang hóa chất đã là chưa đạt.'),('tths',85,'Chứng minh hành vi đã thực hiện, ý chí và nguyên nhân dừng trước khi phân loại.')],
 'Nếu thực sự tự mình dừng dù không bị ngăn cản, áp dụng Điều 16 đối với tội định phạm, vẫn xét tội khác nếu hành vi thực tế đủ cấu thành. Nếu dừng do bảo vệ, phải xác minh đã bắt đầu thực hiện tội phạm hay mới chuẩn bị; chỉ khi đủ điều kiện mới áp dụng chưa đạt và Điều 57. Chưa có cá chết không tự quyết định loại trách nhiệm.'),
('benh_tam_than_hai_thoi_diem',
 'anh tôi bị điều tra vì một hành vi lúc trước, nay bệnh nặng không nhận thức được; gia đình nói anh cũng đã mất khả năng nhận thức ngay lúc xảy ra việc nhưng chưa giám định, phải làm rõ hai thời điểm ấy thế nào để phân biệt không chịu trách nhiệm với chữa bệnh rồi còn bị xử?',
 [('hs',21,'Xác định mất năng lực tại thời điểm thực hiện hành vi.'),('hs',49,'Phân biệt bệnh lúc thực hiện hành vi với mắc bệnh trước kết án sau khi phạm tội có năng lực.'),('tths',206,'Nối nghi ngờ năng lực với bắt buộc trưng cầu giám định.'),('tths',447,'Nối kết luận chuyên môn với điều kiện, thẩm quyền bắt buộc chữa bệnh.')],
 'Phải giám định khi nghi ngờ năng lực trách nhiệm hình sự. Mất khả năng nhận thức hoặc điều khiển do bệnh ngay lúc hành vi thì xét Điều 21; nếu lúc hành vi còn năng lực mà trước kết án mới mắc bệnh đến mức đó, có thể chữa bệnh bắt buộc rồi sau khi khỏi vẫn chịu trách nhiệm. Quyết định phải theo kết luận giám định và đúng thẩm quyền.'),
('ho_so_gia_giao_dich_vo_hieu',
 'người bán đưa tôi giấy xác nhận của cơ quan nhưng hóa ra là giấy giả, tôi vì tin giấy đó mới mua cả lô thiết bị; nay công an điều tra chuyện làm giả, tôi muốn hủy giao dịch lấy lại tiền thì trách nhiệm hình sự, vô hiệu vì bị lừa và khoản hoàn trả có thể được xử lý chung hay phải tách thế nào?',
 [('hs',341,'Kiểm tra hành vi làm, sử dụng tài liệu giả và đủ dấu hiệu tội phạm, không suy từ giấy giả ra mọi người đều phạm tội.'),('ds',127,'Nối thông tin gian dối gây nhầm lẫn khi giao kết với yêu cầu vô hiệu.'),('ds',131,'Suy ra hoàn trả, khôi phục và bồi thường theo lỗi.'),('tths',30,'Nối vấn đề dân sự với vụ án hình sự, điều kiện tách nếu chưa chứng minh được và không ảnh hưởng giải quyết hình sự.')],
 'Phải xác minh người làm hoặc sử dụng giấy giả có đủ dấu hiệu Điều 341. Nếu bị lừa dối dẫn đến giao kết có thể yêu cầu vô hiệu, hoàn trả và bồi thường theo lỗi. Vấn đề dân sự được giải quyết cùng vụ án hình sự; có thể tách khi chưa có điều kiện chứng minh và việc tách không ảnh hưởng giải quyết vụ án hình sự.'),
('hang_lanh_gioi_han_boi_thuong',
 'tôi gửi hải sản bằng tàu biển, hãng biết kho lạnh hỏng mà vẫn nhận nên cả lô hỏng; vận đơn không khai giá, hãng đòi tính mức đền tối đa theo kiện, tôi phải nối nghĩa vụ chuẩn bị kho lạnh với điều kiện mất mức giới hạn ấy ra sao và ở tòa ai chứng minh việc họ biết trước?',
 [('hh',150,'Xác định nghĩa vụ mẫn cán bảo đảm hầm lạnh phù hợp trước, khi bắt đầu chuyến.'),('hh',152,'Xác định mức giới hạn khi không khai giá.'),('hh',153,'Nối cố ý hoặc cẩu thả mà biết khả năng tổn thất với mất quyền giới hạn, không chỉ dựa hàng hỏng.'),('ttds',91,'Gắn yêu cầu vượt giới hạn với chứng cứ về lỗi, nhận thức và thiệt hại.')],
 'Phải xét nghĩa vụ bảo đảm kho lạnh phù hợp; không khai giá thường dẫn đến giới hạn Điều 152. Muốn loại giới hạn phải chứng minh tổn thất do hành vi cố ý hoặc cẩu thả và biết tổn thất có thể xảy ra theo Điều 153; không chỉ chứng minh hàng đã hỏng. Nghĩa vụ chứng minh căn cứ đòi và phản đối theo Điều 91.'),
('van_don_theo_lenh_chuyen_tiep',
 'lô cà phê đi biển được bán lại cho tôi bằng vận đơn theo lệnh đã ký hậu, tôi giữ bản gốc nhưng người gửi cũ vẫn đòi hãng trả hàng cho họ; hãng nói ai cũng có bản chụp nên không biết giao ai, tư cách người nhận phải nối từ ký hậu đến xuất trình thế nào, nếu kiện cần dùng những giấy tờ gì?',
 [('hh',148,'Xác định chức năng vận đơn làm bằng chứng sở hữu, định đoạt và nhận hàng.'),('hh',162,'Xác định chuỗi ký hậu và người có quyền phát lệnh trả hàng cuối cùng.'),('hh',166,'Nối người nhận hợp pháp với xuất trình chứng từ gốc hợp lệ khi trả hàng.'),('ttds',94,'Nối vận đơn gốc và tài liệu giao dịch với nguồn chứng cứ khi tranh chấp.')],
 'Phải kiểm tra loại vận đơn và chuỗi ký hậu hợp lệ, người có quyền phát lệnh cuối cùng theo Điều 162; không chỉ có bản chụp là đủ. Người vận chuyển trả cho người nhận hợp pháp có bản gốc hoặc chứng từ hợp lệ theo Điều 166. Vận đơn và hồ sơ chuyển nhượng là nguồn chứng cứ để xác định quyền.'),
('cam_giu_hang_hai_va_the_chap',
 'tôi bán nhiên liệu cho tàu nhưng chưa được trả, nghe nói cứ là nợ liên quan tàu thì được ưu tiên hơn ngân hàng nhận thế chấp; tàu còn nợ phí cảng và tiền công thuyền bộ, làm sao phân loại khoản nào có quyền cầm giữ, thứ tự trả với thế chấp, và nếu kiện tôi phải chứng minh loại nợ gì?',
 [('hh',40,'Phân biệt quyền cầm giữ hàng hải với mọi khoản nợ tàu và ưu tiên trước thế chấp.'),('hh',41,'Đối chiếu danh mục khiếu nại làm phát sinh cầm giữ, không tự coi cung ứng nhiên liệu thuộc danh mục.'),('hh',42,'Xếp thứ tự các khiếu nại cầm giữ, xét ngoại lệ cứu hộ nếu có.'),('ttds',91,'Chứng minh bản chất khoản nợ, không chỉ tồn tại hóa đơn.')],
 'Không phải mọi nợ liên quan tàu đều có quyền cầm giữ. Phải đối chiếu Điều 41: tiền công thuyền bộ, phí cảng thuộc các nhóm nêu trong luật, nợ cung ứng nhiên liệu đơn thuần không tự thuộc danh mục đó. Các quyền cầm giữ được ưu tiên trước thế chấp và xếp theo Điều 42; người yêu cầu phải chứng minh bản chất, căn cứ khoản nợ.'),
('ton_that_chung_do_loi_hang_tau',
 'tàu chở hàng của tôi gặp hiểm họa do lỗi phía tàu, thuyền trưởng chủ động ném một phần hàng để cứu cả chuyến; họ vừa đòi tôi góp tổn thất chung vừa nói tôi không được đòi người gây lỗi, lại tính cả thời gian phân bổ vào hạn kiện, ba chuyện đó có phải đi cùng nhau như họ nói không?',
 [('hh',292,'Xác định hy sinh có ý thức, hợp lý vì an toàn chung và chỉ hậu quả trực tiếp.'),('hh',293,'Nối phân bổ dù hiểm họa do lỗi với bảo lưu quyền đòi người có lỗi.'),('hh',297,'Xác định hai năm và loại thời gian tiến hành phân bổ khỏi thời hiệu.'),('ttds',184,'Nối tính thời hiệu chuyên ngành với điều kiện tòa áp dụng thời hiệu theo yêu cầu.')],
 'Nếu đủ điều kiện tổn thất chung, vẫn phân bổ dù hiểm họa do lỗi phía tàu; phân bổ không loại trừ quyền đòi người có lỗi bồi thường. Thời hiệu về tổn thất chung là hai năm từ ngày xảy ra, không tính thời gian tiến hành phân bổ; cần phân biệt yêu cầu này với yêu cầu bồi thường khác. Tòa áp dụng thời hiệu theo yêu cầu đúng thời điểm luật định.'),
]


def main():
    chunks = [json.loads(x) for x in CORPUS.read_text(encoding='utf-8').splitlines() if x.strip()]
    rows = []
    for i, (topic, question, links, reference) in enumerate(CASES, 1):
        gold, ids, articles, steps, evidence = [], [], [], [], []
        for alias, number, why in links:
            source = SOURCES[alias]
            found = [c for c in chunks if c['source'] == source and
                     re.search(rf'Điều {number}\.', c['section'] or '')]
            sections = {c['section'] for c in found}
            assert len(sections) == 1, (topic, source, number, sections)
            section = sections.pop()
            gold.append({'source': source, 'section': section})
            ids.extend(c['chunk_id'] for c in found)
            articles.append(f'{source.removesuffix(".txt")} Điều {number}')
            steps.append({'gold_index': len(gold)-1, 'purpose': why})
            evidence.append({'source': source, 'section': section,
                             'chunk_ids': [c['chunk_id'] for c in found],
                             'text': '\n\n'.join(c['text'] for c in found)})
        rows.append({'id': f'mh25_{i:02}', 'question': question, 'type': 'multi',
                     'author': 'codex', 'style': 'colloquial_scenario', 'topic': topic,
                     'gold': gold, 'reference': reference, 'gold_articles': articles,
                     'gold_chunk_ids': list(dict.fromkeys(ids)), 'reasoning_steps': steps,
                     'corpus_scope': 'repository snapshot; not a current-law certification',
                     'evidence': evidence})
    assert len(rows) == 25
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows), encoding='utf-8')
    print(f'{OUT}: {len(rows)} questions, sha256={hashlib.sha256(OUT.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    main()
