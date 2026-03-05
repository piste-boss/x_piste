# Gemini タスク指示書 (2026-03-04) — 画像生成残件

## 概要

AI X の未生成画像62枚を生成し、Googleドライブへアップロード、NotionへのURL同期まで実行してください。

## 作業ディレクトリ

`/Users/ishikawasuguru/x_ai/`

---

## Step 1: 画像生成（62枚）

`x_image_prompt.md` の全セクションのプロンプトから画像を生成してください。

**重要: Gemini自身の画像生成機能（Imagen）を使って画像を生成してください。既存のPythonスクリプトは使用しないでください。**

### 生成ルール

- アスペクト比: **9:16（縦長）**
- 保存先: `x_image/` フォルダ
- 4枚投稿（カルーセル）の場合は「同一のカラーパレット」「同一のキャラクター・画風」「同一の背景トーン」で統一感を出すこと

### ファイル命名規則

YYYY-MMDD-HHMM(-N).png

### 優先度

直近の投稿分（3/4〜3/7）を最優先で生成し、その後過去分を順次生成してください。

---

## Step 2: Googleドライブへアップロード

cd /Users/ishikawasuguru/x_ai && python3 x_image_uplorder.py

---

## Step 3: NotionへのURL同期

cd /Users/ishikawasuguru/x_ai && python3 x_drive_to_notion.py

---

## 完了確認

- [ ] `x_image/` に未生成だった画像が保存されている
- [ ] Googleドライブにアップロードされている
- [ ] NotionのURLプロパティに画像リンクが反映されている
