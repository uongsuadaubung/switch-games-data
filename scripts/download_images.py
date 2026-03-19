#!/usr/bin/env python3
"""
download_images.py — Tải ảnh game về local, convert sang JPG, cập nhật games.json

Luồng hoạt động:
  Phase 1 — Scan: Duyệt toàn bộ games.json, phân loại từng game:
    • Đã có file JPG local  → chỉ cập nhật image_url, KHÔNG tải
    • Chưa có file JPG      → đưa vào danh sách cần tải
  Phase 2 — Download: Tải + convert JPG cho những game cần tải
  Phase 3 — Save: Ghi lại games.json đã cập nhật image_url

Usage:
    python scripts/download_images.py
    python scripts/download_images.py --repo uongsuadaubung/switch-games-data
    python scripts/download_images.py --dry-run
    python scripts/download_images.py --limit 10
    python scripts/download_images.py --force   # tải lại dù file đã tồn tại
"""

import json
import re
import sys
import time
import argparse
import urllib.request
import urllib.error
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("❌ Thiếu thư viện Pillow. Hãy cài: pip install Pillow")
    sys.exit(1)


# ─── Config ───────────────────────────────────────────────────────────────────

DEFAULT_REPO   = "uongsuadaubung/switch-games-data"
DEFAULT_BRANCH = "main"
RAW_BASE       = "https://raw.githubusercontent.com/{repo}/{branch}/images/{filename}"

REPO_ROOT  = Path(__file__).parent.parent
GAMES_JSON = REPO_ROOT / "data" / "games.json"
IMAGES_DIR = REPO_ROOT / "images"

TIMEOUT      = 15    # giây
DELAY        = 0.3   # giây giữa các request
JPEG_QUALITY = 85


# ─── Helpers ──────────────────────────────────────────────────────────────────

def safe_filename(game_id: str, name: str) -> str:
    if game_id and game_id.strip():
        return game_id.strip()
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[\s_]+", "_", slug).strip("_-")
    return slug[:80] or "unknown"


def is_raw_github_url(url: str, repo: str, branch: str) -> bool:
    prefix = f"https://raw.githubusercontent.com/{repo}/{branch}/images/"
    return url.startswith(prefix)


def download_image(url: str) -> bytes | None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        print(f"    ⚠️  HTTP {e.code}")
        return None
    except urllib.error.URLError as e:
        print(f"    ⚠️  URL error: {e.reason}")
        return None
    except Exception as e:
        print(f"    ⚠️  Error: {e}")
        return None


def convert_to_jpg(data: bytes, output_path: Path) -> bool:
    try:
        img = Image.open(BytesIO(data))
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return True
    except Exception as e:
        print(f"    ⚠️  Convert error: {e}")
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Tải ảnh game và cập nhật games.json")
    parser.add_argument("--repo",    default=DEFAULT_REPO,   help=f"GitHub repo (default: {DEFAULT_REPO})")
    parser.add_argument("--branch",  default=DEFAULT_BRANCH, help=f"Branch (default: {DEFAULT_BRANCH})")
    parser.add_argument("--dry-run", action="store_true",    help="Chạy thử, không ghi file")
    parser.add_argument("--limit",   type=int, default=0,    help="Giới hạn số ảnh cần tải (0 = tất cả)")
    parser.add_argument("--force",   action="store_true",    help="Tải lại dù file JPG đã tồn tại")
    args = parser.parse_args()

    print(f"📂 Games JSON : {GAMES_JSON}")
    print(f"🖼️  Images dir : {IMAGES_DIR}")
    print(f"🔗 Repo       : {args.repo} @ {args.branch}")
    if args.dry_run:
        print("🔍 DRY RUN — không ghi file")
    print()

    if not GAMES_JSON.exists():
        print(f"❌ Không tìm thấy {GAMES_JSON}")
        sys.exit(1)

    games = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    print(f"📋 Tổng số game: {len(games)}\n")

    # ── PHASE 1: Scan ─────────────────────────────────────────────────────────
    print("─" * 60)
    print("🔍 Phase 1 — Kiểm tra ảnh đã có local...")
    print("─" * 60)

    already_raw   = []   # image_url đã là raw GitHub URL rồi (parse_zip chưa reset)
    already_local = []   # có file JPG trên disk, chỉ cần cập nhật URL
    need_download = []   # chưa có file → cần tải

    # ── PHASE 1: Scan ─────────────────────────────────────────────────────────

    for game in games:
        name    = game.get("name", "")
        game_id = game.get("game_id", "")
        url     = game.get("image_url", "")

        filename = safe_filename(game_id, name) + ".jpg"
        out_path = IMAGES_DIR / filename
        raw_url  = RAW_BASE.format(repo=args.repo, branch=args.branch, filename=filename)

        # Đổi tên file nếu game vừa được thêm ID
        if game_id:
            old_filename = safe_filename("", name) + ".jpg"
            old_path = IMAGES_DIR / old_filename
            if old_filename != filename and old_path.exists():
                if not args.dry_run:
                    import subprocess
                    subprocess.run(["git", "mv", str(old_path), str(out_path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if old_path.exists():
                        old_path.rename(out_path)
                print(f"  🔄  Đổi tên ảnh: {old_filename} -> {filename}")

        if not url:
            # Nếu url rỗng nhưng file ảnh đã tồn tại trên disk (do đổi tên), cần cập nhật lại raw_url
            if out_path.exists() and not args.force:
                already_local.append((game, out_path, raw_url))
            else:
                already_raw.append(game)   # không có URL, bỏ qua
            continue

        if is_raw_github_url(url, args.repo, args.branch):
            # Nếu URL đã là raw, check xem nó đã đúng filename mới chưa (vì vừa được đổi đuôi thành id.jpg)
            if url != raw_url:
                if out_path.exists() and not args.force:
                    already_local.append((game, out_path, raw_url))
                else:
                    need_download.append((game, out_path, raw_url, url))
            else:
                already_raw.append(game)
            continue

        if out_path.exists() and not args.force:
            already_local.append((game, out_path, raw_url))
        else:
            need_download.append((game, out_path, raw_url, url))

    print(f"  ✅ Đã có file JPG local : {len(already_local):4d} game(s) → chỉ cập nhật URL")
    print(f"  ⬇️  Cần tải về           : {len(need_download):4d} game(s)")
    print(f"  ⏭️  Bỏ qua (raw URL/trống): {len(already_raw):4d} game(s)")
    print()

    # Áp dụng limit
    if args.limit and len(need_download) > args.limit:
        print(f"  ⚠️  Giới hạn --limit={args.limit}, chỉ tải {args.limit}/{len(need_download)} game(s)\n")
        need_download = need_download[:args.limit]

    # ── Cập nhật URL cho những game đã có file ────────────────────────────────
    if already_local and not args.dry_run:
        for game, _, raw_url in already_local:
            game["image_url"] = raw_url

    # ── PHASE 2: Download ─────────────────────────────────────────────────────
    success      = 0
    failed       = 0
    url_cleared  = 0   # số game bị xoá image_url do 404/lỗi vĩnh viễn

    if need_download:
        print("─" * 60)
        print(f"⬇️  Phase 2 — Tải {len(need_download)} ảnh...")
        print("─" * 60)

        for i, (game, out_path, raw_url, src_url) in enumerate(need_download, 1):
            name = game.get("name", "")
            filename = out_path.name
            print(f"[{i:4d}/{len(need_download)}] {name[:50]:<50} → {filename}")

            if args.dry_run:
                print(f"           ↳ [dry-run] sẽ lưu {out_path}")
                success += 1
                continue

            data = download_image(src_url)
            if data is None:
                # HTTP 404 hoặc lỗi vĩnh viễn → xoá image_url để không retry mãi
                print(f"           ↳ 🗑️  Xoá image_url (không thể tải)")
                game["image_url"] = ""
                url_cleared += 1
                failed += 1
                continue

            if convert_to_jpg(data, out_path):
                size_kb = out_path.stat().st_size // 1024
                print(f"           ↳ ✅ {size_kb} KB → cập nhật URL")
                game["image_url"] = raw_url
                success += 1
            else:
                failed += 1

            time.sleep(DELAY)
    else:
        print("✨ Tất cả ảnh đã có sẵn local, không cần tải thêm!")

    # ── PHASE 3: Save ─────────────────────────────────────────────────────────
    total_updated = len(already_local) + success + url_cleared
    if not args.dry_run and total_updated > 0:
        print()
        print("─" * 60)
        print("💾 Phase 3 — Lưu games.json...")
        GAMES_JSON.write_text(
            json.dumps(games, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"   Đã cập nhật {total_updated} image_url trong {GAMES_JSON.name}")

    # ── PHASE 4: Clean up unused images ───────────────────────────────────────
    print()
    print("─" * 60)
    print("🧹 Phase 4 — Xoá ảnh rác (không có trong games.json)...")
    valid_filenames = {safe_filename(g.get("game_id", ""), g.get("name", "")) + ".jpg" for g in games}
    deleted_images = 0
    
    if IMAGES_DIR.exists():
        for img_path in IMAGES_DIR.iterdir():
            if img_path.is_file() and img_path.name not in valid_filenames:
                if not args.dry_run:
                    import subprocess
                    subprocess.run(["git", "rm", "-f", "--ignore-unmatch", str(img_path)], 
                                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if img_path.exists():
                        try:
                            img_path.unlink()
                        except FileNotFoundError:
                            pass
                print(f"   🗑️  Đã xoá: {img_path.name}")
                deleted_images += 1
                
    if deleted_images == 0:
        print("   ✨ Không có ảnh rác nào cần xoá.")
    else:
        print(f"   ✅ Đã xoá {deleted_images} ảnh rác.")

    print(f"""
{"─" * 60}
📊 Kết quả:
   Đã có local (chỉ update URL) : {len(already_local)}
   Tải thành công               : {success}
   Lỗi (xoá image_url)          : {url_cleared}
   Bỏ qua (raw URL / trống)     : {len(already_raw)}
   Đã xoá ảnh rác               : {deleted_images}
{"─" * 60}
""")


if __name__ == "__main__":
    main()
