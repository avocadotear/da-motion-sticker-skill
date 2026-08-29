# Optional Codex pet handoff

This path is opt-in. Enter it only when the user explicitly asks for a Codex desktop pet. `pet=false` and an ordinary sticker/GIF request never trigger it.

## Dependency boundary

Check that the installed `$hatch-pet` skill is available. If it is missing, report that the optional dependency is unavailable and stop the pet portion. Do not download, install, imitate, or partially reimplement it.

When present, read and follow its current `SKILL.md` in full. `$hatch-pet` owns visual generation, pet-state semantics, deterministic assembly, visual QA, v2 validation, packaging and installation. Load the workspace dependencies it requires before running any of its scripts. Do not substitute this skill's GIF pipeline for its atlas pipeline.

## Grounding handoff

Provide `$hatch-pet` with:

- the original character reference as the primary identity source;
- the approved transparent master or representative prepared cells as supporting identity/style references;
- sticker GIFs only as optional motion/action inspiration;
- the user's pet name, description, style or personality constraints when supplied.

Do **not** map the nine arbitrary meme items one-to-one onto pet states. A sticker such as eating pizza, driving, side-eye, or crying is not automatically a valid app state. The pet must independently implement all nine standard semantic rows:

1. `idle`
2. `running-right`
3. `running-left`
4. `waving`
5. `jumping`
6. `failed`
7. `waiting`
8. `running` (active task work, not literal travel)
9. `review`

It must also complete all 16 clockwise look directions using the installed skill's current direction, continuity and blind-QA rules. Preserve the character's identity while allowing `$hatch-pet` to design state-appropriate poses.

## Acceptance and delivery

Do not install an intermediate 8×9 atlas. Accept only the complete v2 result with:

- an 8×11 atlas at the current hatch-pet cell geometry;
- all nine standard rows and 16 look directions validated;
- transparent, despilled, non-clipped sprites;
- required contact sheets, motion previews, direction/continuity QA and deterministic validation passing;
- `pet.json` containing `spriteVersionNumber: 2`.

After the installed `$hatch-pet` workflow passes, install the pet directly into the local Codex pets directory according to that skill's current contract. Report the installed pet ID and validation/preview paths. Do not add pet files to the sticker ZIP, do not create a second pet archive, and do not describe the sticker pack as a validated pet.
