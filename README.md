# da-motion-sticker

`da-motion-sticker` 是一个独立的 Codex Skill：用一张角色参考图和九项内容（或一个主题）生成 3×3 透明动态 GIF 表情包，并输出可追溯的 ZIP 交付包。

[English documentation](README.en.md)

## 功能

- 从精确九项清单建包，或由 Codex 根据主题推导九项并固定顺序。
- 支持 36 种冲突安全风格，也接受名称、编号或自由描述。
- 通过系统 `$imagegen` 生成真实 Alpha 的 3×3 母版，不直接调用 Image API。
- 自动检查真/伪透明、九格占用、透明间隔、越界和伪棋盘格背景。
- 自动选择绿幕 `#00FF00`、蓝幕 `#0000FF` 或洋红幕 `#FF00FF`，并把实际颜色写入视频提示词。
- 两条动态路线：Codex 对完整贴纸做代码动效，或用户在外部 AI 视频工具生成后上传处理。
- 输出 512×512、12 fps、约 1 秒、无限循环的透明 GIF；视频路线支持部分成功交付。
- 可选生成正式 Codex v2 宠物，但只在用户明确提出时交给已安装的 `$hatch-pet`。

## 要求

- Python 3.10+
- [Pillow](https://pillow.readthedocs.io/) 和 [NumPy](https://numpy.org/)
- `ffmpeg` 与 `ffprobe` 可在 `PATH` 中调用
- 用于母版生成的 Codex 内置 `$imagegen`
- 可选：用于宠物路线的已安装 `$hatch-pet`

项目不依赖 SciPy、Node.js 或任何外部视频 API。

### FFmpeg 前置条件

使用系统包管理器安装官方 FFmpeg 发行版，然后确认：

```text
ffmpeg -version
ffprobe -version
```

常见安装方式：

- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt install ffmpeg`
- Windows: `winget install Gyan.FFmpeg` 或其他可验证的 FFmpeg 发行版

## 安装

```text
git clone https://github.com/avocadotear/da-motion-sticker.git
cd da-motion-sticker
python -m pip install -e .
```

把项目根目录作为 Skill 链接到代理 Skill 目录。如果目标已存在，**停止并检查，不覆盖**。

macOS / Linux：

```text
test ! -e "$HOME/.agents/skills/da-motion-sticker"
ln -s "$(pwd)" "$HOME/.agents/skills/da-motion-sticker"
```

Windows PowerShell（创建符号链接可能需要开发者模式或管理员权限）：

```powershell
$Target = Join-Path $HOME ".agents\skills\da-motion-sticker"
if (Test-Path $Target) { throw "Target already exists: $Target" }
New-Item -ItemType SymbolicLink -Path $Target -Target (Get-Location)
```

重启或刷新 Codex 后，Skill 会保持自动触发，也可显式调用 `$da-motion-sticker`。

## 在 Codex 中使用

推荐直接描述交付目标并附上角色参考图。

### 精确九项

```text
使用 $da-motion-sticker，根据附件角色图生成动态表情包。
九项按顺序为：骑车🚲、开车🚗、庆祝🎉、哭泣😭、用力💪、得意😎、思考🤔、惊喜🤩、吃披萨🍕。
风格用 2 号 Q版大头，选择 Codex 直接生成 GIF。
```

### 主题自动生成

```text
使用 $da-motion-sticker，根据附件角色图做一套“周一上班”主题的九宫格动态表情包。
请你推荐风格和九项内容，但建立任务后保持顺序不变。
```

主题模式由 Codex 先推导出九项内容，再传给脚本。`create_job.py` 本身不调用模型，也不在脚本内“猜”九项。

### 同时交付静态 PNG

```text
使用 $da-motion-sticker 生成这套九宫格动态表情，并把九张静态透明 PNG 也加入最终 ZIP。
```

### 外部 AI 视频路线

```text
使用 $da-motion-sticker 先生成透明母版和色幕母版，动态路线选择“AI 视频生成”。
```

Skill 会返回色幕图和已替换实际颜色的视频提示词，然后进入 `waiting_for_video`。你在 Grok、Seedance、豆包或其他工具生成视频后上传，Skill 会通过原 `job.json` 和 SHA-256 继续，不会在多个未完成任务之间猜测。

如果任务最初使用默认 `route=auto`，首次 `prepare_assets.py` 会在色幕母版完成后停在 `awaiting_route`。用户选择后必须执行对应命令：

```text
# Codex 直接生成
python scripts/prepare_assets.py --job "/path/job.json" --route local

# AI 视频生成
python scripts/prepare_assets.py --job "/path/job.json" --route video
```

这两条命令只校验已准备产物的哈希并推进路线/状态，不重新生成素材。创建任务时如果已预选 `local` 或 `video`，后续不允许切换到反方路线。

视频上传限制为 512 MiB、最长 30 秒、单边不超过 4096 像素，解码预算不超过 2.5 亿像素且最多取 360 帧。管线按真实时间戳一次解码并采样到固定 12 fps。低置信网格会保存 `qa/video-grid-preview-<视频SHA前8位>.png`；用户查看后可明确传入 `--accept-low-confidence` 或已确认的 `--grid x1,x2,y1,y2`。只有当任务已在 `video_review_required` 且用户明确上传了不同视频时，才使用 `--replace-video`；旧视频不删除，其相对路径和哈希进入历史记录。

### 显式请求 Codex 宠物

```text
使用 $da-motion-sticker 完成表情包后，还要为这个角色生成并安装 Codex v2 宠物。
```

宠物请求会交给已安装 `$hatch-pet`完成正式九状态、16 环视方向和 QA。九个 Meme 动作不会被生硬当成九种宠物状态。宠物直接安装到本机 Codex pets 目录，不进入表情包 ZIP。

## 底层脚本

脚本是给 Skill 稳定调用的可复现接口，不是一个会自己生成创意内容的独立产品。直接调用时，九项必须已经明确。

`items.json` 示例：

```json
[
  "骑车 🚲",
  "开车 🚗",
  "庆祝 🎉",
  "哭泣 😭",
  "用力 💪",
  "得意 😎",
  "思考 🤔",
  "惊喜 🤩",
  "吃披萨 🍕"
]
```

Codex 直接动效路线：

```text
python scripts/create_job.py --reference "/path/character.png" --items-file "/path/items.json" --style "2" --route local --output-root "/path/runs"
python scripts/inspect_sheet.py --job "/path/runs/<job-id>/job.json" --sheet "/path/generated-transparent-sheet.png"
python scripts/prepare_assets.py --job "/path/runs/<job-id>/job.json"
python scripts/animate_local.py --job "/path/runs/<job-id>/job.json"
python scripts/package_job.py --job "/path/runs/<job-id>/job.json"
```

手工视频交接路线：

```text
python scripts/create_job.py --reference "/path/character.png" --items-file "/path/items.json" --theme "周一上班" --route video --output-root "/path/runs"
python scripts/inspect_sheet.py --job "/path/runs/<job-id>/job.json" --sheet "/path/generated-transparent-sheet.png"
python scripts/prepare_assets.py --job "/path/runs/<job-id>/job.json"
python scripts/process_video.py --job "/path/runs/<job-id>/job.json" --video "/path/uploaded-video.mp4"
python scripts/package_job.py --job "/path/runs/<job-id>/job.json"
```

`--theme` 只作为任务元数据；即使提供主题，仍必须同时用 `--items` 或 `--items-file` 传入已固定的九项。路径可包含中文和空格，但应始终加引号。

查看所有参数：

```text
python scripts/create_job.py --help
python scripts/inspect_sheet.py --help
python scripts/prepare_assets.py --help
python scripts/animate_local.py --help
python scripts/process_video.py --help
python scripts/package_job.py --help
```

## 输出

最终 ZIP 结构固定：

```text
gifs/                         # 1–9 个成功 GIF
png/                          # 仅 static=true 时存在
source/transparent-sheet.png
source/chroma-sheet.png
prompts/image-prompt.txt
prompts/video-prompt.template.txt（任务创建时的占位模板）
prompts/video-prompt.txt（色幕确定后写入的最终提示词）
manifest.json
processing-report.json
```

文件名使用稳定编号和跨平台安全的 ASCII slug，原始中文、Emoji 和显示名保留在清单中。`job.json` 只保存相对路径、输入哈希、状态、色幕分数、产物和 QA，不写密钥或用户主目录绝对路径。自动风格会在建任务时解析成一个确定的“编号 - 名称”（如 `2 - Q版大头 Chibi`）。不可变的 `intake` 与其规范 `input_hash` 用于防止续跑时更换参考图、九项顺序、风格或初始选项；`revision` 使并发或陈旧写入失败。

任务目录、临时目录和所有产物都是任务专属的。最终文件会先在进程专属临时目录中完成校验，再以“仅当目标不存在时创建”的方式发布。任何已有文件或符号链接都会使操作停止，不会被覆盖。续跑必须指定同一个 `job.json`，重新校验 `intake`、参考图/视频和已记录产物的 SHA-256；诊断、已绑定源文件和当前状态会保留供恢复，不会猜测其他未完成任务。

完整契约见 [references/output-contract.md](references/output-contract.md)，自动检查见 [references/qa.md](references/qa.md)，36 种风格见 [references/styles.md](references/styles.md)。

## 隐私与媒体权利

- 参考图、母版、视频和中间帧保存在唯一任务目录中；脚本不上传它们，不记录密钥。
- `$imagegen` 按 Codex 内置工具规则处理图像；本项目不直接调用 OpenAI Image API。
- 外部 AI 视频平台由用户自行选择和操作。上传前请检查平台的隐私、保留和商业使用条款。
- 你必须拥有或获得角色图、人像、商标、生成媒体和最终分发所需的权利与同意。本项目不授予对输入或生成媒体的额外权利。
- 在分享包含真实人物或第三方 IP 的表情包前，请获得必要授权，避免误导、侵权或骚扰用途。

## 开发与验证

```text
python -m pytest
python /path/to/skill-creator/scripts/quick_validate.py .
```

测试使用程序生成的无版权九格 PNG/视频，CI 不调用 ImageGen 或外部视频服务。支持 Python 3.10/3.12 与 macOS、Linux、Windows；媒体编解码测试需要 FFmpeg/FFprobe。

## 设计来源

本项目在概念层面参考了 [`motion-sticker-pack`](https://github.com/kobingogo/motion-sticker-pack/blob/6531b374c8a5c324a7d98067408832084a2182c9/SKILL.md) 的表情包工作流，但没有复制其代码。本项目独立实现透明验证、任务状态、色幕选择、媒体处理和打包，以避免继承参考项目的[历史媒体 CI 失败](https://github.com/kobingogo/motion-sticker-pack/actions/runs/33147161430)。Skill 结构遵循 [OpenAI Build skills](https://developers.openai.com/codex/build-skills)。

## License

MIT © DAAI。详见 [LICENSE](LICENSE)。
