# Media QA rules

Automated checks are gates, not suggestions. Record machine-readable measurements and named failure reasons in `job.json` and `processing-report.json`.

## Transparent master

The sheet passes only when all of these are true:

- It decodes as a square image with an alpha channel and includes genuinely transparent pixels. An opaque RGB image, an all-255 alpha channel, white/solid fill, or visible checkerboard pattern is not transparency.
- All nine fixed cells contain meaningful non-transparent foreground.
- Horizontal and vertical grid gutters contain sufficiently transparent separation across the full sheet, not merely a few empty points.
- Foreground does not touch the outer canvas edge, a cell boundary, or a neighboring cell's safety region.
- Connected/occupied foreground stays within its assigned cell. One large component spanning cells is a hard failure.
- The overlay confirms the expected left-to-right, top-to-bottom mapping and no subject is clipped.

Use alpha occupancy as the primary evidence. RGB values hidden under alpha=0 do not count as visible foreground. Detect likely fake checkerboards from repeated alternating light/dark blocks in opaque or nearly opaque background regions and report that diagnosis explicitly.

On failure, save `qa/sheet-overlay.png` showing thirds, gutter/safety zones, occupied bounds and failed areas. `$imagegen` may retry once using the targeted failure list. A second failure sets `sheet_review_required` and stops for user correction.

## Split cells

For each passing cell:

1. Crop transparent padding around its complete alpha bounds without clipping semitransparent edge pixels.
2. Preserve aspect ratio.
3. Fit within a centered 512×512 transparent canvas with a motion-safe margin.
4. Do not upscale a tiny/noisy component into a valid sticker.

When `static=false`, these PNGs remain internal animation assets. When `static=true`, publish the nine PNGs and list them in the manifest.

## Chroma choice

Candidate colors are fixed:

| Name | Hex |
|---|---|
| green / 绿色 | `#00FF00` |
| blue / 蓝色 | `#0000FF` |
| magenta / 洋红色 | `#FF00FF` |

Measure each candidate against visible foreground pixels only. The collision score is the fraction of foreground colors within the configured color-distance tolerance of that candidate; semitransparent edge pixels may be weighted by alpha. Save the three scores, tolerance and implementation version. Pick the lowest score. Ask the user only when every candidate exceeds the implementation's documented conflict threshold; never silently default to green.

The chroma master must be fully opaque, use one spatially uniform selected color outside the subjects, preserve the 3×3 layout, and contain no transparency. The generated video prompt must repeat the selected human-readable name and exact hex consistently.

## Local animation

`motion-plan.json` may use only `bob`, `bounce`, `shake`, `nod`, `sway`, `pulse`, `tilt`, and `hop`. Transform the complete prepared RGBA sticker only; no local body-part redraw, inpainting or new effect layer is permitted.

Each output should be 512×512, 12 fps, approximately one second, infinitely looping, and encoded with an FFmpeg palette-generation/palette-use workflow that reserves transparency. Motion amplitude must stay within recorded safe margins. The first-to-last transition must be natural: periodic templates should sample a closed phase without duplicating a long pause, and the endpoint difference must remain within the template's acceptance tolerance.

Reject GIFs with an opaque matte, wrong dimensions, zero/one visible frame, no recorded loop, materially wrong duration, clipped motion, or a palette that destroys the subject edge.

## Uploaded video

- Verify the uploaded file's SHA-256 before resuming.
- Decode the source once and use real timestamps to resample to 12 fps. Do not assume 24/30/60 fps or constant frame rate.
- Infer actual row/column separators from multiple frames. Use the expected 3×3 topology as a prior, not as unquestioned fixed thirds.
- Save `qa/video-grid-preview-<video-sha-first-8>.png` with proposed boundaries and a confidence score. Low confidence sets `video_review_required` and stops until the user confirms with `--grid`/`--accept-low-confidence` or supplies a better video using explicit `--replace-video`.
- Key every cell with a soft matte around the recorded chroma value, suppress edge spill without changing alpha, and compute one stable union crop across the selected window. Fit the result to a 512×512 transparent canvas.
- Search for an approximately one-second window with visible motion and the smallest endpoint discontinuity. If no natural loop passes, use a recorded ping-pong fallback. Do not hide the fallback in the report.

Evaluate cells independently. A missing/clipped subject, persistent unkeyed background, cross-cell contamination, unusable loop, or empty result fails that cell but does not discard successful siblings. Package partial success and list failures with diagnostic paths. Nine failures set `video_failed` and prohibit ZIP creation.

## Final delivery

Before packaging, verify:

- One to nine successful GIFs exist and each matches its manifest hash.
- Static PNG presence exactly matches `static`.
- Both master sheets and both resolved prompts exist.
- Filenames, item indices and display names map consistently.
- `manifest.json` and `processing-report.json` contain only relative delivery paths and no secrets.
- GIF loop count, frame timing, dimensions and alpha have been inspected.
- The ZIP opens, contains no duplicate paths, follows the fixed tree and is non-empty.

Do not treat visual plausibility alone as proof of alpha, loop metadata, timing or archive correctness; those properties require deterministic inspection.
