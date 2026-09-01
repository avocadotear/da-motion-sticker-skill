# DA Motion Sticker Skill · 3×3 アニメーション GIF スタンプパック

![License](https://img.shields.io/github/license/avocadotear/da-motion-sticker-skill?style=flat-square)
![Skill](https://img.shields.io/badge/Skill-Codex-111111?style=flat-square)
![GIF Pack](https://img.shields.io/badge/Output-3%C3%973%20GIF%20Pack-FF4D6D?style=flat-square)
![Styles](https://img.shields.io/badge/Styles-36%20Presets-8B5CF6?style=flat-square)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Recommended-007808?style=flat-square)

[中文](./README.md) · [English](./README.en.md) · [한국어](./README.ko.md)

`da-motion-sticker-skill` は、キャラクターの参考画像1枚から、背景が透明なアニメーション GIF スタンプを9個作成します。完成時には GIF、任意の静止 PNG、透過シート、クロマキー用シート、処理レポート、ZIP を出力します。アニメーションは Codex 内でキーポーズを生成する方法と、外部の画像・動画生成ツールを利用してからローカルで分割・キーイングする方法を選べます。

## 主な機能

- キャラクター画像1枚と、9種類の感情・動作・絵文字を受け取ります。テーマだけが指定された場合は、Skill が9項目を提案し、確認してから進めます。
- 36種類のスタイルを収録しています。キャラクターの外周は透明領域に直接接し、白縁、黒い外枠、影、セルごとの背景は付けません。
- Codex ルートでは実際に生成したキーポーズを使用します。同じ PNG を平行移動・回転・拡大縮小・振動させて動きに見せる方式は使用しません。
- Grok、Seedance 2.5、豆包（Doubao）などで生成した動画を受け取り、ローカルでグリッド検出、キーイング、GIF エンコードを行えます。
- Alpha、3×3 の余白、クロマキー色との競合、フレーム数、GIF の透過、無限ループを確認します。

## Codex へのインストール

Git と Python 3.9 以上が必要です。動画ルートには FFmpeg と FFprobe が必要です。Codex ルートでも、GIF のカラーパレット品質を上げるために FFmpeg の使用を推奨します。次のコマンドで Codex が読み込むローカル Skill ディレクトリへクローンし、完了後に Codex を更新または再起動してください。

```bash
git clone https://github.com/avocadotear/da-motion-sticker-skill.git "$HOME/.agents/skills/da-motion-sticker-skill"
```

すでにディレクトリがある場合は、その中で `git pull --ff-only` を実行してください。開発中のコピーや未コミットの変更があるコピーを上書きしないでください。

Windows PowerShell:

```powershell
git clone https://github.com/avocadotear/da-motion-sticker-skill.git "$HOME\.agents\skills\da-motion-sticker-skill"
```

開発時は任意の場所にクローンし、シンボリックリンクでインストールできます。

```bash
git clone https://github.com/avocadotear/da-motion-sticker-skill.git
ln -s "$(pwd)/da-motion-sticker-skill" "$HOME/.agents/skills/da-motion-sticker-skill"
```

## クイックスタート

Codex にキャラクターの参考画像を添付し、次のように依頼します。

```text
添付したキャラクター画像を使い、$da-motion-sticker-skill で3×3のアニメーション GIF スタンプを作成してください。
喜び、悲しみ、怒り、驚き、照れ、困惑、いいね、さようなら、睡眠。
```

テーマから9種類を展開することもできます。

```text
添付したキャラクターで「月曜日の仕事」をテーマにしたスタンプパックを作成し、スタイル04を使用してください。
```

静止 PNG の書き出しは初期設定では無効です。必要な場合は「静止 PNG も出力」と追加してください。元のシートを準備した後、Codex キーポーズルートまたは AI 動画ルートを選びます。

## 処理の流れ

1. Skill が9種類の内容を確認し、画像生成プロンプトを作成します。
2. 元の3×3シートは、正確な単色グリーン `#00FF00` 上に生成します。これは現在の互換性を保つための手順で、最初から透過画像として生成する指定にはしません。
3. ローカル処理でキャンバス端につながる均一な背景だけを削除し、実際の Alpha を作成して、グリッド検出と9セルの切り出しを行います。
4. 動画ルートでは、キャラクターの色と競合しにくい背景をグリーン、ブルー、マゼンタ、ホワイトから自動選択します。
5. 選択したルートで9個の GIF を生成・検証します。9個すべてが合格した場合のみ完成パッケージになります。

元画像生成時のグリーン背景と、動画生成に使うクロマキー背景は別々に決定されます。そのため動画用シートは別の色になる場合があります。

## 36種類のスタイル

番号、正式名、または自然言語の説明で選択できます。静止画と GIF の見本は [6×6 プリセットギャラリー](./README.md#36-种风格一览) で確認できます。正式なラベルは [`references/styles.md`](./references/styles.md)、機械可読の設定は [`assets/style-presets.json`](./assets/style-presets.json) にあります。

どのスタイルでも、外周の透過、セル間の余白、外枠なし、影なし、セル背景なしという出力条件を優先します。

## アニメーションルート

| ルート | 向いている用途 | 処理方法 |
|---|---|---|
| Codex キーポーズ | Codex 内で完結し、読みやすく制御しやすい動きが必要な場合 | 各スタンプに開始・予備動作・動作のピーク・復帰の2×2ポーズシートを生成します。ローカルで `開始 → 予備動作 → ピーク → 復帰 → ピーク → 予備動作` の順に組み、透明なループ GIF にします。 |
| AI 動画 | より連続的、または複雑な動きが必要な場合 | 選択したクロマキー用シートと動画プロンプトを出力します。Grok、Seedance 2.5、豆包などで固定カメラの3×3動画を生成し、アップロード後にローカルで分割・キーイング・GIF エンコードを行います。 |

Codex ルートには、画像全体を変形させるフォールバックはありません。顔、服装、道具が変わった場合や、実際のポーズ差がない場合は1回だけ再生成できます。2回目も失敗したセルは処理を止め、低品質な代替アニメーションを作らずレポートを残します。

ローカルレンダラーは Alpha を正規化してループを組み、利用できる場合は FFmpeg のパレットを使用します。先頭フレームとアニメーション WebP のプレビューも出力できます。実行していないフレーム補間を結果として記載することはありません。

## 出力内容

完了した処理では、次のディレクトリと ZIP を作成します。最終パッケージには検証済み GIF が必ず9個入ります。

```text
delivery/
├── gifs/                       # 01.gif–09.gif
├── static/                     # 静止 PNG を指定した場合のみ
├── first-frames/               # 透過の先頭フレーム（存在する場合）
├── sheet-transparent.png
├── sheet-screen.png
├── image-prompt.txt
├── video-prompt.txt            # 動画／クロマキー手順で作成
├── keypose-plan/               # Codex ルートの計画とセル別プロンプト
├── reports/
├── manifest.json
└── da-motion-sticker-pack.zip
```

途中で失敗した場合、成功した中間素材と診断レポートは作業ディレクトリに残ることがありますが、不完全な結果を9個完成のパックとして扱いません。

## 必要環境とローカル開発

Python 3.9 以上、Pillow、NumPy が必要です。動画ルートには FFmpeg と FFprobe が必要です。Codex ルートは FFmpeg がない場合に Pillow エンコードへ切り替えられますが、通常はカラーパレットの品質が下がります。

```bash
python -m pip install -r requirements.txt
python -m pytest
ffmpeg -version
ffprobe -version
```

主なスクリプトは [`scripts/`](./scripts) にあります。

- `compile_prompts.py`: 画像・動画プロンプトを作成します。
- `prepare_sheet.py`: 単色背景から Alpha を作り、グリッドの検出・分割と動画用背景色の選択を行います。
- `compile_keypose_plan.py`、`prepare_keyposes.py`、`render_keypose_pack.py`: Codex キーポーズルートを実装します。
- `process_video.py`: アップロードされた3×3動画を分割・キーイングし、GIF にエンコードします。
- `package_delivery.py`: 9個の GIF を再検証し、納品ディレクトリと ZIP を作成します。
- `prepare_pet_handoff.py`: ユーザーが Codex デスクトップペットを明示的に依頼した場合のみ、後続処理用のファイルを作成します。

## プライバシーとメディアの権利

外部の動画サービスを選ばない限り、処理ファイルはローカルディレクトリに保存されます。診断のため、レポートには入力パス、SHA-256、処理設定、警告が記録される場合があります。公開前にローカルパスを確認してください。スクリプトは API キーを保存しません。キャラクター画像、動画、完成したスタンプを利用する権利があることを確認してください。外部サービスには、それぞれのアップロード、学習利用、保存期間に関する規約が適用されます。

## ライセンス

[MIT License](./LICENSE) · Copyright © DAAI

## 質問・不具合報告

問題があれば、GitHub で [Issue を作成](https://github.com/avocadotear/da-motion-sticker-skill/issues)するか、WeChat でご連絡ください。WeChat ID は `DAAIGC2046` です。メッセージを確認次第、対応します。

<img src="assets/wechat-daaigc2046.jpg" alt="DAAI の WeChat QR コード、WeChat ID DAAIGC2046" width="360">
