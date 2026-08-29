---
name: da-motion-sticker-skill
description: Create a 3×3 animated GIF sticker pack from a character reference image plus nine reactions or a theme. Use for nine-grid motion sticker, 九宫格动态表情包, or transparent sticker-pack requests; do not use for ordinary image edits, single stickers, or generic GIF conversion.
---

# DA Motion Sticker

Turn one character reference into nine identity-consistent stickers, validate a real-alpha 3×3 master, animate the complete sticker shapes, and deliver a reproducible ZIP.

## Start the job

Require one character reference image. Accept either exactly nine user-supplied items or one theme. For a theme, infer nine distinct reactions/actions in the conversation, fix their left-to-right and top-to-bottom order, and pass that explicit list to `scripts/create_job.py`; the script itself does not call a model.

Accept a style by number, preset name, or free description. If absent, choose the best matching preset from [references/styles.md](references/styles.md). Default `static=false` and `pet=false`. Preserve original display text in the manifest while scripts create ASCII-safe filenames.

Read [references/output-contract.md](references/output-contract.md) before creating or resuming a job. Resume only from the exact `job.json` identified by its manifest and input SHA-256; never guess among unfinished jobs.

## Build and validate the master

Read [references/prompts.md](references/prompts.md), then use the installed `$imagegen` built-in generation path with the reference image visible. Do not call an Image API, external video API, or local image-generation CLI. Ask for a square 3×3 sheet with genuine alpha and isolated subjects. Style traits never override the global transparent-background and no-outer-border rules.

Run `scripts/inspect_sheet.py`, then follow [references/qa.md](references/qa.md). On automatic QA failure, make one targeted `$imagegen` retry. If that also fails, return the generated overlay preview and stop for user correction; do not keep regenerating.

Run `scripts/prepare_assets.py` only after the sheet passes. It splits and pads nine 512×512 assets, selects green, blue, or magenta by measured foreground collision, saves the chroma scores, and writes the selected color name and hex value into the video prompt. If every candidate clearly conflicts, stop and ask the user for a chroma choice.

The chroma set is closed: accept only green `#00FF00`, blue `#0000FF`, or magenta `#FF00FF`, including for a user's explicit conflict-resolution choice. Never accept an arbitrary hex color.

## Choose an animation route

If the route was not supplied earlier, ask only after the chroma master exists:

- **Codex direct generation**: first run `scripts/prepare_assets.py --job <job.json> --route local` to move the verified `awaiting_route` job to `assets_prepared`, then run `scripts/animate_local.py`. Motion is limited to whole-sticker translation, rotation, scale, and slight squash using controlled templates. Do not redraw limbs or add tears, text, props, particles, or other effects.
- **AI video generation**: read [references/video-handoff.md](references/video-handoff.md), run `scripts/prepare_assets.py --job <job.json> --route video` to atomically enter `waiting_for_video`, provide the chroma master and generated prompt, and stop until the user uploads a video. Then run `scripts/process_video.py` against the same verified job.

Both routes are fixed at 512×512, 12 fps, and approximately one second per GIF. Low-confidence video grid detection requires the hashed preview and explicit user confirmation. A different upload may replace a bound review-state video only with `--replace-video`; retain the earlier source and history. Accept partial video delivery: package successful GIFs and report failures. If all nine fail, do not create an empty ZIP.

## Package and optional pet

Run `scripts/package_job.py` only after at least one GIF exists. The ZIP contract is defined in [references/output-contract.md](references/output-contract.md); static PNGs are included only when `static=true`.

Only when the user explicitly requests a Codex pet, read [references/pet-handoff.md](references/pet-handoff.md) and invoke the installed `$hatch-pet`. Treat the original character and sticker outputs as identity/action references, not as nine pet states. Require the full v2 pet workflow and install the approved pet directly; never add it to the sticker ZIP. If `$hatch-pet` is absent, report the optional dependency and do not install it automatically.

## Stop conditions

Stop without guessing or overwriting when the reference is missing, nine items cannot be fixed, a target path or symlink already exists, a resume hash or job revision mismatches, repeated sheet QA fails, chroma selection is ambiguous, video-grid confidence is low, all video cells fail, FFmpeg/FFprobe is unavailable, or an optional pet dependency is missing. Preserve diagnostics and the current job state for recovery; resume only the exact job after verifying its immutable intake and artifact hashes.
