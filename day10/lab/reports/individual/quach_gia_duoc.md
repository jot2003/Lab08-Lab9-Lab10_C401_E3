# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Data Observability

**Họ và tên:** Quách Gia Được  
**Mã số sinh viên:** 2A202600423  
**Vai trò:** Cleaning & Transformation Owner (D10-T02)  
**Ngày nộp:** 15/04/2026  
**Độ dài:** ~520 từ

---

## 1. Tôi phụ trách phần nào?

Trong Day 10, tôi phụ trách task D10-T02 theo phân công nhóm: làm sạch dữ liệu, dedupe, parse date và quarantine logic. File tôi trực tiếp chỉnh là `day10/lab/transform/cleaning_rules.py`; ngoài ra tôi chịu trách nhiệm tạo evidence cho phần quarantine ở `day10/lab/artifacts/quarantine/`.

Phần tôi triển khai tập trung vào bốn nhóm việc chính:

- Chuẩn hóa payload quarantine, tách helper dùng lại và thống nhất reason constants để log dễ theo dõi.
- Bổ sung kiểm tra contract dữ liệu nguồn: `exported_at` phải là ISO datetime, `effective_date` nguồn không nhận dạng `DD/MM/YYYY`.
- Bổ sung rule quarantine cho nội dung refund có marker migration cũ (`policy-v3`, `bản sync cũ`) để chặn context stale trước khi publish.
- Tạo evidence quarantine cho hai run `d10-c2` và `d10-c3` để nhóm có số liệu đối chiếu trước/sau.

Về phối hợp: tôi nhận đầu vào raw từ nhánh ingest (D10-T01), đẩy cleaned/quarantine sang các bước expectation và grading (D10-T03), đồng thời để integration owner (D10-T00/T05) dùng manifest/log chốt release.

---

## 2. Một quyết định kỹ thuật

Quyết định quan trọng nhất của tôi là siết contract dữ liệu ngay tại tầng cleaning, thay vì để sai lệch trôi sang expectation hoặc retrieval.

Cụ thể:

- `exported_at` thiếu hoặc sai format sẽ bị quarantine ngay.
- `effective_date` nguồn dạng `DD/MM/YYYY` cũng bị quarantine (dù có thể convert được), vì dữ liệu upstream phải tuân thủ format ISO đầu vào.
- Chunk refund có dấu hiệu migration cũ (`policy-v3`, `bản sync cũ`) không được cho vào cleaned để tránh lọt context stale vào vector store.

Lý do tôi chọn cách này: nếu normalize quá “dễ dãi”, pipeline vẫn chạy xanh nhưng chất lượng knowledge base bị bẩn âm thầm; đến lúc query fail mới phát hiện thì chi phí sửa cao hơn. Với chiến lược quarantine sớm, lỗi được gắn reason rõ ràng để team truy ngược nguồn và sửa đúng chỗ.

---

## 3. Một lỗi/anomaly tôi đã xử lý

Anomaly tôi xử lý là chunk refund chứa nội dung cũ: “14 ngày làm việc … bản sync cũ policy-v3 — lỗi migration”.

Ở run `d10-c2`, dòng này chưa có reason chuyên biệt, nên dù đã có các rule khác, dữ liệu vẫn chưa được phân loại đúng mức rủi ro migration. Tôi dùng số liệu để xác nhận triệu chứng:

- `manifest_d10-c2.json`: `cleaned_records=5`, `quarantine_records=5`.
- Quarantine chưa có reason `stale_refund_migration_marker`.

Sau đó tôi bổ sung một rule mới để bắt riêng marker migration cũ. Kết quả ở run `d10-c3`:

- `manifest_d10-c3.json`: `cleaned_records=4`, `quarantine_records=6`.
- `quarantine_d10-c3.csv` có thêm reason `stale_refund_migration_marker` cho đúng dòng refund cũ.

Đây là thay đổi có tác động đo được, không phải chỉnh sửa hình thức.

---

## 4. Bằng chứng trước / sau

| run_id | cleaned_records | quarantine_records | Điểm khác biệt chính |
|---|---:|---:|---|
| `d10-c2` | 5 | 5 | Chưa có reason migration marker riêng |
| `d10-c3` | 4 | 6 | Có thêm `stale_refund_migration_marker=1` |

Bằng chứng log ownership cũng khớp phân công D10-T02 trong `artifacts/logs/run_d10-c3.log`:

- `event="cleaned_count"`, `task_id="D10-T02"`, `owner="Quach Gia Duoc"`.
- `event="quarantine_count"`, `task_id="D10-T02"`, `owner="Quach Gia Duoc"`.

Như vậy phần tôi làm vừa có bằng chứng định lượng (delta cleaned/quarantine), vừa có trace owner trong log.

---

## 5. Cải tiến tiếp theo (nếu có thêm 2 giờ)

Nếu có thêm thời gian, tôi sẽ làm 2 việc:

1. Chuyển các marker stale/migration sang cấu hình trong contract (thay vì hard-code), để có thể mở rộng rule mà không phải sửa code nhiều.
2. Viết test tự động cho `clean_rows` theo case chuẩn: `exported_at` thiếu/sai, `effective_date` non-ISO source, refund migration marker.

Mục tiêu là biến các rule cleaning từ “đúng ở run hiện tại” thành “ổn định, kiểm thử được, và dễ bảo trì khi dữ liệu nguồn thay đổi”.