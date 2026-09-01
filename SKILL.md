---
name: da-motion-sticker-skill
description: Create a 3×3 animated GIF sticker pack from a character reference image plus nine reactions or a theme. Use for nine-grid motion sticker, 九宫格动态表情包, or transparent sticker-pack requests; do not use for ordinary image edits, single stickers, or generic GIF conversion.
---

# DA Motion Sticker Skill｜动态表情包制作器

Produce nine independently usable transparent GIF stickers, not only a grid preview. Preserve the reference character, keep every subject isolated inside its own cell, and finish with one delivery folder plus a ZIP.

## Intake

Require one character reference image and nine reactions, Emoji, or short action descriptions. A theme is acceptable when it clearly implies nine distinct reactions; otherwise propose nine and obtain confirmation.

- Style: accept a named/numbered preset. If absent, inspect the reference, read [references/styles.md](references/styles.md), recommend three suitable presets, and ask the user to choose.
- Static stickers: optional and **off by default**. Do not ask merely to reconfirm the default. If enabled, include nine transparent PNGs in delivery.
- Layout: fixed at 3 columns × 3 rows, row-major numbering `01`–`09`.
- Preserve visible identity: face, hair/fur, silhouette, skin/fur color, clothing, accessories, and recognizable props. Do not redesign these unless requested.

## Workflow

1. Create a job directory outside this skill package for the current character. Keep source, prepared assets, GIFs, reports, and delivery together.
2. Run `scripts/compile_prompts.py` with the chosen style and exactly nine reactions. It writes a solid-background source prompt and a screen-aware video prompt template.
3. Use the attached character image with a callable reference-image generation tool. Generate one square opaque 3×3 sheet on the exact uniform pure-green source background `#00FF00`. **Do not ask Codex/ImageGen for a transparent image in the current compatibility mode.** Save the returned file. Reject gradients, scenes, checkerboards, textured backgrounds, shadows, or non-uniform gutters.
4. Run `scripts/prepare_sheet.py`. It removes only the uniform source background connected to the canvas edge, creates and validates real Alpha locally, detects the actual 3×3 gutters, writes nine working PNG cells, chooses the safest final video screen from green/blue/magenta/white, composites the screen sheet, and records a report. The fixed green source-generation background and the dynamically selected video screen are separate stages. If the source image has no clean uniform edge-connected background, stop and regenerate it; do not guess-mask a scene.
5. Show the prepared transparent sheet and screen sheet. Ask the user to choose:
   - **A · Codex 直接生成**: read [references/keypose-route.md](references/keypose-route.md). Compile one vision-informed motion plan per sticker, use reference-image generation to create real anticipation/action/recovery poses on the same uniform pure-green source background, convert them to ordered transparent key poses locally, then run `scripts/render_keypose_pack.py`. Do not ask the generator for transparent pose sheets. Do not animate the original PNG by whole-layer translation, rotation, scaling, bounce, shake, or sway.
   - **B · AI 视频生成**: return `sheet-screen.png` and the compiled `video-prompt.txt`; mention Grok, Seedance 2.5, or 豆包 as examples, then stop and wait for the user to upload the resulting grid video. Do not claim the GIF pack is complete before the upload arrives.
6. For route B, run `scripts/process_video.py` on the uploaded video. It samples the real video, detects persistent gutters, removes only screen-colored regions connected to each crop edge, exports nine transparent GIFs and first-frame PNGs, and writes `processing.json`.
7. Only when the user explicitly asks for a Codex desktop pet, read [references/pet-route.md](references/pet-route.md), run `scripts/prepare_pet_handoff.py`, then use the available `hatch-pet` skill to map the nine reactions, add all required look directions and standard animation rows, visually QA, and package a v2 pet. A sticker-pack request alone does not authorize pet generation.
8. Run `scripts/package_delivery.py`. It verifies that exactly nine animated GIFs exist, copies optional static PNGs only when requested, adds reports/prompts/screen assets, and creates the final ZIP.

## Non-negotiable media rules

- Generated source sheets are intentionally opaque and must use one flat, edge-connected pure-green background. Prepared sheets and delivered PNG/GIF assets must contain real Alpha after local conversion and validation. A simulated checkerboard fails.
- The outer edge of each character meets transparency directly: no white/black/colored sticker outline, cut line, halo, glow, drop shadow, cell card, or opaque cell background. Internal line art belonging to the chosen style is allowed.
- Keep wide transparent gutters. No subject, prop, confetti, tear, motion line, or effect may cross a cell boundary or overlap another cell.
- Treat generated layout as untrusted until locally inspected. Stop if nine non-empty isolated cells cannot be recovered.
- Screen color is chosen from actual foreground pixels. Use the exact selected RGB value in both the composited sheet and video prompt; do not leave a hard-coded green claim when another screen was selected.
- For video matting, never delete a color globally. Remove only near-screen regions connected to crop borders so matching clothing and interior details survive.
- Keep the camera fixed and each loop local to its cell. Do not add people, limbs, fingers, captions, props, scenery, shadows, or camera motion.
- Route A requires genuine pose changes. Whole-layer affine animation is forbidden and is not an eligible fallback. If key-pose generation fails, stop and report or let the user choose route B.
- Package only completed outputs and useful audit files; omit temporary extracted frames.

## References

- Read [references/styles.md](references/styles.md) when selecting or explaining one of the 36 presets.
- Read [references/prompts.md](references/prompts.md) before image generation or when revising a prompt.
- Read [references/video-route.md](references/video-route.md) for A/B commands, upload handoff, and video-background constraints.
- Read [references/keypose-route.md](references/keypose-route.md) before executing route A.
- Read [references/output-contract.md](references/output-contract.md) before final packaging.
- Read [references/pet-route.md](references/pet-route.md) only for an explicit Codex pet request.

Use paths relative to this skill directory. Run scripts with `python3`; `ffmpeg` and `ffprobe` are required for route B.
