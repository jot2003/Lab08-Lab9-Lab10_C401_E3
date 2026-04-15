# Quality report — Lab Day 10 (nhóm)

**run_id:** dung-after-final  
**Ngày:** 2026-04-15

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước | Sau | Ghi chú |
|--------|-------|-----|---------|
| raw_records | 10 | 10 | Cùng raw export để so sánh công bằng |
| cleaned_records | 6 (baseline sprint1) | 4 (final clean) | Final clean quarantine thêm stale marker + source-date non-ISO |
| quarantine_records | 4 (baseline sprint1) | 6 (final clean) | Tăng do rule mới D10-T02 |
| Expectation halt? | Không halt | Không halt | Các expectation halt đều pass trong run final |

---

## 2. Before / after retrieval (bắt buộc)

Evidence file:
- Before/bad: `artifacts/eval/dung_before_bad_eval.csv`
- After/final: `artifacts/eval/dung_after_final_eval.csv`

**Câu hỏi then chốt:** refund window (`q_refund_window`)  
**Trước:** top1 preview có "14 ngày làm việc", `hits_forbidden=yes`.  
**Sau:** top1 preview đổi thành "7 ngày làm việc", `hits_forbidden=no`.

**Merit check (khuyến nghị):** `q_leave_version`
- `contains_expected=yes`
- `hits_forbidden=no`
- `top1_doc_expected=yes`

---

## 3. Freshness & monitor

`freshness_check=FAIL` trên run final (`manifest_dung-after-final.json`) vì dữ liệu mẫu có `latest_exported_at=2026-04-10T08:00:00`, vượt SLA 24h. Đây là expected behavior của monitor với snapshot cũ, không phải pipeline crash.

---

## 4. Corruption inject (Sprint 3)

Inject stale context theo hướng migration cũ (`policy-v3`/`bản sync cũ`) để tái hiện lỗi retrieval chứa forbidden phrase "14 ngày". Sau khi bật full cleaning + rerun publish snapshot, forbidden context bị loại khỏi top-k.

---

## 5. Hạn chế & việc chưa làm

- Chưa có dashboard trực quan; hiện kiểm chứng qua log/CSV/manifest.
- Chưa theo dõi distribution drift tự động.
- Cần duy trì `grading_questions.json` chuẩn rubric để tránh fallback ngoài ý muốn.
