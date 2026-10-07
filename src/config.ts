const spreadsheetId = process.env.SPREADSHEET_ID;
const spreadsheetGid = process.env.SPREADSHEET_GID;

if (!spreadsheetId || !spreadsheetGid) {
  throw new Error("Thiếu SPREADSHEET_ID hoặc SPREADSHEET_GID trong file .env!");
}

export const CONFIG = {
  SPREADSHEET_ID: spreadsheetId,
  TARGET_GID: parseInt(spreadsheetGid, 10),
  TWO_WEEKS_MS: 14 * 24 * 60 * 60 * 1000,
  GAMES_JSON_PATH: "./data/games.json",
};

