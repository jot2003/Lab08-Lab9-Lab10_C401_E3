# Data Contract — IT Helpdesk Tickets
> Day 10 Lab · Trợ lý IT nội bộ CS + IT Helpdesk

---

## Giới thiệu

Data contract là bản thoả thuận giữa **producer** (hệ thống ghi ticket) và **consumer** (ETL pipeline + RAG agent) về schema, kiểu dữ liệu, ràng buộc và SLA. Contract này được kiểm tra tự động mỗi lần pipeline chạy qua `quality/expectations.py`.

---

## Dataset: `helpdesk_tickets`

**Source:** Hệ thống IT Helpdesk nội bộ (CSV export)  
**Owner:** IT Support Team  
**Consumer:** ETL Pipeline → Vector Store → RAG Agent  
**Frequency:** Export hàng ngày (batch), tối thiểu 1 lần/24h  

---

## Schema Contract

| Cột | Kiểu | Bắt buộc | Giá trị hợp lệ | Ví dụ |
|-----|------|----------|----------------|-------|
| `ticket_id` | string | **Có** | Format TKT-\d+ | `TKT-001` |
| `message` | string | **Có** | Không null, không rỗng | `"Không truy cập được email"` |
| `timestamp` | datetime | **Có** | ISO 8601 (`YYYY-MM-DD HH:MM:SS`) | `2026-04-14 09:00:00` |
| `channel` | string | **Có** | `email` \| `chat` \| `phone` | `email` |
| `priority` | string | **Có** | `low` \| `medium` \| `high` | `high` |
| `resolution_minutes` | integer | Không | [0, 10080] (max 7 ngày) | `45` |

---

## Ràng buộc (Constraints)

### Uniqueness
- `ticket_id` phải là duy nhất trong mỗi batch
- Nếu phát hiện duplicate: **giữ bản đầu tiên, xoá các bản sau**

### Completeness
- `ticket_id` và `message`: **không được null** — dòng thiếu hai trường này sẽ bị xoá
- `timestamp`, `channel`, `priority`: null được phép nhưng **cần được flag** trong quality report

### Validity
- `channel`: chỉ nhận `email`, `chat`, `phone` (lowercase)
  - Các biến thể không hợp lệ: `EMAIL`, `E-MAIL`, `Chat` → chuẩn hoá hoặc xoá
- `priority`: chỉ nhận `low`, `medium`, `high`
  - Mapping: `urgent` → `high`, `critical` → `high`
  - Các giá trị khác → flag là invalid
- `resolution_minutes`: phải >= 0 và <= 10080
  - Giá trị âm → đặt về `NULL` (không xoá dòng)
  - Giá trị > 10080 → đặt về `NULL`

### Timeliness (Freshness SLA)
- Dữ liệu **mới nhất** trong batch không được cũ hơn **48 giờ**
- WARN: cũ hơn **24 giờ**
- FAIL: cũ hơn **48 giờ**

---

## Quy tắc làm sạch (Cleaning Rules)

Được implement trong `transform/cleaning_rules.py`:

```
1. parse_timestamps      → str → datetime, parse error → NULL
2. normalize_channel     → lowercase + map về allowed set
3. normalize_priority    → lowercase + map urgent/critical → high
4. fix_resolution_time   → âm hoặc > 10080 → NULL
5. remove_duplicates     → dedup ticket_id, keep=first
6. drop_missing_required → xoá dòng thiếu ticket_id hoặc message
```

**Thứ tự quan trọng:** parse_timestamps phải chạy trước các bước khác để đảm bảo timestamp là datetime object khi cần so sánh.

---

## SLA Cam kết

| Chỉ số | Ngưỡng | Hành động khi vi phạm |
|--------|--------|----------------------|
| Data freshness | ≤ 24h | WARN trong monitor report |
| Data freshness | ≤ 48h | FAIL — trigger alert |
| Quality pass_rate | ≥ 85% | Pipeline tiếp tục + ghi cảnh báo |
| Quality pass_rate | < 85% | Pipeline tiếp tục + escalate |
| Null rate (critical cols) | ≤ 10% | WARN |
| Null rate (critical cols) | > 30% | FAIL |
| Duplicate rate | = 0% | Dedup tự động |

---

## Quy trình xử lý khi breach

```
Phát hiện freshness breach (> 48h)
    ↓
1. Kiểm tra hệ thống export: có job nào fail không?
2. Kiểm tra file source có được cập nhật không?
3. Nếu chưa update: liên hệ IT Support Team để re-export
4. Chạy lại pipeline với file mới
5. Verify: freshness_check trả về PASS
6. Ghi post-mortem vào runbook
```

---

## Versioning

| Version | Ngày | Thay đổi |
|---------|------|---------|
| v1.0 | 2026-04-15 | Initial contract — Day 10 Lab |

---

## Liên hệ

| Vai trò | Trách nhiệm |
|---------|------------|
| Data Producer | IT Support System — export CSV hàng ngày |
| Data Consumer | ETL Pipeline (Day 10) + RAG Agent (Day 08) |
| Contract Owner | Monitoring/Docs Owner (Nguyễn Thành Nam) |

---

*Day 10 Lab — AI in Action · VinUniversity · 2026*
