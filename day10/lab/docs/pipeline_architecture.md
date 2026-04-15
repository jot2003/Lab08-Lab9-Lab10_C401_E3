# Kiến trúc Pipeline — Lab Day 10

**Nhóm:** C401-E3 (Hoang Kim Tri Thanh · Dang Dinh Tu Anh · Quach Gia Duoc · Pham Quoc Dung · Nguyen Thanh Nam)  
**Cập nhật:** 2026-04-15  
**Owner tài liệu (D10-T04):** Nguyễn Thành Nam

---

## 1. Sơ đồ luồng thực tế

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            RAW SOURCE                                           │
│  data/raw/policy_export_dirty.csv                                               │
│  (10 records: policy_refund, sla_p1, it_faq, hr_leave, legacy_catalog)         │
│  exported_at = 2026-04-10T08:00:00  ← đây là điểm đo FRESHNESS_INGEST         │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                               │ load_raw_csv()
                               │ log: raw_records=10  [D10-T01]
                               ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         TRANSFORM / CLEAN                                        │
│  transform/cleaning_rules.py   (D10-T02: Quach Gia Duoc)                        │
│                                                                                  │
│  Rule 1: deduplicate chunk_id               → drop chunk_id=2 (dup of 1)        │
│  Rule 2: drop empty chunk_text              → drop chunk_id=5 (empty)           │
│  Rule 3: refund_window_fix (14→7 ngày)      → quarantine chunk_id=3 (v3 stale) │
│  Rule 4: hr_stale_version (effective<2026)  → quarantine chunk_id=7 (HR 2025)  │
│  Rule 5: allowlist doc_id                   → quarantine chunk_id=9 (legacy)   │
│  Rule 6: effective_date format (ISO only)   → quarantine chunk_id=10 (01/02/..)│
│                                                                                  │
│  Output:  cleaned_records=4  │  quarantine_records=6                            │
│  Files:   artifacts/cleaned/cleaned_<run_id>.csv                                │
│           artifacts/quarantine/quarantine_<run_id>.csv                           │
└──────────────────────────────┬───────────────────────────────────────────────────┘
                               │ run_expectations()
                               ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         VALIDATE / QUALITY                                       │
│  quality/expectations.py   (D10-T03: Pham Quoc Dung)                            │
│                                                                                  │
│  Expectation 1 [warn]:  chunk_text không rỗng                                   │
│  Expectation 2 [warn]:  effective_date phải là ISO-8601                          │
│  Expectation 3 [halt]:  doc_id nằm trong allowlist                              │
│  Expectation 4 [halt]:  không còn chunk có "14 ngày" + "hoàn tiền"             │
│                                                                                  │
│  → HALT nếu bất kỳ halt-expectation nào fail                                    │
│  → WARN ghi vào log, pipeline tiếp tục                                          │
└──────────────────────────────┬───────────────────────────────────────────────────┘
                               │ cmd_embed_internal()
                               ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         EMBED / INDEX                                            │
│  ChromaDB collection: day10_kb   (D10-T05: Hoang Kim Tri Thanh)                 │
│  Model: all-MiniLM-L6-v2 (CPU-safe)                                             │
│                                                                                  │
│  Idempotency:                                                                    │
│    - Upsert theo chunk_id → rerun 2 lần không tạo duplicate                     │
│    - Prune: xoá chunk_id có trong collection nhưng không còn trong cleaned      │
│      → log: embed_prune_removed=N                                                │
│  Metadata ghi kèm: doc_id, effective_date, run_id                               │
│                                                                                  │
│  Output: chroma_db/ (local PersistentClient)                                    │
└──────────────────────────────┬───────────────────────────────────────────────────┘
                               │ check_manifest_freshness()
                               ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         MONITOR / MANIFEST                                       │
│  monitoring/freshness_check.py   (D10-T05: Hoang Kim Tri Thanh)                 │
│                                                                                  │
│  Ghi manifest:  artifacts/manifests/manifest_<run_id>.json                      │
│    { run_id, raw_records, cleaned_records, quarantine_records,                   │
│      latest_exported_at, chroma_collection, ... }                                │
│                                                                                  │
│  Freshness SLA check (env: FRESHNESS_SLA_HOURS=24):                             │
│    latest_exported_at vs run_timestamp                                           │
│    PASS: delta < 12h  │  WARN: 12–24h  │  FAIL: > 24h ← INC-001               │
│                                                                                  │
│  Log cuối: PIPELINE_OK  hoặc PIPELINE_HALT                                      │
└──────────────────────────────┬───────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                     SERVING / GRADING / EVAL                                     │
│                                                                                  │
│  eval_retrieval.py  → artifacts/eval/*_eval.csv                                 │
│  grading_run.py     → artifacts/eval/grading_run.jsonl                          │
│                                                                                  │
│  Câu hỏi test (data/test_questions.json):                                        │
│    q_refund_window: kỳ vọng "7 ngày", forbidden "14 ngày"                       │
│    q_p1_sla:        kỳ vọng "15 phút / 4 giờ"                                  │
│    q_lockout:       kỳ vọng "5 lần"                                             │
│    q_leave_version: kỳ vọng "12 ngày" (2026), top1_doc=hr_leave_policy          │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Điểm đo freshness:** `exported_at` trong CSV (thời điểm upstream export) — không phải thời điểm chạy pipeline.  
**Ghi run_id:** Tự động từ UTC timestamp hoặc flag `--run-id` → mọi artifact đều mang run_id.

---

## 2. Ranh giới trách nhiệm

| Thành phần | Input | Output | Owner (task_id) |
|------------|-------|--------|-----------------|
| **Ingest** | `data/raw/policy_export_dirty.csv` | `rows[]` (list of dicts) | Dang Dinh Tu Anh (D10-T01) |
| **Transform** | `rows[]` (raw 10 records) | `cleaned[]` (4) + `quarantine[]` (6) | Quach Gia Duoc (D10-T02) |
| **Quality** | `cleaned[]` | `results[], halt: bool` | Pham Quoc Dung (D10-T03) |
| **Embed** | `cleaned_*.csv` | ChromaDB collection `day10_kb` | Hoang Kim Tri Thanh (D10-T05) |
| **Monitor** | manifest JSON | freshness status PASS/WARN/FAIL | Hoang Kim Tri Thanh (D10-T05) |
| **Docs & Runbook** | tất cả artifacts & logs | 3 docs này + reports | Nguyen Thanh Nam (D10-T04) |

---

## 3. Idempotency & rerun

Pipeline sử dụng **upsert theo `chunk_id`** làm key idempotency:

- Mỗi `chunk_id` là ID duy nhất trong ChromaDB → `col.upsert(ids=chunk_ids, ...)` không tạo bản ghi trùng.
- Nếu một chunk bị quarantine trong lần rerun (ví dụ sau khi thêm rule mới), pipeline sẽ **prune** (xoá) chunk đó khỏi collection:
  ```
  embed_prune_removed=N   ← log trong artifacts/logs/run_*.log
  ```
- Rerun 2 lần với cùng input → số lượng vector trong collection **không thay đổi** sau lần thứ 2.

**Lưu ý:** `cleaned_path` có chứa `run_id` nên mỗi run tạo file cleaned mới — không ghi đè lịch sử.

---

## 4. Liên hệ Day 09

Pipeline Day 10 và Day 09 dùng **chung thư mục `data/docs/`** cho 5 tài liệu nội bộ (policy_refund, sla_p1, access_control, it_faq, hr_leave):

```
day09/lab/data/docs/   ← Day 09 retrieval workers đọc từ đây (TXT files)
day10/lab/data/docs/   ← mirror (cùng nội dung)
day10/lab/data/raw/    ← CSV export mô phỏng lớp ingestion từ DB/API
```

Day 10 mô phỏng kịch bản **CSV export từ upstream DB** — khác với Day 09 dùng trực tiếp TXT. Collection `day10_kb` (Chroma) được tạo ra từ CSV cleaned; nếu muốn Day 09 dùng lại, cần đổi `CHROMA_COLLECTION=day10_kb` trong `.env` của Day 09 lab.

---

## 5. Rủi ro đã biết

| Rủi ro | Mức | Chi tiết | Owner |
|--------|-----|---------|-------|
| Freshness FAIL khi CSV cũ > 24h | CAO | `exported_at=2026-04-10` → delta ≈ 5 ngày; xem INC-001 trong runbook | D10-T04 |
| Stale refund chunk từ v3 migration | CAO | chunk_id=3 "14 ngày" bị fix bởi `apply_refund_window_fix`; xem INC-002 | D10-T02 |
| chromadb chưa cài → embed fail | TRUNG | `pip install -r requirements.txt` trước khi chạy | D10-T05 |
| HR chunk 2025 lọt qua nếu effective_date bị bỏ qua | TRUNG | chunk_id=7 bị filter bởi `hr_stale_version` rule | D10-T02 |
| Malformed date "01/02/2026" không parse được | THẤP | chunk_id=10 quarantined bởi `effective_date` format rule | D10-T02 |

---

*Day 10 Lab — AI in Action · VinUniversity · 2026 · D10-T04 owner: Nguyễn Thành Nam*
