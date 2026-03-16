# switch-games-data

Repo dữ liệu tập trung cho [Switch Games Manager](https://github.com/YOUR_USERNAME/switch_games).

> **Chỉ admin mới push dữ liệu. Người dùng không cần làm gì — app tự fetch.**

## Cấu trúc

```
switch-games-data/
├── source/
│   └── latest.zip          ← Admin push file ZIP HTML vào đây
├── data/
│   ├── games.json          ← Tự động tạo bởi GitHub Actions
│   └── version.json        ← { hash, timestamp, game_count }
├── scripts/
│   └── parse_zip.py        ← Parser (port từ Rust)
└── .github/workflows/
    └── parse.yml           ← Trigger khi push latest.zip
```

## Cập nhật dữ liệu (Admin)

```bash
# Chỉ cần copy ZIP vào thư mục source/ và push
cp /path/to/new_data.zip source/latest.zip
git add source/latest.zip
git commit -m "Update data"
git push
# → GitHub Action tự chạy, parse, commit games.json mới trong ~30s
```

## API endpoints (public)

```
# Danh sách game đầy đủ
https://raw.githubusercontent.com/YOUR_USERNAME/switch-games-data/main/data/games.json

# Thông tin phiên bản (dùng để check có cập nhật không)
https://raw.githubusercontent.com/YOUR_USERNAME/switch-games-data/main/data/version.json
```

## Chạy parser thủ công (local)

```bash
python scripts/parse_zip.py source/latest.zip
```
