# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** C401-E3  
**Thành viên:**

| Tên | Vai trò (Day 10) | task_id |
|-----|------------------|---------|
| Hoang Kim Tri Thanh | Pipeline Integration & Embed Owner | D10-T00, D10-T05 |
| Dang Dinh Tu Anh | Ingestion & Schema Owner | D10-T01 |
| Quach Gia Duoc | Cleaning & Transformation Owner | D10-T02 |
| Pham Quoc Dung | Quality & Grading Evidence Owner | D10-T03 |
| Nguyen Thanh Nam | Docs & Runbook Owner | D10-T04 |

**Ngày nộp:** 2026-04-15  
**Repo:** https://github.com/jot2003/Lab8-Lab9-Lab10_C401_E3  
**Run ID chính:** `dung-after-final`  
**Artifact chính:** `artifacts/manifests/manifest_dung-after-final.json`

---

## 1. Pipeline tổng quan

**Nguồn raw:** `data/raw/policy_export_dirty.csv` — 10 records mô phỏng export từ upstream DB/API, bao gồm 5 loại tài liệu nội bộ (policy_refund_v4, sla_p1_2026, it_helpdesk_faq, hr_leave_policy, và 1 doc legacy không hợp lệ). File có `exported_at = 2026-04-10T08:00:00`.

**Chuỗi lệnh chạy end-to-end:**
```bash
cd day10/lab
pip install -r requirements.txt
cp .env.example .env
python etl_pipeline.py run --run-id <run_id>
python eval_retrieval.py --out artifacts/eval/<run_id>_eval.csv
python grading_run.py --out artifacts/eval/grading_run.jsonl
```

**Lấy run_id từ log:** Dòng đầu tiên của `artifacts/logs/run_<run_id>.log`:
```
run_id=dung-after-final
event_json={"ts": "2026-04-15T08:23:18...", "event": "run_start", ...}
```

**Kết quả run `dung-after-final`:**
```
raw_records       = 10
cleaned_records   = 4
quarantine_records= 6
freshness_check   = FAIL  (exported_at delta ≈ 5 ngày > SLA 24h)
PIPELINE_OK       ✓
```

Manifest: `artifacts/manifests/manifest_dung-after-final.json`  
Cleaned: `artifacts/cleaned/cleaned_dung-after-final.csv`  
Quarantine: `artifacts/quarantine/quarantine_dung-after-final.csv`

---

## 2. Cleaning & expectation

### 2a. Bảng metric_impact (**bắt buộc**)

| Rule / Expectation mới (tên ngắn) | Trước — inject (`--no-refund-fix`) | Sau — clean (`dung-after-final`) | Chứng cứ |
|-----------------------------------|------------------------------------|----------------------------------|-----------|
| `refund_window_fix` (14→7 ngày) | chunk_id=3 trong index; `hits_forbidden=yes` cho q_refund_window | chunk_id=3 quarantined; `hits_forbidden=no` | `dung_before_bad_eval.csv` vs `dung_after_final_eval.csv` |
| `hr_stale_version` (effective_date < 2026-01-01) | chunk_id=7 "10 ngày phép (HR 2025)" có thể retrieval | chunk_id=7 quarantined; q_leave_version trả về "12 ngày (2026)" | `quarantine_dung-after-final.csv` |
| `allowlist_doc_id` (legacy_catalog bị block) | chunk_id=9 `legacy_catalog_xyz_zzz` có thể lọt vào index | chunk_id=9 quarantined | `quarantine_d10-c2.csv`, `quarantine_dung-after-final.csv` |
| `effective_date_iso` (reject date format sai) | chunk_id=10 `effective_date=01/02/2026` (DD/MM/YYYY) có thể gây lỗi downstream | chunk_id=10 quarantined | `quarantine_d10-c3.csv` |
| `no_empty_chunk` (reject text rỗng) | chunk_id=5 text="" lọt vào index | chunk_id=5 quarantined | log `event_json` rule `empty_text` |
| Expectation `doc_id_in_allowlist` [halt] | Khi inject: halt nếu doc_id lạ lọt qua | Sau clean: pass vì chunk 9 đã bị rule filter trước | `artifacts/logs/run_dung-after-final.log` |
| Expectation `refund_no_stale_14d_window` [halt] | Khi inject: chunk "14 ngày" vào cleaned → FAIL → halt | Sau clean: `violations=0` → PASS | log `expectation[refund_no_stale_14d_window] OK (halt) :: violations=0` |

**Rule chính (reason code từ `transform/cleaning_rules.py`):**
- `unknown_doc_id`: quarantine doc_id không trong allowlist `{policy_refund_v4, sla_p1_2026, it_helpdesk_faq, hr_leave_policy}`
- `missing_chunk_text`: quarantine chunk có `chunk_text` rỗng hoặc null
- `stale_refund_migration_marker`: quarantine chunk refund chứa "bản sync cũ" hoặc "policy-v3"
- `stale_hr_policy_effective_date`: quarantine chunk HR có `effective_date` < 2026-01-01
- `duplicate_chunk_text`: quarantine chunk trùng nội dung text (giữ bản đầu)
- `non_iso_effective_date_source`: quarantine dòng có `effective_date` không theo ISO YYYY-MM-DD

**Ví dụ 1 lần expectation fail:**

Khi chạy pipeline với inject scenario (chunk stale lọt qua cleaning), log ghi:
```
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
WARN: expectation failed → pipeline HALT trước bước embed
```
→ Kết quả eval: `q_refund_window` → `hits_forbidden=yes` (bằng chứng inject hoạt động đúng).

---

## 3. Before / after ảnh hưởng retrieval

**Kịch bản inject (Sprint 3):**

Chạy pipeline với flag `--no-refund-fix --skip-validate` để bỏ qua rule quarantine chunk_id=3 (stale refund "14 ngày") và không dừng khi expectation fail. Chunk này lọt vào ChromaDB collection `day10_kb` và được retrieval khi hỏi về hoàn tiền.

**Kết quả định lượng:**

| Câu hỏi | Before (inject) | After (clean) | Thay đổi |
|---------|-----------------|---------------|---------|
| q_refund_window | `hits_forbidden=yes`, top1="14 ngày làm việc" | `hits_forbidden=no`, top1="7 ngày làm việc" | ✓ Fix |
| q_p1_sla | `hits_forbidden=no` | `hits_forbidden=no` | — không đổi |
| q_lockout | `hits_forbidden=no` | `hits_forbidden=no` | — không đổi |
| q_leave_version | `contains_expected=yes` | `contains_expected=yes`, `top1_doc_expected=yes` | ✓ Tốt hơn |

**Nguồn chứng cứ:**
- Before: `artifacts/eval/dung_before_bad_eval.csv`
- After: `artifacts/eval/dung_after_final_eval.csv`
- Grading JSONL: `artifacts/eval/dung_grading_run.jsonl`

**Kết luận:** Cleaning pipeline (đặc biệt `refund_window_fix` và `hr_stale_version`) trực tiếp cải thiện retrieval quality — giảm `hits_forbidden` từ 1/4 xuống 0/4 câu, tăng `top1_doc_expected` từ 1/4 lên 2/4 câu.

---

## 4. Freshness & monitoring

**SLA chọn:** `FRESHNESS_SLA_HOURS=24` (1 ngày) — phù hợp với chu kỳ export daily của upstream policy DB.

| Status | Điều kiện | Ý nghĩa |
|--------|-----------|---------|
| PASS | delta < 12h | Dữ liệu đủ mới, embed tiếp tục bình thường |
| WARN | 12h ≤ delta < 24h | Cảnh báo, pipeline vẫn chạy, cần kiểm tra upstream |
| FAIL | delta ≥ 24h | Vi phạm SLA; ghi `level=ERROR` vào log; xem runbook INC-001 |

Trong run `dung-after-final`: `latest_exported_at=2026-04-10`, delta ≈ 5 ngày → `freshness_check=FAIL`.  
Đây là hành vi mong đợi với data mẫu có `exported_at` cố định. Trong production, fix bằng cách export lại với timestamp mới.

Manifest mẫu: `artifacts/manifests/manifest_dung-after-final.json`  
Log event: `"event": "freshness_check", "level": "ERROR"`

---

## 5. Liên hệ Day 09

Pipeline Day 10 và Day 09 **dùng chung nội dung tài liệu** (5 docs TXT trong `data/docs/`) nhưng có **index riêng**:

- **Day 09:** `retrieval_worker.py` query trực tiếp TXT files → ChromaDB collection `day09_docs`
- **Day 10:** `etl_pipeline.py` xử lý CSV export → embed vào collection `day10_kb`

Nếu muốn Day 09 workers dùng index đã làm sạch từ Day 10, đổi `.env` của Day 09:
```
CHROMA_COLLECTION=day10_kb
```
Điều này đảm bảo agent Day 09 không retrieval được chunk "14 ngày" (đã quarantine) khi trả lời câu hỏi về hoàn tiền.

---

## 6. Rủi ro còn lại & việc chưa làm

| Rủi ro | Mức | Lý do chưa làm |
|--------|-----|----------------|
| Freshness FAIL sẽ tiếp tục khi data mẫu không đổi | CAO | `exported_at` cố định trong CSV mẫu; trong production cần export mới |
| Chưa có alert tự động (email/Slack) khi freshness FAIL | TRUNG | Ngoài scope lab; cần tích hợp thêm |
| Eval chỉ 4 câu hỏi — coverage thấp | TRUNG | Đủ để demo before/after; cần mở rộng bộ test |
| chunk_id=10 (malformed date) vào quarantine nhưng nội dung có thể vẫn hữu ích | THẤP | Rule cần làm sạch date thay vì drop hoàn toàn |
| `all-MiniLM-L6-v2` không tối ưu cho tiếng Việt | THẤP | Đủ cho lab; production cần model tiếng Việt (PhoBERT, BGE-M3...) |

---

*Day 10 Lab — AI in Action · VinUniversity · 2026*
