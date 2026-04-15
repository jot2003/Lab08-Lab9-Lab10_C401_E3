# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Thành Nam  
**Mã số:** 2A202600205  
**Vai trò trong nhóm:** Monitoring & Docs Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài:** ~650 từ

---

## 1. Phần tôi phụ trách

Trong lab Day 10, tôi đảm nhiệm vai trò **Monitoring & Docs Owner**, phụ trách ba nhóm công việc chính:

**Nhóm 1 — Monitoring layer** (`monitoring/freshness_check.py`): Xây dựng module kiểm tra 5 trụ cột observability (Freshness, Volume, Schema, Distribution, Lineage). Module này chạy độc lập hoặc được gọi từ `etl_pipeline.py` và in ra dashboard trực tiếp trên terminal với màu PASS (xanh) / WARN (vàng) / FAIL (đỏ), đồng thời ghi kết quả ra `artifacts/monitor_report.json`.

**Nhóm 2 — Documentation** (`docs/pipeline_architecture.md`, `docs/data_contract.md`, `docs/runbook.md`): Viết ba tài liệu vận hành để nhóm và giảng viên hiểu kiến trúc pipeline, cam kết schema, và quy trình xử lý sự cố.

**Nhóm 3 — Tích hợp và verify**: Phối hợp với pipeline chính để đảm bảo `monitor()` được gọi đúng thứ tự sau `validate()`, và output được ghi vào `artifacts/` đúng format.

---

## 2. Một quyết định kỹ thuật chính

**Quyết định: Dùng 5-status system (PASS/WARN/FAIL) thay vì boolean pass/fail.**

Ban đầu tôi định implement monitor đơn giản: nếu có bất kỳ check nào fail thì dừng pipeline. Nhưng khi xem xét thực tế vận hành, tôi nhận ra có hai loại vấn đề rất khác nhau:

1. **Vấn đề nghiêm trọng (FAIL):** freshness breach > 48h, thiếu cột schema, volume quá thấp — cần alert ngay
2. **Vấn đề cần theo dõi (WARN):** freshness trong khoảng 24-48h, null rate hơi cao — cần ghi nhận nhưng không nên dừng pipeline gây downtime

Nếu chỉ dùng boolean và hard-stop mọi WARN, pipeline sẽ bị dừng oan trong giờ cao điểm chỉ vì dữ liệu trễ 25h (vượt WARN threshold nhưng chưa vượt FAIL threshold). Điều này gây gián đoạn agent trả lời người dùng trong khi dữ liệu vẫn còn đủ chính xác.

**Bằng chứng từ run thực tế (run_id=20260415T155947):**
```json
{
  "check": "freshness.latest_record_age",
  "status": "WARN",
  "message": "Dữ liệu cách nay 23.5h — gần ngưỡng SLA 24h",
  "value": 23.5
}
```
Monitor trả về WARN nhưng `overall_status = WARN` (không phải FAIL), pipeline tiếp tục chạy và tạo được output. Nếu dùng boolean, pipeline sẽ bị dừng sai.

---

## 3. Một lỗi đã phát hiện và sửa

**Lỗi: UnicodeEncodeError khi print tiếng Việt trên Windows**

Khi chạy `python etl_pipeline.py` lần đầu trên môi trường Windows (PowerShell), pipeline crash ngay bước Ingest với lỗi:
```
UnicodeEncodeError: 'charmap' codec can't encode characters in position 11-12
```

**Nguyên nhân:** Windows PowerShell mặc định dùng encoding `cp1252` cho stdout, không hỗ trợ ký tự tiếng Việt có dấu.

**Cách sửa:** Thêm dòng này vào đầu tất cả modules có print tiếng Việt:
```python
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
```

**Bằng chứng trước/sau:**
- Before: `exit_code: 1`, traceback ở dòng `print(f"\n[Ingest] Đọc dữ liệu từ: {input_path}")`
- After: Pipeline chạy hoàn chỉnh, `exit_code: 0`, in được đầy đủ tiếng Việt

Lỗi này được ghi vào `docs/runbook.md` mục INC-003 để các thành viên khác không mất thời gian debug lại.

---

## 4. Tự đánh giá

**Làm tốt:**
- Module monitoring chạy độc lập, có thể gọi trực tiếp mà không cần chạy cả pipeline
- Ba tài liệu viết theo cấu trúc nhất quán, dùng được ngay khi có incident
- Phát hiện và fix lỗi encoding sớm, không để ảnh hưởng team

**Còn yếu:**
- Monitoring chưa có alerting thực (email/Slack) — hiện chỉ ghi log
- Chưa test được trường hợp volume drop đột ngột so với lần chạy trước (thiếu baseline lịch sử)

**Nhóm phụ thuộc vào tôi ở đâu:**
- `monitor_report.json` và `quality_report.json` là bằng chứng chính trong `before_after_eval.csv`
- `docs/runbook.md` là tài liệu duy nhất giải thích cách xử lý khi pipeline bị incident

---

## 5. Nếu có thêm 2 giờ

Tôi sẽ bổ sung **volume baseline tracking**: lưu lại số dòng của mỗi lần chạy vào một file `artifacts/volume_history.jsonl`, và trong lần chạy tiếp theo, so sánh với lần trước để phát hiện volume drop đột ngột (ví dụ: hôm nay 23 dòng, hôm qua 150 dòng → giảm 85% → FAIL). Hiện tại monitor chỉ so với ngưỡng tuyệt đối (`VOLUME_MIN_ROWS = 10`) mà chưa phát hiện được volume anomaly tương đối, đây là điểm yếu thực sự trong production khi dữ liệu bình thường là vài nghìn dòng/ngày.

---

*Day 10 Lab — AI in Action · VinUniversity · 2026*
