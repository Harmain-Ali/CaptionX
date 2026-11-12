<div align="center">

<img src="frontend/public/icon-256.png" width="112" alt="captionX logo" />

# captionX

**Roman Urdu captions for reels, voice-overs and videos, ready for DaVinci Resolve.**

Drop in a video or audio file. Get perfectly timed captions written the way Pakistan actually types:
`aaj hum baat karenge`, not `آج ہم بات کریں گے`.

[**Download for Windows**](../../releases/latest) · [Features](#features) · [How it works](#how-it-works) · [Run from source](#run-from-source) · [Contributing](#contributing)

![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0A0A0A?style=flat-square&labelColor=0A0A0A&color=FF4C00)
![Python](https://img.shields.io/badge/python-3.10%2B-0A0A0A?style=flat-square&labelColor=0A0A0A&color=FF4C00)
![React](https://img.shields.io/badge/react-19-0A0A0A?style=flat-square&labelColor=0A0A0A&color=FF4C00)
![License](https://img.shields.io/badge/license-MIT-0A0A0A?style=flat-square&labelColor=0A0A0A&color=FF4C00)

</div>

---

## What is captionX?

Most captioning tools are built for English. For Urdu content they either output Nastaliq script, which your audience doesn't read on a reel, or they spell Roman Urdu differently on every line.

captionX fixes that. It transcribes your speech, turns it into clean, consistent Roman Urdu, and gives you files that drop straight into DaVinci Resolve, including **one editable Text+ clip per caption**, and it works on the **free version** of Resolve with no scripting.

It runs on your computer. The only things that leave your machine are the audio and text sent to [Groq's free API](https://console.groq.com) for transcription and spelling.

## Features

- **Roman Urdu done properly.** Consistent Pakistani spellings, English words kept in English, numbers and brand names handled, and a glossary so `فن` always becomes `FANN`.
- **Accurate timing.** Whisper decides every timestamp. The language model only spells words and never sees or changes timing, so captions can't drift.
- **Text+ per line for Resolve.** Export a `.drt` timeline with one real Text+ clip per caption. No scripts, no Studio licence.
- **Every format you need:** `.srt`, `.vtt`, `.txt`, `.fcpxml`, a `.drt` timeline, and a Fusion `.setting` (a single Text+ whose text changes at each caption).
- **Spotify-style preview.** Play your file and watch the words fill in line by line. Click any line to jump to it, edit spelling inline, nudge timing by 50 ms.
- **History with settings.** Every run remembers the settings it used. Reuse them in one click.
- **Fast re-runs.** "Regenerate with other settings" reuses the transcript, so it's instant and uses no speech quota.
- **Clear errors.** Bad key, rate limit, no internet, silent audio, unsupported file: each says what happened and what to do. If the spelling step fails, your transcript is kept.
- **Premium dark UI.** Black and greys with one orange accent, spring-physics animation, and an (i) tooltip on every setting.
- **Private by default.** Settings, key and history stay in a folder on your PC.

## Download

### Windows installer (recommended)

1. Go to the [**latest release**](../../releases/latest) and download **`captionX-Setup-x.y.z.exe`**.
2. Run it. No admin rights are needed.
3. Open **captionX** from the Start menu or the desktop shortcut.
4. In **Settings**, paste your free [Groq API key](https://console.groq.com/keys) and press **Test key**.

Python, Node and ffmpeg are all bundled. You don't install anything else.

> **"Windows protected your PC"?** The installer isn't code-signed yet, so Windows SmartScreen warns about it. Click **More info**, then **Run anyway**. You can also read every line of the source and build the installer yourself (see [Build the installer](#build-the-installer)).

captionX opens in its own window with its own taskbar button, and quits by itself a few seconds after you close that window. It never quits while a job is running. A tray icon (under the `^` arrow) offers **Open** and **Quit** while it runs.

Your settings, key and history live in `%LOCALAPPDATA%\captionX` and survive updates and uninstalls.

### macOS and Linux

There is no installer for these systems yet. You can [run it from source](#run-from-source).

## Quick start

1. **Settings:** paste your Groq key, press **Test key**, then **Save settings**.
2. **Studio:** drop a file and press **Generate captions**. A 1–2 minute reel takes a few seconds.
3. **Check it:** press play and watch the lines light up. If captions are early or late, use the **Timing** nudge (or `,` and `.`). To fix a spelling, hover the line and click the pencil.
4. **Export:** pick a format in the Export panel (see below).

### Using the captions in DaVinci Resolve

| Format | What you get | How to use it in Resolve |
|---|---|---|
| **Text+ clips** (`.drt`) | One real Text+ clip per caption | Set frame rate and size, download, then **File → Import → Timeline…**. Copy the clips into your own timeline if the frame rate differs. |
| **SRT** (`.srt`) | Standard subtitles | **File → Import → Subtitle**, drag onto a subtitle track, style in the Inspector. |
| **Text+ settings** (`.setting`) | One Text+ whose text changes at every caption | Fusion page → right-click the Text+ node → **Settings → Load Settings…** |
| **FCPXML** (`.fcpxml`) | One editable title per caption | **File → Import → Timeline…**, drag onto V2, right-click → **Decompose in Place**. |
| **VTT / TXT** | Web captions / plain transcript | For YouTube, web players, or editing the script. |

> FCPXML can't carry Text+. Resolve itself drops Text+ clips when it exports FCPXML, and imported plain titles become simple Text. Use the `.drt` export when you want Text+.

**Player shortcuts:** `Space` play/pause · `←` `→` previous/next line · `L` loop the current line · `,` `.` timing −/+ 50 ms

## How it works

```
Audio/video ─► ffmpeg ─► Groq Whisper large-v3 ─► cue shaping ─► Groq GPT-OSS 120B ─► exports
               (16 kHz)   Urdu text + word times   3–6 word lines  Urdu script → Roman Urdu
```

1. **ffmpeg** extracts clean 16 kHz audio from your file.
2. **Whisper large-v3** (on Groq) transcribes the Urdu and returns word-level times.
3. The **segmenter** groups words into short, readable caption lines.
4. A **language model** (default `openai/gpt-oss-120b`) rewrites each line in Roman Urdu, following a strict JSON contract and your glossary.
5. The **exporters** write SRT, VTT, TXT, FCPXML, `.drt` and `.setting` files.

Because timestamps come only from Whisper, the spelling step can't shift a caption.

The master prompt lives in `backend/app/prompts.py` and is editable in **Settings → Roman Urdu writing → Master prompt**.

## Settings

Everything in Settings can be overridden for a single run in Studio → **Run options**.

- **Models:** Whisper (`large-v3` for accuracy, `large-v3-turbo` for speed) and the Roman Urdu model. *Refresh models* pulls Groq's live list.
- **Whisper:** language (Urdu or auto), temperature, vocabulary hint, hallucination filter.
- **Roman Urdu:** temperature, lines per request, letter case, punctuation, glossary, master prompt.
- **Timing:** words and seconds per line, minimum duration, pause break, linger, wrap width, default offset.
- **Limits:** audio format and chunk size, max upload and duration, timeout, retries.

## Run from source

You need Python 3.10+, Node.js 18+, [pnpm](https://pnpm.io), ffmpeg, and a free [Groq API key](https://console.groq.com/keys).

| ffmpeg on | Command |
|---|---|
| Windows | `winget install Gyan.FFmpeg` |
| macOS | `brew install ffmpeg` |
| Ubuntu | `sudo apt install ffmpeg` |

```bash
git clone https://github.com/Harmain-Ali/captionX.git
cd captionX

./run.sh          # macOS / Linux / WSL
run.bat           # Windows (double-click)
```

The script creates a virtual environment, installs the backend and frontend dependencies, starts both servers and opens **http://localhost:5173**.

<details>
<summary>Start the two servers manually</summary>

```bash
# terminal 1: backend
cd backend
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py                                           # http://127.0.0.1:8000

# terminal 2: frontend
cd frontend
pnpm install
pnpm dev                                                # http://localhost:5173
```

Single-server mode: run `pnpm build` in `frontend/`, and the backend serves the UI at http://127.0.0.1:8000.

</details>

### Build the installer

Pick one:

- **On GitHub, no Windows PC needed:** push the repo, open **Actions → Windows installer → Run workflow**, or push a tag like `v1.0.0`. Download the `.exe` from the run's artifacts, or from the Release when you used a tag. The workflow also starts the packaged app and checks that ffmpeg is inside it.
- **On a Windows PC:** install Python 3.10+, Node 18+ and pnpm, then double-click `build-windows.bat`. The result is `dist-installer\captionX-Setup-<version>.exe`.

Bump the version in `backend/app/__init__.py` before each release. The bundled ffmpeg is an LGPL build from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds).

## Project structure

```
captionX/
├── backend/            FastAPI app
│   ├── app/            pipeline, transcribe, segmenter, romanize, prompts,
│   │                   exporters (srt, fcpxml, fusion, drt), config, presence
│   ├── tests/          pytest suite (Groq mocked, real ffmpeg)
│   └── launcher.py     desktop entry point (window, tray, auto-quit)
├── frontend/           React 19 + TypeScript + Vite (pnpm)
│   └── src/            pages (Studio, History, Settings, Help), components, lib
├── packaging/          PyInstaller spec, Inno Setup script, ffmpeg fetch script
├── .github/workflows/  Windows installer build
├── run.sh · run.bat    one-step dev launchers
└── build-windows.bat   one-step installer build
```

**Stack:** Python · FastAPI · Groq (Whisper large-v3, GPT-OSS) · ffmpeg · React · TypeScript · Vite · Motion · PyInstaller · Inno Setup

## Contributing

Contributions are welcome: bug reports, ideas, docs and code.

1. **Open an issue first** for anything bigger than a small fix, so we can agree on the approach.
2. **Fork** the repo and create a branch: `git checkout -b fix/short-description`.
3. **Set up** the project with [Run from source](#run-from-source).
4. **Make your change.** Keep it focused, and match the style of the code around it.
5. **Test it:**
   ```bash
   cd backend
   pip install -r requirements-dev.txt
   pytest                       # 51 tests; Groq is mocked, no key needed

   cd ../frontend
   pnpm typecheck
   ```
6. **Open a pull request** that says what changed and why. Add a screenshot for UI changes.

**Good first contributions:** Roman Urdu spelling improvements (`backend/app/prompts.py`), more export formats, macOS and Linux packaging, and translations of the UI.

**Guidelines**
- The model must never touch timestamps. Timing comes from Whisper only.
- Add a test for every bug you fix.
- Never commit API keys. User data lives in `backend/data/` and is git-ignored.

## Troubleshooting

| You see | Do this |
|---|---|
| "Backend not running" | Start it (`./run.sh`). The page reconnects by itself. |
| "ffmpeg isn't installed" | Install ffmpeg and restart (source install only). The Windows installer includes it. |
| "Rate limit reached" with minutes | Free-tier cap. Wait, or pick `openai/gpt-oss-20b` in Settings (separate quota). |
| "Model unavailable" | Groq retired it. Settings → **Refresh models** → pick another, Save, then **Retry** on the failed job. |
| Spellings inconsistent | Lower the model temperature, add Glossary rules, keep the 120B model. |
| Wrong words from Whisper | Add names to **Vocabulary hint** and keep the language on Urdu. |
| Window shows the wrong icon | Update to the latest release. Report it with a screenshot if it persists. |

## Privacy

captionX has no accounts, no analytics and no server of its own. Your audio is sent to Groq for transcription and the transcript text is sent to Groq for spelling, under [Groq's terms](https://groq.com/privacy-policy/). Everything else (files, settings, key, history) stays on your computer.

## License

[MIT](LICENSE) © Harmain Ali

## Author

Built by **Harmain** · [Portfolio](https://harmain-dev.vercel.app/) · [GitHub](https://github.com/Harmain-Ali/) · [LinkedIn](https://www.linkedin.com/in/harmain-ali/)

If captionX saves you time, a ⭐ on the repo helps other creators find it.
