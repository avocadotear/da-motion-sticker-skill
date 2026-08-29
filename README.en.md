# da-motion-sticker

`da-motion-sticker` is a standalone Codex Skill that turns one character reference plus nine requested items—or one theme—into a 3×3 transparent animated GIF sticker pack and a traceable delivery ZIP.

[Chinese documentation](README.md)

## Features

- Build from an exact nine-item list, or let Codex infer and freeze nine ordered items from a theme.
- Choose among 36 conflict-safe style presets by number/name, or provide a free style description.
- Generate a genuine-alpha 3×3 master through the system `$imagegen`; the skill never calls the Image API directly.
- Detect real versus simulated transparency, nine-cell occupancy, transparent gutters, boundary contact, and fake checkerboard backgrounds.
- Select green `#00FF00`, blue `#0000FF`, or magenta `#FF00FF` by foreground color collision, then write the actual choice into the video prompt.
- Choose between Codex whole-sticker code animation and a manual external AI-video handoff.
- Deliver 512×512, 12 fps, roughly one-second, infinitely looping transparent GIFs; the video route supports partial success.
- Optionally create a formal Codex v2 pet, but only after an explicit user request and only through an installed `$hatch-pet`.

## Requirements

- Python 3.10+
- [Pillow](https://pillow.readthedocs.io/) and [NumPy](https://numpy.org/)
- `ffmpeg` and `ffprobe` available on `PATH`
- Codex built-in `$imagegen` for master generation
- Optional: an installed `$hatch-pet` for the pet route

The project does not depend on SciPy, Node.js, or any external video API.

### FFmpeg prerequisite

Install an official FFmpeg distribution through your system package manager and verify:

```text
ffmpeg -version
ffprobe -version
```

Common installation paths:

- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt install ffmpeg`
- Windows: `winget install Gyan.FFmpeg`, or another verifiable FFmpeg distribution

## Installation

```text
git clone https://github.com/avocadotear/da-motion-sticker.git
cd da-motion-sticker
python -m pip install -e .
```

Link the repository root into the agent skill directory. If the target already exists, **stop and inspect it; do not overwrite it**.

macOS / Linux:

```text
test ! -e "$HOME/.agents/skills/da-motion-sticker"
ln -s "$(pwd)" "$HOME/.agents/skills/da-motion-sticker"
```

Windows PowerShell (symbolic links may require Developer Mode or administrator privileges):

```powershell
$Target = Join-Path $HOME ".agents\skills\da-motion-sticker"
if (Test-Path $Target) { throw "Target already exists: $Target" }
New-Item -ItemType SymbolicLink -Path $Target -Target (Get-Location)
```

After Codex restarts or refreshes, the skill remains available for automatic invocation and can also be invoked explicitly as `$da-motion-sticker`.

## Using it in Codex

The recommended interface is a natural-language request with the character reference attached.

### Exact nine items

```text
Use $da-motion-sticker with the attached character reference.
Keep this order: riding a bike 🚲, driving 🚗, celebrating 🎉, crying 😭,
powering up 💪, smug 😎, thinking 🤔, amazed 🤩, eating pizza 🍕.
Use preset 2 (Chibi) and animate directly in Codex.
```

### Infer from a theme

```text
Use $da-motion-sticker with the attached character reference to make a
"Monday at work" nine-grid animated sticker pack. Recommend a style and nine
items, then keep their order fixed after the job is created.
```

In theme mode, Codex infers the nine items before calling the deterministic scripts. `create_job.py` does not call a model and does not guess the list itself.

### Include static PNGs

```text
Use $da-motion-sticker for this animated nine-grid pack and also include all
nine static transparent PNGs in the final ZIP.
```

### External AI-video route

```text
Use $da-motion-sticker to prepare the transparent and chroma masters, then use
the "AI video generation" route.
```

The skill returns the chroma master and a video prompt containing the actual selected color, then enters `waiting_for_video`. Generate the clip yourself in Grok, Seedance, 豆包, or another tool and upload it. The skill resumes through the original `job.json` and SHA-256 values; it never guesses between multiple unfinished jobs.

When a job begins with the default `route=auto`, its first `prepare_assets.py` call stops at `awaiting_route` after creating the chroma master. Run the command matching the user's choice:

```text
# Codex direct generation
python scripts/prepare_assets.py --job "/path/job.json" --route local

# AI video generation
python scripts/prepare_assets.py --job "/path/job.json" --route video
```

These commands verify the hashes of the prepared artifacts and advance only the route/state; they do not regenerate assets. A job created with a preselected `local` or `video` route cannot later switch to the opposite route.

Uploaded videos are limited to 512 MiB, 30 seconds, 4096 pixels on either edge, a 250-million decoded-pixel budget, and at most 360 sampled frames. The pipeline decodes once per processing attempt from real timestamps and resamples to the fixed 12 fps. Low-confidence detection writes `qa/video-grid-preview-<first-8-video-SHA>.png`; after inspecting it, the user may explicitly pass `--accept-low-confidence` or confirmed cuts as `--grid x1,x2,y1,y2`. Use `--replace-video` only when the job is already in `video_review_required` and the user explicitly supplies a different upload. The earlier source is retained, and its relative path and hash move into the job history.

### Explicit Codex pet request

```text
After $da-motion-sticker finishes the sticker pack, also create and install a
Codex v2 pet for this character.
```

The pet request is delegated to an installed `$hatch-pet` for the formal nine states, 16 look directions, and complete QA. Arbitrary meme actions are not forced into pet-state slots. The pet is installed directly into the local Codex pets directory and is not included in the sticker ZIP.

## Deterministic scripts

The scripts are stable, reproducible interfaces primarily called by the Skill; they are not a standalone creative model. When invoking them directly, the exact nine items must already be known.

Example `items.json`:

```json
[
  "Riding a bike 🚲",
  "Driving 🚗",
  "Celebrating 🎉",
  "Crying 😭",
  "Powering up 💪",
  "Smug 😎",
  "Thinking 🤔",
  "Amazed 🤩",
  "Eating pizza 🍕"
]
```

Codex direct-animation route:

```text
python scripts/create_job.py --reference "/path/character.png" --items-file "/path/items.json" --style "2" --route local --output-root "/path/runs"
python scripts/inspect_sheet.py --job "/path/runs/<job-id>/job.json" --sheet "/path/generated-transparent-sheet.png"
python scripts/prepare_assets.py --job "/path/runs/<job-id>/job.json"
python scripts/animate_local.py --job "/path/runs/<job-id>/job.json"
python scripts/package_job.py --job "/path/runs/<job-id>/job.json"
```

Manual video-handoff route:

```text
python scripts/create_job.py --reference "/path/character.png" --items-file "/path/items.json" --theme "Monday at work" --route video --output-root "/path/runs"
python scripts/inspect_sheet.py --job "/path/runs/<job-id>/job.json" --sheet "/path/generated-transparent-sheet.png"
python scripts/prepare_assets.py --job "/path/runs/<job-id>/job.json"
python scripts/process_video.py --job "/path/runs/<job-id>/job.json" --video "/path/uploaded-video.mp4"
python scripts/package_job.py --job "/path/runs/<job-id>/job.json"
```

`--theme` is job metadata only. Even when a theme is supplied, pass the already-frozen list through `--items` or `--items-file`. Quote paths containing spaces or non-ASCII characters.

Inspect every command:

```text
python scripts/create_job.py --help
python scripts/inspect_sheet.py --help
python scripts/prepare_assets.py --help
python scripts/animate_local.py --help
python scripts/process_video.py --help
python scripts/package_job.py --help
```

## Output

The final ZIP has a fixed layout:

```text
gifs/                         # 1–9 successful GIFs
png/                          # present only when static=true
source/transparent-sheet.png
source/chroma-sheet.png
prompts/image-prompt.txt
prompts/video-prompt.template.txt (placeholder template created with the job)
prompts/video-prompt.txt (resolved prompt written after chroma selection)
manifest.json
processing-report.json
```

Artifact names use stable indices and cross-platform-safe ASCII slugs. Original Chinese, emoji, and display names remain in the manifest. `job.json` stores relative paths, input hashes, state, chroma scores, artifacts, and QA; it never stores secrets or absolute user-home paths. An automatic style is resolved at intake to one concrete `number - name` value, such as `2 - Q版大头 Chibi`. The immutable `intake` and its canonical `input_hash` prevent a resume from changing the reference, ordered items, resolved style, or initially requested options; `revision` rejects concurrent and stale writes.

Run directories, process-private temporary directories, and outputs are job-owned. Final artifacts are validated before they are published with create-only semantics. Any existing file or symlink makes the operation stop; nothing is overwritten. Recovery always names the same `job.json` and revalidates the immutable intake, the reference/video, and recorded artifact SHA-256 values. Diagnostics, bound source files, and the current state remain available for recovery, and the skill never guesses another unfinished job.

See [references/output-contract.md](references/output-contract.md) for the full contract, [references/qa.md](references/qa.md) for validation, and [references/styles.md](references/styles.md) for all 36 styles.

## Privacy and media rights

- References, masters, videos, and intermediate frames stay in a unique local job directory. The scripts do not upload them and do not record credentials.
- `$imagegen` handles images according to the Codex built-in tool rules; this project does not call the OpenAI Image API directly.
- External AI-video services are selected and operated by the user. Review each provider's privacy, retention, and commercial-use terms before uploading.
- You must own or obtain the rights and consent needed for character art, likenesses, trademarks, generated media, and final distribution. This project grants no additional rights to inputs or generated media.
- Obtain appropriate permission before sharing stickers depicting real people or third-party IP, and avoid deceptive, infringing, or harassing uses.

## Development and validation

```text
python -m pytest
python /path/to/skill-creator/scripts/quick_validate.py .
```

Tests use programmatically generated, copyright-free nine-grid PNG/video fixtures. CI does not call ImageGen or external video services. The project supports Python 3.10/3.12 on macOS, Linux, and Windows; media codec tests require FFmpeg/FFprobe.

## Design provenance

The project takes conceptual workflow inspiration from [`motion-sticker-pack`](https://github.com/kobingogo/motion-sticker-pack/blob/6531b374c8a5c324a7d98067408832084a2182c9/SKILL.md), but copies none of its code. Transparency validation, job state, chroma selection, media processing, and packaging are independent implementations intended not to inherit the reference project's [historical media CI failure](https://github.com/kobingogo/motion-sticker-pack/actions/runs/33147161430). The skill layout follows [OpenAI Build skills](https://developers.openai.com/codex/build-skills).

## License

MIT © DAAI. See [LICENSE](LICENSE).
