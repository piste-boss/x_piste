# X投稿自動化ワークフロー

以下の手順でX（旧Twitter）への投稿作成からNotion連携までを行います。

## 1. 投稿文の作成
`post_schedule.md` のスケジュールに基づき、AIを使用して `x_post.md` に投稿文（下書き）を作成します。
- **Source**: `post_schedule.md`
- **Target**: `x_post.md`

## 2. 画像生成プロンプトの作成
`x_post.md` の内容を視覚的に補完・要約するインフォグラフィック等の画像生成プロンプトを `x_image_prompt.md` に作成します。
- **Source**: `x_post.md`
- **Target**: `x_image_prompt.md`

## 3. 画像の生成
`x_image_prompt.md` のプロンプトを使用して画像を生成し、 `x_image` ディレクトリに保存します。
- **Source**: `x_image_prompt.md`
- **Target**: `x_image/` (ディレクトリ)
- **Format**: `YYYY-MM-DD-HH_MM.png` 形式推奨

## 4. 画像をGoogleドライブへ保存
`x_image_uplorder.py` を実行して、生成された画像をGoogleドライブの所定フォルダにアップロードします。
- **Script**: `python3 x_image_uplorder.py`
- **Action**: `x_image/` 内の画像をアップロードし、ローカルからは削除

## 5. Notionへの投稿内容連携
`x_notion_uplorder.py` を実行して、`x_post.md` のテキスト内容（タイトル、本文、日時など）をNotionデータベースに追記します。
- **Script**: `python3 x_notion_uplorder.py`
- **Source**: `x_post.md`
- **Target**: Notion Database

## 6. 画像リンクのNotion連携
`x_drive_to_notion.py` を実行して、Googleドライブに保存された画像のリンク（WebViewLink）をNotionの該当ページのURLプロパティに紐付けます。
- **Script**: `python3 x_drive_to_notion.py`
- **Matching**: ファイル名の日時とNotion投稿日時（近似マッチ含む）を照合
