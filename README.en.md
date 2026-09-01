# DA Motion Sticker Skill · 3×3 Animated GIF Sticker Packs

![License](https://img.shields.io/github/license/avocadotear/da-motion-sticker-skill?style=flat-square)
![Skill](https://img.shields.io/badge/Skill-Codex-111111?style=flat-square)
![GIF Pack](https://img.shields.io/badge/Output-3%C3%973%20GIF%20Pack-FF4D6D?style=flat-square)
![Styles](https://img.shields.io/badge/Styles-36%20Presets-8B5CF6?style=flat-square)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Recommended-007808?style=flat-square)

[中文](./README.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

`da-motion-sticker-skill` turns one character reference into nine separate animated GIF stickers with transparent backgrounds. A completed delivery includes the GIFs, optional static PNGs, transparent and chroma-key sheets, processing reports, and a ZIP archive. Animation can stay inside Codex using generated key poses, or move to an external image-to-video tool and return for local splitting and keying.

## What it does

- Accepts one character image plus nine reactions, actions, or emoji. If only a theme is provided, the Skill proposes nine items for approval.
- Includes 36 visual presets. Characters must meet transparency directly at the outer edge, without white strokes, black outlines, shadows, or cell cards.
- Uses real generated key poses for the Codex route. It does not fake motion by moving, rotating, scaling, or shaking an unchanged PNG.
- Supports image-to-video tools such as Grok, Seedance 2.5, and Doubao, followed by local grid detection, keying, and GIF encoding.
- Checks alpha, 3×3 spacing, chroma conflicts, frame count, GIF transparency, and infinite looping.

## Install in Codex

Git and Python 3.9+ are required. The video route requires FFmpeg and FFprobe; they are also recommended for higher-quality GIF palettes on the Codex route. Clone the repository into the local Skill directory scanned by Codex, then refresh or restart Codex.

```bash
git clone https://github.com/avocadotear/da-motion-sticker-skill.git "$HOME/.agents/skills/da-motion-sticker-skill"
```

If the directory already exists, enter it and run `git pull --ff-only`. Do not overwrite a development copy or a copy with uncommitted changes.

Windows PowerShell:

```powershell
git clone https://github.com/avocadotear/da-motion-sticker-skill.git "$HOME\.agents\skills\da-motion-sticker-skill"
```

For development, clone anywhere and install a symbolic link:

```bash
git clone https://github.com/avocadotear/da-motion-sticker-skill.git
ln -s "$(pwd)/da-motion-sticker-skill" "$HOME/.agents/skills/da-motion-sticker-skill"
```

## Quick start

Attach a character reference in Codex, then say:

```text
Use $da-motion-sticker-skill with the attached character reference to create a 3×3 animated GIF pack:
happy, aggrieved, angry, surprised, shy, confused, thumbs-up, goodbye, sleeping.
```

Or let the Skill expand a theme:

```text
Use $da-motion-sticker-skill to make a “Monday at work” sticker pack from the attached character, using style 04.
```

Static PNG export is off by default. Add “also export static PNGs” when needed. After the source sheet is prepared, choose either the Codex key-pose route or the AI video route.

## Workflow

1. The Skill confirms the nine reactions and compiles the image prompt.
2. The source 3×3 sheet is generated on exact flat green `#00FF00`. This compatibility step is intentional; the source image is not requested with transparency.
3. Local processing removes only the uniform background connected to the canvas edges, creates real alpha, detects the grid, and writes nine transparent cells.
4. For the video route, the Skill chooses the least conflicting screen from green, blue, magenta, and white based on the character colors.
5. The selected animation route produces and validates nine GIFs. The package is complete only when all nine pass.

The green source background and the video screen are separate decisions. The video screen may therefore use a different color.

## 36-style gallery

Choose a style by number, exact label, or natural-language description. The illustrated [6×6 preset gallery](./README.md#36-种风格一览) contains both static and animated previews. Canonical labels are stored in [`references/styles.md`](./references/styles.md), with machine-readable presets in [`assets/style-presets.json`](./assets/style-presets.json).

Every preset still follows the same output rules: transparent outer edges, clear spacing, no sticker border, no shadow, and no cell background.

## Animation routes

| Route | Best for | How it works |
|---|---|---|
| Codex key poses | Staying in Codex with controlled, readable motion | Generates a 2×2 pose sheet for each sticker: start, anticipation, peak, and recovery. Local assembly follows `start → anticipation → peak → recovery → peak → anticipation` to create a transparent loop. |
| AI video | More continuous or complex motion | Exports the selected chroma sheet and a video prompt. Generate a fixed-camera 3×3 video in Grok, Seedance 2.5, Doubao, or another tool, then upload it for local splitting, keying, and GIF encoding. |

The Codex route has no whole-layer affine fallback. If a cell changes identity, clothing, props, or lacks real pose differences, it may be regenerated once. A second failure stops that cell and produces a report instead of substituting low-quality motion.

The local renderer normalizes alpha, assembles the loop, and uses an FFmpeg palette when available. It can also export first frames and animated WebP previews. It does not claim frame interpolation that it did not perform.

## Deliverables

A complete run creates this delivery directory and ZIP. The final package always contains exactly nine validated GIFs.

```text
delivery/
├── gifs/                       # 01.gif–09.gif
├── static/                     # only when static PNGs were requested
├── first-frames/               # transparent first frames, when available
├── sheet-transparent.png
├── sheet-screen.png
├── image-prompt.txt
├── video-prompt.txt            # present for the video/screen workflow
├── keypose-plan/               # route-A plans and per-cell prompts
├── reports/
├── manifest.json
└── da-motion-sticker-pack.zip
```

Successful intermediate assets and diagnostics may remain in the run directory after a failure, but an incomplete result is not labeled as a complete nine-sticker pack.

## Requirements and local development

Runtime requirements are Python 3.9+, Pillow, and NumPy. The video route requires FFmpeg and FFprobe. Without FFmpeg, the Codex route can fall back to Pillow encoding, although palette quality is usually lower.

```bash
python -m pip install -r requirements.txt
python -m pytest
ffmpeg -version
ffprobe -version
```

Main scripts in [`scripts/`](./scripts):

- `compile_prompts.py`: compiles image and video prompts.
- `prepare_sheet.py`: converts the flat screen to alpha, detects and splits the grid, and selects a video screen.
- `compile_keypose_plan.py`, `prepare_keyposes.py`, and `render_keypose_pack.py`: implement the Codex key-pose route.
- `process_video.py`: splits and keys an uploaded 3×3 video, then encodes GIFs.
- `package_delivery.py`: revalidates all nine GIFs and creates the delivery directory and ZIP.
- `prepare_pet_handoff.py`: prepares a handoff only when the user explicitly requests a Codex desktop pet.

## Privacy and media rights

Run files stay in a local directory unless you choose an external video service. Reports may record input paths, SHA-256 hashes, processing settings, and warnings for diagnosis; inspect local paths before sharing reports publicly. The scripts do not store API keys. Make sure you have the right to use the character image, video, and resulting stickers. External services apply their own upload, training, and retention policies.

## License

[MIT License](./LICENSE) · Copyright © DAAI

## Questions and feedback

If you run into a problem, feel free to [open an Issue](https://github.com/avocadotear/da-motion-sticker-skill/issues) or add me on WeChat: `DAAIGC2046`. I’ll take a look when I see your message.

<img src="assets/wechat-daaigc2046.jpg" alt="DAAI WeChat QR code, WeChat ID DAAIGC2046" width="360">
