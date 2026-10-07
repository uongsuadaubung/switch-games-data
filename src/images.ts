import * as v from "valibot";
import { SheetCellSchema, type ParsedGame } from "./types";

export interface ImageSyncStats {
  alreadyExisted: number;
  downloaded: number;
  failed: number;
}

/**
 * Trích xuất link ảnh gốc từ công thức =IMAGE("https://...", 2) trong ô của Google Sheet
 * Sử dụng Valibot để loại bỏ hoàn toàn cảnh báo null/undefined
 */
export function extractFormulaImageUrl(rawCell: unknown): string {
  const cell = v.parse(SheetCellSchema, rawCell ?? {});
  const formula = cell.userEnteredValue?.formulaValue || "";
  const match = formula.match(/=IMAGE\(\s*["']([^"']+)["']/i);
  return (match && match[1]) ? match[1] : "";
}

/**
 * Tạo tên file ảnh an toàn dựa trên game_id hoặc slug tên game
 */
export function getImageFileName(game: { game_id?: string; name: string }): string {
  if (game.game_id && game.game_id.trim()) {
    return `${game.game_id.trim()}.jpg`;
  }
  const slug = game.name
    .toLowerCase()
    .replace(/[^a-z0-9àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ\s_]/g, "")
    .trim()
    .replace(/\s+/g, "_");
  return `${slug}.jpg`;
}

/**
 * Tự động tải và đồng bộ ảnh vào thư mục images/
 * - Nếu file ảnh đã có sẵn trong images/ -> Bỏ qua không tải lại (tiết kiệm bandwidth)
 * - Nếu game mới chưa có file ảnh và có link từ formula -> Tải về và lưu thành .jpg
 */
export async function syncGameImages(
  games: ParsedGame[],
  imagesDir: string = "./images"
): Promise<ImageSyncStats> {
  let alreadyExisted = 0;
  let downloaded = 0;
  let failed = 0;

  for (const game of games) {
    const filename = getImageFileName(game);
    const localFilePath = `${imagesDir}/${filename}`;
    const file = Bun.file(localFilePath);

    // 1. Nếu file ảnh đã tồn tại trên disk local -> bỏ qua
    if (await file.exists()) {
      alreadyExisted++;
      continue;
    }

    // 2. Nếu chưa có và game có raw_image_url từ Google Sheet
    if (game.raw_image_url) {
      try {
        console.log(`  ⬇️  Đang tải ảnh mới: ${game.name} -> ${filename}`);
        const res = await fetch(game.raw_image_url, {
          headers: {
            "User-Agent":
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
          },
          // Nintendo CDN thường bị lỗi leaf signature trên một số môi trường Windows Node/Bun
          tls: {
            rejectUnauthorized: false,
          },
        });

        if (!res.ok) {
          console.warn(`  ⚠️ Lỗi HTTP ${res.status} khi tải ảnh cho ${game.name}`);
          failed++;
          continue;
        }

        const buffer = await res.arrayBuffer();
        await Bun.write(localFilePath, buffer);
        downloaded++;
      } catch (err) {
        console.warn(`  ⚠️ Thất bại khi tải ảnh cho ${game.name}:`, err);
        failed++;
      }
    }
  }

  return { alreadyExisted, downloaded, failed };
}
