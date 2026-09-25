# CTKM Pipeline

Hệ thống tổng hợp **chương trình khuyến mãi (CTKM Monthly + Clearance)** với
**vị trí kệ POG**, tạo danh sách thao tác gắn/tháo tem, audit nguồn, phân bổ Tem R
và kiểm tra hạn dùng.

## Mapping cột

Gemini **không phải nguồn mapping mặc định**. Thứ tự hiện tại là:

1. mapping người dùng xác nhận;
2. preset đã lưu;
3. mapping deterministic cho file Pharmacity chuẩn;
4. mapping cache đã được validate;
5. Gemini chỉ là fallback khi bốn nguồn trên không đủ.

`mapping_mode=saved_only` là chế độ **zero-Gemini**. Vì vậy `GEMINI_API_KEY`
có thể để trống nếu chỉ dùng file chuẩn/preset/cache. Nếu một file lạ thực sự cần
AI nhưng server không có API key, request dừng ở preflight với lỗi rõ ràng trước
khi tạo job.

Giá trị nghiệp vụ nguồn như ITEMID, tên sản phẩm, ngày, giá, KEY Channel, Channel,
store/POG fields không bị normalize rồi ghi đè. Các khóa normalize chỉ tồn tại ở
field kỹ thuật dùng để đối chiếu/identity.

## Cấu trúc chính

```text
main.py                         Public pipeline facade
main_core.py                    Pipeline implementation core
backend/main_api.py             Hardened FastAPI entrypoint
backend/main_api_core.py        API implementation core; không deploy trực tiếp
backend/contract_suite.py       Cài + verify runtime/API contracts theo thứ tự cố định
modules/1_loader.py             Loader facade
modules/5_normalizer.py         Source-safe mapping/normalization/unpivot
modules/7_joiner.py             CTKM Monthly ↔ POG reconciliation
modules/8_reconciler.py         Action, overlap, location, task identity
modules/9_exporter.py           Excel report facade
modules/10_tem_r.py             Tem R facade
modules/11_expiration_checker.py Kiểm tra hạn dùng
frontend/                       React/Vite UI
```

Các facade/core riêng được giữ để compatibility với code cũ. Deployment luôn dùng
`backend.main_api:app`; không dùng `backend.main_api_core:app`.

## Cài đặt local

Yêu cầu khuyến nghị: Python 3.11, Node.js 20+.

```bash
cp .env.example .env
# Bắt buộc đổi ADMIN_PASSWORD và ADMIN_SESSION_SECRET.
# GEMINI_API_KEY chỉ cần nếu muốn dùng AI fallback.

bash start.sh --setup
bash start.sh
```

Windows:

```bat
start.bat --setup
start.bat
```

Frontend: `http://localhost:5173`  
Backend: `http://localhost:8000`  
Swagger: `http://localhost:8000/docs`

## Deploy

Docker/Render chạy một Uvicorn worker:

```text
python -m uvicorn backend.main_api:app --host 0.0.0.0 --port $PORT
```

Queue/job state hiện là process-local, vì vậy không tăng `--workers` nếu chưa
chuyển queue/job store sang shared storage. Render Blueprint dùng `render.yaml` và
Dockerfile hiện tại. Blueprint đặt `autoDeployTrigger: checksPass`, vì vậy deploy
tự động chỉ bắt đầu sau khi CI của commit trên branch liên kết đã pass.

Admin workflows cần `ADMIN_PASSWORD` và `ADMIN_SESSION_SECRET`. `GEMINI_API_KEY`
chỉ cần nếu muốn hỗ trợ mapping AI fallback. `/api/health` trả thêm:

```json
{
  "contract_suite": "v1",
  "contracts_ok": true,
  "contract_order": ["runtime", "input", "mapping-result", "..."],
  "main_facade_hooks": ["mapping-result-contract-v1", "backend-contract-suite-verify-v1"]
}
```

Nếu contract bắt buộc bị route khác ghi đè, backend fail ở startup/reload thay vì
âm thầm chạy implementation legacy.

### Xếp lịch nhân viên

Module xếp lịch chạy stateless: tạo phương án, chỉnh tay, validate và xuất Excel trực tiếp.
Lịch làm việc không được lưu trên server; Excel là đầu ra cần giữ. Validate chỉ cung cấp
cảnh báo/gợi ý nghiệp vụ; nếu người dùng chủ động xuất thì workbook vẫn được tạo từ đúng
lịch hiện tại. Chỉ lỗi kỹ thuật/dữ liệu cấu trúc không đủ để dựng workbook mới dừng export.

### Lưu ý persistence trên Render Free

`render.yaml` hiện dùng plan `free`. Workflow preset và mapping cache đang lưu file
local lần lượt tại `logs/workflow_presets.json` và `logs/mapping_cache.json`.
Filesystem của Render Free là ephemeral, nên các file này có thể mất khi service
spin-down, restart hoặc redeploy. Mapping deterministic cho file Pharmacity chuẩn
không phụ thuộc hai file này; nhưng nếu cần giữ custom preset/cache lâu dài thì phải
chuyển chúng sang shared durable storage trước khi coi “mapping đã lưu” là dữ liệu
bền vững qua vòng đời instance.

### Quyền truy cập CTKM / Tem

Các thao tác nghiệp vụ cửa hàng như inspect CTKM/POG, preview mapping, chạy pipeline,
theo dõi đúng job vừa tạo, xem preview/tải kết quả, Tem R và kiểm tem là store-facing:
không yêu cầu đăng nhập admin. Hệ thống hiện chưa có role user thường riêng nên các
route này hoạt động không cần bearer admin.

Các bề mặt quản trị dùng chung vẫn giữ admin: preset backend, queue status, job history,
cấu hình quản trị và module xếp lịch hiện tại.

## CTKM / POG semantics

### Phạm vi tháng

Một promotion được giữ trong operational month khi:

- khoảng ngày promotion giao với tháng mục tiêu; **hoặc**
- ngày tháo tem (`promo_to + 1 ngày`) nằm trong tháng mục tiêu.

Dòng thiếu/sai ngày không bị xóa; nó được giữ để `Cần review`.

### Mã sản phẩm cũ / mới

Monthly/Clearance có thể chứa mã nguồn và mã mới trong giai đoạn chuyển đổi. Hệ
thống giữ raw `item_id` làm identity nguồn, nhưng cho phép POG/comparison match
qua cặp mã cũ↔mới **chỉ khi alias P-code là một-một và không mơ hồ**. One-to-many,
chain hoặc mã mới đồng thời là direct source code sẽ không được tự remap.

### Channel / scope

`KEY Channel` và `Channel` luôn là hai field riêng. Raw source không đổi. Một
operational scope key normalize case/spacing chỉ dùng để tránh duplicate thao tác
như `Offline` vs `OFFLINE`; stable `promotion_id/task_id` nguồn vẫn được giữ.

Overlap cùng scope có thể blocking. All-channel với Online/Offline hoặc các scope
khác vẫn được báo để audit nhưng không tự động block nếu contract không chứng minh
hai offer cùng một phạm vi vận hành.

### POG month và vị trí

`scheduled_action` độc lập với chất lượng POG. Một CTKM vẫn có thể là `gắn tem`
trong khi POG cần review. Các trục chính gồm:

- `location_completeness`;
- `pog_month_status`;
- `location_needs_review`;
- `pog_applicable`.

Explicit `item_id=Bill` được coi là chương trình hóa đơn hợp lệ nhưng
`pog_applicable=False`; các P-code có mô tả "purchase bill ..." vẫn là SKU và vẫn
đối chiếu POG bình thường.

## Excel kết quả

Các sheet chính:

| Sheet | Ý nghĩa |
|---|---|
| `HƯỚNG DẪN` | Card số lượng theo đúng visible business rows |
| `Gắn tem` | Unique operational tasks cần gắn tem |
| `Tháo tem` | Unique operational tasks cần tháo tem |
| `Chờ gắn` | Task chưa đến ngày gắn |
| `Cần review` | Task có lỗi dữ liệu hoặc blocking conflict |
| `Audit hành động` | Toàn bộ action/source lineage, kể cả dòng được gom ở work sheet |
| `CTKM thieu vi tri ke` | Audit các promotion thiếu/không đủ vị trí POG |
| `POG cần kiểm tra` | Vị trí cần review, gồm POG lệch/không rõ tháng khi áp dụng |
| `Tong hop` | **Monthly + Clearance ↔ POG** reconciliation cho toàn bộ KM trong scope |
| `POG không có KM` | POG không có bất kỳ Monthly/Clearance KM phù hợp trong scope |
| `POG không có Monthly CTKM` | Audit lịch sử Monthly-only, tên explicit để không bị hiểu là all-KM |
| `POG không có CTKM` | Compatibility sheet hidden; cùng nghĩa all-KM gap như `POG không có KM` |
| `POG cần review` | Dòng POG business thiếu mã/khóa cần review |
| `Canh bao trung thoi gian` | Blocking và non-blocking overlap diagnostics |
| `Xác nhận CTKM Clearance` | So sánh Monthly và Clearance |
| `Tom tat` | Canonical summary metrics; alias cũ gây hiểu nhầm được ẩn |
| `Mapping log` | Nguồn mapping: manual/preset/standard/cache/Gemini; hidden |

Nếu nguồn chứa các control rows POG (`Total`, `Applied filters/DATEID`) hoặc fact
subtotal/Grand Total đã được chứng minh structurally, chúng không đi vào nghiệp vụ
nhưng vẫn được giữ nguyên lineage/value trong các sheet hidden `POG metadata` và
`KM metadata`.

### All-KM POG coverage và Monthly audit

`Tong hop` là coverage người dùng nhìn thấy và phải phản ánh **toàn bộ KM trong
scope (Monthly ∪ Clearance) có POG**. Một SKU Clearance-only có POG không được bị
loại khỏi `Tong hop` chỉ vì Monthly reconciliation không match.

`POG không có KM` là audit user-facing cho POG thực sự không có bất kỳ KM nào
trong scope. Audit Monthly-only vẫn được giữ riêng ở `POG không có Monthly CTKM`.
Sheet legacy `POG không có CTKM` chỉ còn cho compatibility, bị hidden và mang cùng
nghĩa all-KM gap với `POG không có KM` để không tái tạo cách hiểu sai cũ.

Pipeline enforce invariant cuối export:

- mọi SKU thuộc `(Monthly ∪ Clearance) ∩ POG` phải có coverage trong `Tong hop`;
- metric `So item KM+POG thieu trong Tong hop` phải bằng `0`;
- metric canonical cho gap all-KM vẫn dùng tên `... KM ...`, ví dụ:
  `So dong POG khong co KM phu hop`, `So item POG khong co KM phu hop`.

Legacy key `... CTKM ...` còn tồn tại cho frontend compatibility nhưng phải bằng
canonical alias và bị ẩn trong `Tom tat` khi tên cũ gây hiểu nhầm.

## Preview API

Preview đọc **workbook cuối cùng mà người dùng nhìn thấy**:

- không trả `HƯỚNG DẪN` như DataTable;
- không trả hidden metadata sheets;
- không trả hidden technical columns/rows;
- sheet placeholder `Ghi chu / Không có ...` có `total_rows=0`;
- `total_rows` là số visible non-empty business rows, không phải `max_row - 1`.

## Tem R

Tem R dùng chung heavy-job queue với CTKM. API preflight kiểm sheet/header/mapping,
cột tồn kho và resource limit trước khi nhận job. Final workbook được validate lại
trước khi job thành `completed`.

Tồn kho được quản lý ở cấp `(STOREID, ITEMID)` để không nhân stock khi cùng SKU có
nhiều vị trí POG. Stock `#N/A`, thiếu hoặc không hợp lệ không được coi là 0 để cấp
Tem R; chúng đi vào audit/exception theo contract hiện tại.

## Kiểm tra hạn dùng

Endpoint hạn dùng vẫn public. Input entry dùng format:

```text
MÃ_P;SỐ_LÔ;DD/MM/YYYY
```

Ngày yêu cầu phải đúng `DD/MM/YYYY`. File Excel phải là XLSX hợp lệ, có ITEMID
business rows và nằm trong giới hạn resource. Concurrency quá giới hạn fail-fast
`503` thay vì chiếm threadpool chờ vô hạn.

## API chính

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/health` | Health + contract-suite status |
| `POST` | `/api/jobs/ctkm` | Preflight + queue CTKM/POG/Clearance |
| `POST` | `/api/run` | Alias compatibility của CTKM queue |
| `GET` | `/api/job/{job_id}/status` | Trạng thái job |
| `GET` | `/api/queue/status` | Queue state, admin |
| `GET` | `/api/preview/{job_id}` | Visible workbook preview |
| `GET` | `/api/download/{job_id}` | Download chỉ khi job completed + output hợp lệ |
| `GET` | `/api/jobs` | Job history, admin |
| `POST` | `/api/inspect-tem-r` | Inspect Tem R, store-facing |
| `POST` | `/api/jobs/tem-r` | Queued Tem R, store-facing |
| `POST` | `/api/check-expiration` | Kiểm tra hạn dùng, public |

## Kiểm tra trước merge/release

Repository có GitHub Actions tại `.github/workflows/ci.yml`. Release gate tối thiểu:

```bash
pip install -r requirements-dev.txt
python -m compileall -q main.py main_core.py backend modules tests
pytest -q
npm --prefix frontend ci
npm --prefix frontend run build
docker build -t ctkm-pipeline .
```

CI không cấu hình Gemini key để chứng minh standard/preset/cache paths không phụ
thuộc AI ngoài ý muốn. Docker build chỉ chạy sau khi Python tests và frontend build
đều pass.

Không merge chỉ dựa vào việc file Excel được tạo ra: final-output contract còn kiểm
required sheets, summary ↔ sheet counts, guide cards, hidden metadata và canonical
vs legacy metric invariants trước khi job được publish.
