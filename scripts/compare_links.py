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
    extract_firmware_from_label,
)

OK  = "✅"
ERR = "❌"


# ─── Trích xuất expected từ HTML ──────────────────────────────────────────────

def extract_expected(cell_html: str) -> tuple[list[str], str]:
    """
    Từ HTML raw của cột Link tải, trả về:
      - expected_labels : list label theo thứ tự xuất hiện
      - expected_fw     : chuỗi required_firmware (hoặc "")
    Logic mirror parse_links_cell() để khớp cùng tập label:
      1. Header line kết thúc ':' → label từ phần trước dấu ':'
      2. Fallback keyword header (Base/Update/DLC/...) không link
      3. Inline label: <a>...</a>(Label text) sau link chính
    """
    normalised = cell_html
    for br in ("<br>", "<br/>", "<br />", "<BR>", "<BR/>"):
        normalised = normalised.replace(br, "\n")

    # ─── Gộp các dòng thuần text liên tiếp (multi-line header) ────────────
    raw_segments = [s.strip() for s in normalised.split('\n')]
    merged_segments: list[str] = []
    for seg in raw_segments:
        if not seg:
            continue
        has_link = '<a ' in seg.lower()
        if has_link or not merged_segments:
            merged_segments.append(seg)
        else:
            prev = merged_segments[-1]
            prev_has_link = '<a ' in prev.lower()
            prev_plain = strip_tags(prev).strip()
            prev_ends_colon = prev_plain.endswith(':')
            if prev_has_link or prev_ends_colon:
                merged_segments.append(seg)
            else:
                merged_segments[-1] = prev + ' ' + seg

    expected_labels: list[str] = []
    expected_fw = ""
    seen_labels: set[str] = set()

    for segment in merged_segments:
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

        # Fallback keyword header dạng "Base: (Required Firmware: X.Y.Z)" không kết thúc ':'
        # Cần extract firmware từ full plain trước khi tách label
        has_link_early = "<a " in segment.lower()
        if not has_link_early and len(plain) < 120:
            _kw_early = ("base", "update", "dlc", "việt hóa", "viet hoa")
            if any(plain_lower.startswith(k) for k in _kw_early):
                _, fw_early = extract_firmware_from_label(plain)
                if fw_early and not expected_fw:
                    expected_fw = fw_early

        # Header: kết thúc ':' — trích label trước dấu ':'
        # Cũng check header_part (text trước <a>) kết thúc ':' để bắt
        # trường hợp "Label: <a>file</a>" — plain không kết thúc ':' nhưng header thì có
        has_link = "<a " in segment.lower()
        ends_colon = plain.endswith(":")
        first_a = segment.lower().find("<a ")
        if first_a != -1:
            header_part = strip_tags(segment[:first_a]).strip()
        else:
            header_part = plain
        header_part_ends_colon = header_part.endswith(":")

        if ends_colon or (has_link and header_part_ends_colon):
            raw_label = header_part.rstrip(":").strip()
            clean_label, fw = extract_firmware_from_label(raw_label)
            if fw and not expected_fw:
                expected_fw = fw
            label = clean_label
            if label and label not in seen_labels:
                expected_labels.append(label)
                seen_labels.add(label)
            if ends_colon and not has_link:
                continue
            # Nếu có link → không continue, để xử lý inline label bên dưới

        # Fallback keyword header không có ':' (Base, Update, DLC… không link)
        _kw = ("base", "update", "dlc", "việt hóa", "viet hoa")
        if not has_link and len(plain) < 120:
            if any(plain_lower.startswith(k) for k in _kw):
                colon_idx = plain.find(":")
                raw_label = plain[:colon_idx].strip() if colon_idx != -1 else plain
                clean_label, fw = extract_firmware_from_label(raw_label)
                if fw and not expected_fw:
                    expected_fw = fw
                label = clean_label
                if label and label not in seen_labels:
                    expected_labels.append(label)
                    seen_labels.add(label)
            continue

        if not has_link:
            continue

        # ─── Duyệt từng <a> trong segment, tìm inline label dạng </a>(Label) ──
        # Mirror chính xác logic trong parse_links_cell() của parse_zip.py
        lower_seg = segment.lower()
        pos = 0
        while True:
            a_start = lower_seg.find("<a ", pos)
            if a_start == -1:
                break

            # Nếu link nằm trong () → đây là backup link có URL → skip
            text_before = segment[:a_start]
            last_open  = text_before.rfind("(")
            last_close = text_before.rfind(")")
            if last_open != -1 and last_open > last_close:
                a_tag_end = segment.find(">", a_start) + 1
                close_a   = lower_seg.find("</a>", a_tag_end)
                pos = close_a + 4 if close_a != -1 else len(segment)
                continue

            a_tag_end     = segment.find(">", a_start) + 1
            close_a       = lower_seg.find("</a>", a_tag_end)
            after_close_a = close_a + 4 if close_a != -1 else len(segment)
            pos = after_close_a

            # Phần sau </a>: tìm (plain text không có <a>) → inline label
            remaining = segment[after_close_a:]
            paren_s = remaining.find("(")
            paren_e = remaining.find(")", paren_s) if paren_s != -1 else -1
            if paren_s != -1 and paren_e != -1:
                paren_content = remaining[paren_s + 1:paren_e]
                if "<a " not in paren_content.lower():
                    lbl = strip_tags(paren_content).strip()
                    if lbl and lbl not in seen_labels:
                        expected_labels.append(lbl)
                        seen_labels.add(lbl)
                    pos = after_close_a + paren_e + 1  # advance qua ()

    # Fallback: nếu cell có link nhưng không tìm ra header nào
    # → parse_links_cell() dùng label mặc định "Base"
    if not expected_labels and "<a " in cell_html.lower():
        expected_labels.append("Base")

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
        lines.append(f"  {'(tất cả label khớp)':<{w_html}}  │  {'':<{w_parse}}  │")

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
