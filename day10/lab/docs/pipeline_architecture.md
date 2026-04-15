# Pipeline Architecture — Day 10 Lab
> Trợ lý IT nội bộ CS + IT Helpdesk

---

## Tổng quan

Day 10 xây dựng tầng data pipeline phía dưới toàn bộ hệ AI đã được dựng ở Day 08 (RAG) và Day 09 (Supervisor-Workers). Mục tiêu là đảm bảo dữ liệu feeding vào vector store **không bị stale, dirty, hoặc missing** trước khi agent trả lời.

> _Garbage in → garbage out. Đừng debug model trước khi debug pipeline._

---

## Kiến trúc tổng thể

```
┌──────────────────────────────────────────────────────────────────┐
│                    Sources (IT Helpdesk Data)                    │
│  helpdesk_tickets.csv  │  policy_docs/  │  hr_docs/  │  API     │
└──────────────┬─────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                     INGEST LAYER                                  │
│  - Đọc CSV / text files                                          │
│  - Ghi run_id + timestamp cho mỗi lần chạy                       │
│  - Log: raw_records count                                        │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                     TRANSFORM LAYER                               │
│  transform/cleaning_rules.py                                     │
│                                                                  │
│  1. parse_timestamps      → chuẩn hoá kiểu dữ liệu               │
│  2. normalize_channel     → email/chat/phone (lowercase)         │
│  3. normalize_priority    → low/medium/high (urgent→high)        │
│  4. fix_resolution_time   → loại giá trị âm / quá lớn           │
│  5. remove_duplicates     → dedup theo ticket_id                 │
│  6. drop_missing_required → xoá dòng thiếu ticket_id hoặc msg   │
│                                                                  │
│  Log: số dòng trước/sau từng bước                                │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                     VALIDATE LAYER                                │
│  quality/expectations.py                                         │
│                                                                  │
│  Completeness  : ticket_id, message, timestamp not null          │
│  Validity      : channel ∈ {email,chat,phone}                    │
│                  priority ∈ {low,medium,high}                    │
│                  resolution_minutes ≥ 0                          │
│  Uniqueness    : ticket_id unique                                │
│  Timeliness    : data không cũ hơn 48h                          │
│  Volume        : số dòng trong ngưỡng [10, 100_000]             │
│                                                                  │
│  pass_rate < 85% → pipeline vẫn chạy nhưng ghi cảnh báo         │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                     MONITOR LAYER                                 │
│  monitoring/freshness_check.py                                   │
│                                                                  │
│  Freshness  : dữ liệu mới nhất trong 24h (WARN) / 48h (FAIL)   │
│  Volume     : row count trong ngưỡng bình thường                 │
│  Schema     : đủ cột bắt buộc                                   │
│  Distribution: null rate từng cột < 30%                         │
│  Lineage    : file source tồn tại và có thể đọc                 │
│                                                                  │
│  Output: artifacts/monitor_report.json                          │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                     OUTPUT / STORAGE                              │
│                                                                  │
│  data/cleaned/helpdesk_tickets_clean_<run_id>.csv               │
│  artifacts/quality_report.json                                   │
│  artifacts/monitor_report.json                                   │
│  artifacts/before_after_eval.csv  (bằng chứng data quality)     │
│                                                                  │
│  [Bước tiếp theo — ngoài scope Day 10]                          │
│  → Embed cleaned tickets vào ChromaDB                           │
│  → Supervisor-Workers (Day 09) query từ cleaned vector store     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Các quyết định thiết kế

### 1. ETL (Transform trước Load) thay vì ELT

**Lý do:** Dữ liệu helpdesk chứa PII tiềm năng và có thể có giá trị sai (priority âm, channel không hợp lệ) làm lệch kết quả retrieval. Việc transform trước khi load vào vector store giúp đảm bảo chỉ dữ liệu sạch mới được embed, tránh vector "rác" trong ChromaDB.

### 2. Batch processing thay vì Streaming

**Lý do:** Khối lượng ticket IT Helpdesk không đủ lớn để cần streaming thời gian thực. Batch theo lịch (ví dụ mỗi 6-12 giờ) đủ đáp ứng SLA freshness 24h. Streaming sẽ tăng độ phức tạp vận hành không cần thiết ở giai đoạn này.

### 3. run_id theo timestamp

**Lý do:** Mỗi lần chạy pipeline được đánh dấu bằng `run_id = YYYYMMDDTHHMMSS`. Điều này cho phép:
- Rollback về bản sạch của ngày cụ thể nếu phát hiện vấn đề
- Truy vết lịch sử data quality theo thời gian
- Idempotency: chạy lại cùng input không ghi đè file cũ

### 4. pass_rate thay vì hard stop

**Lý do:** Thay vì dừng hẳn pipeline khi có lỗi quality, sử dụng `pass_rate` threshold (85%). Nếu < 85%: cảnh báo + ghi log, pipeline vẫn tiếp tục. Điều này tránh downtime hoàn toàn trong production khi chỉ có vấn đề nhỏ.

---

## Liên kết với Day 08 & Day 09

```
Day 08 RAG Pipeline
  └── rag_pipeline.py (indexing + retrieval)
       ↑
       │ data đã clean
       │
Day 10 ETL Pipeline  ──→  data/cleaned/*.csv
       │
       │ quality report
       └──→ artifacts/

Day 09 Supervisor-Workers
  └── retrieval_worker.py
       ↑
       │ query ChromaDB built từ cleaned data
```

---

## Cấu trúc thư mục

```
day10/lab/
├── etl_pipeline.py              ← Entry point chính
├── transform/
│   └── cleaning_rules.py        ← 6 cleaning steps
├── quality/
│   └── expectations.py          ← Expectation suite (9 checks)
├── monitoring/
│   └── freshness_check.py       ← 5-pillar monitor
├── data/
│   ├── raw/                     ← Input: dữ liệu thô (dirty)
│   └── cleaned/                 ← Output: dữ liệu đã làm sạch
├── artifacts/
│   ├── before_after_eval.csv    ← Bằng chứng data quality
│   ├── quality_report.json      ← Kết quả expectation suite
│   └── monitor_report.json      ← Kết quả monitor checks
├── docs/
│   ├── pipeline_architecture.md ← File này
│   ├── data_contract.md         ← Hợp đồng schema
│   └── runbook.md               ← Sổ tay xử lý sự cố
└── reports/
    └── individual/
        └── nguyen_thanh_nam.md  ← Báo cáo cá nhân
```

---

## Tech Stack Day 10

| Layer | Tool |
|-------|------|
| Data Processing | Python + pandas |
| Quality Checks | Custom expectation suite (inspired by Great Expectations) |
| Monitoring | Custom 5-pillar monitor |
| Orchestration | Script-based (có thể nâng lên Prefect/Airflow) |
| Storage | CSV → ChromaDB (embed step) |

---

*Day 10 Lab — AI in Action · VinUniversity · 2026*
