# X 自動投稿 GAS 生成スキル

Make (Integromat) のX自動投稿シナリオを Google Apps Script (GAS) で内製化するコードを生成する。

## 生成するフロー

```
Notion検索 → DriveApp(画像取得) → X Media Upload → X Tweet → Notion更新
```

## 生成するファイル

`x_auto_post.gs` - 1ファイル構成の GAS スクリプト

## 必須の関数構成

以下の関数を全て含めること：

### メイン・セットアップ
- `main()` - 6時間トリガーから呼ばれるエントリポイント。5分の実行時間ガード付き（GAS 6分制限対策）。投稿単位で try-catch し、1件失敗しても他は継続
- `setupTrigger()` - 6時間間隔トリガーを作成（既存トリガーは削除して再作成）
- `deleteTriggers()` - 既存の main トリガーを全削除

### Script Properties
- `getProps_()` - Script Properties からAPIキーを取得しキャッシュ。必須キー: `NOTION_API_KEY`, `NOTION_DATABASE_ID`, `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`

### Notion 連携
- `fetchDuePosts()` - Notion API でデータベースクエリ。フィルター: ステータス(status型)=「未着手」& 投稿日<=now(ISO8601)。ページネーション対応。返却: `[{pageId, title, body, imageUrls[], comment}]`
- `parseNotionPage_(page)` - Notion ページからプロパティ読み取り。本文(rich_text)、URL1~URL4(url型)、コメント(rich_text)
- `updateNotionStatus_(pageId, statusName)` - Notion ステータスを更新（status型）

### Google Drive 画像取得
- `getImageFromDrive_(driveUrl)` - Drive URL から画像 Blob を取得し Base64 エンコード。5MB超はサムネイル経由 JPEG 変換を試行
- `extractDriveFileId_(url)` - 正規表現で Drive File ID を抽出（`/file/d/ID` と `?id=ID` の2パターン対応）

### OAuth 1.0a 署名
- `generateOAuthHeader_(method, url, params)` - OAuth 1.0a HMAC-SHA1 署名を生成。`params` は `application/x-www-form-urlencoded` のリクエストパラメータのみ含める（JSON body は署名対象外）
- `percentEncode_(str)` - RFC 5849 準拠のパーセントエンコード
- `generateNonce_()` - `Utilities.getUuid()` でノンス生成

### X API
- `uploadMediaToX_(base64Data)` - `POST https://upload.twitter.com/1.1/media/upload.json` で画像アップロード。`media_data` パラメータ使用。429 レート制限時は `RATE_LIMITED` エラーをスロー
- `postTweet_(text, mediaIds)` - `POST https://api.x.com/2/tweets` でツイート投稿。JSON body（署名対象外）。mediaIds が空ならテキストのみ投稿

### 投稿処理
- `processPost_(post)` - 1件分の統合処理: 画像取得→X アップロード→ツイート→Notion ステータス更新。投稿失敗時は Notion を「投稿エラー」に更新（無限リトライ防止）

## エラーハンドリング要件

- 投稿単位の分離（1件失敗しても他は継続）
- 画像取得失敗時はその画像をスキップして残りで投稿
- X API 429 レート制限時はログ出力して処理中断（次回トリガーで再試行）
- GAS 6分制限対策として main() 内で5分経過チェック
- Notion 更新失敗時は重複投稿リスクをログ警告
- 5MB 超画像はサムネイル JPEG 変換を試行、それでも超える場合はスキップ

## API 定数

```javascript
var NOTION_API_URL = 'https://api.notion.com/v1';
var NOTION_VERSION = '2022-06-28';
var X_MEDIA_UPLOAD_URL = 'https://upload.twitter.com/1.1/media/upload.json';
var X_TWEET_URL = 'https://api.x.com/2/tweets';
var MAX_RUNTIME_MS = 5 * 60 * 1000;
var MAX_IMAGE_SIZE = 5 * 1024 * 1024;
var MAX_MEDIA_PER_TWEET = 4;
```

## 重要な実装ポイント

1. **OAuth 署名**: media/upload は `params` に `media_data` を含めて署名。tweets は `params` 空オブジェクトで署名（JSON body は署名対象外）
2. **media/upload の payload**: `percentEncode_` で手動エンコードした文字列を payload に渡す（署名とボディのエンコード一致を保証）
3. **署名キー**: `percentEncode_(consumerSecret) + '&' + percentEncode_(tokenSecret)`（RFC 5849 仕様）
4. **Notion フィルター**: ステータスは `status` 型（`select` 型ではない）

## ユーザーへの追加指示

$ARGUMENTS
