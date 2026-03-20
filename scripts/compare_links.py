#!/usr/bin/env python3
"""
compare_links.py — So sánh label & firmware: HTML gốc ↔ kết quả parse
✅ = khớp   ❌ = sai / thiếu

Usage:
    python scripts/compare_links.py source/all.html
    python scripts/compare_links.py source/all.html --limit 50
    python scripts/compare_links.py source/all.html --search "Batman"
    python scripts/compare_links.py source/all.html --only-errors
    python scripts/compare_links.py source/all.html --only-mismatch
"""

import sys, os, argparse
sys.path.insert(0, os.path.dirname(__file__))

from parse_zip import (
    parse_links_cell, parse_game_name_cell,
    cell_text, extract_cells, extract_rows, strip_tags,
)

OK  = "✅"
ERR = "❌"


# ─── Trích xuất expected từ HTML ──────────────────────────────────────────────

def extract_expected(cell_html: str) -> tuple[list[str], str]:
    """
    Từ HTML raw của cột Link tải, trả về:
      - expected_labels : list label theo thứ tự xuất hiện (dòng kết thúc ':' không kèm link)
      - expected_fw     : chuỗi required_firmware (hoặc "")
    Logic giống parse_links_cell để tạo ra cùng 1 tập label.
    """
    normalised = cell_html
    for br in ("<br>", "<br/>", "<br />", "<BR>", "<BR/>"):
        normalised = normalised.replace(br, "\n")

    expected_labels: list[str] = []
    expected_fw = ""
    seen_labels: set[str] = set()   # tránh thêm duplicate header

    for segment in normalised.split("\n"):
        segment = segment.strip()
        if not segment:
            continue

        plain = strip_tags(segment).strip()
        plain_lower = plain.lower()

        # Required Firmware
        if plain_lower.startswith("required firmware"):
            parts = plain.split(":", 1)
            expected_fw = parts[1].strip() if len(parts) > 1 else ""
            continue

        # Header: kết thúc ':' — trích label trước dấu ':'
        ends_colon = plain.endswith(":")
        # Header có hoặc không có link kèm theo
        if ends_colon:
            # Tìm phần trước link đầu tiên (nếu có)
            first_a = segment.lower().find("<a ")
            if first_a != -1:
                header_part = strip_tags(segment[:first_a]).strip()
            else:
                header_part = plain
            label = header_part.rstrip(":").strip()
            if label and label not in seen_labels:
                expected_labels.append(label)
                seen_labels.add(label)
            continue

        # Fallback keyword header không có ':'  (Base, Update, DLC… không link)
        _kw = ("base", "update", "dlc", "việt hóa", "viet hoa")
        lower_seg_links = "<a " in segment.lower()
        if not lower_seg_links and len(plain) < 120:
            if any(plain_lower.startswith(k) for k in _kw):
                colon_idx = plain.find(":")
                label = plain[:colon_idx].strip() if colon_idx != -1 else plain
                if label and label not in seen_labels:
                    expected_labels.append(label)
                    seen_labels.add(label)

    return expected_labels, expected_fw


# ─── So sánh và format ────────────────────────────────────────────────────────

def compare_block(
    name: str, game_id: str, cell_html: str, parsed: dict,
    only_mismatch: bool = False,
) -> tuple[str, bool]:
    """
    Tạo block so sánh compact.
    only_mismatch=True → chỉ in dòng ❌, ẩn dòng ✅.
    Trả về (text, has_error).
    """
    exp_labels, exp_fw = extract_expected(cell_html)
    parsed_links = parsed.get("links", [])
    parsed_fw    = parsed.get("required_firmware", "")

    # Labels từ parse (deduplicated, giữ thứ tự)
    seen: set[str] = set()
    parsed_labels: list[str] = []
    for lk in parsed_links:
        lb = lk.get("label", "")
        if lb not in seen:
            parsed_labels.append(lb)
            seen.add(lb)

    # ── So sánh labels ───────────────────────────────────────────────────────
    label_rows: list[tuple[str, str, str]] = []  # (html_label, parse_label, mark)
    max_len = max(len(exp_labels), len(parsed_labels))
    has_error = False

    for i in range(max_len):
        el = exp_labels[i]    if i < len(exp_labels)    else "(thiếu)"
        pl = parsed_labels[i] if i < len(parsed_labels) else "(thiếu)"
        mark = OK if el == pl else ERR
        if mark == ERR:
            has_error = True
        label_rows.append((el, pl, mark))

    # ── So sánh firmware ─────────────────────────────────────────────────────
    fw_match = (exp_fw == parsed_fw)
    fw_mark  = OK if fw_match else ERR
    if not fw_match:
        has_error = True

    # ── Render ───────────────────────────────────────────────────────────────
    # Lọc dòng cần hiển thị
    visible_label_rows = [
        r for r in label_rows
        if (not only_mismatch) or r[2] == ERR
    ]
    show_fw = (not only_mismatch) or (not fw_match)

    # Tất cả dòng để tính độ rộng (kể cả dòng bị ẩn, để cột nhất quán)
    all_rows_for_width = label_rows
    fw_html  = f"firmware: {exp_fw}"   if exp_fw   else "(không có firmware)"
    fw_parse = f"firmware: {parsed_fw}" if parsed_fw else "(không có firmware)"

    w_html  = max((len(r[0]) for r in all_rows_for_width), default=4)
    w_html  = max(w_html, len(fw_html), len("HTML label"), 4)
    w_parse = max((len(r[1]) for r in all_rows_for_width), default=5)
    w_parse = max(w_parse, len(fw_parse), len("PARSE label"), 5)

    sep = "  " + "─" * (w_html + w_parse + 12)
    id_str = f"  [{game_id}]" if game_id else ""

    lines = []
    lines.append(f"  {name}{id_str}")
    lines.append(sep)
    lines.append(f"  {'HTML label':<{w_html}}  │  {'PARSE label':<{w_parse}}  │")
    lines.append(sep)

    if visible_label_rows:
        for el, pl, mark in visible_label_rows:
            lines.append(f"  {el:<{w_html}}  │  {pl:<{w_parse}}  │  {mark}")
    elif only_mismatch:
        lines.append(f"  {'(tất cả label khớp)':<{w_html}}  │  {'':>{w_parse}}  │")

    if show_fw:
        lines.append(sep)
        lines.append(f"  {fw_html:<{w_html}}  │  {fw_parse:<{w_parse}}  │  {fw_mark}")
    else:
        lines.append(sep)

    lines.append("")
    return "\n".join(lines), has_error


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="So sánh label & firmware: HTML gốc ↔ parse_links_cell"
    )
    parser.add_argument("html_file", nargs="?", default="source/all.html")
    parser.add_argument("--limit", "-n", type=int, default=0,
                        help="Giới hạn số game (0 = tất cả)")
    parser.add_argument("--search", "-s", default="",
                        help="Lọc theo tên game")
    parser.add_argument("--only-errors", "-e", action="store_true",
                        help="Chỉ xuất game có lỗi (❌)")
    parser.add_argument("--only-mismatch", "-m", action="store_true",
                        help="Chỉ xuất game có lỗi VÀ ẩn dòng ✅ trong mỗi game")
    parser.add_argument("--out", "-o", default="compare_links_output.txt")
    args = parser.parse_args()

    # --only-mismatch ngầm bật --only-errors
    if args.only_mismatch:
        args.only_errors = True

    if not os.path.exists(args.html_file):
        print(f"❌ File không tìm thấy: {args.html_file}")
        sys.exit(1)

    print(f"📖 Đọc: {args.html_file} ...")
    with open(args.html_file, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()

    rows = extract_rows(html)
    print(f"   Rows: {len(rows)}")

    out_lines: list[str] = []
    count = error_count = skipped = 0

    # Header
    filter_info = f"search='{args.search}'" if args.search else "tất cả"
    limit_info  = str(args.limit) if args.limit > 0 else "không giới hạn"
    mode_info   = ("CHỈ DÒNG ❌" if args.only_mismatch
                   else "CHỈ GAME LỖI" if args.only_errors else "")
    out_lines.append("=" * 72)
    out_lines.append(f"  SO SÁNH LABEL & FIRMWARE  |  {args.html_file}")
    out_lines.append(f"  Filter: {filter_info}  |  Limit: {limit_info}"
                     + (f"  |  {mode_info}" if mode_info else ""))
    out_lines.append("=" * 72)
    out_lines.append(f"  {'HTML label':<28}  │  {'PARSE label':<28}  │  Match")
    out_lines.append("=" * 72)
    out_lines.append("")

    for row in rows:
        cells = extract_cells(row)
        if len(cells) < 5:
            skipped += 1
            continue
        col_a = cell_text(cells[0]).strip()
        if not col_a or col_a == "Tên Game" or "#TAgames" in col_a or "LƯU Ý QUAN TRỌNG" in col_a:
            skipped += 1
            continue
        col_c = cell_text(cells[2])
        if not col_c.splitlines()[0].strip() if col_c.splitlines() else True:
            skipped += 1
            continue

        name, game_id, _ = parse_game_name_cell(col_a)
        if not name:
            skipped += 1
            continue

        if args.search and args.search.lower() not in name.lower():
            continue

        parsed = parse_links_cell(cells[4])
        block, has_error = compare_block(
            name, game_id, cells[4], parsed,
            only_mismatch=args.only_mismatch,
        )

        if args.only_errors and not has_error:
            count += 1
            continue

        if has_error:
            error_count += 1

        out_lines.append(block)
        count += 1

        if args.limit > 0 and count >= args.limit:
            break

    # Summary
    ok_count = count - error_count
    out_lines.append("=" * 72)
    out_lines.append(f"  TỔNG KẾT  |  Game: {count}  |  ✅ Khớp: {ok_count}  |  ❌ Lỗi: {error_count}")
    out_lines.append("=" * 72)

    result = "\n".join(out_lines)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"\n✅ Xong! Game: {count}  |  ✅ {ok_count} khớp  |  ❌ {error_count} lỗi")
    print(f"   Output: {args.out}")


if __name__ == "__main__":
    main()
