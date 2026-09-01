# DA Motion Sticker Skill · 3×3 애니메이션 GIF 스티커 팩

![License](https://img.shields.io/github/license/avocadotear/da-motion-sticker-skill?style=flat-square)
![Skill](https://img.shields.io/badge/Skill-Codex-111111?style=flat-square)
![GIF Pack](https://img.shields.io/badge/Output-3%C3%973%20GIF%20Pack-FF4D6D?style=flat-square)
![Styles](https://img.shields.io/badge/Styles-36%20Presets-8B5CF6?style=flat-square)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Recommended-007808?style=flat-square)

[中文](./README.md) · [English](./README.en.md) · [日本語](./README.ja.md)

`da-motion-sticker-skill`은 캐릭터 참고 이미지 한 장으로 투명 배경의 애니메이션 GIF 스티커 9개를 만듭니다. 완료된 결과에는 GIF, 선택 사항인 정적 PNG, 투명 시트와 크로마키 시트, 처리 보고서, ZIP 압축 파일이 포함됩니다. 애니메이션은 Codex 안에서 실제 키포즈를 생성하거나, 외부 이미지-투-비디오 도구에서 영상을 만든 뒤 로컬로 가져와 분할·키잉하는 방식 중 하나를 선택할 수 있습니다.

## 주요 기능

- 캐릭터 이미지 한 장과 감정·동작·이모지 9개를 입력받습니다. 테마만 주어지면 Skill이 9개 항목을 제안하고 확인을 받은 뒤 진행합니다.
- 36가지 스타일 프리셋을 제공합니다. 캐릭터 바깥 가장자리는 투명 영역과 바로 맞닿아야 하며 흰 테두리, 검은 외곽선, 그림자, 셀 배경을 추가하지 않습니다.
- Codex 경로에서는 실제로 생성된 키포즈를 사용합니다. 동일한 PNG를 이동·회전·확대·축소·흔들어서 움직임처럼 보이게 하지 않습니다.
- Grok, Seedance 2.5, 더우바오(Doubao) 같은 도구에서 만든 영상을 받아 로컬에서 그리드 탐지, 키잉, GIF 인코딩을 수행합니다.
- 알파, 3×3 간격, 크로마키 색상 충돌, 프레임 수, GIF 투명도, 무한 반복 여부를 검사합니다.

## Codex에 설치

Git과 Python 3.9 이상이 필요합니다. 비디오 경로에는 FFmpeg와 FFprobe가 필요하며, Codex 경로에서도 더 나은 GIF 팔레트를 위해 FFmpeg 사용을 권장합니다. 아래 명령으로 Codex가 읽는 로컬 Skill 디렉터리에 복제한 다음 Codex를 새로 고치거나 다시 시작하세요.

```bash
git clone https://github.com/avocadotear/da-motion-sticker-skill.git "$HOME/.agents/skills/da-motion-sticker-skill"
```

디렉터리가 이미 있다면 그 안에서 `git pull --ff-only`를 실행하세요. 개발 중인 사본이나 커밋하지 않은 변경이 있는 사본을 덮어쓰지 마세요.

Windows PowerShell:

```powershell
git clone https://github.com/avocadotear/da-motion-sticker-skill.git "$HOME\.agents\skills\da-motion-sticker-skill"
```

개발할 때는 원하는 위치에 복제한 뒤 심볼릭 링크로 설치할 수도 있습니다.

```bash
git clone https://github.com/avocadotear/da-motion-sticker-skill.git
ln -s "$(pwd)/da-motion-sticker-skill" "$HOME/.agents/skills/da-motion-sticker-skill"
```

## 빠른 시작

Codex에 캐릭터 참고 이미지를 첨부하고 다음과 같이 요청하세요.

```text
첨부한 캐릭터 참고 이미지로 $da-motion-sticker-skill을 사용해 3×3 애니메이션 GIF 스티커 팩을 만들어 주세요.
기쁨, 서운함, 화남, 놀람, 부끄러움, 혼란, 좋아요, 작별, 잠자기.
```

하나의 테마를 9개 항목으로 확장할 수도 있습니다.

```text
첨부한 캐릭터로 “월요일 출근” 테마의 스티커 팩을 만들고 스타일 04를 사용해 주세요.
```

정적 PNG 내보내기는 기본적으로 꺼져 있습니다. 필요하면 “정적 PNG도 내보내기”를 추가하세요. 원본 시트 준비가 끝나면 Codex 키포즈 경로와 AI 비디오 경로 중 하나를 선택합니다.

## 작업 흐름

1. Skill이 9개 반응을 확인하고 이미지 생성 프롬프트를 만듭니다.
2. 원본 3×3 시트는 정확한 단색 녹색 `#00FF00` 배경 위에 생성합니다. 현재 호환성을 위한 의도적인 단계이며, 처음부터 투명 이미지로 요청하지 않습니다.
3. 로컬 처리에서 캔버스 가장자리와 연결된 균일한 배경만 제거하고 실제 알파를 만든 다음 그리드를 탐지하여 투명한 셀 9개로 분할합니다.
4. 비디오 경로에서는 캐릭터 색상과 가장 덜 충돌하는 배경을 녹색, 파란색, 마젠타, 흰색 중에서 자동 선택합니다.
5. 선택한 애니메이션 경로로 GIF 9개를 만들고 검사합니다. 9개 모두 통과해야 완성된 패키지로 처리합니다.

원본 이미지 생성에 쓰는 녹색 배경과 비디오 생성용 크로마키 배경은 별도로 결정합니다. 따라서 비디오용 시트는 다른 색상을 사용할 수 있습니다.

## 36가지 스타일

번호, 정확한 이름, 자연어 설명으로 스타일을 선택할 수 있습니다. 정적 이미지와 GIF 예시는 [6×6 프리셋 갤러리](./README.md#36-种风格一览)에서 확인할 수 있습니다. 정식 라벨은 [`references/styles.md`](./references/styles.md), 기계 판독용 프리셋은 [`assets/style-presets.json`](./assets/style-presets.json)에 있습니다.

모든 스타일에서 바깥 가장자리 투명 처리, 넓은 셀 간격, 스티커 테두리 없음, 그림자 없음, 셀 배경 없음 규칙을 우선합니다.

## 애니메이션 경로

| 경로 | 적합한 경우 | 처리 방식 |
|---|---|---|
| Codex 키포즈 | Codex 안에서 제어하기 쉽고 명확한 움직임을 만들 때 | 각 스티커마다 시작·예비 동작·동작 정점·복귀로 구성된 2×2 포즈 시트를 생성합니다. 로컬에서 `시작 → 예비 동작 → 정점 → 복귀 → 정점 → 예비 동작` 순서로 조립해 투명 반복 GIF를 만듭니다. |
| AI 비디오 | 더 연속적이거나 복잡한 움직임이 필요할 때 | 선택한 크로마키 시트와 비디오 프롬프트를 내보냅니다. Grok, Seedance 2.5, 더우바오 등에서 고정 카메라 3×3 영상을 만든 뒤 업로드하면 로컬에서 분할·키잉·GIF 인코딩을 진행합니다. |

Codex 경로에는 전체 이미지를 변형하는 대체 방식이 없습니다. 얼굴, 의상, 소품이 바뀌거나 실제 포즈 차이가 없으면 한 번만 다시 생성할 수 있습니다. 두 번째에도 실패한 셀은 저품질 대체 애니메이션을 만들지 않고 중단하며 보고서를 남깁니다.

로컬 렌더러는 알파를 정규화하고 반복 구간을 조립하며, 사용할 수 있으면 FFmpeg 팔레트를 적용합니다. 첫 프레임과 애니메이션 WebP 미리보기도 내보낼 수 있습니다. 실제로 수행하지 않은 프레임 보간을 결과에 표시하지 않습니다.

## 결과물

완료된 작업은 아래의 디렉터리와 ZIP을 생성합니다. 최종 패키지에는 검증된 GIF가 정확히 9개 들어갑니다.

```text
delivery/
├── gifs/                       # 01.gif–09.gif
├── static/                     # 정적 PNG를 요청한 경우에만
├── first-frames/               # 투명 첫 프레임(있는 경우)
├── sheet-transparent.png
├── sheet-screen.png
├── image-prompt.txt
├── video-prompt.txt            # 비디오/크로마키 작업에서 생성
├── keypose-plan/               # Codex 경로의 계획과 셀별 프롬프트
├── reports/
├── manifest.json
└── da-motion-sticker-pack.zip
```

중간에 실패하면 성공한 중간 파일과 진단 보고서가 작업 디렉터리에 남을 수 있지만, 불완전한 결과를 완성된 9개 스티커 팩으로 표시하지 않습니다.

## 요구 사항과 로컬 개발

Python 3.9 이상, Pillow, NumPy가 필요합니다. 비디오 경로에는 FFmpeg와 FFprobe가 필요합니다. Codex 경로는 FFmpeg가 없으면 Pillow 인코딩으로 대체할 수 있지만, 일반적으로 팔레트 품질이 낮아집니다.

```bash
python -m pip install -r requirements.txt
python -m pytest
ffmpeg -version
ffprobe -version
```

주요 스크립트는 [`scripts/`](./scripts)에 있습니다.

- `compile_prompts.py`: 이미지 및 비디오 프롬프트를 만듭니다.
- `prepare_sheet.py`: 단색 배경을 알파로 변환하고, 그리드를 탐지·분할하며, 비디오용 배경색을 선택합니다.
- `compile_keypose_plan.py`, `prepare_keyposes.py`, `render_keypose_pack.py`: Codex 키포즈 경로를 구현합니다.
- `process_video.py`: 업로드한 3×3 비디오를 분할·키잉하고 GIF로 인코딩합니다.
- `package_delivery.py`: GIF 9개를 다시 검증하고 결과 디렉터리와 ZIP을 만듭니다.
- `prepare_pet_handoff.py`: 사용자가 Codex 데스크톱 펫을 명시적으로 요청한 경우에만 후속 작업 파일을 준비합니다.

## 개인정보 및 미디어 권리

외부 비디오 서비스를 선택하지 않는 한 작업 파일은 로컬 디렉터리에 저장됩니다. 진단을 위해 보고서에 입력 경로, SHA-256 해시, 처리 설정, 경고가 기록될 수 있으므로 공개 전에 로컬 경로를 확인하세요. 스크립트는 API 키를 저장하지 않습니다. 캐릭터 이미지, 영상, 완성된 스티커를 사용할 권리가 있는지 확인하세요. 외부 서비스에는 각 서비스의 업로드, 학습 활용, 보관 정책이 적용됩니다.

## 라이선스

[MIT License](./LICENSE) · Copyright © DAAI

## 문의 및 문제 제보

문제가 생기면 GitHub에 [Issue를 등록](https://github.com/avocadotear/da-motion-sticker-skill/issues)하거나 WeChat으로 연락해 주세요. WeChat ID는 `DAAIGC2046`입니다. 메시지를 확인하는 대로 살펴보겠습니다.

<img src="assets/wechat-daaigc2046.jpg" alt="DAAI WeChat QR 코드, WeChat ID DAAIGC2046" width="360">
