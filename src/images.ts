import * as fs from "node:fs/promises";
import * as path from "node:path";
import * as v from "valibot";
import { SheetCellSchema, type ParsedGame } from "./types";

export interface ImageSyncStats {
  alreadyExisted: number;
  downloaded: number;
  failed: number;
  cleanedOrphans: number;
  renamed: number;
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
 * - Đổi tên ảnh nếu game trước đó chưa có ID, nay đã có ID
 * - Bỏ qua ảnh đã tồn tại
 * - Tải ảnh mới từ Google Sheet formula
 * - Dọn dẹp ảnh mồ côi (file ảnh thừa trong images/ không còn trong games.json)
 */
export async function syncGameImages(
  games: ParsedGame[],
  imagesDir: string = "./images"
): Promise<ImageSyncStats> {
  let alreadyExisted = 0;
  let downloaded = 0;
  let failed = 0;
  let renamed = 0;
  let cleanedOrphans = 0;

  // Tập hợp các tên file hợp lệ đang có trong games.json
  const validFilenames = new Set<string>();

  for (const game of games) {
    const filename = getImageFileName(game);
    validFilenames.add(filename);
    const localFilePath = `${imagesDir}/${filename}`;

    // Kiểm tra đổi tên nếu trước đó dùng slug, giờ đã có game_id
    if (game.game_id && game.game_id.trim()) {
      const oldSlugFilename = `${getImageFileName({ name: game.name })}.jpg`;
      const oldFilePath = `${imagesDir}/${oldSlugFilename}`;
      if (oldSlugFilename !== filename) {
        try {
          const oldFile = Bun.file(oldFilePath);
          if (await oldFile.exists()) {
            await fs.rename(oldFilePath, localFilePath);
            console.log(`  🔄 Đổi tên ảnh: ${oldSlugFilename} -> ${filename}`);
            renamed++;
          }
        } catch {
          // Bỏ qua lỗi đổi tên
        }
      }
    }

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

  // 3. Dọn dẹp ảnh mồ côi (file không còn tồn tại trong games.json)
  try {
    const entries = await fs.readdir(imagesDir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isFile() && entry.name.endsWith(".jpg")) {
        if (!validFilenames.has(entry.name)) {
          const orphanPath = path.join(imagesDir, entry.name);
          try {
            await fs.unlink(orphanPath);
            console.log(`  🗑️ Đã xóa ảnh rác/mồ côi: ${entry.name}`);
            cleanedOrphans++;
          } catch {
            // Âm thầm bỏ qua lỗi xóa
          }
        }
      }
    }
  } catch {
    // Thư mục images có thể chưa tồn tại hoặc lỗi đọc, bỏ qua an toàn
  }

  return { alreadyExisted, downloaded, failed, renamed, cleanedOrphans };
}
