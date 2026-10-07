export async function sendTelegramAlert(message: string): Promise<void> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;

  if (!token || !chatId) {
    console.log("ℹ️ Chưa cấu hình TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID trong .env nên bỏ qua thông báo Telegram.");
    return;
  }

  try {
    const url = `https://api.telegram.org/bot${token}/sendMessage`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: message,
        parse_mode: "HTML",
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      console.error("❌ Gửi cảnh báo Telegram thất bại:", errText);
    } else {
      console.log("📢 Đã gửi tin nhắn cảnh báo thành công qua Telegram!");
    }
  } catch (err) {
    console.error("❌ Lỗi mạng khi gọi Telegram API:", err);
  }
}

