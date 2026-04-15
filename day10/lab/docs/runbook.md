# Runbook — Data Pipeline Incident Triage
> Day 10 Lab · Trợ lý IT nội bộ CS + IT Helpdesk

---

## Mục đích

Runbook này hướng dẫn xử lý các sự cố phổ biến trong data pipeline theo quy trình:
**Detect → Isolate → Fix → Verify → Post-mortem**

Ai cũng có thể dùng runbook này — không cần biết code sâu.

---

## Bản đồ triệu chứng → Hành động

| Triệu chứng | Nguyên nhân có thể | Chuyển đến |
|-------------|-------------------|-----------|
| Agent trả lời thông tin cũ | Freshness breach | [INC-001] |
| Agent hallucinate thông tin không có trong docs | Dirty data vào vector store | [INC-002] |
| Pipeline crash khi chạy | Lỗi schema hoặc encoding | [INC-003] |
| Quality pass_rate < 85% | Nhiều giá trị invalid hoặc null | [INC-004] |
| Monitor report: FAIL | Xem chi tiết check nào fail | [INC-005] |

---

## [INC-001] Freshness Breach — Dữ liệu bị stale

**Dấu hiệu:**
- `monitoring/freshness_check.py` báo `FAIL` với `freshness.latest_record_age`
- Agent trả lời thông tin của ngày hôm qua hoặc cũ hơn

**Quy trình xử lý:**

```
Bước 1 — Detect
  Đọc artifacts/monitor_report.json
  → Tìm field: "check": "freshness.latest_record_age"
  → Xem "value": số giờ kể từ bản ghi mới nhất

Bước 2 — Isolate
  Kiểm tra file source có được update không?
  → ls -la data/raw/   (xem Last Modified)
  Nếu file không đổi: vấn đề ở upstream (hệ thống export)
  Nếu file mới nhưng data cũ: vấn đề ở field timestamp trong CSV

Bước 3 — Fix
  Nếu upstream chưa export:
    → Liên hệ IT Support Team để re-export CSV hôm nay
    → Copy file mới vào data/raw/
  Nếu timestamp sai:
    → Kiểm tra múi giờ server export (UTC vs UTC+7)
    → Sửa offset trong cleaning_rules.py nếu cần

Bước 4 — Verify
  python etl_pipeline.py --input data/raw/[file_mới].csv
  → Kiểm tra monitor_status = PASS hoặc WARN

Bước 5 — Post-mortem
  Ghi vào bảng Post-mortem ở cuối runbook này
```

---

## [INC-002] Dirty Data vào Vector Store — Agent Hallucinate

**Dấu hiệu:**
- Agent trả lời thông tin sai (priority không đúng, channel sai, số liệu bịa)
- Quality report: có `invalid_channel_values` hoặc `invalid_priority` > 0

**Quy trình xử lý:**

```
Bước 1 — Detect
  Đọc artifacts/quality_report.json
  → Tìm các check với "passed": false
  → Đọc "detail" để biết số dòng vi phạm

Bước 2 — Isolate
  Mở data/raw/helpdesk_tickets_dirty.csv
  Lọc theo cột vi phạm:
    → Cột channel: tìm giá trị khác email/chat/phone
    → Cột priority: tìm giá trị khác low/medium/high

Bước 3 — Fix
  Nếu lỗi có thể map được:
    → Sửa trong transform/cleaning_rules.py (thêm vào priority_map hoặc channel_map)
    → Chạy lại pipeline
  Nếu lỗi quá nhiều (> 20% dòng):
    → Liên hệ upstream để sửa schema export
    → Tạm thời dùng data/cleaned/ từ lần chạy trước (rollback)

Bước 4 — Verify
  python etl_pipeline.py
  → Kiểm tra: quality report pass_rate >= 85%
  → Kiểm tra: invalid_channel = 0, invalid_priority = 0

Bước 5 — Post-mortem
  Ghi nguyên nhân gốc rễ vào bảng Post-mortem
```

---

## [INC-003] Pipeline Crash — Lỗi Schema hoặc Encoding

**Dấu hiệu:**
- `python etl_pipeline.py` báo `UnicodeDecodeError` hoặc `KeyError` hoặc `ValueError`
- Thông báo lỗi: `Missing required columns: [...]`

**Quy trình xử lý:**

```
Bước 1 — Detect
  Đọc traceback trong terminal:
    UnicodeDecodeError  → vấn đề encoding
    KeyError            → thiếu cột trong CSV
    ValueError          → schema không khớp contract

Bước 2 — Isolate
  Mở file CSV bằng editor:
    → Kiểm tra hàng đầu tiên (header): có đủ 6 cột không?
    → Kiểm tra encoding: mở bằng UTF-8, Latin-1 hay khác?

Bước 3 — Fix (theo loại lỗi)

  UnicodeDecodeError:
    python -c "import pandas as pd; pd.read_csv('data/raw/file.csv', encoding='latin-1')"
    Nếu đọc được: thêm encoding='latin-1' vào ingest() trong etl_pipeline.py

  Thiếu cột:
    Kiểm tra file CSV xem header có đúng không
    Nếu tên cột thay đổi: cập nhật required_columns trong expectations.py và contract này

Bước 4 — Verify
  python etl_pipeline.py
  → Không có traceback, pipeline chạy đến cuối

Bước 5 — Post-mortem
  Ghi vào bảng Post-mortem
```

---

## [INC-004] Quality Pass Rate thấp (< 85%)

**Dấu hiệu:**
- Log pipeline: `CẢNH BÁO: pass_rate=XX% thấp hơn ngưỡng 85%`
- Quality report: nhiều checks `"passed": false`

**Quy trình xử lý:**

```
Bước 1 — Detect
  Đọc artifacts/quality_report.json → trường "failed"
  Đọc từng item trong "results" với "passed": false

Bước 2 — Isolate
  Phân loại vi phạm:
    severity=error   → cần fix ngay
    severity=warning → ghi nhận, có thể chạy tiếp

Bước 3 — Fix
  completeness failure:
    → Xem bao nhiêu dòng null → quyết định drop hay giữ với flag
  validity failure:
    → Cập nhật cleaning_rules.py để map thêm giá trị
  uniqueness failure:
    → remove_duplicates đã chạy chưa? Kiểm tra thứ tự steps
  timeliness failure:
    → Xem INC-001

Bước 4 — Verify
  Chạy lại pipeline → pass_rate >= 85%

Bước 5 — Post-mortem
  Ghi lý do pass_rate thấp + cách sửa
```

---

## [INC-005] Monitor Status = FAIL

**Dấu hiệu:**
- `monitoring/freshness_check.py` in ra `FAIL` (màu đỏ)
- artifacts/monitor_report.json: `"overall_status": "FAIL"`

**Quy trình xử lý:**

```
Bước 1 — Detect
  Đọc monitor_report.json → tìm item "status": "FAIL"
  Đọc "message" để hiểu chi tiết

Bước 2 — Route
  freshness.latest_record_age FAIL → Xem INC-001
  schema.required_columns_present FAIL → Xem INC-003
  volume.row_count_min FAIL → kiểm tra ingestion có bị cắt không
  distribution.null_rate.X FAIL → > 30% null ở cột X → Xem INC-002

Bước 3 — Fix theo route ở trên

Bước 4 — Verify
  python monitoring/freshness_check.py data/raw/[file].csv
  → overall_status = PASS hoặc WARN

Bước 5 — Post-mortem
```

---

## Lệnh hữu ích — Quick Reference

```bash
# Chạy full pipeline
python etl_pipeline.py

# Chạy với file cụ thể
python etl_pipeline.py --input data/raw/helpdesk_tickets_dirty.csv

# Chỉ chạy monitor
python monitoring/freshness_check.py data/raw/helpdesk_tickets_dirty.csv

# Xem quality report
type artifacts/quality_report.json

# Xem monitor report
type artifacts/monitor_report.json

# Xem before/after evidence
type artifacts/before_after_eval.csv
```

---

## Bảng Post-mortem (cập nhật khi xử lý incident)

| Ngày | Incident | Nguyên nhân gốc rễ | Cách fix | Người xử lý | Thời gian resolve |
|------|----------|--------------------|----------|-------------|-------------------|
| 2026-04-15 | INC-003 (UnicodeEncodeError trên Windows) | stdout Windows không hỗ trợ UTF-8 mặc định | Thêm `sys.stdout.reconfigure(encoding='utf-8')` vào đầu các module | Nguyễn Thành Nam | 5 phút |
| | | | | | |

---

## Checklist trước khi deploy pipeline lên production

- [ ] Chạy `python etl_pipeline.py` với sample data → không có traceback
- [ ] Quality pass_rate >= 85%
- [ ] Monitor status = PASS hoặc WARN (không phải FAIL)
- [ ] File `artifacts/before_after_eval.csv` được tạo thành công
- [ ] Không có file `.env` hoặc credentials trong repo
- [ ] Freshness check: data source cập nhật trong 24h

---

*Day 10 Lab — AI in Action · VinUniversity · 2026*
