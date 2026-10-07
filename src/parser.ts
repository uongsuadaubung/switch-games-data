import * as v from "valibot";
import { SheetCellSchema, type GameLink, type SheetCell, type UrlSpan, type ParsedGame } from "./types";

/**
 * Thu thập tất cả URL cùng khoảng vị trí chính xác (start -> end) trong ô
 * Sử dụng Valibot để parse cell, loại bỏ hoàn toàn cảnh báo undefined / null
 */
export function extractUrlSpans(rawCell: unknown, fullText: string): UrlSpan[] {
  // Parse cell bằng Valibot, tự động điền giá trị mặc định cho mọi trường undefined
  const cell = v.parse(SheetCellSchema, rawCell ?? {});
  const spans: UrlSpan[] = [];

  // 1. Chip Runs (Smart Chips Google Docs)
  cell.chipRuns.forEach((cr, i) => {
    const uri = cr.chip?.richLinkProperties?.uri;
    if (uri) {
      const start = cr.startIndex;
      const nextCr = cell.chipRuns[i + 1];
      const end = nextCr ? nextCr.startIndex : fullText.length;
      spans.push({
        startIndex: start,
        endIndex: end,
        uri,
      });
    }
  });

  // 2. Text Format Runs
  cell.textFormatRuns.forEach((run, i) => {
    const uri = run.format?.link?.uri;
    if (uri) {
      const start = run.startIndex;
      const nextRun = cell.textFormatRuns[i + 1];
      const end = nextRun ? nextRun.startIndex : fullText.length;
      spans.push({
        startIndex: start,
        endIndex: end,
        uri,
      });
    }
  });

  // 3. Fallback ô chỉ có 1 hyperlink đơn
  if (cell.hyperlink && spans.length === 0) {
    spans.push({
      startIndex: 0,
      endIndex: fullText.length,
      uri: cell.hyperlink,
    });
  }

  return spans.sort((a, b) => a.startIndex - b.startIndex);
}

/**
 * Tìm URL tương ứng với một khoảng ký tự trong văn bản
 */
export function findUrlForRange(spans: UrlSpan[], start: number, end: number): string {
  if (spans.length === 0) return "";
  const matched = spans.find(
    (s) => Math.max(s.startIndex, start) < Math.min(s.endIndex, end)
  );
  if (matched) return matched.uri;

  const nearest = spans
    .filter((s) => s.startIndex <= end)
    .sort((a, b) => b.startIndex - a.startIndex)[0];
  return nearest ? nearest.uri : "";
}

/**
 * Bóc tách danh sách link và firmware từ ô Link tải
 */
export function parseRobustLinks(rawText: string, spans: UrlSpan[]): { links: GameLink[]; firmware: string } {
  let firmware = "";
  const fwMatch = rawText.match(/Required Firmware:\s*([0-9\.]+)/i);
  if (fwMatch && fwMatch[1]) {
    firmware = fwMatch[1];
  }

  const blocks = rawText.split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean);
  const links: GameLink[] = [];

  for (const block of blocks) {
    const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
    if (lines.length === 0) continue;

    const firstLine = lines[0] ?? "";
    if (lines.length === 1 && /^Required Firmware:\s*[0-9\.]+/i.test(firstLine)) {
      continue;
    }

    if (lines.length >= 2) {
      let label = firstLine.replace(/:$/, "").trim();
      label = label.replace(/\s*\(Required Firmware:.*?\)/i, "").trim();

      const fileName = lines[1] ?? "";
      const filePos = rawText.indexOf(fileName);
      const url = findUrlForRange(spans, filePos, filePos + fileName.length);

      links.push({
        label,
        file_name: fileName,
        url,
      });

      for (let j = 2; j < lines.length; j++) {
        const extraLine = lines[j] ?? "";
        if (/^Required Firmware:\s*[0-9\.]+/i.test(extraLine)) continue;
        const extraPos = rawText.indexOf(extraLine);
        const extraUrl = findUrlForRange(spans, extraPos, extraPos + extraLine.length);
        if (extraUrl) {
          links.push({
            label: `${label} (${j})`,
            file_name: extraLine,
            url: extraUrl,
          });
        }
      }
    } else if (lines.length === 1) {
      const line = firstLine;
      const pos = rawText.indexOf(line);
      const url = findUrlForRange(spans, pos, pos + line.length);

      links.push({
        label: "Base",
        file_name: line,
        url,
      });
    }
  }

  if (links.length === 0 && spans.length > 0) {
    spans.forEach((s, idx) => {
      links.push({
        label: idx === 0 ? "Base" : `Link ${idx + 1}`,
        file_name: rawText.slice(s.startIndex, s.endIndex).trim() || "download",
        url: s.uri,
      });
    });
  }

  return { links, firmware };
}

/**
 * Bóc tách và parse 1 dòng dữ liệu Google Sheet thành ParsedGame
 * Sử dụng Valibot và logic chuẩn hóa, trả về null nếu dòng tiêu đề / rỗng
 */
export function parseGameRow(row: any): ParsedGame | null {
  const cells: unknown[] = row?.values || [];
  const cellName = v.parse(SheetCellSchema, cells[0] ?? {});
  const cellImage = v.parse(SheetCellSchema, cells[1] ?? {});
  const cellSizeGenre = v.parse(SheetCellSchema, cells[2] ?? {});
  const cellReview = v.parse(SheetCellSchema, cells[3] ?? {});
  const cellLinks = v.parse(SheetCellSchema, cells[4] ?? {});

  const rawName = cellName.formattedValue.trim();
  if (!rawName || rawName.startsWith("#TAgames") || rawName === "Tên Game") {
    return null;
  }

  // Game ID & Tên
  const idMatch = rawName.match(/\[([0-9A-Fa-f]{15,16})\]/);
  const gameId = (idMatch && idMatch[1]) ? idMatch[1] : "";

  const firstLine = rawName.split("\n")[0] ?? "";
  let name = firstLine.replace(/\[.*?\]/, "").trim();
  name = name.replace(/\(việt\s*hóa\)/i, "").trim();

  const rawLinksText = cellLinks.formattedValue;
  const isVietHoa =
    rawName.toLowerCase().includes("việt hóa") ||
    rawLinksText.toLowerCase().includes("việt hóa");

  // Size & Genres
  const rawSizeGenre = cellSizeGenre.formattedValue.trim();
  const sizeMatch = rawSizeGenre.match(/([\d\.]+\s*(?:GB|MB))/i);
  const size = (sizeMatch && sizeMatch[1]) ? sizeMatch[1] : "";

  let genres: string[] = [];
  const genreMatch = rawSizeGenre.match(/\((.*?)\)/s);
  if (genreMatch && genreMatch[1]) {
    genres = genreMatch[1].split(",").map((g) => g.trim()).filter(Boolean);
  }

  // Review URL
  const reviewSpans = extractUrlSpans(cellReview, cellReview.formattedValue);
  const reviewUrl = (reviewSpans.length > 0 && reviewSpans[0]) ? reviewSpans[0].uri : "";

  // Image URL
  const formulaMatch = (cellImage.userEnteredValue?.formulaValue || "").match(/=IMAGE\(\s*["']([^"']+)["']/i);
  const rawFormulaImageUrl = (formulaMatch && formulaMatch[1]) ? formulaMatch[1] : "";

  let imageUrl = "";
  if (gameId) {
    imageUrl = `https://raw.githubusercontent.com/uongsuadaubung/switch-games-data/main/images/${gameId}.jpg`;
  } else if (name) {
    const slug = name
      .toLowerCase()
      .replace(/[^a-z0-9àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ\s_]/g, "")
      .trim()
      .replace(/\s+/g, "_");
    imageUrl = `https://raw.githubusercontent.com/uongsuadaubung/switch-games-data/main/images/${slug}.jpg`;
  }

  // Parse Links & Firmware
  const linkSpans = extractUrlSpans(cellLinks, rawLinksText);
  const { links, firmware } = parseRobustLinks(rawLinksText, linkSpans);

  return {
    name,
    game_id: gameId,
    is_viet_hoa: isVietHoa,
    image_url: imageUrl,
    raw_image_url: rawFormulaImageUrl || undefined,
    size,
    genres,
    review_url: reviewUrl,
    links,
    required_firmware: firmware,
  };
}
