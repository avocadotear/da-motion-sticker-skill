# A/B 动画路线

## A · Codex 直接生成

路线 A 使用真实关键姿势，不再对一张静态 PNG 做整体平移、旋转、缩放或抖动。完整流程见 [keypose-route.md](keypose-route.md)：

```bash
python3 scripts/compile_keypose_plan.py \
  --input-dir /absolute/path/to/job/prepared/cells \
  --output-dir /absolute/path/to/job/keypose-plan \
  --reactions '🚲,🚗,🎉,😭,💪,😎,🤔,🤩,🍕'
```

然后用每个原始单格 PNG 作为参考图生成对应的 2×2 关键姿势页，经 `prepare_keyposes.py` 拆分后，用 `render_keypose_pack.py` 确定性组帧。关键姿势生成失败时停止并报告，不允许自动退回低质量仿射动画。

## B · AI 视频生成

把 `prepared/sheet-screen.png` 与最终 `prompts/video-prompt.txt` 交给 Grok、Seedance 2.5、豆包或用户选择的图片生视频工具。提示词中的幕布名与 RGB 必须和图片一致。视频工具可能产生费用或上传外部服务；只有用户选择 B 并自行操作或明确授权对应工具时才执行。

收到用户上传的视频后运行：

```bash
python3 scripts/process_video.py input.mp4 /absolute/path/to/job/video-output \
  --rows 3 --cols 3 --fps 12 --grid-debug
```

处理器会：

- 从多帧四角估计实际幕布色并检查边缘一致性；
- 从所有采样帧中寻找持续存在的横纵透明缝，失败时才等分；
- 每格逐帧裁切；
- 仅删除与裁切边界连通的近幕布色区域，保留人物内部相近颜色；
- 用 FFmpeg 两阶段调色板输出循环透明 GIF；
- 解码回查帧数、循环标志、透明索引和空帧。

如果视频出现镜头移动、格子越界、背景渐变/闪烁、人物互相遮挡或无法分离，停止并报告，不能把错误素材静默包装。
