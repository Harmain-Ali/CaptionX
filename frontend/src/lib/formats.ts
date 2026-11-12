export type FormatId = "srt" | "fcpxml" | "drt" | "fusion" | "vtt" | "txt";

export interface FormatInfo {
  id: FormatId;
  name: string;
  ext: string;
  tagline: string;
  /** one line: when to pick it */
  bestFor: string;
  /** needs frame rate and size to match the timeline */
  timeline: boolean;
  steps: string[];
}

export const FORMATS: FormatInfo[] = [
  {
    id: "srt", name: "SRT", ext: ".srt", tagline: "Subtitle track",
    bestFor: "The safe choice. Works in Resolve, Premiere, CapCut, YouTube and almost everything else.",
    timeline: false,
    steps: [
      "Download the .srt file.",
      "In DaVinci Resolve choose File, Import, Subtitle… and pick the file.",
      "Drag it from the Media Pool onto a subtitle track above your video.",
      "Select the track and style font, size and position in the Inspector.",
    ],
  },
  {
    id: "drt", name: "Text+ clips", ext: ".drt", tagline: "One Text+ per caption",
    bestFor: "Real Text+ clips you can move, trim and style one by one on the timeline.",
    timeline: true,
    steps: [
      "Set the frame rate and size to match your project, then download the .drt file.",
      "In Resolve choose File, Import, Timeline… and pick it. It opens as a new timeline with one Text+ clip per caption.",
      "Check Timeline, Settings. If the frame rate is not yours, press Ctrl+A in that timeline, copy, and paste the clips at the start of your main timeline.",
      "Select all the Text+ clips together to change font, colour or outline once in the Inspector.",
    ],
  },
  {
    id: "fusion", name: "Text+ one clip", ext: ".setting", tagline: "One Text+, text keyframed",
    bestFor: "Free Resolve, no scripting. One Text+ clip whose text changes at every caption time.",
    timeline: true,
    steps: [
      "Set the frame rate and size, then download the .setting file.",
      "On the Edit page drag Fusion Titles, Text+ onto a track above your video. Start it at the very beginning and stretch it to the end.",
      "Open the Fusion page, right-click the Text+ node and choose Settings, Load Settings… then pick the file. (Or press Copy here and Ctrl+V in the node area.)",
      "Press play. Fine-tune the look in the Inspector. To change wording, edit it here and export again.",
    ],
  },
  {
    id: "fcpxml", name: "FCPXML", ext: ".fcpxml", tagline: "Title clips (plain Text)",
    bestFor: "Editable title clips for Final Cut or Resolve. Resolve turns them into plain Text, not Text+.",
    timeline: true,
    steps: [
      "Set the frame rate and size to match your timeline, then download the .fcpxml file.",
      "In Resolve choose File, Import, Timeline… and pick it.",
      "Drag the imported timeline onto V2 of your main timeline, at the very start.",
      "Right-click it and choose Decompose in Place. Every caption lands at its exact time as its own clip.",
    ],
  },
  {
    id: "vtt", name: "VTT", ext: ".vtt", tagline: "Web captions",
    bestFor: "Web video players, HTML5 <track>, and some social platforms.",
    timeline: false,
    steps: ["Download the .vtt file.", "Upload it next to your video where the platform asks for captions."],
  },
  {
    id: "txt", name: "Text", ext: ".txt", tagline: "Plain lines",
    bestFor: "A clean transcript with no timing. Good for posts, scripts and proofreading.",
    timeline: false,
    steps: ["Download the .txt file, or use Copy to paste the lines anywhere."],
  },
];

export const formatById = (id: string) => FORMATS.find((f) => f.id === id) ?? FORMATS[0];
