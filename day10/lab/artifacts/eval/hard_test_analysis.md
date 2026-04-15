# Hard Test Evaluation — Phân tích kết quả tự đánh giá

**Ngày chạy:** 2026-04-15  
**Bộ câu hỏi:** `data/hard_test_questions.json` (15 câu)  
**Kết quả raw:** `artifacts/eval/hard_test_eval.csv`  
**Cấu hình:** top-k=5, model=all-MiniLM-L6-v2, collection=day10_kb

---

## 1. Bảng tổng kết

| ID | Độ khó | contains_expected | hits_forbidden | top1_correct | PASS? |
|----|--------|:-----------------:|:--------------:|:------------:|:-----:|
| h01_refund_paraphrase | medium | ✅ | ✅ | ✅ | ✅ PASS |
| h02_refund_digital_exception | hard | ❌ | ✅ | ❌ | ❌ FAIL |
| h03_refund_flash_sale | hard | ❌ | ✅ | ✅ | ❌ FAIL |
| h04_p1_resolution_not_response | hard | ✅ | ❌ (15 phút xuất hiện) | ✅ | ❌ FAIL |
| h05_p2_sla | medium | ❌ | ❌ (hits 15 phút/4 giờ) | ✅ | ❌ FAIL |
| h06_hr_leave_experienced | hard | ❌ | ❌ (hits 12 ngày) | ✅ | ❌ FAIL |
| h07_hr_leave_carryover | hard | ❌ | ✅ | ✅ | ❌ FAIL |
| h08_hr_sick_leave | medium | ❌ | ❌ | ❌ | ❌ FAIL |
| h09_access_level3_approver | hard | ❌ | ✅ | ❌ | ❌ FAIL |
| h10_access_emergency_duration | hard | ❌ | ✅ | ❌ | ❌ FAIL |
| h11_password_expiry | medium | ❌ | ✅ | ✅ | ❌ FAIL |
| h12_vpn_device_limit | medium | ❌ | ✅ | ✅ | ❌ FAIL |
| h13_refund_no_answer | hard | ✅ | ✅ | ❌ | ⚠️ PARTIAL |
| h14_sla_old_version | hard | ❌ | ❌ (hits 4 giờ) | ✅ | ❌ FAIL |
| h15_remote_work_mandatory_days | medium | ❌ | ✅ | ❌ | ❌ FAIL |

**Tổng:** 1/15 PASS (6.7%), 1 PARTIAL, 13 FAIL

---

## 2. Phân tích nguyên nhân gốc rễ

### Root Cause #1 — Vector DB thiếu corpus (chiếm ~50% lỗi)

Pipeline chỉ embed chunks từ `data/raw/policy_export_dirty.csv` (10 dòng → sau clean ~7 dòng).  
Các file `.txt` trong `data/docs/` **KHÔNG được embed** vào ChromaDB.

**Ảnh hưởng:**
- `access_control_sop` hoàn toàn không có trong index → h09, h10, h15 fail hoàn toàn
- `it_helpdesk_faq.txt` có rất nhiều nội dung (password expiry, VPN limit) nhưng chỉ có 1 chunk duy nhất trong CSV (về account lockout)  
  → h11 (password expiry), h12 (VPN limit) không tìm được đúng chunk

**Fix đề xuất:**
```python
# Trong cmd_embed_internal: đọc thêm .txt docs
docs_dir = ROOT / "data" / "docs"
for txt in docs_dir.glob("*.txt"):
    doc_id = txt.stem
    content = txt.read_text(encoding="utf-8")
    # chunk theo section (split bằng "===")
    sections = [s.strip() for s in content.split("===") if s.strip()]
    for i, sec in enumerate(sections):
        ids.append(f"{doc_id}__sec{i}")
        documents.append(sec)
        metadatas.append({"doc_id": doc_id, "source": "docs_txt"})
```

---

### Root Cause #2 — Chunk quá thô, một chunk chứa nhiều giá trị mâu thuẫn

Chunk từ `sla_p1_2026` trong CSV:
> "Ticket P1 có SLA phản hồi ban đầu 15 phút và resolution trong 4 giờ."

Chunk này chứa đồng thời **cả hai** giá trị: `15 phút` (first response) và `4 giờ` (resolution).

**Ảnh hưởng:**
- h04: câu hỏi về "resolution" → muốn "4 giờ" không có "15 phút" → **hits_forbidden=yes**
- h05: câu về P2 SLA → top-k trả về chunk P1 → **cả hai bị forbidden**
- h14: câu về SLA cũ (6 giờ) → chunk hiện tại trả về "4 giờ" → **hits_forbidden=yes**

**Fix đề xuất:**  
Tách chunk SLA thành 2 chunk riêng: 1 cho first_response, 1 cho resolution.

---

### Root Cause #3 — Semantic drift: câu hỏi về chủ đề X → retrieval trả về Y

Nhiều câu (h08, h09, h15) trả về top1 là `it_helpdesk_faq` mặc dù không liên quan.  
Nguyên nhân: `it_helpdesk_faq` chunk về "5 lần đăng nhập sai" có **embedding đủ gần** với các câu hỏi về IT/access vì domain overlap.

**Bằng chứng:** Top1 cho h09 (access level approver) → `sla_p1_2026`, không phải `access_control_sop`  
Top1 cho h08 (sick leave) → `it_helpdesk_faq` thay vì `hr_leave_policy`

**Fix đề xuất:**  
Thêm metadata filter theo `department` hoặc tăng số chunk (rerank).

---

### Root Cause #4 — Version confusion trong cùng một doc (hr_leave_policy)

CSV chứa 2 chunk hr_leave_policy:
- chunk 7: "10 ngày phép năm (bản HR 2025)" — **bản cũ**
- chunk 8: "12 ngày phép năm theo chính sách 2026" — **bản mới**

Câu h06 hỏi về nhân viên ≥5 năm (18 ngày) → không có chunk nào cover → trả về chunk dưới-3-năm (12 ngày) → **hits_forbidden=yes** (12 ngày có mặt trong top-k)

**Fix đề xuất:**  
Embed đầy đủ `hr_leave_policy.txt` theo section (3 mức phép năm sẽ được phân tách thành chunk riêng).

---

## 3. Tóm tắt điểm yếu hệ thống

| Điểm yếu | Mức độ nghiêm trọng | Câu ảnh hưởng |
|-----------|:-------------------:|---------------|
| Corpus chưa đủ (thiếu txt docs) | 🔴 CRITICAL | h09, h10, h11, h12, h15 |
| Chunk quá coarse (multi-fact chunk) | 🟠 HIGH | h04, h05, h14 |
| Semantic drift (domain overlap) | 🟡 MEDIUM | h06, h07, h08 |
| Thiếu chunk về ngoại lệ/exception | 🟡 MEDIUM | h02, h03 |
| Câu hỏi về lịch sử phiên bản | 🟡 MEDIUM | h14 |

---

## 4. Câu pass: Phân tích h01

**h01_refund_paraphrase**: "Đơn hàng tôi muốn trả lại, tôi có bao lâu để gửi yêu cầu?"

Pass vì:
- Từ "trả lại" và "bao lâu" → semantic similarity cao với chunk về "7 ngày làm việc kể từ xác nhận"
- top1 đúng doc (`policy_refund_v4`) vì chunk này có semantic match tốt
- forbidden keyword "14 ngày" chỉ có trong chunk bị quarantine → **KHÔNG xuất hiện trong index**

→ Đây là câu **duy nhất** pipeline xử lý tốt vì cleaning pipeline đã loại đúng stale chunk.

---

## 5. Kết luận

**Điểm số thực tế:** 1/15 = 6.7%  
**Điểm số tiềm năng (nếu embed đầy đủ txt docs + tách chunk):** ước tính 10-12/15 (67-80%)

Đây là bằng chứng cho thấy:
1. **Bước ingest/embed là bottleneck chính** — không phải model embedding
2. **Cleaning pipeline đang hoạt động đúng** (stale chunk bị loại → h01 pass)
3. **Design lỗi**: pipeline thiết kế để đọc CSV thay vì đọc trực tiếp từ doc store
