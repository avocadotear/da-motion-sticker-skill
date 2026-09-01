# A · Codex 关键姿势路线

本路线采用参考项目的 `keypose-local` 原则：图像模型负责生成真实姿势变化，本地代码只负责透明度归一、固定画布、排序、往返循环和编码。代码不能用整体平移、旋转、缩放、bounce、shake、sway 等方式假装角色在做动作。

## 1. 编译逐格动作计划

```bash
python3 scripts/compile_keypose_plan.py \
  --input-dir /absolute/path/to/job/prepared/cells \
  --output-dir /absolute/path/to/job/keypose-plan \
  --reactions '🚲,🚗,🎉,😭,💪,😎,🤔,🤩,🍕'
```

脚本生成 `keypose-plan.json` 和 `prompts/01.txt`–`09.txt`。动作必须根据每格真正可见的表情、姿势和现有道具决定；Emoji 只提供语义方向，不能凭空增加图中没有的道具。

## 2. 生成九张 2×2 关键姿势页

对每个 `01`–`09`：

1. 读取对应提示词。
2. 把 `prepared/cells/NN.png` 作为唯一角色参考图传给支持参考图的图像生成工具。
3. 生成一张正方形不透明纯绿底 2×2 姿势页，四格依次为：原始起始姿势、动作预备、动作峰值、动作恢复。不要向生成器请求透明底。
4. 保存为 `keypose-sheets/NN.png`。

每次生成必须锁定身份、画风、服装、颜色、道具库存、主体尺度和镜头。背景固定为平坦、均匀、连接画布四边的纯绿色 `#00FF00`，不得有纹理、渐变、阴影或光照变化。只改变动作所必需的身体姿态与表情细节。禁止文字、额外人物、额外肢体、跨格元素、场景、阴影底板、棋盘格和外轮廓贴纸边。

如果姿势页明显换脸、换装、改变道具、格数错误或没有真实姿势差异，重新生成该格，最多一次；仍失败则停止并报告。不能改用仿射抖动来冒充完成。

## 3. 拆分并锁定起始帧

```bash
python3 scripts/prepare_keyposes.py \
  --source-cells /absolute/path/to/job/prepared/cells \
  --pose-sheets /absolute/path/to/job/keypose-sheets \
  --output-dir /absolute/path/to/job/keyposes
```

处理器先移除与画布边缘连通的均匀背景，再验证真实 Alpha、2×2 透明缝与四个非空格子。为保证身份和首尾一致，`01-start.png` 使用原始静态单格；生成页的其余三格成为 `02-anticipation.png`、`03-peak.png`、`04-recovery.png`。所有姿势保留相同固定画布，不做逐帧自动缩放或漂移对齐。

## 4. 确定性组帧

```bash
python3 scripts/render_keypose_pack.py \
  /absolute/path/to/job/keyposes \
  /absolute/path/to/job/keypose-output \
  --fps 6
```

默认顺序为 `start → anticipation → peak → recovery → peak → anticipation`，回到下一轮的 `start`。每张 GIF 使用自适应二值 Alpha 阈值、两阶段 FFmpeg 调色板、无限循环与编码后复检，同时输出透明首帧 PNG 和无损动画 WebP。没有运行光流或生成式插帧时，不得声称存在平滑插帧。
