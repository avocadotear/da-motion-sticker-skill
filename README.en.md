# DA Motion Sticker Skill · 3×3 Animated GIF Sticker Packs

![License](https://img.shields.io/github/license/avocadotear/da-motion-sticker-skill?style=flat-square)
![Skill](https://img.shields.io/badge/Skill-Codex-111111?style=flat-square)
![GIF Pack](https://img.shields.io/badge/Output-3%C3%973%20GIF%20Pack-FF4D6D?style=flat-square)
![Styles](https://img.shields.io/badge/Styles-36%20Presets-8B5CF6?style=flat-square)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Required-007808?style=flat-square)
![Codex](https://img.shields.io/badge/Codex-Supported-222222?style=flat-square)

[中文 README](./README.md)

Turn one character reference into a clean, deliverable 3×3 animated GIF sticker pack. `da-motion-sticker-skill` produces a transparent master sheet, individual animated GIFs, optional static PNGs, a processing report, and a traceable ZIP. It can also hand off a chroma master to an AI video tool and resume with local keying and loop selection.

## Highlights

- One character image plus nine reactions, or one theme that expands into a fixed nine-item list.
- 36 style presets. Styles affect materials, lines, and shape language only; transparency, no outer frame, and inter-cell spacing always win.
- Two animation routes: safe local transforms or a resume workflow for an externally generated AI video.
- Automated checks for real alpha, a complete 3×3 grid, transparent gaps, chroma conflicts, GIF alpha, and looping.
- Portable job folders retain media, state, hashes, and reports without secrets or absolute home-directory paths.

## One-command Codex install

Git, Python 3.10+, and FFmpeg are required. This clones directly into the local Skill directory scanned by Codex; refresh or restart Codex when it completes.

```bash
git clone https://github.com/avocadotear/da-motion-sticker-skill.git "$HOME/.agents/skills/da-motion-sticker-skill"
```

Do not overwrite an existing directory. Update it with `git pull`, or remove a confirmed-unused copy before installing again.

Windows PowerShell:

```powershell
git clone https://github.com/avocadotear/da-motion-sticker-skill.git "$HOME\.agents\skills\da-motion-sticker-skill"
```

For development, clone anywhere and install a symlink instead:

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

Or let the skill expand a theme:

```text
Use $da-motion-sticker-skill to make a “Monday at work” sticker pack from the attached character, using style 04.
```

Add “also export static PNGs” for stills, or “use AI video generation” for the handoff route.

## The 36-style gallery

Choose by number, exact label, or natural-language description. The illustrated [6×6 preset gallery](./README.md#36-种风格一览) shows the exact visual mapping used by the skill. The canonical style labels are also listed in [`references/styles.md`](./references/styles.md).

## Animation routes

| Route | Best for | Output |
|---|---|---|
| Codex direct generation (default) | Fast, stable, naturally looped light motion | Chooses from `bob`, `bounce`, `shake`, `nod`, `sway`, `pulse`, `tilt`, and `hop` to make about one second of 12 fps transparent GIF animation. |
| AI video generation | More complex character motion | Exports transparent/chroma masters and a video prompt. Upload the result from Grok, Seedance, Doubao, or another tool to resume grid detection, soft keying, spill removal, and loop selection. |

The local route only translates, scales, rotates, or lightly squashes the whole sticker. It never redraws body parts or invents tears, text, or effects.

## Deliverables

Every job creates an atomically written ZIP in its own run directory:

```text
sticker-pack.zip
├── gifs/                       # 1–9 successful transparent GIFs
├── png/                        # present only when stills were requested
├── source/transparent-sheet.png
├── source/chroma-sheet.png
├── prompts/image-prompt.txt
├── prompts/video-prompt.txt
├── manifest.json
└── processing-report.json
```

For the video route, successful cells are delivered even if some cells fail; failures are recorded in the report. No empty ZIP is made if all nine cells fail.

## Requirements and local development

Runtime requirements: Python 3.10+, Pillow, NumPy, FFmpeg, and FFprobe. The project does not use SciPy, Node.js, or external video APIs. Install the Python dependencies with:

```bash
python -m pip install -e .
ffmpeg -version
ffprobe -version
```

The repeatable media entry points live in [`scripts/`](./scripts): `create_job.py`, `inspect_sheet.py`, `prepare_assets.py`, `animate_local.py`, `process_video.py`, and `package_job.py`. The Skill orchestrates them; the scripts keep media handling testable and deterministic.

## Privacy and media rights

Job files stay in a local run directory. `job.json` stores only relative paths, input hashes, status, and processing results—never API keys or absolute home-directory paths. Ensure you have rights to use the character image, video, and resulting stickers. Uploading to an external video service is governed by that service’s own retention and privacy terms.

## License

[MIT License](./LICENSE) · Copyright © DAAI
