# Hướng Dẫn Deploy Ứng Dụng Lên Render.com Với Docker

Tài liệu này hướng dẫn bạn cách triển khai công cụ **Facebook Post Reaction & Interaction Scanner** lên nền tảng đám mây [Render.com](https://render.com) bằng **Docker** (hỗ trợ đầy đủ FastAPI và Playwright Chromium).

---

## 1. Các File Cấu Hình Đã Chuẩn Bị Sẵn

Trong dự án, các file phục vụ deploy đã được tạo hoàn chỉnh:
- [Dockerfile](file:///d:/postercontest/Dockerfile): Build môi trường Python 3.11-slim, cài đặt đầy đủ Playwright Chromium và các thư viện hệ thống Linux cần thiết.
- [.dockerignore](file:///d:/postercontest/.dockerignore): Loại bỏ các file tạm, cache, file log và thư mục thử nghiệm để Docker build nhanh và nhẹ nhất.
- [render.yaml](file:///d:/postercontest/render.yaml): File Render Blueprint cấu hình sẵn service, region và biến môi trường.

---

## 2. Hướng Dẫn Từng Bước Deploy Lên Render

### Bước 1: Đẩy mã nguồn lên GitHub
1. Khởi tạo Git và commit toàn bộ code (nếu chưa làm):
   ```bash
   git init
   git add .
   git commit -m "Configure Docker & Render deployment"
   ```
2. Tạo một Repository mới trên GitHub (chọn Public hoặc Private đều được).
3. Đẩy code lên GitHub:
   ```bash
   git remote add origin https://github.com/<tai-khoan-cua-ban>/<ten-repo>.git
   git branch -M main
   git push -u origin main
   ```

---

### Bước 2: Tạo Web Service trên Render.com
1. Truy cập [dashboard.render.com](https://dashboard.render.com) và đăng nhập (bằng GitHub).
2. Bấm nút **New +** ở góc trên bên phải, chọn **Web Service**.
3. Chọn tùy chọn **Build and deploy from a Git repository**.
4. Chọn repository GitHub bạn vừa đẩy lên ở Bước 1 (nếu chưa thấy, bấm *Configure account* để cấp quyền truy cập repo).
5. Điền thông tin cấu hình dịch vụ:
   - **Name**: `fb-interaction-scanner` (hoặc tên bất kỳ bạn thích).
   - **Region**: Chọn **Singapore** (gần Việt Nam nhất, độ trễ thấp và quét Facebook nhanh nhất).
   - **Branch**: `main`.
   - **Runtime**: Chọn **Docker** (Render thường sẽ tự động nhận diện `Dockerfile`).
   - **Instance Type / Plan**:
     - *Khuyên dùng*: **Starter** ($7/tháng - 1 vCPU, 1GB RAM). Vì Playwright Chromium khi cuộn Facebook tải hàng trăm avatar và bài viết cần khoảng 400MB - 700MB RAM. Gói Starter sẽ đảm bảo trình duyệt chạy cực kỳ mượt mà, không bao giờ bị tràn RAM (OOM).
     - *Thử nghiệm*: Bạn vẫn có thể chọn gói **Free** (0.5 CPU, 512MB RAM) cho mục đích test hoặc bài viết có lượng tương tác vừa phải.
6. Bấm **Create Web Service**.

---

### Bước 3: Chờ Render Build và Lấy Link Web
1. Render sẽ tự động pull code, build Docker image, tải Chromium và khởi chạy server Uvicorn.
2. Quá trình build lần đầu tiên thường mất khoảng **2 - 4 phút**.
3. Khi thấy log báo:
   ```text
   Application startup complete.
   Uvicorn running on http://0.0.0.0:10000
   ==> Your service is live 🎉
   ```
4. Bấm vào đường link URL do Render cấp (dạng `https://fb-interaction-scanner.onrender.com`) để mở và sử dụng ngay lập tức!

---

## 3. Các Điểm Tối Ưu Đã Được Cấu Hình Tự Động Trong Code

1. **Tự động nhận diện Port**: Ứng dụng tự động đọc biến môi trường `$PORT` do Render cấp (mặc định 10000) và bind vào `0.0.0.0`.
2. **Cờ tối ưu Chromium Container**: 
   - Code Playwright trong [scraper.py](file:///d:/postercontest/scraper.py) đã được gắn sẵn các cờ bắt buộc cho Docker:
     `--no-sandbox`, `--disable-setuid-sandbox`, `--disable-dev-shm-usage`, `--disable-gpu`.
   - Giúp Chromium không bị crash bộ nhớ chia sẻ `/dev/shm` trên Linux container.
3. **Headless Tự Động**:
   - Khi chạy trên Cloud (không có màn hình GUI `DISPLAY`), hệ thống tự động ép chế độ `headless = True` để bảo đảm không bị lỗi thiếu giao diện đồ họa.
4. **Hỗ trợ Quét File HTML / Token Graph API**:
   - Bên cạnh việc quét tự động bằng Playwright, bạn vẫn có thể tải mã nguồn HTML bài viết về máy và dán vào quét hoặc dùng Access Token để quét với tốc độ cao.
