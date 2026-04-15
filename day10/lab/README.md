# Lab Day 10 — Data Pipeline & Data Observability

**Môn:** AI in Action (AICB-P1)  
**Chủ đề:** ETL Pipeline · Data Quality · Observability  
**Tiếp nối:** Day 09 — Multi-Agent → Day 10 — Data Layer

---

## Bối cảnh

Cùng bài toán **trợ lý IT nội bộ CS + IT Helpdesk** từ Day 08-09. Hôm nay xây dựng tầng data pipeline đảm bảo dữ liệu feeding vào vector store không bị stale, dirty hoặc missing.

> _Garbage in → garbage out. Đừng debug model trước khi debug pipeline._

---

## Cấu trúc thư mục

```
day10/lab/
├── etl_pipeline.py              ← Entry point — chạy full pipeline
├── transform/
│   └── cleaning_rules.py        ← 6 cleaning steps
├── quality/
│   └── expectations.py          ← Expectation suite (9 checks)
├── monitoring/
│   └── freshness_check.py       ← 5-pillar observability monitor
├── data/
│   ├── raw/
│   │   └── helpdesk_tickets_dirty.csv   ← Input: dữ liệu thô có lỗi
│   └── cleaned/                         ← Output: dữ liệu đã làm sạch
├── artifacts/
│   ├── before_after_eval.csv    ← Bằng chứng data quality ảnh hưởng agent
│   ├── quality_report.json      ← Kết quả expectation suite
│   └── monitor_report.json      ← Kết quả monitor checks
├── docs/
│   ├── pipeline_architecture.md ← Thiết kế pipeline
│   ├── data_contract.md         ← Hợp đồng schema
│   └── runbook.md               ← Sổ tay xử lý sự cố
├── reports/
│   └── individual/
│       └── nguyen_thanh_nam.md  ← Báo cáo cá nhân
├── requirements.txt
└── README.md
```

---

## Cài đặt

```bash
pip install -r requirements.txt
```

---

## Chạy nhanh

```bash
# Vào thư mục lab
cd day10/lab

# Chạy full pipeline (ingest → clean → validate → monitor → output)
python etl_pipeline.py

# Chạy với file input cụ thể
python etl_pipeline.py --input data/raw/helpdesk_tickets_dirty.csv

# Chỉ chạy monitor
python monitoring/freshness_check.py data/raw/helpdesk_tickets_dirty.csv
```

---

## Kết quả mong đợi sau khi chạy

```
=================================================================
  ETL Pipeline — Day 10 Lab
  run_id = 20260415TXXXXXX
=================================================================

[Ingest]   raw_records = 27
[Clean]    cleaned_records = 23
[Validate] Quality Suite Report [PASS]  pass_rate: 88.9%
[Monitor]  Data Observability Dashboard  status: WARN
[Output]   data/cleaned/helpdesk_tickets_clean_XXXX.csv
[Output]   artifacts/before_after_eval.csv
[Output]   artifacts/quality_report.json
[Output]   artifacts/monitor_report.json
```

---

## Deliverables

| File | Mô tả | Owner |
|------|-------|-------|
| `etl_pipeline.py` | Pipeline ingest → clean → validate → embed | Toàn nhóm |
| `transform/cleaning_rules.py` | Quy tắc làm sạch dữ liệu | Cleaning Owner |
| `quality/expectations.py` | Expectation suite kiểm tra quality | Quality Owner |
| `monitoring/freshness_check.py` | Freshness + volume monitor | Nguyễn Thành Nam |
| `artifacts/before_after_eval.csv` | Bằng chứng data quality | Toàn nhóm |
| `docs/pipeline_architecture.md` | Thiết kế pipeline | Nguyễn Thành Nam |
| `docs/data_contract.md` | Hợp đồng schema | Nguyễn Thành Nam |
| `docs/runbook.md` | Sổ tay xử lý sự cố | Nguyễn Thành Nam |
| `reports/individual/*.md` | Báo cáo cá nhân | Từng người |

---

## Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
|-----|------------|---------|
| `UnicodeEncodeError` khi print | Windows stdout không phải UTF-8 | Đã fix: thêm `sys.stdout.reconfigure(encoding='utf-8')` |
| `FileNotFoundError: data/raw/...` | Chạy lệnh sai thư mục | `cd day10/lab` trước khi chạy |
| `Missing required columns` | File CSV thiếu cột bắt buộc | Kiểm tra header của CSV, xem `docs/data_contract.md` |
| Monitor status = FAIL | Freshness hoặc volume breach | Xem `docs/runbook.md` mục INC-001 hoặc INC-005 |

---

*Day 10 Lab — AI in Action · VinUniversity · 2026*
