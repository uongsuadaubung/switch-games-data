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


def extract_backup_link(segment_after_main: str) -> tuple[str, str] | None:
    """
    Tìm link dự phòng nằm trong cặp () ngay sau link chính.
    segment_after_main: phần HTML sau </a> của link chính trong cùng một segment.
    Trả về (file_name, url) hoặc None.
    """
    # Tìm nội dung trong cặp ngoặc đơn đầu tiên: ( ... )
    s = segment_after_main
    paren_start = s.find('(')
    if paren_start == -1:
        return None
    paren_end = s.find(')', paren_start)
    if paren_end == -1:
        return None
    inside = s[paren_start + 1:paren_end]
    # Kiểm tra có <a href=...> bên trong không
    links = extract_links_from_cell(inside)
    if links:
        text, href = links[0]
        filename = text if text else (href.split('/')[-1] or href)
        return filename, href
    return None


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
    """
    Parse cột 'Link tải'.
    Trả về:
      {
        "links": [
          {
            "label": "Base",          # phần trước dấu ':' của dòng header
            "file_name": "abc.rar",   # text của <a>, fallback về tên file trong URL
            "url": "https://...",
            "backup_url": "https://...",     # tùy chọn, link trong () sau link chính
            "backup_file_name": "...",       # tùy chọn
          },
          ...
        ],
        "required_firmware": "16.0.3"  # hoặc ""
      }
    """
    links: list[dict] = []
    required_firmware = ""

    # Chuẩn hóa <br> → newline
    normalised = cell_html
    for br in ("<br>", "<br/>", "<br />", "<BR>", "<BR/>"):
        normalised = normalised.replace(br, "\n")

    # ─── Gộp các dòng thuần text liên tiếp (multi-line header) ────────────────
    # Ví dụ: "Pokémon Scarlet: The Hidden Treasure of Area Zero DLC\n
    #          (Part 1: The Teal Mask + Part 2: The Indigo Disk +\n
    #          New Uniform Set):"
    # → gộp thành 1 segment duy nhất.
    raw_segments = [s.strip() for s in normalised.split('\n')]
    merged_segments: list[str] = []
    for seg in raw_segments:
        if not seg:
            continue
        has_link = '<a ' in seg.lower()
        if has_link or not merged_segments:
            # Dòng có link hoặc dòng đầu tiên → bắt đầu segment mới
            merged_segments.append(seg)
        else:
            # Dòng thuần text → kiểm tra dòng trước cũng thuần text không
            prev = merged_segments[-1]
            prev_has_link = '<a ' in prev.lower()
            prev_plain = strip_tags(prev).strip()
            prev_ends_colon = prev_plain.endswith(':')
            if prev_has_link or prev_ends_colon:
                # Dòng trước có link hoặc đã kết thúc bằng ':' (header hoàn chỉnh)
                # → segment mới
                merged_segments.append(seg)
            else:
                # Dòng trước cũng thuần text chưa kết thúc → gộp lại (nối bằng space)
                merged_segments[-1] = prev + ' ' + seg

    current_label = "Base"
    label_from_header = False  # True nếu current_label được đặt từ header line
    label_used = False         # True nếu current_label đã được dùng bởi ít nhất 1 link

    def _flush_unused_label():
        """Nếu label hiện tại từ header mà chưa link nào dùng → thêm entry rỗng."""
        nonlocal label_used
        if label_from_header and not label_used and links:
            links.append({
                "label": current_label,
                "file_name": "",
                "url": "",
            })

    for segment in merged_segments:
        segment = segment.strip()
        if not segment:
            continue

        plain = strip_tags(segment).strip()
        plain_lower = plain.lower()

        # ─── Phát hiện Required Firmware ───────────────────────────────────────
        if plain_lower.startswith("required firmware"):
            parts = plain.split(':', 1)
            required_firmware = parts[1].strip() if len(parts) > 1 else ""
            continue

        segment_links = extract_links_from_cell(segment)
        ends_with_colon = plain.endswith(':')

        # ─── Header thuần: kết thúc bằng ':' và KHÔNG chứa link ───────────────
        # Ví dụ: "Base:", "Update (1.1.0):", "Việt hóa được port bởi Bánh Mì:"
        if ends_with_colon and not segment_links:
            new_label = plain.rstrip(':').strip()
            # Nếu label cũ chưa được dùng bởi link nào → flush ra empty entry
            _flush_unused_label()
            current_label = new_label
            label_from_header = True
            label_used = False
            continue

        # ─── Header có link inline ─────────────────────────────────────────────
        # Ví dụ: "Base (Required Firmware: 20.5.0): <a>..."
        # Ví dụ: "Base: (lưu ý...) <a>..." — plain kết thúc bằng ':' nhưng link là ở sau
        if ends_with_colon and segment_links:
            first_a = segment.lower().find('<a ')
            if first_a != -1:
                header_part = strip_tags(segment[:first_a]).strip()
            else:
                header_part = plain
            _flush_unused_label()
            current_label = header_part.rstrip(':').strip()
            label_from_header = True
            label_used = False
            # Không continue — tiếp tục xử lý links bên dưới

        # ─── Fallback keyword header (không có dấu ':', không có link) ─────────
        # Xử lý: "Base: (lưu ý...)", "Base: (Required Firmware: X.Y.Z)"
        # → bắt đầu bằng keyword, có ':' ở giữa, không có link
        if not segment_links and len(plain) < 120:
            _kw = ("base", "update", "dlc", "việt hóa", "viet hoa")
            if any(plain_lower.startswith(k) for k in _kw):
                # Nếu có ':' trong plain → lấy phần trước ':' đầu tiên làm label
                colon_idx = plain.find(':')
                _flush_unused_label()
                if colon_idx != -1:
                    current_label = plain[:colon_idx].strip()
                else:
                    current_label = plain
                label_from_header = True
                label_used = False
                continue

        # ─── Xử lý links trong segment ─────────────────────────────────────────
        if not segment_links:
            continue

        lower_seg = segment.lower()
        pos = 0
        for link_text, href in segment_links:
            # Tìm vị trí <a> của link này trong segment (từ pos hiện tại)
            a_start = lower_seg.find('<a ', pos)
            if a_start == -1:
                break

            # Kiểm tra xem link này có nằm bên trong '(' không (tức là backup link)
            # Tìm '(' gần nhất trước a_start
            text_before = segment[:a_start]
            last_paren_open = text_before.rfind('(')
            last_paren_close = text_before.rfind(')')
            if last_paren_open != -1 and last_paren_open > last_paren_close:
                # Link này nằm trong (), đây là backup → skip
                a_tag_end = segment.find('>', a_start) + 1
                close_a = lower_seg.find('</a>', a_tag_end)
                pos = close_a + 4 if close_a != -1 else len(segment)
                continue

            a_tag_end = segment.find('>', a_start) + 1
            close_a = lower_seg.find('</a>', a_tag_end)
            after_close_a = close_a + 4 if close_a != -1 else len(segment)
            pos = after_close_a

            file_name = link_text if link_text else (href.split('/')[-1] or href)
            link_obj: dict = {
                "label": current_label,
                "file_name": file_name,
                "url": href,
            }

            # Tìm link dự phòng trong phần còn lại sau </a>: (<a href="...">...</a>)
            remaining = segment[after_close_a:]
            backup = extract_backup_link(remaining)
            if backup:
                link_obj["backup_file_name"] = backup[0]
                link_obj["backup_url"] = backup[1]
                # Advance pos qua backup link để không xử lý lại
                bp_start = remaining.find('(')
                bp_end = remaining.find(')', bp_start) if bp_start != -1 else -1
                if bp_end != -1:
                    pos = after_close_a + bp_end + 1

            links.append(link_obj)
            label_used = True

    return {
        "links": links,
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

        links_data = parse_links_cell(cells[4])

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
            "links": links_data["links"],
            "required_firmware": links_data["required_firmware"],
        })

    return games


# ─── ZIP Reading + Merge (port từ parser/zip.rs) ──────────────────────────────

def merge_links(existing: list, incoming: list):
    """Merge links, dedup theo URL."""
    existing_keys = {(l["url"] or l["file_name"]) for l in existing}
    for link in incoming:
        key = link["url"] or link["file_name"]
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

                # --- Xử lý tách các game trùng ID thành các game độc lập ---
                if key in games_map and game["game_id"] and key == game["game_id"]:
                    existing = games_map[key]
                    if existing["name"].lower() != game["name"].lower():
                        print(f"    🚨 TÁCH GAME LỖI ID: Trùng '{key}' giữa '{existing['name']}' và '{game['name']}'. Tước bỏ ID của game sau, chuyển qua dùng Tên để định danh!")
                        game["game_id"] = ""
                        key = game["name"]
                
                # Sau khi chốt được Key cuối cùng (là ID, hoặc đã fallback về Tên)
                if key in games_map:
                    existing = games_map[key]
                    # Nếu một trong các sheet có đánh dấu việt hoá, thì game này tính là việt hoá
                    existing["is_viet_hoa"] = existing["is_viet_hoa"] or game["is_viet_hoa"]
                    merge_links(existing["links"], game["links"])
                    if not existing["required_firmware"]:
                        existing["required_firmware"] = game["required_firmware"]
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
    keep_zip = "--keep-zip" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if args:
        zip_path = args[0]
    else:
        zip_path = "source/latest.zip"
        print(f"ℹ️  Không có argument — dùng mặc định: {zip_path}")

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
