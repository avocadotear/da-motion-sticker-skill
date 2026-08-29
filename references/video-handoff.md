# Manual video handoff

Read this reference only for the external-video route.

## Entering the wait state

After `prepare_assets.py` has selected the least-conflicting chroma color:

1. Verify `source/chroma-sheet.png` is fully opaque and `prompts/video-prompt.txt` contains the same selected color name and hex value stored in `job.json`.
2. Set the job route to video and status to `waiting_for_video`.
3. Return the chroma master, the complete video prompt, the job ID, and the path/hash information needed to resume.
4. Tell the user to generate one fixed-camera image-to-video clip with their chosen service and upload the resulting video here.

Grok, Seedance, and 豆包 are examples, not integrated dependencies. Do not open them, log in, upload media, call an API, or claim provider-specific settings on the user's behalf. Do not continue polling while the user is away.

A concise handoff message should make these facts explicit:

- keep the original 3×3 layout and fixed camera;
- keep the exact pure background color shown in the supplied master;
- use roughly one-second simple loops and no cross-cell interaction;
- upload the video together with the job ID if several jobs exist;
- keep the local `job.json`; it is required for verified continuation.

## Resuming from an upload

Require the exact `job.json` and check that it is `waiting_for_video` or an explicitly confirmed `video_review_required` job. Recompute the reference SHA-256, hash the uploaded video, store the video at a job-relative path without overwriting any prior file, and record its hash.

Never choose among multiple unfinished jobs by filename, recency, topic or visual similarity. If the supplied job ID/path is ambiguous or its reference hash differs, stop and ask for the correct manifest.

Run:

```text
python scripts/process_video.py --job <run-directory>/job.json --video <uploaded-video>
```

The script owns decoding, timestamp-based resampling, multi-frame grid detection, chroma keying, stable crop, loop selection, GIF encoding and per-cell reporting. Do not pre-extract a second independent frame set with another tool; the pipeline must decode the video only once.

Reject an upload before binding it to the job if it exceeds 512 MiB, 30 seconds, 4096 pixels on either edge, the 250-million decoded-pixel budget, or the 360-frame cap. Probe and perform the bounded first decode before copying it under `source/`; an invalid upload must not become the recorded input.

## Review and completion

When grid confidence is low, return `qa/video-grid-preview-<video-sha-first-8>.png` and stop in `video_review_required`. Ask the user to confirm cuts with `--grid x1,x2,y1,y2` or `--accept-low-confidence`, or upload a cleaner fixed-grid video. Do not infer consent from silence and do not process a guessed layout. A different upload is allowed only with explicit `--replace-video` while already in review; retain the earlier source in `video_history`.

When one to nine cells succeed, status becomes `video_processed`. Show the successful count and identify failures by original item name, reason and diagnostic path. Continue to `package_job.py` for partial delivery unless the user asks to repair first.

When all nine cells fail, status becomes `video_failed`. Preserve the source video, preview, hashes and diagnostics; do not create an empty archive.
