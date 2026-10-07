import * as v from "valibot";
import { GamesListSchema, type ParsedGame } from "./types";
import { sendTelegramAlert } from "./notifier";

/**
 * Hàng rào bảo vệ (Circuit Breaker) sử dụng Valibot
 */
export async function validateGamesData(
  newGames: unknown,
  existingGames: ParsedGame[]
): Promise<ParsedGame[]> {
  const validationResult = v.safeParse(GamesListSchema, newGames);

  if (!validationResult.success) {
    const formattedIssues = v.flatten<typeof GamesListSchema>(validationResult.issues);
    console.error("❌ VALIBOT VALIDATION FAILED:");
    console.error(JSON.stringify(formattedIssues, null, 2));

    const totalErrors = validationResult.issues.length;
    // Lấy 3 lỗi đầu tiên để gửi thông báo chi tiết
    const sampleErrors = validationResult.issues
      .slice(0, 3)
      .map((iss, idx) => {
        const path = iss.path?.map((p) => p.key).join(".") || "root";
        return `${idx + 1}. [<code>${path}</code>]: ${iss.message}`;
      })
      .join("\n");

    await sendTelegramAlert(
      `🚨 <b>[CẢNH BÁO QUÉT GAME SWITCH]</b>\n\n` +
      `❌ <b>Phát hiện dữ liệu Google Sheets bị lỗi Schema!</b>\n` +
      `• Tổng số lỗi phát hiện: <b>${totalErrors}</b>\n\n` +
      `<b>Chi tiết lỗi mẫu:</b>\n${sampleErrors}\n\n` +
      `🛑 <b>Quy trình đã DỪNG LẬP TỨC!</b>\n` +
      `File <code>data/games.json</code> được giữ nguyên, không cập nhật.`
    );

    throw new Error(`🚨 Dữ liệu có ${totalErrors} lỗi không đạt chuẩn Valibot schema! Dừng quy trình ngay lập tức.`);
  }

  const validGames = validationResult.output;

  if (validGames.length === 0) {
    await sendTelegramAlert(
      `🚨 <b>[CẢNH BÁO QUÉT GAME SWITCH]</b>\n\n` +
      `❌ Danh sách game quét về hoàn toàn <b>RỖNG</b>!\n` +
      `🛑 Quy trình đã DỪNG LẬP TỨC. Giữ nguyên data/games.json.`
    );
    throw new Error("🚨 BẢO VỆ: Danh sách game tải về hoàn toàn RỖNG! Hủy bỏ.");
  }

  // Chống sụt giảm game bất thường (> 10%)
  if (existingGames.length > 0) {
    const minAcceptable = Math.floor(existingGames.length * 0.9);
    if (validGames.length < minAcceptable) {
      const dropMsg = `Số lượng game giảm đột ngột từ ${existingGames.length} xuống ${validGames.length} (dưới ngưỡng an toàn ${minAcceptable})!`;
      await sendTelegramAlert(
        `🚨 <b>[CẢNH BÁO QUÉT GAME SWITCH]</b>\n\n` +
        `❌ <b>Sụt giảm game bất thường!</b>\n` +
        `• ${dropMsg}\n` +
        `🛑 Quy trình đã DỪNG LẬP TỨC để bảo vệ data/games.json.`
      );
      throw new Error(`🚨 BẢO VỆ: ${dropMsg}`);
    }
  }

  return validGames;
}

