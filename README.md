# Facebook Contest Scoring & Anti-Spam Tool
> **Hệ Thống Chấm Điểm Cuộc Thi Thiết Kế Poster & Lọc Tương Tác Ảo / Spam Trên Facebook**

---

## 🎯 1. TỔNG QUAN & MỤC TIÊU (OVERVIEW)

Công cụ **Facebook Contest Scoring & Anti-Spam Tool** là giải pháp phần mềm chuyên nghiệp chạy trực tiếp trên máy cục bộ (`localhost`), hỗ trợ Quản trị viên Fanpage Facebook (Admin) tính điểm bình chọn minh bạch, tự động và công bằng cho các bài thi thiết kế poster dự thi.

### 🌟 Tính năng cốt lõi:
1. **Đăng nhập Quản trị viên Facebook 1 lần duy nhất (Admin Session):**
   - Lưu trữ cookies và phiên làm việc nội bộ tại thư mục `./fb_session` qua Playwright Persistent Context.
   - Vượt qua các lớp xác thực 2FA/CAPTCHA, giải quyết triệt để vấn đề bị Facebook chặn IP đám mây.
2. **Cào dữ liệu tự động 3 hạng mục tương tác:**
   - **Reactions (Chỉ lấy Like 👍 và Love ❤️):** Tự động mở hộp thoại cảm xúc, lọc riêng tab Thích và Yêu thích, cuộn tải toàn bộ danh sách.
   - **Bình luận (Comments):** Tự động chuyển chế độ sang *"Tất cả bình luận"* (*All comments*), tự động bấm *"Xem thêm bình luận"* lặp lại cho đến khi lấy hết bình luận cấp 1. Hỗ trợ thêm module Graph API siêu tốc nếu có Page Access Token.
   - **Lượt chia sẻ công khai (Public Shares):** Tự động mở hộp thoại người chia sẻ công khai và cuộn tải toàn bộ danh sách.
3. **Bộ lọc Chống Gian Lận & Lọc Nick Ảo (Anti-Spam & Bot Filtering Engine):**
   - **Rule 1: Lọc nick nước ngoài / bot ngoại quốc:**
     - Loại bỏ ngay lập tức nếu tên chứa ký tự CJK (Trung/Nhật/Hàn), Thái Lan, Ấn Độ (Devanagari/Bengali/Tamil...), Ả Rập, Nga (Cyrillic)...
     - Cho phép thông qua ngay nếu có dấu tiếng Việt (`[àáạảãâ...đ]`).
     - Nếu tên không dấu: Kiểm tra đối chiếu với từ điển họ và tên tiếng Việt thông dụng (hơn 150+ từ: *nguyen, tran, le, pham, hoang, huynh, anh, minh, tuan, thao, linh...*). Nếu 0 từ khớp (ví dụ: *Rahul Sharma, Priya Patel, John Smith, Mohammed Ali*) -> Phân loại vào nick ảo/nước ngoài không hợp lệ.
   - **Rule 2: Chống spam tương tác lặp lại (Deduplication):**
     - Chuẩn hóa URL trang cá nhân Facebook (loại bỏ tracking `?__cft__`, `comment_id`, `id=...`).
     - Trong cùng 1 hạng mục: 1 tài khoản hợp lệ tương tác $N$ lần ($N \ge 1$) chỉ được tính **1 lượt HỢP LỆ**, còn lại $N - 1$ lượt tính là **VI PHẠM (Spam tương tác lặp)**.
     - Tài khoản nước ngoài / bot tương tác $N$ lần: Tính **0 lượt hợp lệ**, toàn bộ $N$ lượt bị loại bỏ.
4. **Công thức tính điểm chung cuộc:**
   $$\text{Tổng Điểm} = (\text{Like+Love Hợp Lệ} \times 1) + (\text{Bình Luận Hợp Lệ} \times 2) + (\text{Chia Sẻ Hợp Lệ} \times 3)$$
5. **Giao diện Dashboard Single-Page trực quan & Can thiệp thủ công:**
   - Theo dõi tiến độ thời gian thực (Server-Sent Events / SSE).
   - Xem danh sách tài khoản Hợp lệ vs. Vi phạm/Spam với lý do cụ thể.
   - **Nút can thiệp thủ công ("Duyệt Hợp lệ" / "Chuyển sang Vi phạm"):** Admin có thể tự duyệt lại nick nghi vấn; hệ thống tự động cập nhật số liệu và tính toán lại Tổng điểm ngay lập tức trên giao diện.
6. **Xuất báo cáo kiểm toán đầy đủ sang Excel (`.xlsx`):**
   - Tạo file Excel nhiều sheet định dạng chuẩn (Tổng quan điểm, Hợp lệ & Vi phạm từng hạng mục).

---

## 🏗️ 2. CẤU TRÚC MÃ NGUỒN (PROJECT STRUCTURE)

```
d:/postercontest/
├── app.py                # Máy chủ FastAPI, API endpoints, xử lý tác vụ nền, xuất Excel
├── scraper.py            # Trình thu thập dữ liệu Playwright, quản lý session, Graph API, dữ liệu Demo
├── filters.py            # Bộ lọc ngôn ngữ tiếng Việt, Regex chữ tượng hình, khử trùng lặp & tính điểm
├── requirements.txt      # Danh sách thư viện Python cần thiết
├── fb_session/           # Thư mục lưu phiên đăng nhập Facebook Admin cục bộ
├── templates/
│   └── index.html        # Giao diện Dashboard SPA (TailwindCSS, Material Symbols, SSE)
└── README.md             # Tài liệu hướng dẫn sử dụng chi tiết
```

---

## 🚀 3. HƯỚNG DẪN CÀI ĐẶT & KHỞI CHẠY (LOCAL SETUP)

### Bước 1: Mở Terminal (PowerShell hoặc CMD) tại thư mục dự án
```powershell
cd d:\postercontest
```

### Bước 2: Cài đặt các thư viện Python
```powershell
pip install -r requirements.txt
```

### Bước 3: Cài đặt trình duyệt Chromium cho Playwright
```powershell
playwright install chromium
```

### Bước 4: Khởi động máy chủ ứng dụng
```powershell
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Mở trình duyệt bất kỳ và truy cập địa chỉ:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## 📖 4. HƯỚNG DẪN SỬ DỤNG CHI TIẾT

### 1. Thiết lập phiên Facebook Admin (Chỉ cần làm 1 lần đầu)
- Trên giao diện chính, click nút **"Admin Facebook Login"**.
- Một modal hướng dẫn hiện ra -> Nhấn **"Mở Trình Duyệt Đăng Nhập"**.
- Cửa sổ Chromium sẽ mở ra trang `facebook.com`.
- Bạn tiến hành đăng nhập tài khoản Facebook của mình (giải quyết 2FA/mã OTP nếu có).
- Khi đã vào được trang News Feed Facebook, bạn có thể đóng cửa sổ trình duyệt lại. Session đã được lưu vĩnh viễn trong `./fb_session`.
- Badge góc phải trên Dashboard sẽ chuyển sang màu xanh lá: `Admin Session: Đã lưu`.

### 2. Quét bài viết cuộc thi & Tính điểm
- Dán link bài viết Facebook dự thi vào ô input:
  Ví dụ: `https://www.facebook.com/yourfanpage/posts/1029384756`
- Nhấn **"Quét & Tính Điểm Cuộc Thi"**.
- Theo dõi thanh tiến độ phần trăm và nhật ký hoạt động thời gian thực.
- Khi hoàn tất:
  - Bảng tổng kết điểm chung cuộc sẽ hiển thị điểm chính thức kèm công thức chi tiết.
  - 3 khối thống kê Reactions, Comments, Shares thể hiện số lượng Hợp lệ vs. Vi phạm.
  - Bảng dữ liệu phía dưới cho phép chuyển đổi giữa các tab và lọc theo trạng thái tài khoản.

### 3. Kiểm tra thử nhanh với dữ liệu mẫu (Quick Demo)
- Nếu chưa có link bài viết thật hoặc chưa đăng nhập Facebook, nhấn ngay nút **"Dữ Liệu Mẫu (Demo)"** ở góc trên thanh điều hướng hoặc nhập link bất kỳ có chữ `demo`.
- Hệ thống sẽ nạp một tập dữ liệu giả lập thực tế gồm hàng chục thí sinh Việt Nam (có dấu và không dấu), nick spam comment nhiều lần, và các nick bot nước ngoài (Ấn Độ, Thái Lan, Trung Quốc, Ả Rập...) để bạn quan sát cơ chế lọc spam và tính điểm hoạt động.

### 4. Can thiệp thủ công (Manual Override)
- Tại bảng danh sách tài khoản, nếu phát hiện một tài khoản bị nghi ngờ (hoặc tài khoản thật bị nhận diện nhầm):
  - Nhấn nút **"Duyệt Hợp lệ"** (nếu đang ở danh sách Vi phạm) hoặc **"Chuyển sang Vi phạm"** (nếu đang ở danh sách Hợp lệ).
  - Hệ thống sẽ gửi yêu cầu về backend, chuyển đổi tài khoản, cập nhật số liệu và **tự động tính toán lại Tổng Điểm Chung Cuộc** ngay lập tức mà không cần tải lại trang.

### 5. Xuất báo cáo Excel (.xlsx)
- Nhấn nút **"Xuất Excel (.xlsx)"** trên bảng điểm.
- Trình duyệt sẽ tải về file `Facebook_Contest_Scoring_Report_[ID].xlsx` với 7 sheet chi tiết:
  1. `TongQuan_KetQua`: Tổng hợp điểm, công thức tính, số liệu chi tiết.
  2. `HopLe_Reactions`: Danh sách tài khoản Thả Like/Love hợp lệ.
  3. `ViPham_Reactions`: Danh sách tài khoản cảm xúc vi phạm/bot.
  4. `HopLe_BinhLuan`: Danh sách tài khoản bình luận hợp lệ & số cmt đã đăng.
  5. `ViPham_BinhLuan`: Danh sách tài khoản bình luận spam/bot.
  6. `HopLe_ChiaSe`: Danh sách tài khoản chia sẻ hợp lệ & số lượt share.
  7. `ViPham_ChiaSe`: Danh sách tài khoản chia sẻ vi phạm.

---

## 🛡️ 5. CƠ CHẾ BẢO MẬT & ĐỘ TIN CẬY
- **An toàn tuyệt đối:** Chạy 100% trên máy tính cá nhân (`localhost`), không gửi cookie hay dữ liệu về bất kỳ máy chủ bên thứ ba nào.
- **Persistent Context:** Tránh được cơ chế phát hiện tự động hóa của Facebook nhờ cấu hình browser flags `--disable-blink-features=AutomationControlled`.
