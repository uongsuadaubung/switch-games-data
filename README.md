# switch-games-data

Repo dữ liệu tập trung cho [Switch Games Manager](https://github.com/uongsuadaubung/switch-games).

> **Dữ liệu được tự động đồng bộ hàng ngày từ Google Sheets qua GitHub Actions.**

---

## 📁 Cấu trúc Thư mục

```text
switch-games-data/
├── src/                    ← Các modules nghiệp vụ (Bun + TypeScript)
│   ├── config.ts           ← Hằng số cấu hình (Spreadsheet ID, GID, paths)
│   ├── types.ts            ← Schemas (Valibot) & Types
│   ├── google.ts           ← Google Sheets API OAuth2 Client
│   ├── parser.ts           ← Trích xuất link ẩn, Smart Chips & Firmware
│   ├── validator.ts        ← Hàng rào bảo vệ Circuit Breaker (Valibot safeParse)
│   ├── notifier.ts         ← Module gửi cảnh báo khẩn cấp qua Telegram Bot
│   ├── lifecycle.ts        ← Quản lý vòng đời (game mới, hết hạn 14 ngày, xóa/sửa)
│   └── images.ts           ← Module đồng bộ hình ảnh
├── data/
│   ├── games.json          ← Dữ liệu chính thức phục vụ app
│   └── games.backup.json   ← Bản sao lưu tự động trước mỗi lần ghi
├── images/
│   └── *.jpg               ← Ảnh cover game (định danh theo game_id.jpg)
├── fetch-data.ts           ← Script chính kéo dữ liệu từ Google Sheets
├── compare.ts              ← Script so sánh dữ liệu mới vs hiện tại
├── sync-images.ts          ← Script riêng đồng bộ tải ảnh game
└── .github/workflows/
    └── sync.yml            ← Tự động chạy cron job hàng ngày lúc 00:00 UTC
```

---

## ⚡ Các lệnh vận hành (Bun)

```bash
# 1. Kéo và cập nhật dữ liệu tự động từ Google Sheets
bun run fetch

# 2. So sánh dữ liệu mới cào với dữ liệu hiện tại
bun run compare

# 3. Đồng bộ tải ảnh mới về thư mục images/ (quy trình riêng)
bun run sync-images
```

---

## 🌐 Public Endpoints

```text
# Dữ liệu game đầy đủ
https://raw.githubusercontent.com/uongsuadaubung/switch-games-data/main/data/games.json

# Ảnh game
https://raw.githubusercontent.com/uongsuadaubung/switch-games-data/main/images/{game_id}.jpg
```

Chi tiết tài liệu kiến trúc và hướng dẫn cài đặt xem tại [`WORKFLOW.md`](./WORKFLOW.md).
