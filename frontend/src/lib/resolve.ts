export const FPS_OPTIONS = [
  { value: "23.976", label: "23.976 fps" }, { value: "24", label: "24 fps" }, { value: "25", label: "25 fps" },
  { value: "29.97", label: "29.97 fps" }, { value: "30", label: "30 fps" }, { value: "50", label: "50 fps" },
  { value: "59.94", label: "59.94 fps" }, { value: "60", label: "60 fps" },
];

export const SIZE_OPTIONS = [
  { value: "1080x1920", label: "1080 × 1920 (Reels, Shorts, TikTok)" },
  { value: "1080x1350", label: "1080 × 1350 (4:5)" },
  { value: "1080x1080", label: "1080 × 1080 (square)" },
  { value: "1920x1080", label: "1920 × 1080 (landscape HD)" },
  { value: "1440x1080", label: "1440 × 1080 (4:3)" },
  { value: "2160x3840", label: "2160 × 3840 (vertical 4K)" },
  { value: "3840x2160", label: "3840 × 2160 (4K UHD)" },
];

/** Keep a saved custom value selectable even if it isn't one of the presets. */
export const withValue = (opts: { value: string; label: string }[], v: string) =>
  opts.some((o) => o.value === v) ? opts : [...opts, { value: v, label: v }];
