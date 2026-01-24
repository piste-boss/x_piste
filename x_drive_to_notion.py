#!/usr/bin/env python3
"""
Google Driveの画像リンクをNotionデータベースに同期するスクリプト

機能:
1. 指定されたGoogle Driveフォルダ内の画像ファイルを取得
2. ファイル名から日時と枝番を解析 (例: 2026-0126-2000-1.png)
3. Notionデータベースの「投稿日」と照合
4. 対応するURLプロパティにGoogle DriveのWebViewLinkを追記
"""

import os
import sys
import re
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
import requests
from notion_client import Client
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

# --- 設定 ---

# Google DriveフォルダID
DRIVE_FOLDER_ID = "16pMNNI_5lLPcDGIbHNxDRjQ1zczcd5Na"

# NotionデータベースURL
NOTION_DATABASE_URL = "https://www.notion.so/2f2c991b527b803eaa40df67788a9df7?v=2f2c991b527b8046a921000c186c175f&source=copy_link"

# パス設定
BASE_DIR = Path(__file__).parent
SYSTEM_DIR = BASE_DIR.parent / "Threads_piste" / "image_upload" # Credentials location
ENV_PATH = Path("/Users/ishikawasuguru/Threads_piste/90_System/.env") # .env location
TOKEN_FILE = BASE_DIR / "token.pickle"
CREDENTIALS_FILE = SYSTEM_DIR / "client_secret_googleusercontent.com.json" # Fallback, needs wild card logic usually

# OAuth2スコープ
SCOPES = ['https://www.googleapis.com/auth/drive.readonly'] # 読み取り専用でOK

# JSTタイムゾーン
JST = timezone(timedelta(hours=9))

# --- 初期化 ---

load_dotenv(ENV_PATH)
NOTION_API_KEY = os.getenv("NOTION_API_KEY")

# --- Google Drive 関連関数 ---

def find_credentials_file():
    """OAuth2認証情報ファイルを探す"""
    # SYSTEM_DIR内の client_secret*.json を探す
    if SYSTEM_DIR.exists():
        for file in SYSTEM_DIR.glob("client_secret*.json"):
            return file
    return None

def get_drive_service():
    """Google Drive APIサービスを取得"""
    creds = None
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, 'rb') as token:
                creds = pickle.load(token)
        except Exception:
            pass

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        
        if not creds:
            creds_path = find_credentials_file()
            if not creds_path:
                print("✗ エラー: Google Drive認証情報が見つかりません (client_secret*.json)")
                sys.exit(1)
                
            flow = InstalledAppFlow.from_client_secrets_file(
                str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)

    return build('drive', 'v3', credentials=creds)

def list_drive_files(service, folder_id):
    """フォルダ内のファイル一覧を取得（WebViewLinkを含む）"""
    files = []
    page_token = None
    try:
        while True:
            # webViewLink, name, id を取得
            response = service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                spaces='drive',
                fields='nextPageToken, files(id, name, webViewLink)',
                pageToken=page_token
            ).execute()
            
            files.extend(response.get('files', []))
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return files
    except HttpError as e:
        print(f"✗ Drive API エラー: {e}")
        return []

def parse_filename(filename):
    """ファイル名から日時と枝番を抽出"""
    # パターン: YYYY-MMDD-HHMM(-N).ext
    # 例: 2026-0126-2000-1.png -> 2026-01-26 20:00, 1
    # 例: 2026-0125-0900.png   -> 2026-01-25 09:00, 1 (default)
    
    stem = Path(filename).stem
    
    # 枝番あり
    match_branch = re.match(r'(\d{4})-(\d{2})(\d{2})-(\d{2})(\d{2})-(\d+)', stem)
    if match_branch:
        year, month, day, hour, minute, branch = map(int, match_branch.groups())
        return datetime(year, month, day, hour, minute, tzinfo=JST), branch
        
    # 枝番なし
    match_single = re.match(r'(\d{4})-(\d{2})(\d{2})-(\d{2})(\d{2})', stem)
    if match_single:
        year, month, day, hour, minute = map(int, match_single.groups())
        return datetime(year, month, day, hour, minute, tzinfo=JST), 1
        
    return None, None

# --- Notion 関連関数 ---

def extract_database_id(url):
    match = re.search(r'notion\.so/([a-f0-9]{32})', url)
    if match:
        return match.group(1)
    return None

def get_notion_pages(notion, database_id):
    """データベースの全ページを取得 (requests使用)"""
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    pages = []
    cursor = None
    while True:
        payload = {}
        if cursor:
            payload["start_cursor"] = cursor
            
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        pages.extend(data.get("results", []))
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return pages

def find_page_by_date(pages, target_date):
    """指定された日時のページを探す"""
    # target_dateはJST aware
    
    for page in pages:
        props = page.get("properties", {})
        
        # 投稿日プロパティを探す (Prop name might vary, check "投稿日" or type date)
        date_prop = props.get("投稿日")
        if not date_prop:
             # Fallback: search for any date property
            for k, v in props.items():
                if v.get("type") == "date":
                    date_prop = v
                    break
        
        if date_prop and date_prop.get("date"):
            start_iso = date_prop["date"]["start"]
            if start_iso:
                try:
                    # ISO format parse
                    page_date = datetime.fromisoformat(start_iso)
                    # Adjust to JST if matched (or just compare timestamp)
                    if page_date == target_date:
                        return page
                except ValueError:
                    continue
    return None

def update_page_url(notion, page_id, branch_num, url, existing_props):
    """ページのURLプロパティを更新"""
    
    # プロパティ名の決定（ユーザー指定）
    # 枝番1 -> URL1 (なければ URL)
    # 枝番2 -> URL2
    # ...
    
    prop_name = None
    
    if branch_num == 1:
        # Check if URL1 exists, else URL
        if "URL1" in existing_props:
            prop_name = "URL1"
        elif "URL" in existing_props:
            prop_name = "URL"
    else:
        # URL2, URL3...
        candidate = f"URL{branch_num}"
        # Case insensitive check might be nice but let's stick to exact
        if candidate in existing_props:
            prop_name = candidate
        else:
            # lowercase check
            candidate_lower = f"url{branch_num}"
            for k in existing_props.keys():
                if k.lower() == candidate_lower:
                    prop_name = k
                    break
    
    if not prop_name:
        print(f"  ⚠ 対応するプロパティが見つかりません (枝番: {branch_num})")
        return False
        
    try:
        notion.pages.update(
            page_id=page_id,
            properties={
                prop_name: {
                    "url": url
                }
            }
        )
        print(f"  ✓ 更新: {prop_name} <- {url}")
        return True
    except Exception as e:
        print(f"  ✗ 更新失敗: {e}")
        return False

# --- メイン処理 ---

def main():
    print("="*60)
    print("Google Drive -> Notion 画像リンク同期スクリプト")
    print("="*60)

    # 1. Drive 認証 & ファイル取得
    print("\nGoogle Driveからファイル一覧を取得中...")
    drive_service = get_drive_service()
    drive_files = list_drive_files(drive_service, DRIVE_FOLDER_ID)
    print(f"✓ {len(drive_files)} 個のファイルが見つかりました")

    # 2. Notion 認証 & ページ取得
    print("\nNotionデータベースからページ一覧を取得中...")
    if not NOTION_API_KEY:
        print("✗ エラー: NOTION_API_KEYが設定されていません")
        sys.exit(1)
        
    notion = Client(auth=NOTION_API_KEY)
    db_id = extract_database_id(NOTION_DATABASE_URL)
    if not db_id:
        print("✗ エラー: データベースIDの抽出に失敗")
        sys.exit(1)
        
    try:
        pages = get_notion_pages(notion, db_id)
        print(f"✓ {len(pages)} 件のページを取得しました")
        
        # データベースのプロパティ構造を取得（カラム名チェック用）
        # 最初のページから取得するのが手っ取り早い
        db_props = {}
        if pages:
            db_props = pages[0].get("properties", {})
            
    except Exception as e:
        print(f"✗ Notion API エラー: {e}")
        sys.exit(1)

    # 3. マッチングと更新
    print("\n同期処理を開始します...")
    update_count = 0
    
    for file in drive_files:
        name = file.get('name')
        link = file.get('webViewLink')
        
        dt, branch = parse_filename(name)
        if not dt:
            # 日時ファイル名でないものはスキップ
            continue
            
        print(f"\nファイル: {name}")
        print(f"  日時: {dt}, 枝番: {branch}")
        
        page = find_page_by_date(pages, dt)
        if page:
            page_title_prop = page["properties"].get("タイトル", {}).get("title", [])
            page_title = "".join([t["plain_text"] for t in page_title_prop]) if page_title_prop else "No Title"
            print(f"  ページ一致: {page_title}")
            
            if update_page_url(notion, page["id"], branch, link, db_props):
                update_count += 1
        else:
            print(f"  ⚠ 対応するNotionページが見つかりません")

    print("\n" + "="*60)
    print(f"処理完了: {update_count} 件のプロパティを更新しました")
    print("="*60)

if __name__ == "__main__":
    main()
