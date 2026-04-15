# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Data Observability

**Họ và tên:** Nguyễn Thành Nam  
**Mã số sinh viên:** 2A202600205  
**Vai trò trong nhóm:** Docs & Runbook Owner (D10-T04)  
**Ngày nộp:** 2026-04-15  
**Độ dài:** ~600 từ

---

## 1. Tôi phụ trách phần nào?

**Task ID:** D10-T04 — scope theo `contracts/task_owner_map.json`: *"Runbook, architecture docs, incident documentation"*

**File tôi trực tiếp viết:**

| File | Nội dung cụ thể |
|------|----------------|
| `docs/runbook.md` | 2 incident đầy đủ 5 mục (INC-001 freshness FAIL, INC-002 stale refund chunk) + bảng post-mortem |
| `docs/pipeline_architecture.md` | ASCII diagram toàn luồng ingest→clean→validate→embed→grading, bảng owner theo task_id, mục idempotency và liên hệ Day 09 |
| `reports/group_report.md` | Điền toàn bộ 6 section: pipeline overview, bảng `metric_impact` (7 rows), before/after retrieval, freshness SLA, Day 09 link, risk table |

**Kết nối với team:** Tôi phụ thuộc vào D10-T02 (Được) và D10-T03 (Dũng) để có artifacts (quarantine CSV, eval CSV, log) trước khi viết docs. Team phụ thuộc vào `group_report.md` của tôi để nộp bài và tránh bị trừ điểm vì thiếu `metric_impact`.

---

## 2. Một quyết định kỹ thuật trong phần docs

**Quyết định: Gắn mỗi incident trực tiếp với artifact path cụ thể, không viết hướng dẫn chung chung.**

Ban đầu tôi điền runbook theo template — 5 section nhưng chỉ là mô tả tổng quát như "kiểm tra manifest", "chạy lại pipeline". Khi đọc lại `TEAM_EXECUTION_GUIDE_DAY10.md` mục 6, tôi thấy yêu cầu rõ: "mở log trong `artifacts/logs/` và tìm `event_json=`" — nghĩa là runbook phải trích dẫn được event cụ thể.

Tôi đổi cách viết: mỗi bước Diagnosis và Mitigation đều dùng đường dẫn file thật và dòng lệnh copy-paste được. Ví dụ INC-001 Detection có đoạn trích thẳng từ log:

```
freshness_check=FAIL {"latest_exported_at": "2026-04-10T08:00:00", ...}
event_json={"task_id": "D10-T05", "level": "ERROR", "event": "freshness_check", ...}
```

**Trade-off:** Runbook gắn chặt với run cụ thể (`dung-after-final`) nên nếu nhóm đổi run_id thì cần cập nhật. Đổi lại, giảng viên có thể verify ngay mà không cần đoán.

---

## 3. Một sự cố tôi phát hiện và xử lý

**Vấn đề: Template `pipeline_architecture.md` ghi sai điểm đo freshness.**

Template ban đầu mô tả sơ đồ chỉ là `raw → clean → validate → embed → serving` và ghi điểm đo freshness là "sau khi embed". Sau khi đọc `etl_pipeline.py` dòng 155:

```python
latest_exported = max((r.get("exported_at") or "" for r in cleaned), default="")
```

Và `monitoring/freshness_check.py` hàm `check_manifest_freshness()` đọc `latest_exported_at` từ manifest — tức là freshness được đo từ `exported_at` trong CSV (thời điểm upstream export), **không phải** thời điểm chạy pipeline hay thời điểm embed xong.

Tôi sửa diagram để ghi chú rõ:
```
exported_at = 2026-04-10T08:00:00  ← đây là điểm đo FRESHNESS_INGEST
```

**Bằng chứng trước/sau:**

| | Trước (template) | Sau (đã sửa) |
|---|---|---|
| Điểm đo freshness | "Sau khi embed xong" (sai) | `exported_at` trong raw CSV (đúng) |
| Bảng owner | Trống — "___" | Đủ 6 hàng, task_id từ `contracts/task_owner_map.json` |
| Số liệu | placeholder "..." | raw=10, cleaned=4, quarantine=6 từ `manifest_dung-after-final.json` |

Phát hiện này quan trọng: nếu team giải thích sai "freshness đo ở publish step", giảng viên sẽ hỏi vặn và nhóm không trả lời được từ code thực.

---

## 4. Tự đánh giá

**Làm tốt:** Bảng `metric_impact` trong `group_report.md` liên kết từng rule với file chứng cứ cụ thể (`dung_before_bad_eval.csv`, `quarantine_d10-c2.csv`, log line `expectation[refund_no_stale_14d_window] OK`). Điều này đáp ứng đúng yêu cầu của SCORING.md: "nhóm không điền metric_impact → dễ bị trừ khi tranh chấp".

**Còn yếu:** Tôi viết docs sau khi nhóm đã chạy pipeline xong, nên không phát hiện sớm được vấn đề freshness FAIL để báo lên D10-T01 kịp thời. Trong thực tế, docs owner nên có mặt từ Sprint 1 để cùng thiết kế schema log.

**Nhóm phụ thuộc vào tôi:** `group_report.md` với bảng `metric_impact` — thiếu bảng này nhóm bị trừ điểm chống trivial theo SCORING.

**Tôi phụ thuộc vào:** D10-T02 (rule names trong `cleaning_rules.py`) và D10-T03 (expectation names trong log) để điền đúng tên vào bảng metric_impact và runbook.

---

## 5. Nếu có thêm 2 giờ

Tôi sẽ bổ sung **mục Prevention của INC-001** bằng cách thêm expectation `exported_at_freshness` vào `quality/expectations.py` — halt nếu max(`exported_at`) < now − 24h. Hiện tại freshness chỉ được check ở bước monitor (sau embed), nhưng nếu check sớm ở bước validate thì pipeline dừng trước khi embed dữ liệu cũ vào ChromaDB. Bằng chứng cần thiết: `expectation[exported_at_freshness] FAIL (halt)` xuất hiện trong log trước dòng `embed_upsert`.

---

*Day 10 Lab — AI in Action · VinUniversity · 2026 · D10-T04*
