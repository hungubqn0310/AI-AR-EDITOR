# All-in-one image: chạy API backend thật (FastAPI + Node/Puppeteer/Chrome)
# — không phải chỉ web server tĩnh như bản trước. Khách tự deploy chỉ cần
# Docker, không cần tự cài Python/Node/Chrome.
FROM python:3.12-slim

# Dùng google-chrome-stable (build chính thức của Google), KHÔNG dùng gói
# "chromium" của Debian — bản Debian mới (v150, Debian trixie) bị crash
# SIGILL (illegal instruction) trên CPU Intel Gen 12+ (Alder Lake trở lên
# tắt phần cứng AVX-512 dù có vẻ vẫn báo hỗ trợ một phần); google-chrome-stable
# đã verify chạy ổn định trên đúng loại CPU này.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl gnupg ca-certificates fonts-liberation ffmpeg \
    && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_PATH=/usr/bin/google-chrome-stable

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Đảm bảo image tự chạy được kể cả khi không mount volume (docker-compose
# mount đè lên để giữ dữ liệu bền, nhưng image vẫn cần tự đủ thư mục để
# StaticFiles không lỗi lúc khởi động).
RUN mkdir -p media/images media/videos qrcodes targets

EXPOSE 5556
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "5556"]
