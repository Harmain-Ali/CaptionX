import { applyCasing, wrapBalanced } from "../lib/format";

/** A 9:16 frame showing the caption exactly as the exported SRT will carry it (casing + line wrap). */
export function PhonePreview({ text, casing, maxChars }: { text: string | null; casing: string; maxChars: number }) {
  const shown = text ? wrapBalanced(applyCasing(text, casing), maxChars) : "";
  return (
    <div className="phone" aria-label="How the caption looks on screen">
      <div className="phone-screen">
        <div className="phone-chrome" aria-hidden="true"><i /><i /><i /></div>
        {shown
          ? <p className="phone-caption" key={shown}>{shown}</p>
          : <p className="phone-idle">Press play to see captions</p>}
      </div>
    </div>
  );
}
