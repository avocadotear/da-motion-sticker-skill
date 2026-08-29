# Job, state, and output contract

Read this reference when creating, resuming, packaging, or auditing a run.

## Ownership and paths

- Each run uses a unique ASCII-safe directory under the chosen output root. Never reuse, delete, or overwrite an existing run directory.
- Every script receives the exact job path. A process uses its own temporary directory; final media is published create-new by hard link, while only the managed manifest may atomically replace its prior revision.
- Store paths inside `job.json` relative to the run directory. Never persist API keys, access tokens, environment dumps, or absolute home-directory paths.
- Keep original Chinese, emoji, punctuation and display names in manifest fields. Artifact filenames use a stable two-digit index plus an ASCII slug; if transliteration is empty or unsafe, fall back to `01-sticker` through `09-sticker`.
- Reject traversal, device names, path separators, control characters and destinations outside the run directory.

## Job record

`job.json` is the source of truth. It records, at minimum:

```json
{
  "schema_version": "0.1",
  "skill": "da-motion-sticker",
  "job_id": "unique-ascii-id",
  "status": "awaiting_sheet_generation",
  "created_at": "RFC-3339 UTC timestamp",
  "updated_at": "RFC-3339 UTC timestamp",
  "revision": 1,
  "input_hash": "canonical SHA-256 string",
  "intake": {
    "reference_sha256": "file SHA-256",
    "contents": ["骑车 🚲", "... exactly nine ordered labels"],
    "style_requested": "2",
    "style_resolved": "2 - Q版大头 Chibi",
    "route_requested": "auto",
    "static_requested": false,
    "pet_requested": false
  },
  "pack": {
    "display_name": "工作日表情包",
    "slug": "sticker-pack"
  },
  "reference": {
    "path": "source/reference.png",
    "original_name": "角色.png",
    "sha256": "file SHA-256",
    "width": 1024,
    "height": 1024
  },
  "theme": null,
  "contents": [
    {"index": 1, "display_name": "骑车 🚲", "slug": "01-sticker", "motion_hint": null}
  ],
  "style": {
    "requested": "2",
    "resolved": "2 - Q版大头 Chibi"
  },
  "options": {
    "static": false,
    "route": "auto",
    "pet": false
  },
  "paths": {
    "image_prompt": "prompts/image-prompt.txt",
    "video_prompt": "prompts/video-prompt.txt",
    "video_prompt_template": "prompts/video-prompt.template.txt",
    "transparent_sheet": "source/transparent-sheet.png",
    "chroma_sheet": "source/chroma-sheet.png",
    "cells_dir": "work/cells",
    "gifs_dir": "gifs",
    "png_dir": "png",
    "qa_dir": "qa",
    "motion_plan": "motion-plan.json",
    "processing_report": "processing-report.json"
  },
  "chroma": {
    "selected": null,
    "scores": {},
    "needs_review": false
  },
  "artifacts": {
    "cells": [],
    "pngs": [],
    "gifs": [],
    "transparent_sheet": null,
    "chroma_sheet": null,
    "package": null
  },
  "qa": {"sheet": {"passed": null, "attempts": []}},
  "errors": []
}
```

This is an explanatory minimum, not permission to remove additional reproducibility fields used by the scripts. `input_hash` is the canonical SHA-256 string over the immutable intake fields; `reference.sha256` is the copied file hash. Both are immutable after intake. Artifact groups are objects/arrays of records rather than bare path arrays. Every state-changing command appends structured QA/error evidence, updates `updated_at`, and advances the manifest `revision` with a lock/CAS check.

## State transitions

The normal path is:

```text
awaiting_sheet_generation
  ├─ sheet_review_required       (QA failed; one retry or user correction)
  └─ sheet_validated
       ├─ chroma_review_required    (all three candidates conflict)
       ├─ awaiting_route            (prepared, route=auto)
       ├─ assets_prepared            (prepared, route=local)
       └─ waiting_for_video           (prepared, route=video)
            ├─ video_review_required  (grid confidence too low)
            ├─ video_processed        (one to nine cells succeeded)
            └─ video_failed           (all cells failed)

assets_prepared → local_animated
local_animated | video_processed → packaged
```

When `route=auto`, choosing local changes the prepared job into the local-animation path; choosing video changes it to `waiting_for_video`. A low-confidence video grid may proceed only after explicit confirmation against the stored preview. Do not package `video_failed` or create an archive containing zero GIFs.

Resume rules:

1. Require the exact `job.json` path; do not select the newest directory or infer which unfinished job the user meant.
2. Recompute and compare SHA-256 for the reference and any uploaded video before mutation.
3. Verify the state permits the requested transition and all recorded relative paths stay inside the run directory.
4. Never silently rewind a later state. Start a new unique job if the user wants a different reference, item order, or incompatible option.

## Working tree

A typical job may contain additional diagnostic files, but owned paths follow this shape:

```text
<job-id>/
├─ job.json
├─ source/
│  ├─ reference.png
│  ├─ transparent-sheet.png
│  └─ chroma-sheet.png
├─ prompts/
│  ├─ image-prompt.txt
│  ├─ video-prompt.template.txt
│  └─ video-prompt.txt              # rendered after chroma selection
├─ work/
│  └─ cells/
├─ gifs/
├─ png/                         # populated only when static=true
├─ qa/
│  ├─ sheet-attempt-01-overlay.png
│  └─ video-grid-preview-<sha8>.png
├─ motion-plan.json
├─ processing-report.json
└─ delivery/
   └─ <pack-slug>.zip
```

Intermediates are job-local and never enter the final archive unless the ZIP contract names them.

## Script responsibilities

- `scripts/create_job.py`: create a unique run, copy/hash the reference, freeze nine items and write prompts/job state. Theme inference happens in Codex before this command; the script always receives the explicit nine-item list.
- `scripts/inspect_sheet.py`: copy and validate the generated transparent sheet, record QA, and render an overlay when useful.
- `scripts/prepare_assets.py`: split/trim/pad cells, measure chroma collision, create the chroma master, and finish the dynamic video prompt.
- `scripts/animate_local.py`: create `motion-plan.json` and nine whole-sticker GIFs with the supported templates.
- `scripts/process_video.py`: hash and decode one uploaded video once, detect the grid across frames, key/crop/pad cells, select loop windows, encode successful GIFs, and record per-cell failures.
- `scripts/package_job.py`: validate required artifacts and atomically build a deterministic ZIP. It performs no generation or media repair.

Commands must fail clearly when FFmpeg/FFprobe is absent and must not install system dependencies.

## ZIP contract

The final archive contains exactly the applicable paths below:

```text
gifs/                              # one to nine successful GIFs
  01-<ascii-slug>.gif
  ...
png/                               # directory omitted unless static=true
  01-<ascii-slug>.png
  ...
source/
  transparent-sheet.png
  chroma-sheet.png
prompts/
  image-prompt.txt
  video-prompt.txt
manifest.json
processing-report.json
```

`manifest.json` is a delivery-safe snapshot of the job: original display names, stable order, relative artifact paths, source hashes, style, options, route, chroma choice/scores, GIF properties, and tool/schema versions. It contains no secret or user-home path. `processing-report.json` records QA results, loop method, warnings, successful indices and failed indices with actionable reasons.

The archive is reproducible: use stable path ordering, stable metadata/permissions and a fixed ZIP timestamp. Write to a job-owned temporary file, validate it, then atomically publish it. If the final ZIP path already exists, stop instead of overwriting it.
