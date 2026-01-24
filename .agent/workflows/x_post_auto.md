---
description: X(Twitter)投稿の作成から画像生成、アップロード、Notion連携までを一括で行うワークフロー
---

# X投稿自動作成ワークフロー

このワークフローは、X(Twitter)の投稿作成からNotionへの登録までを自動化する手順です。

## 1. 投稿スケジュールの確認と投稿案の作成
1.  `post_schedule.md` (スケジュール) と `x_algorithm.md` (アルゴリズム分析) を読み込みます。
2.  指定された期間の投稿案を作成し、 `x_post.md` に保存します。
    - 構成: 日時、種別、タイトル、本文、コメント欄
    - スタイル: インプレッション重視、共感、有益性

## 2. 画像生成プロンプトの作成
1.  `x_post.md` の内容に基づき、画像生成用のプロンプトを作成し、 `x_image_prompt.md` に保存します。
    - スタイル参照: `Threads_piste/Piste_threads_image_prompt.md` 等の既存スタイル
    - ルール: 4枚投稿(カルーセル)の場合は `Carousel Consistency` ルールを含める
    - ファイル名指定: `YYYY-MMDD-HHMM` (例: `2026-0125-0900`)

## 3. 画像の生成
1.  `x_image_prompt.md` のプロンプトに従い、 `generate_image` ツールを使用して画像を生成します。
    - 保存先: `x_image` ディレクトリ (なければ作成)
    - 注意: 4枚投稿の場合は統一感を意識して生成する
    - 生成後、ファイル名を `YYYY-MMDD-HHMM(-N).png` 形式にリネームして移動する

## 4. Google Driveへの画像アップロード
// turbo
1.  以下のコマンドを実行して、生成された画像をGoogle Driveへアップロードします。
    ```bash
    python3 x_image_uplorder.py
    ```
    - 認証が必要な場合はブラウザで承認を行う

## 5. Notionへの投稿案アップロード
// turbo
1.  以下のコマンドを実行して、 `x_post.md` の内容をNotionデータベースに登録します。
    ```bash
    python3 x_notion_uplorder.py
    ```
    - 確認: ステータスが「未着手」になっていること

## 6. 画像リンクの同期 (Drive -> Notion)
// turbo
1.  以下のコマンドを実行して、Google Driveの画像リンクをNotionの各ページに紐付けます。
    ```bash
    python3 x_drive_to_notion.py
    ```
    - 確認: Notion上でURLプロパティが埋まっていること
