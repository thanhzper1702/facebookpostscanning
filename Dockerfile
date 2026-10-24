# Sử dụng Python 3.11-slim nhẹ, ổn định
FROM python:3.11-slim

# Thiết lập biến môi trường tối ưu cho Python và Playwright
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Cài đặt các gói phụ thuộc hệ thống cần thiết
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt thư viện Python từ requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cài đặt Chromium của Playwright cùng tất cả thư viện hệ thống Linux cần thiết
RUN playwright install --with-deps chromium

# Copy toàn bộ mã nguồn ứng dụng vào container
COPY . .

# Render tự động inject biến môi trường $PORT
EXPOSE 8000

# Khởi chạy Uvicorn server, tự động bind 0.0.0.0 và nhận $PORT từ Render
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
