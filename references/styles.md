# Conflict-safe style library

Use this catalog when the user selects a style by number/name or when `style=auto`. Apply only the listed material, line, palette, and character-shape traits.

## Global invariants override every preset

Every output remains a genuine-alpha, background-free 3×3 sheet with nine separated characters. The outer silhouette touches transparency directly. Never add an outer white/black/color sticker border, die-cut edge, cell panel, scenery, cast/contact/drop shadow, floor patch, glow, halo, aura, detached decoration, or cross-cell element. Keep all texture and graphic treatment clipped inside the character or an identity-essential held prop. Internal line art is allowed.

If a source style normally relies on paper, UI, stars, rays, scanlines, print offsets, or environmental motifs, express those traits inside the subject silhouette. Do not turn them into a cell background. These invariants take priority over the style name, a free-form description, and any example language.

## Presets

| # | Name | Conflict-safe traits | Good fit |
|---:|---|---|---|
| 1 | 低保真剪纸 Meme | Coarse paper grain, deliberately cut edges, awkward proportions, exaggerated internet-reaction faces; **no white cutline**. | Absurd reactions, crying, side-eye, giving up |
| 2 | Q版大头 Chibi | Head at roughly 50–65% of height, tiny torso and limbs, clean shapes, identity-preserving facial cues. | Friendly chat stickers and broad emotion sets |
| 3 | 3D 软陶 / Clay | Rounded hand-shaped volumes, subtle fingerprints and matte clay material, compact big-head proportions. | Joy, awe, tears, shock |
| 4 | 3D 毛绒玩偶 | Short plush fibers contained by a clean silhouette, stitched material details, collectible-toy proportions. | A recurring personal mascot or cozy reactions |
| 5 | 搪胶公仔 / Vinyl Toy | Smooth molded surfaces, simplified glossy volumes, bold collectible-figure proportions. | Branded character systems and playful reactions |
| 6 | 黏土定格 | Rougher handmade clay, visible tool marks, intentionally clumsy pose design. | Deadpan and absurd meme motion |
| 7 | 像素 / Pixel Art | Crisp 8-bit or 16-bit clusters, limited palette, game-like pose readability; no HUD or labels. | Tech, gaming, programmer, Codex themes |
| 8 | 复古街机 | Rich 1990s arcade sprite palette, chunky pixel shading, expressive combat-like silhouettes; no HP bars or UI panels. | Energetic action and achievement reactions |
| 9 | 日漫夸张表情 | Bold internal manga line work, elastic facial construction, strong pose language; no detached speed or focus lines. | Shock, disbelief, frustration, curiosity |
| 10 | 美式卡通 Meme | Heavy internal ink lines, flat color blocks, adult-animation timing and deadpan facial shapes. | Side-eye, smugness, disbelief |
| 11 | 报纸漫画 | Pen-and-ink line work, restrained red/yellow/blue, warm paper tones clipped inside the character only. | Dry humor and workplace reactions |
| 12 | 复古漫画网点 | Ben-Day dots and slight CMYK misregistration clipped to the subject, high-impact internal ink. | Loud surprise and refusal poses |
| 13 | 黑白漫画 | Near-monochrome palette, high contrast, controlled internal black masses and expressive hatching. | Silence, collapse, skepticism |
| 14 | 手绘涂鸦 | Uneven sketch lines, intentionally naive anatomy, spontaneous coloring contained by the silhouette. | Awkward, silly, low-fi reactions |
| 15 | 儿童蜡笔 | Thick waxy strokes, uneven fill, simplified shapes and deliberately innocent construction. | Adult sentiments with comic contrast |
| 16 | 油画恶搞 | Classical brushwork, modeled face and fabric, modern absurd pose; no painted backdrop or frame. | Formal-vs-modern meme contrast |
| 17 | 文艺复兴名画 Meme | Classical drapery, solemn pose design, old-master palette and modeling inside the isolated figure; no rays or scenery. | Waiting, failure, mock-heroic reactions |
| 18 | 浮世绘 Meme | Woodblock contours, flat color areas, period pattern language within clothing/props; no surrounding waves or clouds. | Modern actions in a traditional visual idiom |
| 19 | 中国传统年画 | Saturated red/green/yellow palette, woodblock texture, festive stylized anatomy; no decorative background panel. | Lunar New Year and celebratory sets |
| 20 | 国潮剪纸 | Extremely flat red-paper construction, cutout-like internal negative shapes, modern emoji-informed poses; no external cutline. | Festive, graphic, high-readability reactions |
| 21 | 水墨 Meme | Expressive ink contour, wash gradation and restrained negative-space logic within the subject; no detached splashes. | Quiet, dry, contemplative humor |
| 22 | 刺绣 / 布艺贴章 | Thread direction, fabric weave, internal stitched detail and simplified patch-like shapes; no separate patch border. | Brand mascots and tactile craft looks |
| 23 | 毛毡布贴 | Layered felt shapes, soft fibrous material, visible hand assembly inside a clean silhouette. | Warm handmade characters |
| 24 | 纸雕 / Layered Paper | Multiple paper layers and internal edge depth, achieved without cast/drop shadows or a backing panel. | Refined graphic sticker sets |
| 25 | 撕纸拼贴 Meme | Torn internal edges, mixed magazine/paper textures, deliberately rough collage construction; no loose scraps outside the subject. | Chaotic and absurd actions |
| 26 | Riso 孔版印刷 | Two-to-four ink colors, grain and slight registration drift clipped within the character. | Contemporary design-led IP |
| 27 | 丝网印刷 | Limited colors, high contrast, coarse ink texture and bold simplified shapes. | Indie-merch energy and strong silhouettes |
| 28 | Y2K 网络表情 | Early-web color choices, intentionally compressed rendering and metallic/iridescent accents contained inside the subject; no floating stars or text. | Nostalgic internet reactions |
| 29 | VHS / 低清截图 | Color drift, grain and scanline treatment clipped to the character, readable low-resolution silhouette. | Found-footage and reaction-frame humor |
| 30 | Windows 95 / 复古电脑 UI | Gray UI palette, beveled geometry and pixel-system motifs integrated into clothing/body/held props; no windows, labels, or cell panels. | AI, programmer, error-state themes |
| 31 | Mac OS 复古系统图标 | Classic Macintosh pixel palette, compact icon geometry and hourglass/bomb-inspired shapes integrated into the character; no dialog box. | Desktop-helper and retro-computing themes |
| 32 | Emoji 3D 混合 | Identity-preserving face with simplified emoji-like body language, rounded 3D forms and direct emotional readability. | Mainstream chat reactions |
| 33 | 表情符号拟人 | Character anatomy interprets the selected emoji expression through brows, eyes, mouth, hands and pose; no detached symbols. | Complete emoji-driven reaction sets |
| 34 | Reaction GIF 截帧 | Strong in-motion pose, deliberate pose imbalance and restrained subject-clipped motion softness; keep edges extractable. | Outputs intended to feel immediately animated |
| 35 | 夸张真人头 + 卡通小身体 | Photographic facial identity with a very small illustrated body and maximal scale contrast. | Personal-IP recognition and absurdity |
| 36 | 半写实 3D 大头人物 | Recognizable facial structure, polished semi-real 3D materials, highly chibi body proportions. | Balanced identity preservation and sticker appeal |

## `auto` recommendation

Choose one preset, state its number and name in the job, and avoid silently mixing several unrelated visual systems.

- Favor **2, 32, or 36** when identity recognition and broad chat usability matter most.
- Favor **1, 6, 14, 25, 29, or 34** for intentionally awkward internet-meme energy.
- Favor **3, 4, 5, 22, 23, or 24** for a tactile, collectible or mascot-led result.
- Favor **7, 8, 28, 30, or 31** for game, software, AI or retro-digital themes.
- Favor **16–21** when the humor depends on a traditional-art versus modern-action contrast.
- Favor **26 or 27** for limited-color graphic design, and **9, 10, 12, or 13** for line-led comic reactions.

When the reference strongly establishes a medium, prefer the closest compatible preset. A free style description may refine a preset, but it cannot weaken the global invariants.
