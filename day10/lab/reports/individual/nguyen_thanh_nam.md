# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Thành Nam  
**Vai trò:** Docs & Runbook — D10-T04  
**Ngày nộp:** 2026-04-15  
**Độ dài yêu cầu:** 400–650 từ

---

> Viết **"tôi"**, đính kèm **run_id**, **tên file**, **đoạn log** hoặc **dòng CSV** thật.

---

## 1. Tôi phụ trách phần nào? (80–120 từ)

**File / module:**

- `docs/runbook.md` — 2 incident đầy đủ 5 mục (Symptom → Detection → Diagnosis → Mitigation → Prevention): INC-001 freshness FAIL và INC-002 stale refund chunk; có bảng post-mortem với run_id, root cause, time to resolve.
- `docs/pipeline_architecture.md` — ASCII diagram toàn luồng ingest → clean → validate → embed → grading; bảng ranh giới trách nhiệm theo `task_id` từ `contracts/task_owner_map.json`; mục idempotency và liên hệ Day 09.
- `reports/group_report.md` — điền toàn bộ 6 section, đặc biệt bảng `metric_impact` (7 dòng) là yêu cầu bắt buộc của SCORING.md.

**Kết nối với thành viên khác:** Tôi đọc artifact của D10-T02 (Được — `quarantine_dung-after-final.csv`) và D10-T03 (Dũng — `dung_before_bad_eval.csv`, `dung_after_final_eval.csv`) để điền số liệu vào bảng metric_impact và runbook. D10-T05 (Tri Thanh) cung cấp manifest `manifest_dung-after-final.json` làm nguồn dữ liệu freshness.

**Bằng chứng:** commit `docs(day10-lab): complete D10-T04 runbook, architecture and group report` trên nhánh `chore/day10-nam-docs-monitoring`; commit `fix(day10-nam-docs)` sửa tên expectation và rule code.

---

## 2. Một quyết định kỹ thuật (100–150 từ)

**Quyết định: Gắn từng bước Diagnosis và Mitigation trực tiếp với dòng log/artifact path cụ thể, không mô tả chung chung.**

Khi bắt đầu điền runbook theo template, các mục Diagnosis chỉ ghi "kiểm tra manifest" hay "chạy lại pipeline" — đủ về cấu trúc nhưng không thể verify bằng artifact. Sau khi đọc `TEAM_EXECUTION_GUIDE_DAY10.md` mục 6 ("mở log trong `artifacts/logs/` và tìm `event_json=`"), tôi nhận ra reviewer sẽ test ngay bằng cách mở log — nếu không có dòng cụ thể thì runbook bị coi là placeholder.

Tôi đổi cách viết: mỗi bước Diagnosis có bảng `| Bước | Việc làm | Kết quả mong đợi |` với đường dẫn file thật. INC-001 Detection trích thẳng từ log thực tế:

```
freshness_check=FAIL {"latest_exported_at": "2026-04-10T08:00:00", "age_hours": 120.388, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}
```

**Trade-off:** Runbook gắn chặt `run_id=dung-after-final`; nếu nhóm đổi run mới phải cập nhật. Đổi lại, giảng viên verify được ngay mà không cần đoán context.

---

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

**Anomaly: Template `pipeline_architecture.md` mô tả sai điểm đo freshness — ghi "sau khi embed xong" thay vì đo từ `exported_at` trong raw CSV.**

**Phát hiện:** Khi điền sơ đồ pipeline, tôi đọc `etl_pipeline.py` để tìm chỗ freshness được tính. Thấy dòng:

```python
latest_exported = max((r.get("exported_at") or "" for r in cleaned), default="")
```

Và `monitoring/freshness_check.py` hàm `check_manifest_freshness()` đọc `latest_exported_at` từ manifest — nghĩa là điểm đo là `exported_at` trong CSV (thời điểm upstream export), **không phải** lúc pipeline chạy.

**Tác động:** Nếu ghi sai, khi giảng viên hỏi "freshness tính từ lúc nào", nhóm không trả lời khớp code. Giảm điểm mục architecture docs.

**Fix:** Sửa diagram để ghi chú rõ tại bước Ingest:
```
exported_at = 2026-04-10T08:00:00  ← đây là điểm đo FRESHNESS_INGEST
```
Đồng thời cập nhật danh sách expectation trong sơ đồ Validate từ tên tự bịa sang 6 tên thật từ log: `expectation[refund_no_stale_14d_window]`, `expectation[hr_leave_no_stale_10d_annual]`, v.v.

---

## 4. Bằng chứng trước / sau (80–120 từ)

**run_id:** `dung-after-final` — `artifacts/manifests/manifest_dung-after-final.json`

**Trước (inject — `dung_before_bad_eval.csv`):**
```
q_refund_window,...,top1_preview="...14 ngày làm việc...",contains_expected=yes,hits_forbidden=yes
q_leave_version,...,top1_preview="12 ngày...",contains_expected=yes,hits_forbidden=no,top1_doc_expected=yes
```

**Sau (clean — `dung_after_final_eval.csv`):**
```
q_refund_window,...,top1_preview="...7 ngày làm việc...",contains_expected=yes,hits_forbidden=no
q_leave_version,...,top1_preview="12 ngày...",contains_expected=yes,hits_forbidden=no,top1_doc_expected=yes
```

Thay đổi đo được: `q_refund_window` đổi từ `hits_forbidden=yes` → `hits_forbidden=no`, top1_preview từ **"14 ngày"** → **"7 ngày"**. Đây là bằng chứng trực tiếp cho INC-002 trong runbook của tôi: chunk_id=3 (stale v3 migration) đã bị quarantine bởi rule `stale_refund_migration_marker` trong `cleaning_rules.py`.

Log xác nhận: `expectation[refund_no_stale_14d_window] OK (halt) :: violations=0`

---

## 5. Cải tiến tiếp theo (40–80 từ)

Nếu có thêm 2 giờ, tôi sẽ bổ sung **expectation `exported_at_freshness` vào `quality/expectations.py`** — halt nếu max(`exported_at`) trong cleaned < now − 24h. Hiện tại freshness chỉ check ở bước Monitor (sau embed), nhưng nếu check sớm ở bước Validate thì pipeline dừng trước khi embed dữ liệu cũ vào ChromaDB. Chứng minh bằng log: `expectation[exported_at_freshness] FAIL (halt)` xuất hiện trước dòng `embed_upsert`.
