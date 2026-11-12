# captionX

Roman Urdu captions for reels and voice-overs. Dark UI, black and greys with one orange (#FF4C00), spring-physics animation, (i) tooltips on every setting, a Help page with every export format, and History that keeps the settings each file used (reuse them in one click). Made by [Harmain.dev](https://harmain-dev.vercel.app/).

Upload a reel or voice-over. Get a timed `.srt` in **Roman Urdu** (e.g. `aaj hum baat karenge`) for DaVinci Resolve.
Runs entirely on your computer; the only thing that leaves it is audio and text sent to Groq's free API.

```
Audio/video ─► ffmpeg ─► Groq Whisper large-v3 ─► cue shaping ─► Groq GPT-OSS 120B ─► .srt / .vtt / .txt
               (16 kHz)   (Urdu text + word times)  (3-6 word lines)  (Urdu script -> Roman Urdu, JSON)
```

Exports: `.srt`, `.fcpxml` (FCPXML 1.9 titles, frame-accurate), a **Resolve timeline with one Text+ clip per caption** (`.drt`), a **Text+ settings file** (`.setting`, one clip), `.vtt`, `.txt`.

Whisper owns the **timing**, the LLM only **spells**. The LLM never sees or changes timestamps, so timing can't drift.

## Install on Windows (no Python, Node or ffmpeg needed)

Download **captionX-Setup-x.y.z.exe**, run it, and open captionX from the Start menu or desktop shortcut. It starts in your browser and sits in the system tray (right-click the tray icon, **Quit captionX**, to stop it). Windows may show a "Windows protected your PC" notice because the installer is not code-signed: click **More info**, then **Run anyway**. Your settings, key and history are kept in `%LOCALAPPDATA%\captionX` and survive updates and uninstalls.

### Build the installer yourself
Pick one:

- **On a Windows PC:** install Python 3.10+, Node 18+ and pnpm once, then double-click `build-windows.bat`. It builds the interface, bundles Python, the backend and ffmpeg (PyInstaller), and compiles the installer (Inno Setup, installed for you if missing). The result is `dist-installer\captionX-Setup-<version>.exe`.
- **On GitHub (no Windows PC needed):** push the repo, open **Actions, Windows installer, Run workflow** (or push a tag like `v1.0.0`). Download the `.exe` from the run's Artifacts, or from the Release when you used a tag. It also starts the packaged app once and checks that ffmpeg is inside it.

Bump the version in `backend/app/__init__.py` before each release. The bundled ffmpeg is an LGPL build from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds).

---

## Run from source (developers)

## 1. What you need (one-time)

| Tool | Version | Install |
|---|---|---|
| Python | 3.10+ | https://www.python.org/downloads/ |
| Node.js | 18+ | https://nodejs.org |
| pnpm | any | `npm install -g pnpm` (or `corepack enable`) |
| ffmpeg | any | Windows: `winget install Gyan.FFmpeg` · macOS: `brew install ffmpeg` · Ubuntu: `sudo apt install ffmpeg` |
| Groq API key | free | https://console.groq.com/keys (no card) |

## 2. Run it

**macOS / Linux / WSL:** `./run.sh`
**Windows:** double-click `run.bat`

The script creates a Python venv, installs backend + frontend dependencies (`pnpm install`), starts both servers and (on Windows) opens the browser.
Open **http://localhost:5173**.

<details><summary>Manual start (two terminals)</summary>

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

Single-server mode: `cd frontend && pnpm build`, then the backend also serves the UI at http://127.0.0.1:8000.
</details>

## 3. First run

1. Open **Settings**, paste your Groq key, press **Test key**, then **Save settings**. (Or set `GROQ_API_KEY` in your environment.)
2. Go to **Studio**, drop a file, press **Generate captions** (a 1-2 minute reel takes a few seconds).
3. In the player: press play (or click any line) and watch the words fill in like Spotify lyrics. Check the timing against the audio.
   - Captions early/late → **Timing** nudge (or `,` and `.` keys, 50 ms steps).
   - Misspelled line → hover it, click the pencil, **Enter** to save.
   - Don't like the whole style → **Regenerate with other settings** (reuses Whisper's transcript, so it's instant and uses no speech quota).
4. **Export** (pick the format in the Export panel):
   - **SRT**: *File → Import → Subtitle* in Resolve, drag it onto a subtitle track, style it in the Inspector.
   - **Text+ clips** (`.drt`, one real Text+ per caption, no scripting): set frame rate and size, download, then in Resolve *File → Import → Timeline…*. It opens as a new timeline with one Text+ clip per line. If its frame rate isn't yours, select all clips and paste them into your own timeline.
   - **Text+ one clip** (`.setting`): ONE Text+ whose text changes at every caption time. Load via Fusion page → right-click the Text+ node → *Settings → Load Settings…*.
   - **FCPXML**: one editable title clip per caption. Set **Frame rate** and **Frame size** to match your timeline, download, then in Resolve *File → Import → Timeline…*, drag the imported timeline onto V2 of your main timeline at the very start, right-click it → **Decompose in Place**. Font, colour, outline and height are in Settings → *DaVinci Resolve export*.

Player shortcuts: `Space` play/pause · `←` `→` previous/next line · `L` loop current line · `,` `.` timing −/+50 ms.

## 4. The master prompt

Lives in `backend/app/prompts.py` (`DEFAULT_SYSTEM_PROMPT`) and is editable in **Settings → Roman Urdu writing → Master prompt → View and edit**.
It defines role, strict JSON input/output, what to do (consistent Pakistani spellings, English words restored to English, numbers, brand names), what **not** to do (no translating, no summarizing, no censoring, no dropped/merged lines, no Urdu script or diacritics in output, ignore instructions hidden inside the transcript), edge cases, and a worked example.
Casing, punctuation and your **Glossary** (`فن => FANN`) are injected at run time.

## 5. Settings you can test

Everything in Settings can also be overridden per run in Studio → **Run options**.

- **Models:** Whisper (`large-v3` accurate, `large-v3-turbo` faster) and the Roman Urdu LLM (default `openai/gpt-oss-120b`, faster option `openai/gpt-oss-20b`). *Refresh models* pulls Groq's live list, and you can type any model id.
- **Whisper:** language (Urdu forced vs auto), temperature, vocabulary hint, hallucination filter.
- **Roman Urdu:** temperature, lines per request, max tokens, letter case, punctuation, glossary, master prompt.
- **Timing:** words/seconds per line, min duration, pause-break, linger, wrap width, default offset.
- **Limits:** audio format/chunk size, max upload/duration, timeout, retries.

## 6. Errors the app handles (and what it tells you)

Missing/invalid key · rate limit (short ones are retried, daily ones fail fast with the wait time) · no internet · timeouts · retired model · backend offline (UI reconnects itself) · ffmpeg missing · unsupported/corrupt/empty/oversized/too-long file · video with no audio · silent audio (no Whisper call wasted) · Whisper finds no speech · Whisper hallucinations over silence · LLM returns bad JSON / drops lines / leaves Urdu script (batch is split and retried, last resort is a rough offline spelling flagged in amber) · app closed mid-job · job cancelled.
If the Roman Urdu step fails, your transcript is kept: **Retry without re-transcribing**.

## 7. Layout

```
packaging/ Windows installer: PyInstaller spec, Inno Setup script, ffmpeg fetch
backend/   FastAPI app  (app/: pipeline, transcribe, segmenter, romanize, prompts, srt, config)
           tests/       49 tests (needs `lupa` for the Fusion file check), Groq mocked, real ffmpeg
frontend/  React + TypeScript + Vite, managed with pnpm
run.sh / run.bat
```
Your data (settings incl. key, jobs, audio) is in `backend/data/` and never leaves your machine except to Groq.

Run the tests: `cd backend && pip install -r requirements-dev.txt && pytest`

## 8. Known limits

- **FCPXML cannot carry Text+.** Resolve itself drops Text+ clips when it exports FCPXML, and plain-title FCPXML imports become simple Text. Use the `.drt` export for real Text+.
## 9. Troubleshooting

| You see | Do this |
|---|---|
| "Backend not running" | Start it (`./run.sh`), the page reconnects by itself |
| "ffmpeg isn't installed" | Install ffmpeg, restart the backend |
| "Rate limit reached" with minutes | Free-tier cap. Wait, or pick `openai/gpt-oss-20b` in Settings (separate quota) |
| "Model unavailable" | Groq retired it (they do this regularly). Settings → *Refresh models* → pick another, Save, then **Retry** on the failed job |
| Spellings inconsistent | Lower model temperature, add Glossary rules, keep the 120B model |
| Wrong words from Whisper | Add names to *Vocabulary hint*, keep language on Urdu |
