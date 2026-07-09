# AR QR Demo

Quét QR (hoặc trực tiếp chĩa camera vào 1 ảnh) → thấy vật thể/video chuyển
động AR đè lên đúng vị trí ảnh đó, qua camera thật của điện thoại.

## Cấu trúc thư mục

```text
ar-qr/
  api/
    main.py         # FastAPI: POST /api/generate, GET /upload, GET /api/generations
    db.py           # async SQLAlchemy engine/session (Postgres)
    models.py       # model Generation (lịch sử từng lần tạo)
    templates/
      upload.html   # trang upload test, chỉ đọc qua route /upload (không static)
  pages/      # các trang demo (html) + ar-view.html (template AR chung), xem bên dưới
  media/
    images/   # ảnh tĩnh nguồn (dùng để track AR và/hoặc sinh video)
    videos/   # video do Veo sinh ra + video ghép cuối cùng
  qrcodes/    # QR code đã tạo (png)
  targets/    # file .mind đã biên dịch cho MindAR
  generate_video.py    # sinh video chuyển động tiếp diễn từ 1 ảnh (Veo)
  generate-qr.js        # tạo QR code trỏ tới 1 URL, lưu vào qrcodes/
  compile-target.js      # biên dịch ảnh → file .mind, lưu vào targets/
  compile.html             # trang chạy compiler (được compile-target.js mở, ở gốc)
  Dockerfile, docker-compose.yml, .env.example   # deploy, xem mục "Deploy lên server thật"
```

## Demo có sẵn

### 1. Cat AR (ảnh chụp thường → track trực tiếp)

- `pages/cat-qr.html` — mở trên máy tính: QR + ảnh mèo để quét.
- `pages/cat-ar.html` — trang AR, track `media/images/cat-target.jpg` bằng
  `targets/cat-targets.mind`, hiện khối vuông cam xoay + chữ "Meo Meo!" khi nhận diện.

### 2. AEON MALL banner (ảnh minh hoạ dài → track + phủ video AI)

- `pages/aeon-site.html` — banner AEON hiển thị to, canh giữa (để chĩa camera).
- `pages/aeon-qr.html` — QR quét để mở `aeon-full-ar.html`.
- `pages/aeon-full-ar.html` — track `media/images/aeon.png` bằng
  `targets/aeon-full-target.mind`, phủ `media/videos/aeon-full.mp4` lên đúng vị trí banner.
- `aeon-full.mp4` được ghép từ: `aeon-vn.mp4` + `aeon-jp.mp4` (2 đoạn do
  Google Veo sinh ra từ `aeon-vn.png`/`aeon-jp.png`, hiệu ứng cô gái Việt
  Nam tiếp tục thêu / cô gái Nhật Bản vẫy quạt) ghép ngang (`ffmpeg hstack`)
  với phần nền tĩnh còn lại, để khớp đúng chiều rộng banner gốc `aeon.png`
  mà không mất chi tiết (Veo chỉ nhận video tỷ lệ 16:9/9:16, banner gốc
  thì dài hơn nhiều).

### 3. Harvest AI video (chỉ xem video AI, không cần AR/camera)

- `pages/show-qr-harvest.html` — QR quét để mở `harvest-video.html`.
- `pages/harvest-video.html` — phát loop `media/videos/harvest.mp4`, sinh từ
  `media/images/harvest-source.jpg` (người đang gặt lúa, video tiếp diễn
  động tác gặt).

## Sinh video mới từ 1 ảnh (`generate_video.py`)

```bash
cd ar-qr
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # 1 lần
cp .env.example .env && vim .env   # điền GOOGLE_API_KEY (cần billing bật cho Veo, không thì lỗi 429)

.venv/bin/python3 generate_video.py media/images/cat-target.jpg \
  --prompt "the cat continues waving its paw" \
  --out media/videos/cat.mp4
```

- `--prompt`: mô tả hành động tiếp diễn mong muốn (tiếng Anh cho kết quả
  ổn định hơn). Mặc định: giữ nguyên phong cách ảnh, chuyển động tự nhiên.
- `--model`: mặc định `veo-3.1-fast-generate-preview` (rẻ/nhanh). Có thể
  đổi `veo-3.1-generate-preview` cho chất lượng cao hơn (chậm/đắt hơn).
- Ảnh dạng banner/tỷ lệ dài bất thường: Veo chỉ nhận 16:9 hoặc 9:16, cần
  tự cắt vùng cần animate trước (xem cách làm `aeon-vn.mp4`/`aeon-jp.mp4`
  ở trên — cắt bằng `ffmpeg crop`, rồi ghép lại bằng `ffmpeg hstack` nếu
  cần khớp lại đúng khung ảnh gốc).

## Chạy demo

```bash
cd ar-qr
npm install            # 1 lần
npm run serve          # python http.server tại :8080 (phục vụ toàn bộ thư mục, kể cả pages/)
# song song, cần tunnel HTTPS để điện thoại quét được:
ngrok http 8080
```

Sau khi có URL ngrok, dùng `generate-qr.js` để tạo lại QR trỏ đúng URL đó
(URL ngrok bản free đổi mỗi lần restart, nhớ thêm tiền tố `/pages/`):

```bash
node generate-qr.js "https://<ngrok-url>/pages/cat-ar.html" "qr-cat-ar.png"
node generate-qr.js "https://<ngrok-url>/pages/aeon-full-ar.html" "qr-aeon-full.png"
node generate-qr.js "https://<ngrok-url>/pages/harvest-video.html" "qr-harvest.png"
# (lưu vào qrcodes/ tự động; đưa full path nếu muốn lưu chỗ khác)
```

Mở `pages/cat-qr.html` / `pages/aeon-site.html` + `pages/aeon-qr.html` /
`pages/show-qr-harvest.html` trên máy tính, quét bằng camera điện thoại.

## Biên dịch target mới (`.mind`) cho ảnh khác

```bash
node compile-target.js "./media/images/ten-anh.jpg" "ten-target.mind"
# (lưu vào targets/ tự động; đưa full path nếu muốn lưu chỗ khác)
```

Chạy headless bình thường, **không cần GPU hay màn hình thật** — chạy
được trên server/container thông thường (đã verify: headless swiftshader
cho ra số lượng feature point giống hệt bản dùng GPU thật).

### Bug đã gặp và đã fix (quan trọng nếu sửa lại script)

`serve-handler` mặc định tự động redirect `/compile.html?src=X` →
`/compile` ("clean URLs") và **làm rớt mất query string** trong lúc
redirect. Hậu quả: `compile.html` luôn luôn compile nhầm ảnh mặc định,
bất kể tham số truyền vào là gì — mọi target compile ra đều "hỏng"
(không match được gì khi quét thật), dù không có lỗi/exception nào
được ném ra. Đã fix bằng cách thêm `cleanUrls: false` khi khởi tạo
`serve-handler`. Nếu sau này thấy target compile ra luôn có cùng kích
thước bất kể ảnh input khác nhau → nghi ngay bug này trước.

(Ban đầu nghi ngờ thêm là do thiếu GPU thật khi compile bằng Chrome
headless — đã test và loại trừ: headless + swiftshader (phần mềm, không
GPU) cho ra target giống hệt bản dùng GPU thật về số lượng feature
point. `cleanUrls` là nguyên nhân duy nhất.)

## API backend — upload ảnh tự động ra video AR + QR (`api/main.py`)

Dịch vụ đứng riêng (đồng bộ, chưa có queue) cho use case: 1 nơi khác (vd
WordPress) gửi ảnh lên, nhận lại link ảnh + QR + trang AR để nhúng vào
landing page — không cần biết gì về Veo/MindAR bên trong.

Cần Postgres (lưu lịch sử từng lần tạo — bảng `generations`: id, status,
prompt, tên file ảnh/video/target/QR, `error_message` nếu lỗi). Chạy
bằng Docker Compose (đã có sẵn service `db`, xem mục Deploy bên dưới)
là dễ nhất:

```bash
cd ar-qr
cp .env.example .env && vim .env
# GOOGLE_API_KEY=...           key Veo, cần billing
# PUBLIC_BASE_URL=...          domain public thật (ngrok/domain), không phải localhost
#                              nếu muốn WordPress/điện thoại khác truy cập được
# API_KEY=...                  tuỳ chọn — đặt để bắt buộc header X-API-Key,
#                              chặn người lạ gọi tốn phí Veo của bạn
# DATABASE_URL=...             mặc định trỏ service "db" trong docker-compose,
#                              không cần đổi nếu chạy qua Docker Compose

docker compose up -d --build
```

Bảng `generations` tự tạo lúc app khởi động (`Base.metadata.create_all`,
không dùng Alembic — 1 bảng đơn giản, không cần migration framework).

Muốn chạy `uvicorn` trực tiếp trên host (không qua Docker) thì cần tự
có Postgres riêng reachable ở `DATABASE_URL` (Postgres của Compose
không lộ port ra host, chỉ `api` container gọi được qua network nội bộ).

Có sẵn trang upload đơn giản để tự test: mở `http://localhost:5556/upload`
(route động — server tự điền `API_KEY` từ `.env` vào, không cần gõ tay).
Chọn ảnh, prompt đã điền sẵn mặc định (ẩn trong mục "Tuỳ chỉnh prompt"),
bấm nút, chờ ~1-2 phút, ra ảnh gốc + QR + link AR ngay trên trang.

`POST /api/generate` (multipart form: `image` = file, `prompt` = tuỳ chọn)
→ chạy tuần tự: lưu ảnh → gọi Veo sinh video (~1-2 phút) → compile
`.mind` (`compile-target.js`, vài giây) → tạo QR trỏ tới
`pages/ar-view.html?id=...` → trả JSON:

```json
{
  "id": "a1b2c3d4e5f6",
  "image_url": "https://.../media/images/a1b2c3d4e5f6.jpg",
  "video_url": "https://.../media/videos/a1b2c3d4e5f6.mp4",
  "target_url": "https://.../targets/a1b2c3d4e5f6.mind",
  "qr_code_url": "https://.../qrcodes/a1b2c3d4e5f6.png",
  "ar_page_url": "https://.../pages/ar-view.html?id=a1b2c3d4e5f6"
}
```

WordPress chỉ cần nhúng `image_url` + `qr_code_url` lên landing page —
khi ai đó quét QR đó, mở `ar_page_url` (dùng chung 1 template
`pages/ar-view.html`, đọc `?id=` để biết track ảnh/target/video nào,
không sinh file html riêng mỗi lần upload).

`GET /api/generations` — xem lại lịch sử tất cả lần tạo (id, status,
prompt, thời gian, lỗi nếu có), mới nhất trước. Ghi vào DB ngay khi
nhận ảnh (status `processing`), cập nhật `completed`/`failed` sau — nên
kể cả request đang chạy dở (đang chờ Veo) cũng thấy được trong danh sách.

Vì gọi tuần tự (đợi luôn, không job queue/polling) nên 1 request có thể
mất 1-2 phút — chấp nhận được cho quy mô cá nhân/thấp tải. Đây là bản
"standalone" ban đầu — nếu sau cần chịu tải cao hơn, hướng scale dễ nhất
là thêm queue (Celery/arq) + endpoint `/api/status/{id}` mà không đổi
response shape hiện tại.

**Lưu ý:** endpoint này gọi Veo thật — **mỗi lần gọi tốn phí thật**. Test
bằng ảnh nhỏ/prompt ngắn trước khi tích hợp WordPress thật.

## Deploy lên server thật (Docker)

Đóng gói sẵn 2 container qua `docker-compose.yml`: `api` (Python + Node +
Chromium, image build từ `Dockerfile`) và `db` (Postgres) — khách chỉ
cần cài Docker, không cần tự cài gì khác kể cả Postgres.

```bash
cp .env.example .env && vim .env   # điền GOOGLE_API_KEY, PUBLIC_BASE_URL, API_KEY
docker compose up -d --build
```

- `media/`, `qrcodes/`, `targets/` mount làm volume (dữ liệu không mất
  khi container restart/redeploy); Postgres cũng có volume riêng
  (`pgdata`) để không mất lịch sử.
- `shm_size: 1gb` cho container `api` — Chrome cần nhiều `/dev/shm` hơn
  mức mặc định 64MB của Docker, thiếu sẽ crash ngẫu nhiên.
- Postgres **không lộ port ra host** (chỉ `api` gọi qua network nội bộ
  Docker) — muốn xem dữ liệu trực tiếp thì `docker compose exec db psql
  -U ar_qr -d ar_qr`, không cần mở port ra ngoài.

### Bắt buộc trước khi cho khách thật dùng

1. **HTTPS thật** — camera chỉ chạy qua HTTPS. Cách đơn giản nhất: dùng
   [Caddy](https://caddyserver.com/) làm reverse proxy trước container
   (tự xin cert Let's Encrypt, gần như không cần config):

   ```caddyfile
   your-domain.com {
     reverse_proxy localhost:5556
   }
   ```

2. **Timeout đủ dài** — mỗi request `/api/generate` mất 1-2 phút. Nếu có
   reverse proxy/load balancer khác (nginx, Cloudflare, ALB...), tăng
   timeout đọc/ghi lên tối thiểu 180s ở mọi lớp, không chỉ ở app — mặc
   định nhiều proxy là 30-60s, sẽ cắt ngang request dù server vẫn đang
   xử lý bình thường.
3. **Đặt `API_KEY`** trong `.env` (xem mục trên) — không đặt = ai cũng
   gọi được, tốn phí Veo của bạn vô tội vạ nếu URL bị lộ.
4. **`PUBLIC_BASE_URL` phải là domain thật** (không phải `localhost`)
   để QR/link trong response dùng được từ điện thoại/WordPress thật.

## Ghi chú khác

- Camera cần HTTPS (hoặc `localhost`) để trình duyệt cho phép — dùng
  ngrok để điện thoại truy cập được qua HTTPS từ xa.
- Ảnh dùng để track nên có nhiều chi tiết/tương phản (ảnh chụp thật tốt
  hơn hẳn ảnh vector phẳng), và cần lấy trọn ảnh vào khung hình camera
  khi quét — ảnh càng dài/hẹp (như banner) càng khó lấy trọn khung.
