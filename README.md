# CTKM Pipeline

Tổng hợp **chương trình khuyến mãi (CTKM)** × **vị trí kệ (POG)** theo tháng,
dùng **Gemini API** nhận diện tên cột linh hoạt.

---

## Cấu trúc

```
ctkm_pipeline/
├── start.sh                        ← Khởi động 1 lệnh (backend + frontend)
├── main.py                         ← CLI / hàm run_pipeline() cho code khác gọi
├── .env.example                    ← Copy thành .env, điền GEMINI_API_KEY
├── requirements.txt                ← Deps cho CLI
│
├── backend/
│   ├── main_api.py                 ← FastAPI: /api/run, /api/preview, /api/download
│   └── requirements_backend.txt   ← Deps cho backend (gồm cả pipeline deps)
│
├── frontend/
│   ├── src/App.jsx                 ← React UI toàn bộ (1 file)
│   ├── vite.config.js              ← Proxy /api → localhost:8000
│   └── package.json
│
├── modules/                        ← 9 module pipeline core (không đổi)
│   ├── 1_loader.py
│   ├── 2_sheet_classifier.py
│   ├── 3_column_mapper.py          ← Gọi Gemini API
│   ├── 4_mapping_cache.py          ← Cache tránh gọi Gemini lại
│   ├── 5_normalizer.py             ← Apply mapping, parse, unpivot
│   ├── 6_time_filter.py            ← Lọc CTKM theo overlap tháng
│   ├── 7_joiner.py                 ← Outer join CTKM × POG
│   ├── 8_reconciler.py             ← Phát hiện campaign chồng thời gian
│   └── 9_exporter.py              ← Xuất Excel 6 sheet
│
├── config/                         ← 4 file JSON cấu hình
└── logs/                           ← mapping_cache.json (tự tạo khi chạy)
```

---

## Cài đặt & chạy

### Lần đầu

```bash
cd ctkm_pipeline
cp .env.example .env
# Mở .env, điền: GEMINI_API_KEY=your_key_here

bash start.sh --setup    # cài Python deps + npm install
```

> **Yêu cầu:** Python 3.10+, Node.js 18+

### Chạy hàng ngày

```bash
bash start.sh
```

Mở trình duyệt: **http://localhost:5173**

## Deploy lên Render

Repository đã được cấu hình để build React và phục vụ giao diện cùng FastAPI
trong một Docker service:

1. Đẩy source code lên GitHub/GitLab (không commit file `.env`).
2. Trên Render, tạo Blueprint từ repository; Render sẽ đọc `render.yaml`.
3. Nhập secret `GEMINI_API_KEY` và `ADMIN_PASSWORD` khi được yêu cầu.
   `ADMIN_SESSION_SECRET` được Render tự sinh. Tên đăng nhập mặc định là `admin`;
   có thể đổi bằng biến `ADMIN_USERNAME`.
4. Sau khi deploy, kiểm tra `/api/health` và mở URL gốc để dùng giao diện.

Khách không cần đăng nhập và chỉ thấy chức năng kiểm tra hạn dùng. Admin đăng
nhập ở thanh trên cùng để mở Công cụ CTKM và Phân bổ Tem R. Các API quản trị
cũng yêu cầu token admin, vì vậy việc phân quyền không chỉ dựa vào ẩn giao diện.

CTKM và Tem R dùng chung một hàng đợi nhẹ trong ứng dụng: mỗi lần chỉ xử lý một
tác vụ Excel nặng, mặc định nhận tối đa 5 tác vụ gồm cả đang chạy và đang chờ.
Có thể đổi giới hạn bằng `HEAVY_JOB_QUEUE_SIZE`. Kiểm tra hạn dùng chạy riêng và
không phải chờ hàng đợi này. Vì hàng đợi nằm trong bộ nhớ, nó sẽ mất khi Render
restart/redeploy.

Kiểm tra hạn dùng cho phép mặc định 5 lượt dò đồng thời (`EXPIRATION_CONCURRENCY`).
Nếu nhiều người tải lên cùng một file tồn kho, hệ thống nhận diện theo nội dung và
chỉ đọc Excel một lần; file gần nhất được giữ trong cache RAM
(`EXPIRATION_CACHE_SIZE=1`). CTKM/Tem R trả mã tác vụ ngay, sau đó giao diện tự
theo dõi trạng thái và vị trí hàng đợi của chính người dùng.

Giới hạn mặc định là 20 MB cho file hạn dùng, 25 MB cho Tem R và 50 MB cho mỗi
file CTKM/POG. Kết quả hết hạn sau 6 giờ và được dọn khi có yêu cầu mới.

Lưu ý: gói miễn phí dùng filesystem tạm thời. Kết quả Excel và mapping preset có
thể mất khi service restart/redeploy; cần persistent disk hoặc object storage nếu
muốn lưu lâu dài.

Kiểm tra trước khi đẩy code:

```bash
pip install -r requirements-dev.txt
pytest -q
npm --prefix frontend ci
npm --prefix frontend run build
docker build -t ctkm-pipeline .
```

---

## Dùng từ code / tích hợp hệ thống khác

```python
from main import run_pipeline

result = run_pipeline(
    ctkm_filepath = "file_ctkm_thang5.xlsx",
    pog_filepath  = "file_pog_thang5.xlsx",
    target_month  = "2026-05",          # frontend truyền vào
    business_date = "2026-05-15",       # tùy chọn; mặc định là ngày hiện tại theo giờ VN
    output_path   = "output/ket_qua.xlsx",
    fail_on_month_mismatch = False,     # True = dừng cứng nếu lệch tháng
)

print(result.output_filepath)   # đường dẫn file Excel xuất ra
print(result.warnings)          # list cảnh báo (lệch tháng, mapping ngờ vực…)
print(result.summary)           # dict số liệu tổng quan
```

---

## File kết quả Excel

| Sheet | Nội dung |
|---|---|
| `Tong hop` | CTKM phù hợp phạm vi tháng và có vị trí POG để đối chiếu |
| `CTKM thieu vi tri ke` | Chỉ các công việc không tìm thấy SKU hoặc thiếu một phần thông tin vị trí |
| `POG cần kiểm tra` | Vị trí cần review riêng, gồm thiếu vị trí hoặc snapshot POG lệch/không rõ tháng |
| `POG không có CTKM` | SKU có trên POG nhưng không có CTKM phù hợp trong dữ liệu/tháng đang xét — cần kiểm tra |
| `POG cần review` | Dòng POG thiếu mã sản phẩm hoặc không đủ khóa để đối chiếu |
| `Canh bao trung thoi gian` | Cặp campaign chồng ngày, có `conflict_type` và `is_blocking`; chỉ xung đột chặn mới vào `Cần review` |
| `Mapping log` | Gemini map cột nào, confidence bao nhiêu — để audit |
| `Tom tat` | Số liệu tổng + cảnh báo lệch tháng POG/CTKM |
| `Gắn tem` | Danh sách CTKM cần gắn tem, kèm vị trí kệ |
| `Tháo tem` | Danh sách CTKM cần tháo tem, kèm vị trí kệ |
| `Chờ gắn` | CTKM chưa đến ngày gắn theo ngày nghiệp vụ |
| `Cần review` | Dòng thiếu mã/tên chương trình, thiếu/sai ngày hoặc có xung đột chặn cần xác nhận |
| `Audit hành động` | Toàn bộ dữ liệu hành động, kể cả dòng ngoài phạm vi tháng, kèm lineage và ID ổn định |

---

## API endpoints (FastAPI)

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/run` | Upload 2 file + chọn tháng → chạy pipeline |
| `GET` | `/api/preview/{job_id}` | JSON preview dữ liệu (N dòng đầu mỗi sheet) |
| `GET` | `/api/download/{job_id}` | Download file Excel kết quả |
| `GET` | `/api/jobs` | Lịch sử job trong session hiện tại |
| `GET` | `/docs` | Swagger UI (tự động từ FastAPI) |

---

## Nguyên tắc thiết kế quan trọng

- **Gemini chỉ gán nhãn tên cột** — không được sửa/suy đoán giá trị dữ liệu thực tế.
- **Unpivot whitelist**: chỉ `campaign_detail` và `promo_price` được phép có nhiều slot
  trên 1 dòng. Field khác bị trùng slot → KHÔNG nhân dòng, ghi cảnh báo trong Mapping log.
- **Không mất dữ liệu âm thầm**: mọi trường hợp lệch đều được GIU LẠI và cảnh báo.
- **Overlap filter**: lọc CTKM theo `promo_from <= cuối_tháng AND promo_to >= đầu_tháng`
  — bắt trọn campaign chạy xuyên nhiều tháng.
- **Detect overlap TRƯỚC khi join**: tránh false positive do 1-nhiều POG nhân dòng.
- **Cache mapping** (`logs/mapping_cache.json`): tháng sau dùng cùng template Excel
  thì Gemini KHÔNG bị gọi lại.
