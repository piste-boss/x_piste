// ============================================================
// X_auto_post_piste - Make シナリオ内製化 GAS
// Notion → Google Drive → X API 自動投稿
// ============================================================

// --- 定数 ---
var NOTION_API_URL = 'https://api.notion.com/v1';
var NOTION_VERSION = '2022-06-28';
var X_MEDIA_UPLOAD_URL = 'https://upload.twitter.com/1.1/media/upload.json';
var X_TWEET_URL = 'https://api.x.com/2/tweets';
var MAX_RUNTIME_MS = 5 * 60 * 1000; // 5分（GAS 6分制限対策）
var MAX_IMAGE_SIZE = 5 * 1024 * 1024; // 5MB
var MAX_MEDIA_PER_TWEET = 4; // X API 上限

// --- Script Properties キャッシュ & 取得 ---
var cachedProps_ = null;

function getProps_() {
  if (cachedProps_) return cachedProps_;
  var props = PropertiesService.getScriptProperties();
  var required = [
    'NOTION_API_KEY', 'NOTION_DATABASE_ID',
    'X_API_KEY', 'X_API_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_TOKEN_SECRET'
  ];
  var missing = required.filter(function(key) { return !props.getProperty(key); });
  if (missing.length > 0) {
    throw new Error('Script Properties が未設定です: ' + missing.join(', '));
  }
  cachedProps_ = {
    notionApiKey: props.getProperty('NOTION_API_KEY'),
    notionDatabaseId: props.getProperty('NOTION_DATABASE_ID'),
    xApiKey: props.getProperty('X_API_KEY'),
    xApiSecret: props.getProperty('X_API_SECRET'),
    xAccessToken: props.getProperty('X_ACCESS_TOKEN'),
    xAccessTokenSecret: props.getProperty('X_ACCESS_TOKEN_SECRET')
  };
  return cachedProps_;
}

// ============================================================
// OAuth 1.0a 署名生成
// ============================================================

function percentEncode_(str) {
  return encodeURIComponent(str)
    .replace(/!/g, '%21')
    .replace(/\*/g, '%2A')
    .replace(/'/g, '%27')
    .replace(/\(/g, '%28')
    .replace(/\)/g, '%29');
}

function generateNonce_() {
  return Utilities.getUuid().replace(/-/g, '');
}

function generateOAuthHeader_(method, url, params) {
  var props = getProps_();
  var oauthParams = {
    oauth_consumer_key: props.xApiKey,
    oauth_nonce: generateNonce_(),
    oauth_signature_method: 'HMAC-SHA1',
    oauth_timestamp: String(Math.floor(Date.now() / 1000)),
    oauth_token: props.xAccessToken,
    oauth_version: '1.0'
  };

  // 全パラメータを結合（OAuth + リクエストパラメータ）
  var allParams = {};
  for (var key in oauthParams) allParams[key] = oauthParams[key];
  for (var key in params) allParams[key] = params[key];

  // パラメータをソートしてエンコード
  var sortedKeys = Object.keys(allParams).sort();
  var paramString = sortedKeys.map(function(key) {
    return percentEncode_(key) + '=' + percentEncode_(allParams[key]);
  }).join('&');

  // 署名ベース文字列
  var baseString = method.toUpperCase() + '&' + percentEncode_(url) + '&' + percentEncode_(paramString);

  // 署名キー: percentEncode した consumer_secret & token_secret を連結
  // （OAuth 1.0a RFC 5849 仕様通り）
  var signingKey = percentEncode_(props.xApiSecret) + '&' + percentEncode_(props.xAccessTokenSecret);

  // HMAC-SHA1 署名
  var signatureBytes = Utilities.computeHmacSignature(
    Utilities.MacAlgorithm.HMAC_SHA_1,
    baseString,
    signingKey,
    Utilities.Charset.UTF_8
  );
  var signature = Utilities.base64Encode(signatureBytes);
  oauthParams.oauth_signature = signature;

  // Authorization ヘッダー組み立て
  var authHeader = 'OAuth ' + Object.keys(oauthParams).sort().map(function(key) {
    return percentEncode_(key) + '="' + percentEncode_(oauthParams[key]) + '"';
  }).join(', ');

  return authHeader;
}

// ============================================================
// Notion API 連携
// ============================================================

function getNowISO_() {
  return new Date().toISOString();
}

function fetchDuePosts() {
  var props = getProps_();
  var posts = [];
  var hasMore = true;
  var startCursor = undefined;

  while (hasMore) {
    var body = {
      filter: {
        and: [
          {
            property: 'ステータス',
            status: { equals: '未着手' }
          },
          {
            property: '投稿日',
            date: { on_or_before: getNowISO_() }
          }
        ]
      },
      sorts: [
        { property: '投稿日', direction: 'ascending' }
      ]
    };
    if (startCursor) {
      body.start_cursor = startCursor;
    }

    var response = UrlFetchApp.fetch(
      NOTION_API_URL + '/databases/' + props.notionDatabaseId + '/query',
      {
        method: 'post',
        headers: {
          'Authorization': 'Bearer ' + props.notionApiKey,
          'Notion-Version': NOTION_VERSION,
          'Content-Type': 'application/json'
        },
        payload: JSON.stringify(body),
        muteHttpExceptions: true
      }
    );

    var data = JSON.parse(response.getContentText());
    if (response.getResponseCode() !== 200) {
      Logger.log('Notion query error: ' + response.getContentText());
      return posts;
    }

    data.results.forEach(function(page) {
      var post = parseNotionPage_(page);
      if (post) posts.push(post);
    });

    hasMore = data.has_more;
    startCursor = data.next_cursor;
  }

  Logger.log('取得した投稿数: ' + posts.length);
  return posts;
}

function parseNotionPage_(page) {
  var p = page.properties;

  // タイトル
  var title = '';
  if (p['タイトル'] && p['タイトル'].title && p['タイトル'].title.length > 0) {
    title = p['タイトル'].title.map(function(t) { return t.plain_text; }).join('');
  }

  // 本文
  var body = '';
  if (p['本文'] && p['本文'].rich_text) {
    body = p['本文'].rich_text.map(function(t) { return t.plain_text; }).join('');
  }

  // コメント
  var comment = '';
  var commentProp = p['コメント'] || p['コメント欄'];
  if (commentProp && commentProp.rich_text) {
    comment = commentProp.rich_text.map(function(t) { return t.plain_text; }).join('');
  }

  // 画像 URL (URL1~URL4, 最大4枚)
  var imageUrls = [];
  ['URL1', 'URL2', 'URL3', 'URL4'].forEach(function(key) {
    if (p[key] && p[key].url && p[key].url !== '') {
      imageUrls.push(p[key].url);
    }
  });
  // URL プロパティのフォールバック（URL1~4 が無い場合）
  if (imageUrls.length === 0 && p['URL'] && p['URL'].url && p['URL'].url !== '') {
    imageUrls.push(p['URL'].url);
  }

  if (!body) {
    Logger.log('本文が空のためスキップ: ' + page.id);
    return null;
  }

  return {
    pageId: page.id,
    title: title,
    body: body,
    comment: comment,
    imageUrls: imageUrls
  };
}

function updateNotionStatus_(pageId, statusName) {
  var props = getProps_();
  var response = UrlFetchApp.fetch(
    NOTION_API_URL + '/pages/' + pageId,
    {
      method: 'patch',
      headers: {
        'Authorization': 'Bearer ' + props.notionApiKey,
        'Notion-Version': NOTION_VERSION,
        'Content-Type': 'application/json'
      },
      payload: JSON.stringify({
        properties: {
          'ステータス': {
            status: { name: statusName }
          }
        }
      }),
      muteHttpExceptions: true
    }
  );

  if (response.getResponseCode() !== 200) {
    Logger.log('Notion status update error (page: ' + pageId + ', status: ' + statusName + '): ' + response.getContentText());
    return false;
  }
  return true;
}

// ============================================================
// Google Drive 画像取得
// ============================================================

function extractDriveFileId_(url) {
  // /file/d/FILE_ID/ パターン（webViewLink 等）
  var match = url.match(/\/file\/d\/([a-zA-Z0-9_-]{25,})/);
  if (match) return match[1];

  // ?id=FILE_ID or &id=FILE_ID パターン（open?id=, uc?id= 等）
  match = url.match(/[?&]id=([a-zA-Z0-9_-]{25,})/);
  if (match) return match[1];

  Logger.log('Drive File ID を抽出できません: ' + url);
  return null;
}

function getImageFromDrive_(driveUrl) {
  var fileId = extractDriveFileId_(driveUrl);
  if (!fileId) return null;

  try {
    var file = DriveApp.getFileById(fileId);
    var blob = file.getBlob();
    var mimeType = blob.getContentType();
    var bytes = blob.getBytes();

    // 5MB 超の場合、サムネイル経由で JPEG 取得を試行
    if (bytes.length > MAX_IMAGE_SIZE) {
      Logger.log('画像サイズが5MB超: ' + fileId + ' (' + bytes.length + ' bytes). サムネイル経由で取得を試行');
      var thumbnailUrl = 'https://drive.google.com/thumbnail?id=' + fileId + '&sz=w4096';
      var thumbResponse = UrlFetchApp.fetch(thumbnailUrl, { muteHttpExceptions: true });
      if (thumbResponse.getResponseCode() === 200) {
        blob = thumbResponse.getBlob();
        bytes = blob.getBytes();
        mimeType = 'image/jpeg';
        Logger.log('サムネイル経由で取得成功: ' + bytes.length + ' bytes');
      }
      if (bytes.length > MAX_IMAGE_SIZE) {
        Logger.log('画像サイズが5MB超のためスキップ: ' + fileId);
        return null;
      }
    }

    return {
      base64: Utilities.base64Encode(bytes),
      mimeType: mimeType || 'image/jpeg'
    };
  } catch (e) {
    Logger.log('Drive 画像取得エラー (' + fileId + '): ' + e.message);
    return null;
  }
}

// ============================================================
// X API メディアアップロード・ツイート投稿
// ============================================================

function uploadMediaToX_(base64Data) {
  var params = {
    media_data: base64Data
  };

  var authHeader = generateOAuthHeader_('POST', X_MEDIA_UPLOAD_URL, params);

  // OAuth 署名と実際のリクエストボディで同一のエンコードを保証するため、
  // percentEncode_ で手動エンコードした文字列を payload に渡す
  var encodedBody = percentEncode_('media_data') + '=' + percentEncode_(base64Data);

  var response = UrlFetchApp.fetch(X_MEDIA_UPLOAD_URL, {
    method: 'post',
    headers: {
      'Authorization': authHeader,
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    payload: encodedBody,
    muteHttpExceptions: true
  });

  var code = response.getResponseCode();
  if (code === 429) {
    Logger.log('X API レート制限に到達 (media upload)');
    throw new Error('RATE_LIMITED');
  }
  if (code !== 200 && code !== 202) {
    Logger.log('X media upload error (' + code + '): ' + response.getContentText());
    return null;
  }

  var data = JSON.parse(response.getContentText());
  Logger.log('メディアアップロード成功: ' + data.media_id_string);
  return data.media_id_string;
}

function postTweet_(text, mediaIds) {
  // テキスト長チェック（日本語は2文字分カウントされるため概算）
  var weightedLength = text.replace(/[\u3000-\u9FFF\uF900-\uFAFF]/g, 'xx').length;
  if (weightedLength > 280) {
    Logger.log('警告: ツイートが280文字超の可能性 (概算: ' + weightedLength + '文字)。X Premium でない場合はエラーになります');
  }

  var tweetBody = { text: text };
  if (mediaIds && mediaIds.length > 0) {
    if (mediaIds.length > MAX_MEDIA_PER_TWEET) {
      Logger.log('警告: メディアIDが' + mediaIds.length + '件。上限の' + MAX_MEDIA_PER_TWEET + '件に切り詰めます');
      mediaIds = mediaIds.slice(0, MAX_MEDIA_PER_TWEET);
    }
    tweetBody.media = { media_ids: mediaIds };
  }

  // v2 tweets endpoint: JSON body は OAuth 署名対象外 → params は空
  var authHeader = generateOAuthHeader_('POST', X_TWEET_URL, {});

  var response = UrlFetchApp.fetch(X_TWEET_URL, {
    method: 'post',
    headers: {
      'Authorization': authHeader,
      'Content-Type': 'application/json'
    },
    payload: JSON.stringify(tweetBody),
    muteHttpExceptions: true
  });

  var code = response.getResponseCode();
  if (code === 429) {
    Logger.log('X API レート制限に到達 (tweet)');
    throw new Error('RATE_LIMITED');
  }
  if (code !== 200 && code !== 201) {
    Logger.log('X tweet error (' + code + '): ' + response.getContentText());
    return null;
  }

  var data = JSON.parse(response.getContentText());
  Logger.log('ツイート投稿成功: ' + JSON.stringify(data));
  return data;
}

// ============================================================
// 投稿処理（1件分）
// ============================================================

function processPost_(post) {
  Logger.log('--- 投稿処理開始: ' + post.title + ' (Page: ' + post.pageId + ') ---');

  // 1. 画像アップロード
  var mediaIds = [];
  for (var i = 0; i < post.imageUrls.length && i < MAX_MEDIA_PER_TWEET; i++) {
    var imageData = getImageFromDrive_(post.imageUrls[i]);
    if (!imageData) {
      Logger.log('画像取得失敗、スキップ: ' + post.imageUrls[i]);
      continue;
    }

    var mediaId = uploadMediaToX_(imageData.base64);
    if (mediaId) {
      mediaIds.push(mediaId);
    }
  }

  Logger.log('アップロードしたメディア数: ' + mediaIds.length + '/' + post.imageUrls.length);

  // 2. ツイート投稿
  var result = postTweet_(post.body, mediaIds);
  if (!result) {
    // 非回復性エラーの無限リトライを防ぐため「投稿エラー」に更新
    updateNotionStatus_(post.pageId, '投稿エラー');
    throw new Error('ツイート投稿に失敗: ' + post.title);
  }

  // 3. Notion ステータス更新
  var updated = updateNotionStatus_(post.pageId, '完了');
  if (!updated) {
    Logger.log('警告: ツイートは投稿済みですが Notion のステータス更新に失敗。重複投稿のリスクあり。Page: ' + post.pageId);
  }

  Logger.log('--- 投稿処理完了: ' + post.title + ' ---');
}

// ============================================================
// メイン関数・セットアップ
// ============================================================

function main() {
  var startTime = Date.now();
  Logger.log('=== X 自動投稿処理開始 ===');

  var posts = fetchDuePosts();
  if (posts.length === 0) {
    Logger.log('投稿対象なし');
    return;
  }

  var successCount = 0;
  var errorCount = 0;

  for (var i = 0; i < posts.length; i++) {
    // 実行時間ガード
    if (Date.now() - startTime > MAX_RUNTIME_MS) {
      Logger.log('実行時間制限（5分）に達したため中断。残り ' + (posts.length - i) + ' 件は次回実行で処理');
      break;
    }

    try {
      processPost_(posts[i]);
      successCount++;
    } catch (e) {
      if (e.message === 'RATE_LIMITED') {
        Logger.log('レート制限のため処理を中断。残り ' + (posts.length - i) + ' 件は次回実行で処理');
        break;
      }
      Logger.log('投稿処理エラー [' + (i + 1) + '/' + posts.length + '] '
        + '(タイトル: ' + posts[i].title + ', PageID: ' + posts[i].pageId + '): ' + e.message);
      errorCount++;
    }
  }

  Logger.log('=== 処理完了: 成功 ' + successCount + ' 件, 失敗 ' + errorCount + ' 件 ===');
}

function setupTrigger() {
  // 既存トリガーを削除
  deleteTriggers();

  // 6時間間隔トリガーを作成
  ScriptApp.newTrigger('main')
    .timeBased()
    .everyHours(6)
    .create();

  Logger.log('トリガーを設定しました（6時間間隔）');
}

function deleteTriggers() {
  var triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(function(trigger) {
    if (trigger.getHandlerFunction() === 'main') {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  Logger.log('既存のトリガーを削除しました');
}
