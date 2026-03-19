#!/usr/bin/env python3
"""
parse_zip.py — Port chính xác từ Rust parser (src-tauri/src/parser/)
Đọc ZIP chứa HTML files, parse danh sách game, xuất ra games.json + version.json

Usage:
    python scripts/parse_zip.py <zip_path>
    python scripts/parse_zip.py source/latest.zip
"""

import zipfile
import json
import hashlib
import os
import sys
import re
from pathlib import Path
from datetime import datetime, timezone


# ─── HTML Utilities (port từ parser/html.rs) ──────────────────────────────────

def decode_html(s: str) -> str:
    return (s
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&apos;", "'")
            .replace("&#x27;", "'")
            .replace("&nbsp;", " ")
            .replace("&#160;", " "))


def strip_tags(html: str) -> str:
    out = []
    in_tag = False
    for ch in html:
        if ch == '<':
            in_tag = True
        elif ch == '>':
            in_tag = False
        elif not in_tag:
            out.append(ch)
    return decode_html("".join(out))


def extract_attr(html: str, attr: str) -> str | None:
    """Extract value of an HTML attribute (e.g. href, src). Port của extract_attr() trong Rust."""
    lower = html.lower()
    for quote in ('"', "'"):
        pattern = f"{attr}={quote}"
        idx = lower.find(pattern)
        if idx != -1:
            val_start = idx + len(pattern)
            end = html.find(quote, val_start)
            if end != -1:
                return decode_html(html[val_start:end])
    return None


def extract_links_from_cell(cell_html: str) -> list[tuple[str, str]]:
    """Trả về list (text, href) cho mọi <a> trong cell. Port của extract_links_from_cell()."""
    result = []
    pos = 0
    lower = cell_html.lower()
    while True:
        a_start = lower.find("<a ", pos)
        if a_start == -1:
            break
        tag_end_rel = cell_html[a_start:].find('>')
        if tag_end_rel == -1:
            break
        tag_end = a_start + tag_end_rel + 1
        opening_tag = cell_html[a_start:tag_end]
        href = extract_attr(opening_tag, "href") or ""

        close_rel = cell_html[tag_end:].lower().find("</a>")
        if close_rel != -1:
            close_pos = tag_end + close_rel
            text = strip_tags(cell_html[tag_end:close_pos]).strip()
            next_pos = close_pos + 4
        else:
            text = ""
            next_pos = tag_end

        if href:
            result.append((text, href))
        pos = next_pos
    return result


def cell_text(cell_html: str) -> str:
    """Text content của một TD, <br> → newline. Port của cell_text()."""
    s = cell_html
    for br in ("<br>", "<br/>", "<br />", "<BR>", "<BR/>"):
        s = s.replace(br, "\n")
    return decode_html(strip_tags(s))


def extract_cells(row_html: str) -> list[str]:
    """Trích xuất raw HTML nội dung từng <td>. Port của extract_cells()."""
    cells = []
    pos = 0
    lower = row_html.lower()
    while True:
        td_start = lower.find("<td", pos)
        if td_start == -1:
            break
        tag_end_rel = row_html[td_start:].find('>')
        if tag_end_rel == -1:
            break
        tag_end = td_start + tag_end_rel + 1

        close_rel = row_html[tag_end:].lower().find("</td>")
        if close_rel != -1:
            close_pos = tag_end + close_rel
            cells.append(row_html[tag_end:close_pos])
            pos = close_pos + 5
        else:
            cells.append("")
            pos = tag_end
    return cells


def extract_rows(html: str) -> list[str]:
    """Trích xuất raw HTML nội dung từng <tr> trong <tbody>. Port của extract_rows()."""
    rows = []
    lower = html.lower()

    body_idx = lower.find("<tbody>")
    body_start = body_idx + 7 if body_idx != -1 else 0
    body_end_rel = lower[body_start:].find("</tbody>")
    body_end = body_start + body_end_rel if body_end_rel != -1 else len(html)

    tbody = html[body_start:body_end]
    lower_body = tbody.lower()

    pos = 0
    while True:
        tr_start = lower_body.find("<tr", pos)
        if tr_start == -1:
            break
        tag_open_rel = tbody[tr_start:].find('>')
        if tag_open_rel == -1:
            break
        tag_open_end = tr_start + tag_open_rel + 1

        close_rel = lower_body[tag_open_end:].find("</tr>")
        if close_rel != -1:
            close_pos = tag_open_end + close_rel
            rows.append(tbody[tag_open_end:close_pos])
            pos = close_pos + 5
        else:
            rows.append("")
            pos = tag_open_end
    return rows


# ─── Game Parsing (port từ parser/game.rs) ────────────────────────────────────

def parse_game_name_cell(raw: str) -> tuple[str, str, bool]:
    """Trả về (name, game_id, is_viet_hoa). Port của parse_game_name_cell()."""
    raw = raw.strip()
    raw_lower = raw.lower()
    is_viet_hoa = "việt hóa" in raw_lower or "viet hoa" in raw_lower

    # Tìm [TitleID]
    bracket_start = raw.find('[')
    bracket_end = raw.find(']')
    if bracket_start != -1 and bracket_end != -1 and bracket_end > bracket_start:
        game_id = raw[bracket_start + 1:bracket_end]
    else:
        game_id = ""

    # Tên game = dòng đầu tiên
    name = raw.splitlines()[0].strip() if raw else ""

    # Bỏ [TitleID] ra khỏi tên
    bs = name.find('[')
    be = name.find(']')
    if bs != -1 and be != -1 and be > bs:
        before = name[:bs].strip()
        after = name[be + 1:].strip()
        name = (f"{before} {after}".strip()) if after else before

    # Bỏ annotation việt hóa khỏi tên
    name = name.replace("(việt hóa)", "").replace("(Việt Hóa)", "").strip()

    return name, game_id, is_viet_hoa


def parse_size_genres(raw: str) -> tuple[str, list[str]]:
    """Port của parse_size_genres()."""
    lines = raw.splitlines()
    size = lines[0].strip() if lines else ""
    genres_raw = lines[1].strip() if len(lines) > 1 else ""
    genres_raw = genres_raw.lstrip('(').rstrip(')')
    genres = [g.strip() for g in genres_raw.split(',') if g.strip()]
    return size, genres


def parse_links_cell(cell_html: str) -> dict:
    """Parse cột 'Link tải'. Port của parse_links_cell()."""
    base = []
    update = []
    dlc = []
    viet_hoa = []
    required_firmware = ""

    # Chuẩn hóa <br> → newline
    normalised = cell_html
    for br in ("<br>", "<br/>", "<br />", "<BR>", "<BR/>"):
        normalised = normalised.replace(br, "\n")

    current_section = "base"
    current_label = "Base"

    # Keywords để fallback nhận ra section header kể cả thiếu dấu ':'
    _SECTION_KEYWORDS = ("base", "update", "dlc", "việt hóa", "viet hoa", "required firmware")

    for segment in normalised.split('\n'):
        segment = segment.strip()
        if not segment:
            continue

        plain = strip_tags(segment).strip()
        plain_lower = plain.lower()

        # is_header: có dấu ':' Ở CUỐI, hoặc bắt đầu bằng keyword section
        # (fallback cho trường hợp thiếu dấu ':', chỉ áp dụng cho dòng ngắn < 80 ký tự
        #  để tránh nhầm với text game có chứa các từ này)
        ends_with_colon = plain.endswith(':')
        is_fw_header = plain_lower.startswith("required firmware")
        is_keyword_header = (
            not ends_with_colon
            and len(plain) < 80
            and not extract_links_from_cell(segment)  # dòng không chứa link → khả năng cao là header
            and any(plain_lower.startswith(k) for k in _SECTION_KEYWORDS)
        )
        is_header = ends_with_colon or is_fw_header or is_keyword_header

        if is_header:
            clean = plain.rstrip(':').strip()
            clean_lower = clean.lower()

            if is_fw_header or clean_lower.startswith("required firmware"):
                parts = plain.split(':', 1)
                required_firmware = parts[1].strip() if len(parts) > 1 else ""
                current_section = ""  # không thêm links vào section này
            elif clean_lower.startswith("base") and ("+ update" in clean_lower or "+update" in clean_lower):
                current_section = "base"
                current_label = clean
            elif clean_lower.startswith("base"):
                current_section = "base"
                current_label = clean
            elif clean_lower.startswith("update"):
                current_section = "update"
                current_label = clean
            elif clean_lower.startswith("dlc") or "dlc pack" in clean_lower:
                current_section = "dlc"
                current_label = clean
            elif "việt hóa" in clean_lower or "viet hoa" in clean_lower:
                current_section = "viet_hoa"
                current_label = clean

        links = extract_links_from_cell(segment)
        for text, href in links:
            if not current_section:
                continue
            filename = text if text else (href.split('/')[-1] or href)
            link = {"label": current_label, "filename": filename, "url": href}
            if current_section == "base":
                base.append(link)
            elif current_section == "update":
                update.append(link)
            elif current_section == "dlc":
                dlc.append(link)
            elif current_section == "viet_hoa":
                viet_hoa.append(link)
            else:
                base.append(link)

    return {
        "base": base,
        "update": update,
        "dlc": dlc,
        "viet_hoa": viet_hoa,
        "required_firmware": required_firmware,
    }


def parse_html_file(html: str, sheet_name: str) -> list[dict]:
    """Parse một HTML file thành list game. Port của parse_html_file()."""
    rows = extract_rows(html)
    games = []

    for row in rows:
        cells = extract_cells(row)
        if len(cells) < 5:
            continue

        col_a = cell_text(cells[0]).strip()
        if not col_a:
            continue
        if col_a == "Tên Game" or "#TAgames" in col_a or "LƯU Ý QUAN TRỌNG" in col_a:
            continue

        image_url = extract_attr(cells[1], "src") or ""

        col_c = cell_text(cells[2])
        size, genres = parse_size_genres(col_c)
        if not size and not genres:
            continue

        review_links = extract_links_from_cell(cells[3])
        review_url = review_links[0][1] if review_links else ""

        links = parse_links_cell(cells[4])

        name, game_id, is_viet_hoa = parse_game_name_cell(col_a)
        if not name:
            continue

        games.append({
            "name": name,
            "game_id": game_id,
            "is_viet_hoa": is_viet_hoa,
            "image_url": image_url,
            "size": size,
            "genres": genres,
            "review_url": review_url,
            "sheets": [sheet_name],
            "links": links,
        })

    return games


# ─── ZIP Reading + Merge (port từ parser/zip.rs) ──────────────────────────────

def merge_links(existing: list, incoming: list):
    """Merge links, dedup theo URL. Port của merge_links()."""
    existing_keys = {(l["url"] or l["filename"]) for l in existing}
    for link in incoming:
        key = link["url"] or link["filename"]
        if key not in existing_keys:
            existing.append(link)
            existing_keys.add(key)


def read_zip_html(zip_path: str) -> list[dict]:
    """Đọc ZIP, parse tất cả HTML, merge game trùng key. Port của read_zip_html()."""
    games_map: dict[str, dict] = {}

    with zipfile.ZipFile(zip_path, 'r') as z:
        html_files = sorted(n for n in z.namelist() if n.lower().endswith(".html"))
        print(f"  Found {len(html_files)} HTML file(s): {html_files}")

        for html_name in html_files:
            try:
                content = z.read(html_name).decode("utf-8", errors="replace")
            except Exception as e:
                print(f"  ⚠️  Cannot read {html_name}: {e}")
                continue

            sheet_name = Path(html_name).stem
            games = parse_html_file(content, sheet_name)
            print(f"  [{sheet_name}] → {len(games)} games")

            for game in games:
                key = game["game_id"] or game["name"]
                if key in games_map:
                    existing = games_map[key]
                    
                    # Báo động nếu 2 tên game khác nhau nhưng dùng chung 1 ID (Tránh lỗi do người nhập liệu)
                    if game["game_id"] and key == game["game_id"]:
                        if existing["name"].lower() != game["name"].lower():
                            print(f"    🚨 CẢNH BÁO LỖI NHẬP (Trùng ID): '{key}' đang chứa 2 game khác tên là '{existing['name']}' và '{game['name']}'. Dữ liệu đang bị gộp cứng!")
                            
                    if game["sheets"][0] not in existing["sheets"]:
                        existing["sheets"].append(game["sheets"][0])
                    merge_links(existing["links"]["base"],     game["links"]["base"])
                    merge_links(existing["links"]["update"],   game["links"]["update"])
                    merge_links(existing["links"]["dlc"],      game["links"]["dlc"])
                    merge_links(existing["links"]["viet_hoa"], game["links"]["viet_hoa"])
                    if not existing["links"]["required_firmware"]:
                        existing["links"]["required_firmware"] = game["links"]["required_firmware"]
                    if not existing["review_url"]:
                        existing["review_url"] = game["review_url"]
                else:
                    games_map[key] = game

    games = sorted(games_map.values(), key=lambda g: g["name"])
    return games


# ─── Version helpers ──────────────────────────────────────────────────────────

def compute_md5(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


# ─── New-game tracking helpers ────────────────────────────────────────────────

TWO_WEEKS_SECONDS = 14 * 24 * 60 * 60


def load_old_games(games_out: str) -> tuple[dict[str, dict], bool]:
    """Đọc games.json cũ, trả về (dict key → game, file_existed)."""
    path = Path(games_out)
    if not path.exists():
        return {}, False
    try:
        old_list = json.loads(path.read_text(encoding="utf-8"))
        return {(g.get("game_id") or g.get("name")): g for g in old_list}, True
    except Exception as e:
        print(f"  ⚠️  Không thể đọc file cũ {games_out}: {e}")
        return {}, True  # file tồn tại nhưng đọc lỗi → vẫn coi là không phải lần đầu


def backup_old_games(games_out: str) -> None:
    """Sao lưu games.json cũ → games.backup.json (nếu tồn tại)."""
    src = Path(games_out)
    if not src.exists():
        return
    backup_path = src.with_suffix(".backup.json")
    try:
        backup_path.write_bytes(src.read_bytes())
        print(f"  💾 Backup: {backup_path}")
    except Exception as e:
        print(f"  ⚠️  Không thể backup: {e}")


def apply_new_game_tracking(
    new_games: list[dict],
    old_map: dict[str, dict],
    now: datetime,
    is_first_run: bool = False,
) -> tuple[list[dict], int, int]:
    """
    - is_first_run=True (chưa có games.json) → không đánh nhãn game nào là mới.
    - Game có trong old_map → giữ nguyên is_new / added_at từ lần trước,
      nhưng nếu added_at đã quá 2 tuần thì xóa cả hai trường.
    - Game KHÔNG có trong old_map → đánh dấu is_new=True + added_at=now.
    Trả về (danh sách đã xử lý, số game mới, số game hết hạn is_new).
    """
    if is_first_run:
        return new_games, 0, 0
    new_count = 0
    expired_count = 0
    result = []

    now_ts = now.timestamp()

    for game in new_games:
        key = game.get("game_id") or game.get("name")
        old = old_map.get(key)

        # Fallback tìm bằng name nếu truy vấn bằng id không thấy (game cũ chưa có id)
        if old is None and game.get("game_id") and game.get("name"):
            old = old_map.get(game.get("name"))

        if old is None:
            # Game hoàn toàn mới — đánh dấu
            game["is_new"] = True
            game["added_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            new_count += 1
        else:
            # Game đã có — kế thừa trạng thái is_new / added_at
            if old.get("is_new") and old.get("added_at"):
                try:
                    added_dt = datetime.fromisoformat(
                        old["added_at"].replace("Z", "+00:00")
                    )
                    age_seconds = now_ts - added_dt.timestamp()
                    if age_seconds >= TWO_WEEKS_SECONDS:
                        # Đã quá 2 tuần → xóa nhãn
                        expired_count += 1
                    else:
                        # Vẫn còn trong 2 tuần → giữ nhãn
                        game["is_new"] = True
                        game["added_at"] = old["added_at"]
                except Exception:
                    pass  # added_at lỗi định dạng → bỏ qua, không gắn lại

        result.append(game)

    return result, new_count, expired_count


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/parse_zip.py <zip_path>")
        sys.exit(1)

    zip_path = sys.argv[1]
    keep_zip = "--keep-zip" in sys.argv
    games_out  = "data/games.json"
    version_out = "data/version.json"

    if not Path(zip_path).exists():
        print(f"❌ File not found: {zip_path}")
        sys.exit(1)

    # 1️⃣  Đọc & backup dữ liệu cũ trước khi ghi đè
    print(f"🔍 Đọc dữ liệu cũ...")
    old_map, file_existed = load_old_games(games_out)
    backup_old_games(games_out)
    if not file_existed:
        print(f"   ℹ️  Chưa có games.json — lần đầu chạy, không đánh nhãn game mới")
    else:
        print(f"   Số game cũ: {len(old_map)}")

    print(f"\n📦 Parsing: {zip_path}")
    games = read_zip_html(zip_path)

    # 2️⃣  So sánh & đánh dấu game mới / hết hạn nhãn
    now = datetime.now(timezone.utc)
    games, new_count, expired_count = apply_new_game_tracking(
        games, old_map, now, is_first_run=not file_existed
    )

    # Tính MD5 của ZIP (để app có thể so sánh phiên bản)
    zip_hash = compute_md5(zip_path)
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 3️⃣  Ghi games.json
    Path(games_out).parent.mkdir(parents=True, exist_ok=True)
    Path(games_out).write_text(
        json.dumps(games, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # Ghi version.json
    version = {
        "hash": zip_hash,
        "timestamp": timestamp,
        "game_count": len(games),
    }
    Path(version_out).write_text(
        json.dumps(version, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n✅ Done!")
    print(f"   Games tổng  : {len(games)}")
    print(f"   Games mới   : {new_count} 🆕")
    print(f"   Hết hạn mới : {expired_count} (đã xóa is_new)")
    print(f"   Hash        : {zip_hash}")
    print(f"   Output      : {games_out}, {version_out}")

    # Xoá ZIP sau khi parse xong (dùng --keep-zip để giữ lại)
    if not keep_zip:
        try:
            os.remove(zip_path)
            print(f"   🗑️  Đã xoá: {zip_path}")
        except OSError as e:
            print(f"   ⚠️  Không thể xoá ZIP: {e}")

    # 4️⃣  Xóa file backup (không cần giữ lại sau khi mọi thứ hoàn tất)
    backup_path = Path(games_out).with_suffix(".backup.json")
    if backup_path.exists():
        try:
            backup_path.unlink()
            print(f"   🗑️  Đã xoá backup: {backup_path}")
        except OSError as e:
            print(f"   ⚠️  Không thể xoá backup: {e}")


if __name__ == "__main__":
    main()
