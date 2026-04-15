# Runbook — Lab Day 10: Data Pipeline Incident Response

**Owner (D10-T04):** Nguyễn Thành Nam (2A202600205)  
**Cập nhật:** 2026-04-15  
**Áp dụng cho:** `day10/lab/` pipeline — `policy_export_dirty.csv` → clean → embed → `day10_kb`

> Mỗi incident ghi theo đúng 5 mục: **Symptom → Detection → Diagnosis → Mitigation → Prevention**.  
> Số liệu trích từ run thực tế: `run_id=dung-after-final`, manifest tại `artifacts/manifests/manifest_dung-after-final.json`.

---

## INC-001 — Freshness FAIL: Dữ liệu export quá cũ

### Symptom

Agent trả lời đúng về nội dung policy nhưng phiên bản có thể đã lỗi thời. Khi hỏi về chính sách hoàn tiền hoặc SLA mới nhất, câu trả lời dựa trên snapshot từ ngày xa so với hiện tại. User/auditor không thể biết dữ liệu trong vector store đến từ khi nào.

Ví dụ cụ thể từ run `dung-after-final`:
```
latest_exported_at = "2026-04-10T08:00:00"
run_timestamp      = "2026-04-15T08:23:18"
→ delta = 120.388h (≈ 5.02 ngày) — vượt SLA 24h
```

### Detection

Metric báo trong log `artifacts/logs/run_dung-after-final.log`:

```
freshness_check=FAIL {"latest_exported_at": "2026-04-10T08:00:00", "age_hours": 120.388, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}
event_json={"ts": "2026-04-15T08:23:18...", "level": "ERROR", "task_id": "D10-T05", "event": "freshness_check", ...}
```

Đọc nhanh manifest:
```bash
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_dung-after-final.json
```

Kết quả `FAIL` khi `latest_exported_at` < (now − `FRESHNESS_SLA_HOURS`).  
Mặc định `FRESHNESS_SLA_HOURS=24` (đặt trong `.env`).

### Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Mở `artifacts/manifests/manifest_*.json` mới nhất | Kiểm tra `latest_exported_at` và `run_timestamp` |
| 2 | Tính delta: `run_timestamp - latest_exported_at` | > 24h → FAIL; 12–24h → WARN; < 12h → PASS |
| 3 | Kiểm tra `data/raw/policy_export_dirty.csv` | Xem `exported_at` của dòng mới nhất — nếu cùng ngày cũ: vấn đề ở upstream export |
| 4 | Chạy `python eval_retrieval.py` | Nếu `contains_expected` vẫn đúng → nội dung chưa thay đổi, rủi ro thấp; nếu sai → cần rollback |

**Root cause điển hình:**
- Hệ thống upstream (DB/API) chưa export lại CSV sau khi có bản policy mới
- Job export chạy nhưng file không được copy vào `data/raw/`
- `exported_at` trong CSV là timestamp của lần export trước (pipeline tính theo max của cột này)

### Mitigation

```bash
# Bước 1: Lấy file export mới từ upstream
cp /path/to/new_export.csv day10/lab/data/raw/policy_export_dirty.csv

# Bước 2: Chạy lại pipeline với run-id mới
cd day10/lab
python etl_pipeline.py run --run-id recovery-$(date +%Y%m%d)

# Bước 3: Verify freshness
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_recovery-*.json
# Mong đợi: PASS hoặc WARN

# Bước 4: Re-run eval để xác nhận chất lượng
python eval_retrieval.py --out artifacts/eval/recovery_eval.csv
```

Nếu không có export mới ngay:
- Thêm banner "data last updated: YYYY-MM-DD" vào giao diện agent
- Ghi incident vào bảng post-mortem (cuối runbook)
- **Không rollback embed** trừ khi có bằng chứng nội dung sai (xem `hits_forbidden` trong eval)

### Prevention

1. **Đặt alert tự động:** thêm bước `freshness_check` vào CI/CD — job fail nếu `FAIL`
2. **Tăng tần suất export:** từ hàng tuần → hàng ngày; cấu hình cron upstream
3. **Đo 2 boundary:** log cả `ingest_timestamp` (khi pipeline đọc file) và `publish_timestamp` (khi embed xong) vào manifest — phân biệt "data cũ" vs "pipeline chậm"
4. **Mở rộng expectation:** thêm check `exported_at_freshness` vào `quality/expectations.py` (hiện chưa có) để halt khi tất cả dòng đều có `exported_at` cũ hơn SLA

---

## INC-002 — Stale Refund Chunk: Chunk "14 ngày" từ migration v3 lọt vào index

### Symptom

Agent trả lời sai về thời hạn hoàn tiền: nói **"14 ngày làm việc"** thay vì **"7 ngày"** theo policy v4 hiện hành. Đây là lỗi nghiêm trọng vì ảnh hưởng trực tiếp đến quyền lợi khách hàng và có thể gây khiếu nại.

Bằng chứng trước khi fix (`artifacts/eval/dung_before_bad_eval.csv`):
```
q_refund_window | top1_preview: "...trong vòng 14 ngày làm việc..." | hits_forbidden=yes
```

### Detection

Metric báo trong eval CSV (`hits_forbidden=yes`):

```csv
q_refund_window,...,Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày...,yes,yes,,3
```

Kiểm tra nhanh trong raw CSV:
```
chunk_id=3, doc_id=policy_refund_v4
chunk_text="Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày làm việc kể từ xác nhận đơn
           (ghi chú: bản sync cũ policy-v3 — lỗi migration)."
```

Chunk 3 chứa từ khoá "lỗi migration" và số ngày sai (14 thay vì 7) — đây là tàn dư từ lần sync policy-v3.

### Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Mở `data/raw/policy_export_dirty.csv` | Tìm chunk có `chunk_text` chứa "14 ngày" hoặc "v3" hoặc "migration" |
| 2 | Kiểm tra `effective_date` của chunk đó | Nếu `effective_date` cũ hơn policy hiện hành → stale |
| 3 | Mở `artifacts/quarantine/quarantine_*.csv` | Chunk này có bị quarantine không? Nếu không → rule chưa bắt được |
| 4 | Chạy `python eval_retrieval.py` với `--no-refund-fix` | Xác nhận `hits_forbidden=yes` → bằng chứng inject hoạt động đúng |
| 5 | Chạy lại với fix bình thường | Xác nhận `hits_forbidden=no`; trong log: `expectation[refund_no_stale_14d_window] OK (halt) :: violations=0` |

**Root cause:** Hệ thống export đồng bộ nhầm cả chunk từ policy-v3 (cũ) cùng với policy-v4 (hiện hành). Không có rule kiểm tra nội dung "stale marker" ("lỗi migration", "bản sync cũ").

### Mitigation

```bash
# Confirm rule đang hoạt động (pipeline bình thường):
python etl_pipeline.py run --run-id fix-refund-check

# Xác nhận chunk 3 vào quarantine:
cat artifacts/quarantine/quarantine_fix-refund-check.csv
# Mong đợi: chunk_id=3 xuất hiện trong file này

# Verify eval sau fix:
python eval_retrieval.py --out artifacts/eval/fix_refund_eval.csv
# Mong đợi: q_refund_window → hits_forbidden=no, top1_preview chứa "7 ngày"
```

Kết quả sau khi fix (`artifacts/eval/dung_after_final_eval.csv`):
```
q_refund_window | top1_preview: "Yêu cầu được gửi trong vòng 7 ngày làm việc..." | hits_forbidden=no
```

→ **Raw: 10 records → Cleaned: 4 records, Quarantine: 6 records** (bao gồm chunk 3)

### Prevention

1. **Rule "refund window fix"** trong `transform/cleaning_rules.py`: quarantine bất kỳ chunk nào có `chunk_text` chứa "14 ngày" kết hợp "hoàn tiền" hoặc chứa marker "lỗi migration" / "bản sync cũ"
2. **Expectation `no_forbidden_content`** trong `quality/expectations.py`: halt nếu bất kỳ cleaned chunk nào matches danh sách pattern cấm
3. **Upstream fix:** yêu cầu team export kiểm tra và xoá các chunk có annotation "v3" hoặc "migration" trước khi export
4. **Thêm field `policy_version`** vào schema để pipeline có thể filter chính xác theo version

---

## Bảng Post-mortem

| Ngày | run_id | Incident | Root cause | Cách fix | Người xử lý | Time to resolve |
|------|--------|----------|------------|----------|-------------|-----------------|
| 2026-04-15 | dung-after-final | INC-001: freshness FAIL | exported_at=2026-04-10, delta≈5 ngày > SLA 24h | Ghi nhận, chờ export mới; thêm freshness expectation | D10-T04 (Nam) | — |
| 2026-04-15 | dung-after-final | INC-002: stale refund chunk | chunk_id=3 "14 ngày" từ v3 migration lọt vào index | apply_refund_window_fix=True → chunk 3 quarantined | D10-T02 (Được) + D10-T04 (Nam document) | Sprint 2→3 |

---

*Day 10 Lab — AI in Action · VinUniversity · 2026 · D10-T04 owner: Nguyễn Thành Nam*
