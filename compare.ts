import type { ParsedGame as Game } from "./fetch-data";

async function compare() {
  const originalFile = Bun.file("./data/games.json");
  const newFile = Bun.file("./data.json");

  if (!(await originalFile.exists()) || !(await newFile.exists())) {
    console.error("❌ Không tìm thấy một trong hai file để so sánh!");
    return;
  }

  const originalGames: Game[] = await originalFile.json();
  const newGames: Game[] = await newFile.json();

  console.log("=========================================");
  console.log("📊 BÁO CÁO SO SÁNH DỮ LIỆU GAME");
  console.log("=========================================");
  console.log(`- File gốc (data/games.json) : ${originalGames.length} games`);
  console.log(`- File mới (data.json)       : ${newGames.length} games\n`);

  // Dùng name làm primary key để so sánh sự thay đổi của từng game
  const origMap = new Map<string, Game>();
  originalGames.forEach((g) => {
    origMap.set(g.name.toLowerCase().trim(), g);
  });

  const newMap = new Map<string, Game>();
  newGames.forEach((g) => {
    newMap.set(g.name.toLowerCase().trim(), g);
  });

  // 1. Game mới thêm vào
  const addedGames: Game[] = [];
  for (const [key, g] of newMap.entries()) {
    if (!origMap.has(key)) {
      addedGames.push(g);
    }
  }

  // 2. Game bị xoá hoặc không còn
  const removedGames: Game[] = [];
  for (const [key, g] of origMap.entries()) {
    if (!newMap.has(key)) {
      removedGames.push(g);
    }
  }

  // 3. Game có thay đổi nội dung
  interface DiffDetail {
    game: string;
    game_id: string;
    changes: string[];
  }
  const changedGames: DiffDetail[] = [];

  for (const [key, newG] of newMap.entries()) {
    const origG = origMap.get(key);
    if (!origG) continue;

    const changes: string[] = [];

    if (origG.name !== newG.name) {
      changes.push(`Tên: "${origG.name}" ➔ "${newG.name}"`);
    }
    if (origG.is_viet_hoa !== newG.is_viet_hoa) {
      changes.push(`Việt hóa: ${origG.is_viet_hoa} ➔ ${newG.is_viet_hoa}`);
    }
    if (origG.size !== newG.size) {
      changes.push(`Size: "${origG.size}" ➔ "${newG.size}"`);
    }
    if (JSON.stringify(origG.genres) !== JSON.stringify(newG.genres)) {
      changes.push(`Thể loại: [${origG.genres.join(", ")}] ➔ [${newG.genres.join(", ")}]`);
    }
    if (origG.required_firmware !== newG.required_firmware) {
      changes.push(`Firmware: "${origG.required_firmware}" ➔ "${newG.required_firmware}"`);
    }
    if (origG.review_url !== newG.review_url) {
      changes.push(`Review URL: "${origG.review_url}" ➔ "${newG.review_url}"`);
    }

    // So sánh số lượng link hoặc url link
    if (origG.links.length !== newG.links.length) {
      changes.push(`Số lượng link: ${origG.links.length} ➔ ${newG.links.length}`);
    } else {
      const origUrls = origG.links.map((l) => l.url).join(";");
      const newUrls = newG.links.map((l) => l.url).join(";");
      if (origUrls !== newUrls) {
        changes.push(`Link tải đã thay đổi hoặc cập nhật URL mới`);
      }
    }

    if (changes.length > 0) {
      changedGames.push({
        game: newG.name,
        game_id: newG.game_id,
        changes,
      });
    }
  }

  // IN KẾT QUẢ
  console.log(`➕ Game mới thêm (${addedGames.length}):`);
  if (addedGames.length > 0) {
    addedGames.slice(0, 10).forEach((g) => console.log(`   + [${g.game_id || "NO_ID"}] ${g.name}`));
    if (addedGames.length > 10) console.log(`   ... và ${addedGames.length - 10} game khác.`);
  } else {
    console.log("   (Không có)");
  }

  console.log(`\n➖ Game bị xoá (${removedGames.length}):`);
  if (removedGames.length > 0) {
    removedGames.slice(0, 10).forEach((g) => console.log(`   - [${g.game_id || "NO_ID"}] ${g.name}`));
    if (removedGames.length > 10) console.log(`   ... và ${removedGames.length - 10} game khác.`);
  } else {
    console.log("   (Không có)");
  }

  console.log(`\n✏️ Game có thông tin thay đổi (${changedGames.length}):`);
  if (changedGames.length > 0) {
    changedGames.slice(0, 10).forEach((c) => {
      console.log(`   * [${c.game_id}] ${c.game}`);
      c.changes.forEach((ch) => console.log(`       - ${ch}`));
    });
    if (changedGames.length > 10) console.log(`   ... và ${changedGames.length - 10} game khác có thay đổi.`);
  } else {
    console.log("   (Không có)");
  }

  // Tùy chọn xuất file diff chi tiết
  if (addedGames.length > 0 || removedGames.length > 0 || changedGames.length > 0) {
    const diffReport = {
      summary: {
        original_total: originalGames.length,
        new_total: newGames.length,
        added_count: addedGames.length,
        removed_count: removedGames.length,
        changed_count: changedGames.length,
      },
      added: addedGames,
      removed: removedGames,
      changed: changedGames,
    };
    await Bun.write("./diff_report.json", JSON.stringify(diffReport, null, 2));
    console.log("\n📄 Báo cáo chi tiết toàn bộ khác biệt đã được lưu vào ./diff_report.json");
  } else {
    console.log("\n✨ Dữ liệu hoàn toàn trùng khớp 100%!");
  }
}

compare().catch(console.error);
