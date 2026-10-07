import * as v from "valibot";

// ─── Google Sheets Cell Raw Schemas ──────────────────────────────────────────
export const ChipRunSchema = v.object({
  startIndex: v.optional(v.number(), 0),
  chip: v.optional(
    v.object({
      richLinkProperties: v.optional(
        v.object({
          uri: v.optional(v.string(), ""),
          mimeType: v.optional(v.string(), ""),
        })
      ),
    })
  ),
});

export const TextFormatRunSchema = v.object({
  startIndex: v.optional(v.number(), 0),
  format: v.optional(
    v.object({
      link: v.optional(
        v.object({
          uri: v.optional(v.string(), ""),
        })
      ),
    })
  ),
});

export const SheetCellSchema = v.object({
  formattedValue: v.optional(v.string(), ""),
  hyperlink: v.optional(v.string(), ""),
  chipRuns: v.optional(v.array(ChipRunSchema), []),
  textFormatRuns: v.optional(v.array(TextFormatRunSchema), []),
  userEnteredValue: v.optional(
    v.object({
      formulaValue: v.optional(v.string(), ""),
      stringValue: v.optional(v.string(), ""),
    })
  ),
});

export type SheetCell = v.InferOutput<typeof SheetCellSchema>;

// ─── Game Output Schemas ─────────────────────────────────────────────────────
export const GameLinkSchema = v.object({
  label: v.pipe(v.string(), v.trim(), v.minLength(1, "Label không được rỗng")),
  file_name: v.pipe(v.string(), v.trim(), v.minLength(1, "Tên file không được rỗng")),
  url: v.pipe(v.string(), v.trim(), v.minLength(1, "URL tải không được để trống")),
});

export const GameItemSchema = v.object({
  name: v.pipe(v.string(), v.trim(), v.minLength(1, "Tên game không được để trống")),
  game_id: v.string(),
  is_viet_hoa: v.boolean(),
  image_url: v.string(),
  size: v.pipe(v.string(), v.trim(), v.minLength(1, "Dung lượng không được rỗng")),
  genres: v.array(v.string()),
  review_url: v.string(),
  links: v.pipe(v.array(GameLinkSchema), v.minLength(1, "Game phải có ít nhất 1 link tải")),
  required_firmware: v.string(),
  is_new: v.optional(v.boolean()),
  added_at: v.optional(v.string()),
  raw_image_url: v.optional(v.string()),
});

export const GamesListSchema = v.array(GameItemSchema);

export type GameLink = v.InferOutput<typeof GameLinkSchema>;
export type ParsedGame = v.InferOutput<typeof GameItemSchema>;

export interface UrlSpan {
  startIndex: number;
  endIndex: number;
  uri: string;
}
