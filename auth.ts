import { google } from "googleapis";
import http from "http";

const CLIENT_ID = process.env.GOOGLE_CLIENT_ID;
const CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET;
const REDIRECT_URI = process.env.GOOGLE_REDIRECT_URI || "http://localhost:3000";

if (!CLIENT_ID || !CLIENT_SECRET) {
  console.error("❌ Vui lòng điền GOOGLE_CLIENT_ID và GOOGLE_CLIENT_SECRET vào file .env trước khi chạy auth.ts!");
  process.exit(1);
}

const oauth2Client = new google.auth.OAuth2(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI);

const authUrl = oauth2Client.generateAuthUrl({
  access_type: "offline", // bắt buộc để lấy refresh_token
  prompt: "consent",
  scope: ["https://www.googleapis.com/auth/spreadsheets.readonly"],
});

console.log("👉 Mở link này trên trình duyệt để đăng nhập Google:\n\n", authUrl, "\n");

// Mở server tạm để đón mã code Google trả về
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url!, `http://${req.headers.host}`);
  const code = url.searchParams.get("code");

  if (code) {
    res.end("Xác thực thành công! Bạn có thể tắt tab này và quay lại terminal.");
    server.close();

    const { tokens } = await oauth2Client.getToken(code);
    console.log("================ CHUỖI CẦN LẤY ================");
    console.log("REFRESH TOKEN CỦA BẠN LÀ:");
    console.log(tokens.refresh_token);
    console.log("================================================");
  }
}).listen(3000);
