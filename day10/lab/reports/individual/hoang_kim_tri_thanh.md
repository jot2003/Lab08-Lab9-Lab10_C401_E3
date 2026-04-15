# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Hoang Kim Tri Thanh  
**Vai trò:** Embed & Idempotency Owner (D10-T05) + Integration Lead (D10-T00)  
**Ngày nộp:** 15/04/2026  
**Độ dài:** ~530 từ

---

## 1. Tôi phụ trách phần nào?

File/module chính: `etl_pipeline.py` (hàm `cmd_embed_internal`, `_load_txt_chunks`, `_split_into_paragraphs`), `monitoring/freshness_check.py`, `contracts/task_owner_map.json`, `grading_questions.json`, `final_readiness_check.py`.

**D10-T05 (Embed & Idempotency):** triển khai bước nhúng vector vào ChromaDB, bao gồm idempotency (so sánh `prev_ids` vs `all_ids` rồi prune ID cũ trước khi upsert) và đảm bảo toàn bộ corpus `data/docs/*.txt` được embed, không chỉ 4 dòng từ CSV sau cleaning.

**D10-T00 (Integration Lead):** thiết lập `contracts/task_owner_map.json` để mọi log event tự ghi `task_id` + `owner`; điều phối merge các nhánh (Tu Anh → Duoc → Dung → main); chạy `final_readiness_check.py` để chốt submission gate.

**Kết nối với thành viên:** nhận `artifacts/cleaned/cleaned_dung-after-final.csv` từ D10-T02 (Duoc) làm đầu vào embed; cung cấp ChromaDB collection `day10_kb` cho D10-T03 (Dung) chạy `grading_run.py`.

**Bằng chứng:** hàm `_load_txt_chunks` và `_split_into_paragraphs` trong `etl_pipeline.py`; file `contracts/task_owner_map.json`; `artifacts/logs/run_dung-after-final.log`.

---

## 2. Một quyết định kỹ thuật

**Chọn 2-level chunking (section → paragraph/bullet) thay vì flat section-level.**

Khi embed lần đầu chỉ tách theo ranh giới `===` (mỗi section là 1 chunk), các query như "SLA P1 là bao lâu?" hay "nhân viên dưới 3 năm được mấy ngày phép?" đều trả về chunk dài chứa nhiều tier (P1, P2, P3 hoặc <3 năm, 3–10 năm, >10 năm) cùng lúc, làm loãng nội dung và `all-MiniLM-L6-v2` không tách được fact chính xác.

Quyết định: thêm `_split_into_paragraphs` chia tiếp mỗi section theo dòng trống và marker phụ (`Ticket P\d`, `Level \d`, `\d+\.\d+\s`, `Q:`) với ngưỡng bullet ≥ 5 dòng mới tách để tránh phá vỡ danh sách quan hệ nhân quả. Chunk count tăng từ 38 (sau bước 1) lên 79. Hard test score tăng từ 7/15 lên 11/15.

---

## 3. Một sự cố / anomaly đã xử lý

**Toàn bộ corpus `data/docs/*.txt` không được embed — ChromaDB chỉ chứa 4 chunks.**

Triệu chứng: chạy `eval_retrieval.py` với `data/hard_test_questions.json` (15 câu tự tạo) → chỉ **2/15** pass. Kiểm tra `col.count()` bằng `debug_pipeline.py` → 4 chunks, trong khi corpus có 5 file txt (`policy_refund_v4`, `hr_leave_policy`, `access_control_sop`, `sla_p1_2026`, `it_helpdesk_faq`).

Nguyên nhân gốc: `cmd_embed_internal` chỉ đọc và embed các dòng từ `cleaned_csv` (4 dòng sau cleaning), bỏ qua hoàn toàn thư mục `data/docs/`.

Fix: thêm hàm `_load_txt_chunks(docs_dir, run_id)` đọc tất cả `*.txt`, split theo `===`, ghép với chunks từ CSV, rồi gọi chung 1 lần `col.upsert()`. Log sau fix (trích từ `run_dung-after-final.log`):

```
event_json={"task_id": "D10-T05", "owner": "Hoang Kim Tri Thanh",
            "event": "embed_upsert_count", "message": "upserted=79"}
```

Hard test tăng từ **2/15 → 7/15** ngay sau bước này, trước khi thêm paragraph splitting.

---

## 4. Bằng chứng trước / sau

| Artifact | Hard test pass | Ghi chú |
|---|---|---|
| `artifacts/eval/hard_test_eval.csv` | **2 / 15** | ChromaDB 4 chunks; trước khi fix embed |
| `artifacts/eval/hard_test_iter05.csv` | **11 / 15** | ChromaDB 79 chunks; sau 2-level chunking |

Official run `run_id=dung-after-final` — `grading_run.jsonl`:

```
gq_d10_01: contains_expected=True, hits_forbidden=False       → PASS
gq_d10_02: contains_expected=True, hits_forbidden=False       → PASS
gq_d10_03: contains_expected=True, hits_forbidden=False,
           top1_doc_matches=True                              → PASS  (3/3 MERIT_CHECK)
```

---

## 5. Cải tiến tiếp theo (nếu có thêm 2 giờ)

Tích hợp BM25 sparse retrieval song song với dense embedding, sau đó dùng Reciprocal Rank Fusion (RRF) để gộp kết quả. Đặc biệt cần thiết với corpus tiếng Việt: các từ ghép như "phép năm" vs "nghỉ phép" hay "P1 incident" vs "sự cố ưu tiên cao" bị drift nghĩa với `all-MiniLM-L6-v2` — BM25 khắc phục được qua exact-match token. Ước tính cải thiện thêm 2–3/15 câu hiện đang fail do semantic drift.
