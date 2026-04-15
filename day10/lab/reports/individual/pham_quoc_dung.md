# Báo cáo cá nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Phạm Quốc Dũng  
**Mã số sinh viên:** 2A202600490  
**Vai trò:** Quality & Grading Evidence Owner (D10-T03)  
**Ngày nộp:** 2026-04-15  
**Độ dài:** ~500 từ

---

## 1. Phụ trách

Tôi phụ trách task D10-T03 theo phân công nhóm, tập trung vào ba đầu việc: thiết kế expectation có phân tầng warn/halt, tạo evidence before/after cho retrieval, và xuất grading JSONL để phục vụ chấm điểm. Các file tôi sở hữu chính là `quality/expectations.py`, `eval_retrieval.py`, và `grading_run.py`. Tôi nhận dữ liệu cleaned từ nhánh cleaning và phối hợp với owner tích hợp để dùng collection `day10_kb` đã publish cho bước đánh giá.

Run chính dùng để chốt artifact là `dung-after-final`, có manifest xác nhận số liệu `raw_records=10`, `cleaned_records=4`, `quarantine_records=6`. Đây là nền để tôi đối chiếu hiệu quả của expectation và retrieval trước/sau. Bằng chứng code và artifact gắn với commit `babbce2` (nội dung: hoàn thiện evidence D10-T03 và harden luồng grading khi thiếu file câu hỏi mặc định).

---

## 2. Quyết định kỹ thuật

Quyết định quan trọng nhất của tôi là giữ ranh giới rõ giữa **halt** và **warn** trong expectation suite, thay vì gom toàn bộ về một mức cảnh báo. Những điều kiện có thể làm sai kiến thức trả lời hoặc gây publish dữ liệu lỗi được đặt ở mức halt, ví dụ: không còn refund window 14 ngày, định dạng `effective_date` phải ISO, và loại trừ bản HR cũ 10 ngày. Các tiêu chí chất lượng mềm hơn như độ dài tối thiểu của chunk được đặt warn để không chặn pipeline khi rủi ro thấp.

Cách tách này giúp pipeline dừng đúng điểm khi có lỗi nghiệp vụ nghiêm trọng, nhưng vẫn đảm bảo vận hành ổn định trong các trường hợp chỉ cần cảnh báo. Log run `dung-after-final` cho thấy expectation `refund_no_stale_14d_window` pass ở halt và `chunk_min_length_8` pass ở warn, đúng với chủ đích thiết kế.

---

## 3. Sự cố / anomaly

Sự cố lớn nhất tôi xử lý là lỗi vỡ luồng grading khi thiếu file `data/grading_questions.json`. Triệu chứng là `grading_run.py` dừng với `FileNotFoundError`, khiến nhóm không thể xuất JSONL dù index đã sẵn sàng. Tôi sửa bằng cách bổ sung cơ chế resolve đường dẫn câu hỏi: ưu tiên file grading chính thức, nếu thiếu thì fallback có kiểm soát sang `data/test_questions.json` và in cảnh báo rõ ràng.

Cách sửa này đảm bảo luồng chấm không bị đứt trong quá trình demo/kiểm thử nội bộ, đồng thời vẫn giữ hành vi CLI minh bạch. Sau thay đổi, file `artifacts/eval/dung_grading_run.jsonl` được tạo ổn định, gồm đầy đủ các khóa cần thiết (`id`, `contains_expected`, `hits_forbidden`, `top1_doc_matches`, ...), phục vụ kiểm tra và đối chiếu nhanh.

---

## 4. Before/after

Bằng chứng rõ nhất nằm ở câu `q_refund_window`.

- **Before** (`artifacts/eval/dung_before_bad_eval.csv`): top1 preview vẫn chứa “14 ngày làm việc”, đồng thời `hits_forbidden=yes`.
- **After** (`artifacts/eval/dung_after_final_eval.csv`): top1 preview đã về “7 ngày làm việc”, `hits_forbidden=no`.

Song song với đó, log của run cuối ghi `expectation[refund_no_stale_14d_window] OK (halt)` và pipeline kết thúc bằng `PIPELINE_OK`. Điều này chứng minh thay đổi có tác động thực tế, không chỉ thay đổi hình thức trong mã.

---

## 5. Cải tiến thêm 2 giờ

Nếu có thêm 2 giờ, tôi sẽ chuẩn hóa bộ câu `grading_questions.json` theo ID chính thức `gq_d10_01..gq_d10_03` và thêm bước validate schema JSONL trước khi ghi file. Mục tiêu là đồng bộ hoàn toàn với quick-check của giảng viên, giảm rủi ro mismatch ID khi chấm tự động và giúp release gate chặt chẽ hơn.
