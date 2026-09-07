# Kiểm toàn kệ — manual fast path

## Scope

Mode này ưu tiên kiểm **action Gắn tem hiện hành** theo POG/vị trí. Camera/template/OCR không nằm trong critical path và sẽ được phát triển sau.

## Luồng vận hành

1. Mở `/scan-tem?mode=shelf` (không cần đăng nhập Admin).
2. Tải workbook action `.xlsx`.
3. Chọn kệ theo POG/vị trí.
4. Mỗi action hiện một sản phẩm với ITEMID, tên, CTKM, giá và ngày cần thấy trên tem.
5. Bấm **Đúng** hoặc **Sai**; nếu Sai chọn lý do. Sau khi lưu sẽ tự chuyển sang action chưa kiểm kế tiếp trong cùng kệ.
6. Progress lưu ngay trên thiết bị, theo **ngày + context workbook**.
7. Mục **Sai & Review** gom toàn bộ action lỗi để kiểm lại và đánh dấu đã sửa.

## Quyền và cách ly

Shelf mode không dùng Admin token. Workbook được parse vào một session tạm thời, có token ngẫu nhiên, TTL và giới hạn số session; session này không thay đổi context scanner/Admin toàn cục.

## Lý do sai chuẩn

- Sai giá
- Sai ngày
- Sai CTKM
- Thiếu tem
- Dư tem
- Sai sản phẩm
- Khác

## Ngoài scope hiện tại

- Template từ file in tem.
- Nhận diện ảnh/camera live.
- OCR tự động.
- Đồng bộ tiến độ đa thiết bị/server-side.
