# Typefully経由 X自動投稿 GAS 実装プラン

## Context
X Developer APIが読み取り専用権限しか付与されないため、既存の`x_auto_post.gs`（X API直接投稿）をTypefully API経由に変更する。BufferはAPI新規登録が停止しているため、Typefully（v2 API、2025年12月リリース）を使用する。

## 新しいフロー
```
Notion検索 → DriveApp(画像Blob取得) → Typefully Media Upload(S3) → Typefully Draft作成(即時投稿) → Notion更新
```

## 前提条件
- Typefullyアカウントが必要（APIキー発行は全ユーザー可能）
- Typefully v2 API使用（`Authorization: Bearer API_KEY`）
- 画像は1枚/投稿のみ対応

---

## 生成するファイル
`/Users/ishikawasuguru/x_piste/x_auto_post_typefully.gs` - 新規作成（既存の`x_auto_post.gs`は保持）

## 関数構成

### 定数
```javascript
var NOTION_API_URL = 'https://api.notion.com/v1';
var NOTION_VERSION = '2022-06-28';
var TYPEFULLY_API_URL = 'https://api.typefully.com/v2';
var MAX_RUNTIME_MS = 5 * 60 * 1000;
var MAX_IMAGE_SIZE = 5 * 1024 * 1024; // 5MB（Typefully無料プラン制限）
```

### 削除する関数（OAuth 1.0a + X API関連）
- `percentEncode_()`, `generateNonce_()`, `generateOAuthHeader_()` - OAuth不要
- `uploadMediaToX_()`, `postTweet_()` - X API直接投稿不要

### 変更する関数

#### `getProps_()` - Script Properties変更
- 削除: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`
- 追加: `TYPEFULLY_API_KEY`, `TYPEFULLY_SOCIAL_SET_ID`
- `cachedProps_`キャッシュ変数は継続

#### `getImageFromDrive_(driveUrl)` - 既存を簡略化して流用
- Drive URLからBlob取得（既存ロジックをほぼそのまま使用）
- 5MB超のサムネイル経由JPEG変換も既存ロジックを維持
- base64エンコードは不要（Blobをそのまま返す）

#### `uploadMediaToTypefully_(blob)` - 新規（3ステップ）
1. `POST /v2/social-sets/{id}/media/initiate` → `media_id` + `upload_url`取得
2. `PUT {upload_url}` → presigned S3 URLにBlob送信
3. `media_id`を返す

#### `createTypefullyDraft_(text, mediaId)` - 新規
- `POST /v2/social-sets/{id}/drafts`
- JSON body: `{ platforms: { x: { enabled: true, posts: [{ text, media_ids? }] } }, publish_at: "now" }`
- 280文字制限チェック（警告ログ）を既存コードから移植
- `muteHttpExceptions: true`

#### `processPost_(post)` - 簡素化（エラー時throwは維持）
1. 画像Blob取得（最初の1枚のみ）→ `getImageFromDrive_`
2. 画像アップロード → `uploadMediaToTypefully_`
3. ドラフト作成（即時投稿）→ `createTypefullyDraft_`
4. 投稿失敗時はNotionを「投稿エラー」に更新してthrow
5. Notion ステータス更新 → `updateNotionStatus_`

#### `testTypefullyConnection()` - 新規（診断用）
- APIキーの有効性確認
- social_set_idの確認

### 変更なしの関数
- `getNowISO_()`, `fetchDuePosts()`, `parseNotionPage_()`, `updateNotionStatus_()` - Notion連携
- `extractDriveFileId_()` - Drive ID抽出
- `main()` - メインループ（ログメッセージのみ変更）
- `setupTrigger()`, `deleteTriggers()` - トリガー管理

---

## エラーハンドリング

| エラー | 対応 | Notionステータス |
|---|---|---|
| Typefully 429レート制限 | `RATE_LIMITED`をthrow、main()でループ中断 | 変更なし |
| Typefully APIエラー（非200/201） | ログ出力、null返却→processPost_でthrow | 投稿エラー |
| Media initiate失敗 | ログ出力、テキストのみで投稿 | 継続 |
| S3アップロード失敗 | ログ出力、テキストのみで投稿 | 継続 |
| Drive画像取得失敗 | テキストのみで投稿 | 継続 |
| 5MB超画像 | サムネイルJPEG変換試行、失敗ならスキップ | 継続 |
| Notion更新失敗 | 重複投稿リスクをログ警告 | - |
| 5分実行時間超過 | ループ中断 | 変更なし |

---

## Script Properties

| プロパティ名 | 説明 |
|---|---|
| `NOTION_API_KEY` | そのまま |
| `NOTION_DATABASE_ID` | そのまま |
| `TYPEFULLY_API_KEY` | Typefully Settings → API で発行 |
| `TYPEFULLY_SOCIAL_SET_ID` | Typefully Settings → API（Development mode有効化で表示） |

---

## セットアップ手順

### 0. 旧トリガー削除
- 既存の`x_auto_post.gs`で`deleteTriggers()`を実行

### 1. Typefully APIキー取得
1. Typefullyにログイン → Settings → API
2. 新しいAPIキーを作成（WRITE + PUBLISH権限）

### 2. Social Set ID取得
1. Settings → API → Development modeを有効化
2. 表示されるsocial_set_idをコピー

### 3. GAS Script Properties設定
- `TYPEFULLY_API_KEY`: 手順1のキー
- `TYPEFULLY_SOCIAL_SET_ID`: 手順2のID

### 4. 動作確認
1. `testTypefullyConnection()`で接続確認
2. Notionにテスト投稿を作成（ステータス=未着手、投稿日=過去日時）
3. `main()`を手動実行
4. X/Twitterに投稿が表示されることを確認

### 5. トリガー設定
- `setupTrigger()`で6時間間隔トリガーを作成

---

## 検証方法
1. `testTypefullyConnection()` - API接続確認
2. テスト投稿（画像なし） - テキストのみで`main()`実行
3. テスト投稿（画像あり） - 画像URL付きのNotion投稿で`main()`実行
4. Notionステータスが「完了」に更新されていることを確認
5. X/Twitterで投稿と画像が正しく表示されていることを確認

---

## 参照ファイル
- `/Users/ishikawasuguru/x_piste/x_auto_post.gs` - 既存GAS（Notion/Drive関数を流用）
- `/Users/ishikawasuguru/x_piste/x_auto_post_typefully.gs` - 新規作成ファイル
