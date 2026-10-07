import { CONFIG } from "./src/config";
import { syncGameImages } from "./src/images";
import type { ParsedGame } from "./src/types";

async function main() {
  console.log("=========================================");
  console.log("🖼️  QUY TRÌNH ĐỒNG BỘ HÌNH ẢNH SWITCH GAMES");
  console.log("=========================================");

  // Đọc danh sách game từ data/games.json
  const targetFile = Bun.file(CONFIG.GAMES_JSON_PATH);

  let games: ParsedGame[] = [];
  if (await targetFile.exists()) {
    games = await targetFile.json();
    console.log(`📖 Đọc dữ liệu từ ${CONFIG.GAMES_JSON_PATH} (${games.length} games)`);
  } else {
    throw new Error(`❌ Không tìm thấy file ${CONFIG.GAMES_JSON_PATH} để lấy danh sách ảnh!`);
  }

  console.log(`📁 Thư mục lưu ảnh: ./images\n`);
  const stats = await syncGameImages(games, "./images");

  console.log("\n-----------------------------------------");
  console.log("📊 KẾT QUẢ ĐỒNG BỘ ẢNH:");
  console.log(`   ✅ Ảnh đã có sẵn từ trước : ${stats.alreadyExisted}`);
  console.log(`   ⬇️  Ảnh mới vừa tải về    : ${stats.downloaded}`);
  console.log(`   🔄 Ảnh được đổi tên       : ${stats.renamed}`);
  console.log(`   🗑️  Ảnh rác/mồ côi đã dọn : ${stats.cleanedOrphans}`);
  console.log(`   ⚠️  Ảnh tải thất bại       : ${stats.failed}`);
  console.log("=========================================");
}

main().catch((err) => {
  // Âm thầm bỏ qua, không chặn quy trình
  console.log("ℹ️ Tiến trình đồng bộ ảnh kết thúc với thông báo:", err?.message || err);
});

