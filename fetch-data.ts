import { CONFIG, validateSpreadsheetConfig } from "./src/config";
import { getGoogleSheetsClient } from "./src/google";
import { parseGameRow } from "./src/parser";
import { validateGamesData } from "./src/validator";
import { applyGameLifecycle } from "./src/lifecycle";
import type { ParsedGame } from "./src/types";

// Re-export types cho các file khác dùng (như compare.ts)
export * from "./src/types";

async function main() {
  validateSpreadsheetConfig();
  const sheets = getGoogleSheetsClient();

  console.log("⏳ [1/4] Đang kết nối Google Sheets API...");

  const meta = await sheets.spreadsheets.get({ spreadsheetId: CONFIG.SPREADSHEET_ID });
  const targetSheetMeta = meta.data.sheets?.find(
    (s) => s.properties?.sheetId === CONFIG.TARGET_GID
  );

  if (!targetSheetMeta?.properties?.title) {
    throw new Error(`Không tìm thấy sheet nào có GID = ${CONFIG.TARGET_GID}`);
  }

  const sheetTitle = targetSheetMeta.properties.title;
  console.log(`📑 [2/4] Đang kéo metadata và hyperlinks từ tab "${sheetTitle}"...`);

  const res = await sheets.spreadsheets.get({
    spreadsheetId: CONFIG.SPREADSHEET_ID,
    ranges: [sheetTitle],
    fields: "sheets(properties,data.rowData.values)",
  });

  const rowData = res.data.sheets?.[0]?.data?.[0]?.rowData;
  if (!rowData || rowData.length === 0) {
    throw new Error("Sheet không có dữ liệu rowData!");
  }

  console.log("⚙️  [3/4] Đang bóc tách dữ liệu chuẩn...");
  const rawGames: ParsedGame[] = [];

  for (const row of rowData) {
    const game = parseGameRow(row);
    if (game) {
      rawGames.push(game);
    }
  }

  // 1. Đọc file cũ
  const existingFile = Bun.file(CONFIG.GAMES_JSON_PATH);
  let existingGames: ParsedGame[] = [];
  if (await existingFile.exists()) {
    try {
      existingGames = await existingFile.json();
    } catch (e) {
      console.warn("⚠️ Không thể đọc file games.json cũ:", e);
    }
  }

  // 2. 🛡️ Circuit Breaker & Valibot Validator
  const validatedGames = await validateGamesData(rawGames, existingGames);

  // 3. Quản lý vòng đời toàn diện: game mới, game bị xoá, game thay đổi, hết hạn 14 ngày
  const { games: finalGames, stats } = applyGameLifecycle(validatedGames, existingGames);

  // 4. Ghi dữ liệu kết quả trực tiếp vào data/games.json chính thức
  await Bun.write(CONFIG.GAMES_JSON_PATH, JSON.stringify(finalGames, null, 2));
  console.log(`✅ THÀNH CÔNG: Đã xuất ${finalGames.length} game vào ${CONFIG.GAMES_JSON_PATH}`);
  console.log(`📊 BÁO CÁO VÒNG ĐỜI DỮ LIỆU:`);
  console.log(`   ➕ Game mới thêm vào : ${stats.newCount}`);
  console.log(`   ➖ Game bị gỡ khỏi Sheet: ${stats.removedCount}`);
  console.log(`   ✏️ Game có thông tin thay đổi: ${stats.updatedCount}`);
  console.log(`   ⏳ Game hết hạn nhãn mới (14 ngày): ${stats.expiredCount}`);
}

main().catch((err) => {
  console.error("❌ QUY TRÌNH THẤT BẠI:", err.message);
  process.exit(1);
});
