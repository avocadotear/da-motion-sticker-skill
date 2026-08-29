# Generation prompts

These templates are authoritative scaffolding. Fill every placeholder from the verified job manifest. Do not weaken the constraints when applying a style.

## Transparent 3×3 master

Use the installed `$imagegen` built-in path. Make the character reference visible and label it as the **identity reference**, not a pixel-exact edit target. Do not call an Image API or CLI fallback from this skill.

```text
Use case: stylized-concept
Asset type: transparent 3×3 reaction-sticker master sheet

Primary request:
Using the attached character identity reference, create exactly nine distinct character stickers in one square 1:1 image. Arrange them in a strict 3×3 grid, ordered left-to-right and top-to-bottom as follows:

1. {{ITEM_1}}
2. {{ITEM_2}}
3. {{ITEM_3}}
4. {{ITEM_4}}
5. {{ITEM_5}}
6. {{ITEM_6}}
7. {{ITEM_7}}
8. {{ITEM_8}}
9. {{ITEM_9}}

Identity lock:
Keep the same recognizable character identity, face, head shape, hair, clothing, signature colors, body proportions and identity-essential props in all nine cells. Each cell may change only the expression, pose and action needed for its assigned item. Show one complete isolated character per cell.

Style/medium:
{{STYLE_NAME}}. Apply only these conflict-safe traits: {{STYLE_TRAITS}}.

Composition:
Square 1:1 canvas; exact 3×3 organization; nine non-empty independent subjects; generous fully transparent gutters horizontally and vertically; generous transparent padding around the outer canvas. No subject may touch the canvas edge, a grid boundary, a neighboring subject or another cell.

Transparency:
Output genuine RGBA transparency. The area outside each subject must have real alpha=0, not a white background, colored background, checkerboard pattern or simulated transparency. Every outer character silhouette must meet transparent pixels directly.

Hard constraints:
No outer white, black or colored outline; no sticker cutline or border; no background; no cell panel; no scenery; no cast, contact or drop shadow; no floor patch; no glow, halo or aura; no detached particles or decorations; no cross-cell element; no overlap between cells. Internal line art that belongs to the selected style is allowed. Keep all material and print texture clipped within the subject. Do not add captions, labels or unrequested text. If an item explicitly requires visible text, render only that exact text inside its own safe cell.

Deliverable:
One square PNG with a genuine alpha channel, suitable for deterministic 3×3 validation and splitting.
```

### Targeted retry

Automatic QA permits one retry only. Reuse the same reference, order, style and identity lock. Add only the concrete failures reported by `inspect_sheet.py`, for example:

```text
Regenerate the same nine-cell master and correct only these validation failures:
{{QA_FAILURES}}

Keep every requirement from the original prompt. In particular, preserve true alpha, wide empty gutters, transparent outer padding, complete subjects, fixed item order and no outer border. Do not change the character identity or approved cells merely to vary the result.
```

If the retry fails, stop and present the overlay preview; do not attempt a third generation.

## Chroma-screen video handoff

`prepare_assets.py` must replace both `{{CHROMA_NAME}}` and `{{CHROMA_HEX}}` with the selected value. The only allowed pairs are `green / 绿色` + `#00FF00`, `blue / 蓝色` + `#0000FF`, or `magenta / 洋红色` + `#FF00FF`. A delivered prompt must contain no unresolved placeholder and must never keep a hardcoded green instruction after another color is selected.

```text
将这张 3×3 九宫格中的九个角色视为九个彼此独立的 GIF 表情素材。

所有角色必须固定在各自原来的格子和位置内，只做轻微、简单、可循环的表情包动作。不得跨出各自区域，不得互相遮挡，不得与其他格子中的角色交互。

每个角色的单次动作周期约为 1 秒，并可自然循环。根据原表情分别匹配幅度克制的摇头、摆手、点头、耸肩、轻微后退、得意晃动、轻跳或左右侧目等动作。保持角色整体完整，让首尾动作尽可能衔接。

不要改变角色原本的身份、脸部特征、发型、服装、表情主题、道具、身体比例和九宫格位置。不要新增角色、手臂、手指、文字、道具或特效，不要让身体结构变形。

背景始终保持输入图片中的同一种纯 {{CHROMA_NAME}}（{{CHROMA_HEX}}），颜色、亮度和纹理均不得变化。不要生成场景、阴影、光斑、渐变或背景动画；不要在视频生成阶段尝试把背景改成透明。

镜头完全固定，不推拉、不摇移、不旋转，不改变构图。输出适合社交平台使用的短循环动画。

Keep every subject isolated in its original cell. Animate only the characters. Preserve clean edges, the original 3×3 layout, the fixed camera, and the uniform pure {{CHROMA_NAME}} ({{CHROMA_HEX}}) background. Do not add text, objects, effects, shadows, scenery, camera motion, or cross-cell interaction.
```

Provider names such as Grok, Seedance, or 豆包 are examples only. Do not call or automate any provider; the user generates and uploads the video manually.
