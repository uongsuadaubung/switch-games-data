const spreadsheetId = process.env.SPREADSHEET_ID || "";
const spreadsheetGid = process.env.SPREADSHEET_GID || "";

export const CONFIG = {
  SPREADSHEET_ID: spreadsheetId,
  TARGET_GID: spreadsheetGid ? parseInt(spreadsheetGid, 10) : 0,
  TWO_WEEKS_MS: 14 * 24 * 60 * 60 * 1000,
  GAMES_JSON_PATH: "./data/games.json",
};

export function validateSpreadsheetConfig() {
  if (!CONFIG.SPREADSHEET_ID || !CONFIG.TARGET_GID) {
    throw new Error("Thiếu SPREADSHEET_ID hoặc SPREADSHEET_GID trong file .env!");
  }
}

