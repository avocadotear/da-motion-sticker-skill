# 交付契约

最终目录应为：

```text
delivery/
├── gifs/
│   ├── 01.gif
│   └── ... 09.gif
├── static/                 # 仅用户选择生成静态表情包时存在
│   ├── 01.png
│   └── ... 09.png
├── first-frames/           # 路线 A/B 的透明起始帧（如存在）
├── sheet-transparent.png
├── sheet-screen.png
├── image-prompt.txt
├── video-prompt.txt
├── keypose-plan/            # 路线 A：逐格动作计划与 9 个姿势页提示词
├── manifest.json
└── da-motion-sticker-pack.zip
```

硬性要求：

- `gifs/` 恰好九个文件，按行优先编号 `01.gif`–`09.gif`。
- 每个 GIF 至少两帧、设置无限循环、尺寸一致、存在透明索引，且不能全部透明。
- GIF 是二值透明；抗锯齿边缘以透明 WebP/PNG 更自然，但本技能的必交付格式是 GIF。
- 启用静态输出时，`static/` 恰好九个真正带 Alpha 的 PNG。
- ZIP 内使用相对路径，不能包含自身、临时帧目录、绝对路径或父目录跳转。
- `manifest.json` 记录来源路线、风格、反应列表、幕布 RGB、文件尺寸、SHA-256 与所有警告。
- 路线 A 的 `processing.json` 必须声明 `mode: keypose-local`、每格关键姿势数量和实际往返帧序列。不得出现仿射动画模式或把整体抖动称作角色动作。
- 低置信度网格、边界触碰、背景残留、首尾跳变或失败格必须明确报告。失败时交付成功格和报告，但不能声称完整九张。

运行 `scripts/package_delivery.py` 时默认拒绝覆盖已有交付目录。只有用户明确要求覆盖或当前任务使用全新空目录时才传 `--overwrite`。
