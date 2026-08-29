# Generation prompts

These templates are authoritative scaffolding. Fill every placeholder from the verified job manifest. Do not weaken the constraints when applying a style.

## Transparent 3×3 master

Use the installed `$imagegen` built-in path. Make the character reference visible and label it as the **identity reference**, not a pixel-exact edit target. Do not call an Image API or CLI fallback from this skill.

```text
Use case: stylized-concept
Asset type: transparent 3×3 reaction-sticker master sheet

STYLE DEFINITION:
Apply this resolved style to the material, internal line work, palette, texture, and character-shape treatment: {{STYLE_NAME}}. Apply only these conflict-safe traits: {{STYLE_TRAITS}}. Keep the same visual style consistently across all nine characters.

ACTION DEFINITIONS — FIXED GRID ORDER, LEFT TO RIGHT AND TOP TO BOTTOM:

1. {{ITEM_1}}
2. {{ITEM_2}}
3. {{ITEM_3}}
4. {{ITEM_4}}
5. {{ITEM_5}}
6. {{ITEM_6}}
7. {{ITEM_7}}
8. {{ITEM_8}}
9. {{ITEM_9}}

IDENTITY LOCK:
Use the supplied character image as the identity reference. Show the same recognizable character exactly nine times, once per cell. Preserve the face, head shape, hair, clothing, signature colors, body proportions, and identity-essential details. Change only the expression, pose, and action required by each definition above. Do not add unrequested text; if an action explicitly requires visible text, render only that exact text inside its own safe cell.

Use exaggerated internet-reaction expressions, including crying, confusion, shock, smugness, side-eye, and deadpan disbelief, with awkward poses, low-fi cutout textures, and absurd humor.

创建一张正方形（1:1）透明贴纸页，包含九个各不相同的贴纸，按 3×3 网格排列，每个贴纸呈现不同的表情、姿势或反应。贴纸之间留出较宽且完全透明的间隔。

无背景、阴影或重叠元素。所有人物均直接置于透明背景上，人物外轮廓与透明区域直接相接。禁止出现任何白色描边、黑色外描边、彩色描边、贴纸切边、轮廓边框、光晕、阴影或半透明边缘。不要模拟实体贴纸的白色切割边缘。

每个人物应像已经精准抠图完成的独立 PNG 表情素材。允许人物内部保留原本画风所需要的黑色线稿，但人物最外层禁止出现任何额外白色描边或贴纸边框。
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
