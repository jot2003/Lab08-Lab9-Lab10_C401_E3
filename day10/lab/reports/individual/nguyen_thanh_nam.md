# Báo cáo cá nhân — Lab Day 10

**Họ và tên:** Nguyễn Thành Nam  
**Vai trò:** Docs & Runbook — D10-T04  
**Độ dài:** ~480 từ

---

## 1. Phụ trách

Tôi viết toàn bộ `docs/runbook.md`, `docs/pipeline_architecture.md` và điền `reports/group_report.md` (đặc biệt bảng `metric_impact`).

- **`runbook.md`:** 2 incident đủ 5 mục Symptom → Prevention: INC-001 freshness FAIL (delta = 120.388h > SLA 24h) và INC-002 stale refund chunk (chunk_id=3, reason `stale_refund_migration_marker`). Có bảng post-mortem gắn `run_id=dung-after-final`.
- **`pipeline_architecture.md`:** ASCII diagram ingest → clean → validate → embed → grading; bảng ranh giới owner theo `contracts/task_owner_map.json`; mục idempotency (`embed_prune_removed`, upsert theo `chunk_id`).
- **`group_report.md`:** bảng `metric_impact` 7 dòng, mục before/after retrieval, freshness SLA, Day 09 link.

**Kết nối:** Đọc artifact từ D10-T02 (`quarantine_dung-after-final.csv`) và D10-T03 (`dung_before_bad_eval.csv`, `dung_after_final_eval.csv`) để điền số liệu. Manifest từ D10-T05 (`manifest_dung-after-final.json`) làm nguồn freshness.

**Bằng chứng:** commit `docs(day10-lab): complete D10-T04 runbook, architecture and group report` trên `chore/day10-nam-docs-monitoring`.

---

## 2. Quyết định kỹ thuật

**Gắn Diagnosis và Mitigation trực tiếp với dòng log/artifact path — không mô tả chung chung.**

Template gốc chỉ ghi "kiểm tra manifest" và "chạy lại pipeline". Tôi đổi thành bảng `| Bước | Việc làm | Kết quả mong đợi |` với đường dẫn file thật và lệnh copy-paste được. Lý do: reviewer sẽ mở log ngay — nếu không có dòng cụ thể thì runbook bị coi là placeholder, mất điểm mục documentation.

Trade-off: runbook gắn chặt `run_id=dung-after-final`; nếu nhóm đổi run mới cần cập nhật lại. Đổi lại, GV verify được tức thì.

---

## 3. Sự cố / anomaly

Template `pipeline_architecture.md` ban đầu ghi điểm đo freshness là "sau khi embed xong". Tôi đọc `etl_pipeline.py`:

```python
latest_exported = max((r.get("exported_at") or "" for r in cleaned), default="")
```

`monitoring/freshness_check.py` hàm `check_manifest_freshness()` đọc trường `latest_exported_at` từ manifest — tức freshness đo từ `exported_at` trong CSV (thời điểm upstream export), không phải lúc pipeline chạy.

Fix: sửa diagram ghi chú tại bước Ingest:
```
exported_at = 2026-04-10T08:00:00  ← điểm đo FRESHNESS_INGEST
```
Đồng thời cập nhật section Validate dùng tên expectation thật từ log thay vì tên tự đặt.

---

## 4. Before / after

**run_id:** `dung-after-final`

Trước (`dung_before_bad_eval.csv`):
```
q_refund_window | top1_preview="...14 ngày làm việc..." | hits_forbidden=yes
```

Sau (`dung_after_final_eval.csv`):
```
q_refund_window | top1_preview="...7 ngày làm việc..."  | hits_forbidden=no
```

Log xác nhận: `expectation[refund_no_stale_14d_window] OK (halt) :: violations=0`

---

## 5. Cải tiến thêm 2 giờ

Đọc ngưỡng freshness SLA từ `contracts/data_contract.yaml` thay vì hard-code `FRESHNESS_SLA_HOURS=24` trong `.env` — đồng thời thêm expectation `exported_at_freshness` vào `quality/expectations.py` để halt trước bước embed khi dữ liệu đã stale, không chờ đến monitor sau embed (hướng Distinction b).
