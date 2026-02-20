# Make シナリオ「X_auto_post_piste」GAS 内製化プラン

## Context

Make (Integromat) で運用中の X 自動投稿シナリオを完全内製化する。
Buffer・Cloudinary を排除し、Google Apps Script (GAS) のみで Notion → Google Drive → X API の直接連携を実現する。

### 現在の Make フロー
```
Notion検索 → 変数セット → HTTP(Drive画像DL) → Cloudinary → Buffer → Notion更新
```

### 内製化後のフロー
```
Notion検索 → DriveApp(画像取得) → X Media Upload → X Tweet → Notion更新
```

---

## 実装ファイル

**1ファイル構成**: `/Users/ishikawasuguru/x_piste/x_auto_post.gs`

GAS プロジェクトとして Google Apps Script エディタにコピーして使用。

---

## Script Properties（設定値）

GAS エディタの「プロジェクトの設定 > スクリプトプロパティ」に設定：

| キー | 値 | 説明 |
|------|-----|------|
| `NOTION_API_KEY` | `ntn_xxx...` | Notion API トークン |
| `NOTION_DATABASE_ID` | `2f2c991b-527b-803e-8fb0-000b6a65080f` | Notion データベース ID |
| `X_API_KEY` | `xxx` | X API Key (Consumer Key) |
| `X_API_SECRET` | `xxx` | X API Secret (Consumer Secret) |
| `X_ACCESS_TOKEN` | `xxx` | X Access Token |
| `X_ACCESS_TOKEN_SECRET` | `xxx` | X Access Token Secret |

---

## 関数構成

### 1. メイン関数

```
main()
```
- 6時間トリガーから呼ばれるエントリポイント
- Notion から投稿対象を全件取得
- 各投稿を順次処理（1件失敗しても他は継続）
- **実行時間ガード**: 5分経過で処理を中断（GAS の6分制限対策。残りは次回実行で処理）
- 処理結果をログ出力

### 2. セットアップ関数

```
setupTrigger()
```
- 6時間間隔のトリガーを作成
- 既存トリガーがあれば削除してから再作成

```
deleteTriggers()
```
- 既存の全トリガーを削除

### 3. Notion 連携

```
fetchDuePosts()
```
- Notion API: `POST /v1/databases/{id}/query`
- フィルター（`status` 型を使用）:
  ```json
  {
    "and": [
      {"property": "ステータス", "status": {"equals": "未着手"}},
      {"property": "投稿日", "date": {"on_or_before": "now(ISO8601/JST)"}}
    ]
  }
  ```
- **投稿日の now 生成**: JST タイムゾーン（UTC+9）で ISO 8601 文字列を生成
- ページネーション対応（has_more / start_cursor）
- 返却: `[{pageId, title, body, imageUrls[], comment}]`
- プロパティ読み取り:
  - `本文` → rich_text の plain_text を結合
  - `URL1`, `URL2`, `URL3`, `URL4` → url 型、空でないもののみ収集
  - `コメント` → rich_text（将来のリプライ投稿用に取得、現時点では未使用）

```
updateNotionStatus(pageId)
```
- Notion API: `PATCH /v1/pages/{pageId}`
- ステータスを「完了」に更新（`status` 型）:
  ```json
  {"ステータス": {"status": {"name": "完了"}}}
  ```

### 4. Google Drive 画像取得

```
getImageFromDrive(driveUrl)
```
- `extractDriveFileId()` で File ID 抽出
- `DriveApp.getFileById(fileId).getBlob()` で画像 Blob 取得
- **サイズチェック**: 5MB 超の場合は JPEG 変換でサイズ削減を試行
- Base64 エンコードして返却

```
extractDriveFileId(url)
```
- 正規表現: `/\/file\/d\/([a-zA-Z0-9_-]{25,})/` で webViewLink から ID 抽出
- フォールバック: `/[?&]id=([a-zA-Z0-9_-]{25,})/` パターンにも対応

### 5. X API OAuth 1.0a 署名

```
generateOAuthHeader(method, url, params)
```
- OAuth 1.0a 署名を生成
- `oauth_nonce`: `Utilities.getUuid()` で生成
- `oauth_timestamp`: `Math.floor(Date.now() / 1000)`
- `oauth_signature_method`: `HMAC-SHA1`
- 署名計算: `Utilities.computeHmacSignature(Utilities.MacAlgorithm.HMAC_SHA_1, baseString, signingKey)`
- `Authorization: OAuth ...` ヘッダー文字列を返却
- **重要**: `params` は `application/x-www-form-urlencoded` のリクエストパラメータのみ含める。JSON body のパラメータは含めない（v2 tweets エンドポイント用）

### 6. X メディアアップロード

```
uploadMediaToX(base64Data, mimeType)
```
- `POST https://upload.twitter.com/1.1/media/upload.json`
- `media_data` パラメータに Base64 画像データ送信（5MB 以下）
- Content-Type: `application/x-www-form-urlencoded`
- OAuth 署名: `params` に `media_data` を含めて署名生成
- 返却: `media_id_string`
- **エラー処理**: 429 (Rate Limit) の場合はログ出力して処理中断

### 7. X ツイート投稿

```
postTweet(text, mediaIds)
```
- `POST https://api.x.com/2/tweets`
- JSON body: `{"text": "...", "media": {"media_ids": ["id1", ...]}}`
- Content-Type: `application/json`
- OAuth 署名: `params` は空オブジェクト `{}` で生成（JSON body は署名対象外）
- mediaIds が空の場合はテキストのみ投稿
- **テキスト長チェック**: 280文字超の場合はログ警告（X Premium なら25,000文字まで可）

### 8. 投稿処理（1件分の統合処理）

```
processPost(post)
```
- 1件の投稿について以下を順次実行：
  1. `post.imageUrls` の各 URL から `getImageFromDrive()` で画像取得
  2. 各画像を `uploadMediaToX()` で X にアップロード
  3. `postTweet()` で本文 + メディア ID で投稿
  4. `updateNotionStatus()` でステータスを「完了」に更新

---

## データフロー詳細

```
[6時間トリガー]
    ↓
main()
    ↓
fetchDuePosts()  ← Notion API Query
    ↓              フィルター: ステータス(status型)="未着手" & 投稿日<=now(JST)
    ↓              ページネーション対応で全件取得
[投稿リスト]
    ↓
for each post:
    ↓
    [実行時間チェック: 5分超なら break]
    ↓
    processPost(post)
        ↓
        for each imageUrl in post.imageUrls (URL1~URL4):
            ↓
            extractDriveFileId(imageUrl)  ← 正規表現: /\/file\/d\/([a-zA-Z0-9_-]{25,})/
                ↓
            getImageFromDrive(fileId)  ← DriveApp.getFileById().getBlob()
                ↓                        5MB超ならJPEG変換試行
            uploadMediaToX(base64)  ← X API v1.1 media/upload (OAuth 1.0a)
                ↓
            [media_id_string を収集]
        ↓
        postTweet(body, mediaIds[])  ← X API v2 /2/tweets (OAuth 1.0a, JSON body)
        ↓
        updateNotionStatus(pageId)  ← Notion API pages/update (status→完了)
        ↓
        [ログ出力: 成功/失敗]
```

---

## エラーハンドリング

- **投稿単位の分離**: 1件の投稿処理が失敗しても、他の投稿は継続処理
- **try-catch**: `processPost()` を try-catch で囲み、エラーは `Logger.log()` に記録
- **画像取得失敗**: 個別画像の取得に失敗した場合、その画像をスキップして残りで投稿
- **全画像失敗**: 全画像が取得できない場合でも、テキストのみで投稿を試みる
- **X API レート制限**: 429 レスポンス時はログ出力してその回の処理を中断（次回トリガーで再試行）
- **GAS 6分制限**: main() 内で5分経過チェック、超過時は中断（未処理分は次回実行で処理）
- **Notion 更新失敗**: ツイート成功後の更新失敗時は重複投稿リスクをログ警告
- **画像サイズ**: 5MB 超の画像は JPEG 変換を試行、それでも超える場合はスキップしてログ警告

---

## 既知の制限事項

1. **X API Free プランのレート制限**: 24時間あたり17ツイートまで
2. **6時間間隔の投稿遅延**: 最大5時間59分の遅延が発生する可能性あり（投稿日 7:30 の場合、次のトリガーは最大 13:29）
3. **重複投稿リスク**: ツイート成功→Notion更新失敗のケースで発生しうる（ログ確認で対応）
4. **コメント欄**: 現時点ではリプライ投稿は非対応（将来拡張として検討可能）

---

## X API 認証情報の取得手順

ユーザーが事前に実施する必要がある手順：

1. https://developer.x.com/en/portal/dashboard にアクセス
2. プロジェクト & アプリを作成（Free プランで OK）
3. アプリの「User authentication settings」で **OAuth 1.0a** を有効化、**Read and Write** 権限を設定
4. アプリの「Keys and tokens」タブから取得：
   - API Key & API Secret
   - Access Token & Access Token Secret（権限変更後に再生成が必要）
5. GAS の Script Properties に設定

---

## デプロイ手順

1. https://script.google.com で新規プロジェクト作成
2. `x_auto_post.gs` の内容をコピー＆ペースト
3. Script Properties に上記6つの値を設定
4. Google Drive フォルダ (`16pMNNI_5lLPcDGIbHNxDRjQ1zczcd5Na`) に GAS 実行アカウントがアクセス可能か確認
5. `setupTrigger()` を手動実行してトリガー登録
6. `main()` を手動実行してテスト

---

## 検証方法

1. **単体テスト**: Notion に ステータス「未着手」& 投稿日を過去日時のテスト投稿を1件作成
2. **`main()` を手動実行**: GAS エディタで実行
3. **確認項目**:
   - X にツイートが投稿されているか
   - 画像が添付されているか（複数枚の場合カルーセル表示）
   - Notion のステータスが「完了」に変更されているか
   - Logger.log でエラーが出ていないか
4. **エッジケース確認**:
   - 画像なし投稿（URL1~4 が全て空の場合）
   - 画像1枚のみの投稿
   - 画像4枚の投稿
   - 投稿対象なし（全て「完了」済み）の場合

---

## 既存コードとの関係

- 既存の Python スクリプト（`x_notion_uplorder.py`, `x_drive_to_notion.py`, `x_image_uplorder.py`）はそのまま維持
- GAS は Make シナリオの置き換えのみ（投稿 & ステータス更新）
- 既存ワークフロー（コンテンツ作成 → 画像生成 → Drive アップ → Notion 同期）は変更なし
