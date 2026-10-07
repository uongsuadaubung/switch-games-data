import type { ParsedGame } from "./types";
import { CONFIG } from "./config";

export interface LifecycleStats {
  newCount: number;
  expiredCount: number;
  removedCount: number;
  updatedCount: number;
  newGames: ParsedGame[];
  removedGames: ParsedGame[];
  updatedGames: { game: ParsedGame; changes: string[] }[];
}

/**
 * Quản lý vòng đời toàn diện:
 * 1. Phát hiện Game mới (gán is_new, added_at)
 * 2. Kế thừa & kiểm tra hết hạn 14 ngày của nhãn is_new
 * 3. Phát hiện Game bị xóa khỏi Sheet
 * 4. Phát hiện Game có thông tin thay đổi (Link, Firmware, Thể loại, Review, Size...)
 */
export function applyGameLifecycle(
  newGames: ParsedGame[],
  existingGames: ParsedGame[]
): { games: ParsedGame[]; stats: LifecycleStats } {
  // Map game cũ theo cả game_id và name chuẩn hoá để tìm kiếm nhanh
  const existingMap = new Map<string, ParsedGame>();
  const existingByName = new Map<string, ParsedGame>();

  existingGames.forEach((g) => {
    if (g.game_id) existingMap.set(g.game_id.toLowerCase(), g);
    existingByName.set(g.name.toLowerCase().trim(), g);
  });

  const now = new Date();
  const nowMs = now.getTime();
  const nowIso = now.toISOString();

  let expiredCount = 0;
  const newGamesList: ParsedGame[] = [];
  const updatedGamesList: { game: ParsedGame; changes: string[] }[] = [];

  // Mảng tập hợp ID/Name của game mới để phục vụ tìm game bị xóa
  const processedOldKeys = new Set<string>();

  const games = newGames.map((game) => {
    // Tìm game cũ: ưu tiên theo game_id, nếu không có thì tìm theo name
    const oldGame =
      (game.game_id && existingMap.get(game.game_id.toLowerCase())) ||
      existingByName.get(game.name.toLowerCase().trim());

    if (!oldGame) {
      // 1. GAME HOÀN TOÀN MỚI
      const brandNewGame: ParsedGame = {
        ...game,
        is_new: true,
        added_at: nowIso,
      };
      newGamesList.push(brandNewGame);
      return brandNewGame;
    }

    // Đánh dấu game cũ này đã xuất hiện (chưa bị xóa)
    if (oldGame.game_id) processedOldKeys.add(oldGame.game_id.toLowerCase());
    if (game.game_id) processedOldKeys.add(game.game_id.toLowerCase());
    processedOldKeys.add(oldGame.name.toLowerCase().trim());
    processedOldKeys.add(game.name.toLowerCase().trim());

    // 2. PHÁT HIỆN THAY ĐỔI THÔNG TIN (GAME UPDATED)
    const changes: string[] = [];
    if (oldGame.name !== game.name) changes.push(`Tên: "${oldGame.name}" ➔ "${game.name}"`);
    if (oldGame.size !== game.size) changes.push(`Size: "${oldGame.size}" ➔ "${game.size}"`);
    if (oldGame.required_firmware !== game.required_firmware) {
      changes.push(`Firmware: "${oldGame.required_firmware}" ➔ "${game.required_firmware}"`);
    }
    if (oldGame.review_url !== game.review_url) changes.push(`Review URL đã đổi`);
    if (oldGame.links.length !== game.links.length) {
      changes.push(`Số lượng link: ${oldGame.links.length} ➔ ${game.links.length}`);
    } else {
      const oldUrls = oldGame.links.map((l) => l.url).join(";");
      const newUrls = game.links.map((l) => l.url).join(";");
      if (oldUrls !== newUrls) {
        changes.push("Link tải cập nhật URL mới");
      }
    }

    if (changes.length > 0) {
      updatedGamesList.push({ game, changes });
    }

    // 3. KẾ THỪA VÒNG ĐỜI IS_NEW (14 NGÀY)
    if (oldGame.is_new && oldGame.added_at) {
      const addedMs = new Date(oldGame.added_at).getTime();
      if (nowMs - addedMs < CONFIG.TWO_WEEKS_MS) {
        return { ...game, is_new: true, added_at: oldGame.added_at };
      } else {
        expiredCount++;
      }
    }

    return game;
  });

  // 4. PHÁT HIỆN GAME BỊ XÓA (CÓ TRONG OLD NHƯNG KHÔNG CÒN TRÊN SHEET)
  const removedGamesList = existingGames.filter((g) => {
    const hasId = g.game_id && processedOldKeys.has(g.game_id.toLowerCase());
    const hasName = processedOldKeys.has(g.name.toLowerCase().trim());
    return !hasId && !hasName;
  });

  return {
    games,
    stats: {
      newCount: newGamesList.length,
      expiredCount,
      removedCount: removedGamesList.length,
      updatedCount: updatedGamesList.length,
      newGames: newGamesList,
      removedGames: removedGamesList,
      updatedGames: updatedGamesList,
    },
  };
}
