# TÀI LIỆU QUY TRÌNH TỰ ĐỘNG THU THẬP & ĐỒNG BỘ DỮ LIỆU SWITCH GAMES

Tài liệu này mô tả chi tiết kiến trúc, quy trình vận hành và các cơ chế an toàn của hệ thống tự động cào dữ liệu từ Google Sheets sang định dạng JSON cho ứng dụng.

---

## 1. Tổng quan Kiến trúc Hệ thống

Hệ thống hoạt động trên nền tảng runtime **Bun + TypeScript**, kết nối trực tiếp với **Google Sheets API v4** để lấy dữ liệu thời gian thực và xử lý qua 4 tầng bảo vệ trước khi xuất bản.

```mermaid
flowchart TD
    A[Google Sheets Private\nID: 1ctWR5HcGNM... | GID: 1005217806] -->|Google Sheets API v4| B[src/google.ts\nOAuth 2.0 Client]
    B -->|Metadata + RowData + ChipRuns| C[src/parser.ts\nRobust Link Parser & Span Matcher]
    C -->|Mảng Raw Games| D[src/validator.ts\nValibot Schema + Circuit Breaker]
    
    D -->|Lỗi Schema / Sụt giảm > 10% / Mất link > 5%| E[src/notifier.ts\nTelegram Bot Alert & ABORT]
    
    D -->|Dữ liệu Hợp Lệ 100%| F[src/lifecycle.ts\nNew Game Lifecycle & 14-day Expire]
    F -->|Kế thừa is_new, added_at| G[Tự động Backup\ndata/games.backup.json]
    G --> H[Xuất bản dữ liệu\ndata.json / data/games.json]
```

---

## 2. Chi tiết các Module chức năng (`src/`)

| File Module | Vai trò / Trách nhiệm chính |
| :--- | :--- |
| [`src/config.ts`](file:///c:/Users/kien.hm/Desktop/switch-games-data/src/config.ts) | Lưu trữ tập trung các hằng số: `SPREADSHEET_ID`, `TARGET_GID`, đường dẫn file và thời gian chu kỳ (`TWO_WEEKS_MS`). |
| [`src/types.ts`](file:///c:/Users/kien.hm/Desktop/switch-games-data/src/types.ts) | Định nghĩa Schema hợp đồng dữ liệu bằng thư viện **Valibot** (`GamesListSchema`, `GameItemSchema`, `GameLinkSchema`) và suy luận Types tự động. |
| [`src/google.ts`](file:///c:/Users/kien.hm/Desktop/switch-games-data/src/google.ts) | Quản lý phiên xác thực OAuth2 bằng `REFRESH_TOKEN` và cấp phát client Google Sheets API. |
| [`src/parser.ts`](file:///c:/Users/kien.hm/Desktop/switch-games-data/src/parser.ts) | Bóc tách liên kết bằng toạ độ `UrlSpan` (giao cắt toạ độ text và chip link ẩn), trích xuất Base, Update, DLC, Firmware. |
| [`src/validator.ts`](file:///c:/Users/kien.hm/Desktop/switch-games-data/src/validator.ts) | **Hàng rào an toàn (Circuit Breaker)**: Dùng `valibot.safeParse` kiểm tra tính hợp lệ dữ liệu. Chặn đứng việc ghi file hỏng. |
| [`src/notifier.ts`](file:///c:/Users/kien.hm/Desktop/switch-games-data/src/notifier.ts) | Gửi thông báo khẩn cấp (HTML) về Telegram Bot khi xảy ra sự cố dữ liệu. |
| [`src/lifecycle.ts`](file:///c:/Users/kien.hm/Desktop/switch-games-data/src/lifecycle.ts) | Theo dõi vòng đời game mới (`is_new: true`, `added_at: ISO_STRING`) và tự động dọn dẹp nhãn khi quá 14 ngày. |
| [`fetch-data.ts`](file:///c:/Users/kien.hm/Desktop/switch-games-data/fetch-data.ts) | **Orchestrator**: Điều phối tuần tự toàn bộ quy trình từ kết nối, trích xuất, xác thực, backup đến lưu trữ. |
| [`compare.ts`](file:///c:/Users/kien.hm/Desktop/switch-games-data/compare.ts) | Script so sánh 2 tập tin JSON (`data/games.json` cũ vs `data.json` mới) và xuất báo cáo `diff_report.json`. |

---

## 3. Quy trình Vận hành 5 Bước (Step-by-Step Execution)

### Bước 1: Xác thực & Kéo Dữ liệu Thô (Fetch Metadata)
- `fetch-data.ts` khởi tạo Google Auth từ 3 biến môi trường (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`).
- Dò tìm chính xác tab chứa game qua `GID = 1005217806` (kháng lỗi chủ sheet đổi tên tab).
- Kéo toàn bộ dữ liệu cấu trúc dạng:
  ```typescript
  fields: "sheets(properties,data.rowData.values)"
  ```
  giúp thu thập cả `formattedValue`, `hyperlink`, `textFormatRuns` và đặc biệt là `chipRuns` (Smart Chips của Google Docs).

### Bước 2: Bóc tách & Chuẩn hóa (Robust Parsing)
- **Tên & Game ID**: Tách mã Hex 15-16 ký tự trong ngoặc vuông `[0100...000]`. Tên game được lọc bỏ nhãn `(việt hóa)`.
- **Việt Hóa (`is_viet_hoa`)**: Tự động đánh dấu `true` nếu ô tên hoặc ô link tải có chứa từ khoá "việt hóa".
- **URL Liên kết (Google Drive)**:
  - Thay vì dùng `indexOf` dễ nhầm lẫn khi trùng tên file, parser chuyển sang dùng **Span Coordinates Matching**.
  - Tính toán khoảng ký tự `[startIndex, endIndex]` của từng file trên text rồi đối soát với mảng `UrlSpan` của ô.
  - Hỗ trợ cả game nhiều link (`Base`, `Update`, `DLC`) lẫn ứng dụng 1 dòng (`Youtube`, `PPSSPP`).
- **Firmware**: Tách tự động version từ chuỗi `Required Firmware: X.Y.Z` hoặc `Base (Required Firmware: X.Y.Z)`.

### Bước 3: Hàng rào Kiểm duyệt & Circuit Breaker (Valibot Validation)
Trước khi ghi bất kỳ dữ liệu nào vào ổ đĩa, dữ liệu bắt buộc phải vượt qua hàng rào kiểm duyệt:
1. **Kiểm tra Schema (`v.safeParse`)**:
   - `name`: Chuỗi không được để trống (tối thiểu 1 ký tự).
   - `links`: Phải là mảng chứa các đối tượng có `label` và `file_name` hợp lệ.
2. **Kiểm tra Sụt giảm Đột ngột (Sudden Drop Protection)**:
   - Nếu số lượng game quét về giảm quá 10% so với dữ liệu cũ (ví dụ từ 672 tụt dưới 604 game), hệ thống nghi vấn sheet bị xoá nhầm hoặc mạng chập chờn $\rightarrow$ **Dừng ngay lập tức (Abort)**.
3. **Kiểm tra Tỷ lệ Mất URL**:
   - Nếu số link không lấy được URL vượt quá 5% tổng số game $\rightarrow$ **Dừng ngay lập tức (Abort)**.
4. **Cảnh báo Telegram**: Nếu vi phạm bất kỳ điều kiện nào ở trên, hệ thống gửi tin nhắn báo động về Telegram và kết thúc với `exit code 1`.

### Bước 4: Quản lý Vòng đời Game Mới (Game Lifecycle)
- So khớp dữ liệu mới với file hiện tại theo cả `game_id` và `name`.
- Nếu là game chưa từng có: Gán `is_new: true` và `added_at: "<ISO_TIME>"`.
- Nếu là game cũ: Kế thừa `is_new` và `added_at`. Nếu `now - added_at >= 14 ngày`, tự động xoá bỏ cả 2 trường này.

### Bước 5: Sao lưu & Ghi dữ liệu An toàn (Atomic Backup & Write)
- Tự động sao lưu dữ liệu cũ ra [`data/games.backup.json`](file:///c:/Users/kien.hm/Desktop/switch-games-data/data/games.backup.json).
- Ghi dữ liệu đã làm sạch và đạt chuẩn vào [`data.json`](file:///c:/Users/kien.hm/Desktop/switch-games-data/data.json) (hoặc `data/games.json`).

---

## 4. Hướng dẫn Vận hành & Cấu hình

### 4.1. File cấu hình môi trường (`.env`)
Tạo file `.env` ở thư mục gốc (không commit lên Git):

```env
# Google OAuth 2.0 Credentials
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your_client_secret
GOOGLE_REFRESH_TOKEN=1//04your_refresh_token

# Telegram Alert Bot (Tùy chọn, để trống nếu không dùng)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuVWXyz
TELEGRAM_CHAT_ID=987654321
```

### 4.2. Các câu lệnh thông dụng

| Thao tác | Câu lệnh Bun |
| :--- | :--- |
| **Chạy xác thực ban đầu** (chỉ 1 lần trên máy local) | `bun run auth.ts` |
| **Kéo và cập nhật dữ liệu từ Google Sheets** | `bun run fetch` *(hoặc `bun run fetch-data.ts`)* |
| **So sánh dữ liệu mới vs dữ liệu hiện tại** | `bun run compare` *(hoặc `bun run compare.ts`)* |
| **Đồng bộ tải ảnh game về thư mục `images/`** | `bun run sync-images` *(hoặc `bun run sync-images.ts`)* |

---

## 5. Tích hợp Tự động hóa qua GitHub Actions

Để hệ thống chạy tự động mỗi ngày trên GitHub mà không cần máy tính cá nhân bật, cấu hình workflow `.github/workflows/sync.yml`:

```yaml
name: Auto Sync Switch Games Data

on:
  schedule:
    - cron: '0 0 * * *' # Chạy tự động lúc 00:00 UTC hàng ngày
  workflow_dispatch:      # Nút bấm chạy thủ công trên web GitHub

permissions:
  contents: write

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Setup Bun
        uses: oven-sh/setup-bun@v2
        with:
          bun-version: latest

      - name: Install Dependencies
        run: bun install

      - name: Fetch & Validate Data
        env:
          GOOGLE_CLIENT_ID: ${{ secrets.GOOGLE_CLIENT_ID }}
          GOOGLE_CLIENT_SECRET: ${{ secrets.GOOGLE_CLIENT_SECRET }}
          GOOGLE_REFRESH_TOKEN: ${{ secrets.GOOGLE_REFRESH_TOKEN }}
          SPREADSHEET_ID: ${{ secrets.SPREADSHEET_ID }}
          SPREADSHEET_GID: ${{ secrets.SPREADSHEET_GID }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: bun run fetch

      - name: Sync Images (Quy trình riêng)
        run: bun run sync-images

      - name: Commit & Push Changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/ images/
          git diff --quiet && git diff --staged --quiet || (git commit -m "chore(data): auto sync games data & images [skip ci]" && git push)
```

