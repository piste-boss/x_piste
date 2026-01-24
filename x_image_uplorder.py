#!/usr/bin/env python3
"""
x_image内の画像をGoogleドライブに移動するスクリプト

指定されたディレクトリ内の画像ファイルをGoogleドライブの指定フォルダにアップロードし、
アップロード成功後に元のファイルを削除します（移動処理）。
"""

import os
import sys
from pathlib import Path
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import pickle

# 画像ディレクトリのパス
IMAGE_DIRECTORY = Path("/Users/ishikawasuguru/x_piste/x_image")

# GoogleドライブフォルダID（URLから抽出）
DRIVE_FOLDER_ID = "16pMNNI_5lLPcDGIbHNxDRjQ1zczcd5Na"

# サービスアカウントJSONファイルのパス
SERVICE_ACCOUNT_FILE = Path(__file__).parent.parent.parent / "90_System" / "service_account.json.json"

# OAuth2トークンファイルのパス
TOKEN_FILE = Path(__file__).parent / "token.pickle"
SYSTEM_DIR = Path(__file__).parent.parent / "Threads_piste" / "image_upload"

# OAuth2認証情報ファイルを探す（複数のファイル名に対応）
def find_credentials_file():
    """OAuth2認証情報ファイルを探す"""
    # 一般的なファイル名を試す
    possible_names = [
        "credentials.json",
        "client_secret*.json"  # ワイルドカードパターン
    ]
    
    # credentials.jsonを探す
    credentials_file = SYSTEM_DIR / "credentials.json"
    if credentials_file.exists():
        return credentials_file
    
    # client_secretで始まるJSONファイルを探す
    for file in SYSTEM_DIR.glob("client_secret*.json"):
        return file
    
    return None

CREDENTIALS_FILE = find_credentials_file()

# OAuth2スコープ
SCOPES = ['https://www.googleapis.com/auth/drive']

# 対応する画像ファイルの拡張子
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}


def get_drive_service():
    """Google Drive APIサービスを取得（OAuth2を使用）"""
    creds = None
    
    # 既存のトークンを読み込む
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, 'rb') as token:
                creds = pickle.load(token)
        except Exception as e:
            print(f"⚠ トークンファイルの読み込みに失敗しました: {e}")
    
    # トークンが無効または存在しない場合、再認証
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("✓ トークンを更新しました")
            except Exception as e:
                print(f"⚠ トークンの更新に失敗しました: {e}")
                creds = None
        
        if not creds:
            # OAuth2認証フローを開始
            if not CREDENTIALS_FILE or not CREDENTIALS_FILE.exists():
                print(f"✗ エラー: OAuth2認証情報ファイルが見つかりません")
                print(f"  90_Systemディレクトリ内に credentials.json または client_secret*.json を配置してください")
                print(f"\nOAuth2認証情報ファイルの取得方法:")
                print(f"  1. Google Cloud Console (https://console.cloud.google.com/) にアクセス")
                print(f"  2. プロジェクトを選択または作成")
                print(f"  3. 「APIとサービス」→「認証情報」に移動")
                print(f"  4. 「認証情報を作成」→「OAuth クライアント ID」を選択")
                print(f"  5. アプリケーションの種類で「デスクトップアプリ」を選択")
                print(f"  6. 作成した認証情報をダウンロードして 90_System ディレクトリに保存")
                sys.exit(1)
            
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), SCOPES)
                creds = flow.run_local_server(port=0)
                print("✓ OAuth2認証が完了しました")
            except Exception as e:
                print(f"✗ OAuth2認証に失敗しました: {e}")
                sys.exit(1)
        
        # トークンを保存
        try:
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(creds, token)
            print("✓ トークンを保存しました")
        except Exception as e:
            print(f"⚠ トークンの保存に失敗しました: {e}")
    
    try:
        # Drive APIサービスを構築
        service = build('drive', 'v3', credentials=creds)
        print("✓ Google Drive API認証に成功しました")
        return service
    except Exception as e:
        print(f"✗ Google Drive API認証に失敗しました: {e}")
        sys.exit(1)


def verify_folder_access(service, folder_id):
    """フォルダへのアクセス権限を確認"""
    try:
        folder = service.files().get(
            fileId=folder_id,
            fields='id,name',
            supportsAllDrives=True
        ).execute()
        folder_name = folder.get('name', '不明')
        print(f"✓ フォルダにアクセス可能: {folder_name} (ID: {folder_id})")
        return True
    except HttpError as e:
        if e.resp.status == 404:
            print(f"✗ エラー: フォルダが見つかりません (ID: {folder_id})")
            print("  フォルダIDが正しいか、アカウントにフォルダへのアクセス権限があるか確認してください")
        else:
            print(f"✗ エラー: フォルダへのアクセスに失敗しました: {e}")
        return False
    except Exception as e:
        print(f"✗ エラー: {e}")
        return False


def upload_file_to_drive(service, file_path, folder_id):
    """ファイルをGoogleドライブにアップロード"""
    file_name = file_path.name
    
    try:
        # ファイルのメタデータ
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        
        # メディアファイルのアップロード
        mimetype = 'image/png' if file_path.suffix.lower() == '.png' else 'image/jpeg'
        media = MediaFileUpload(
            str(file_path),
            mimetype=mimetype,
            resumable=True
        )
        
        # ファイルをアップロード
        print(f"  アップロード中: {file_name}...")
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name',
            supportsAllDrives=True
        ).execute()
        
        print(f"  ✓ アップロード成功: {file.get('name')} (ID: {file.get('id')})")
        return True
    except HttpError as e:
        print(f"  ✗ アップロード失敗: {file_name}")
        error_details = e.error_details if hasattr(e, 'error_details') else []
        for detail in error_details:
            print(f"    エラー: {detail}")
        print(f"    詳細: {e}")
        return False
    except Exception as e:
        print(f"  ✗ アップロード失敗: {file_name}")
        print(f"    エラー: {e}")
        return False


def get_image_files(directory):
    """ディレクトリ内の画像ファイルを取得"""
    if not directory.exists():
        print(f"✗ エラー: ディレクトリが見つかりません: {directory}")
        return []
    
    if not directory.is_dir():
        print(f"✗ エラー: 指定されたパスはディレクトリではありません: {directory}")
        return []
    
    image_files = [
        f for f in directory.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    ]
    
    return sorted(image_files)


def main():
    """メイン処理"""
    print("=" * 60)
    print("Googleドライブへの画像移動スクリプト (x_image)")
    print("=" * 60)
    
    # 画像ディレクトリの確認
    print(f"\n画像ディレクトリを確認しています: {IMAGE_DIRECTORY}")
    image_files = get_image_files(IMAGE_DIRECTORY)
    
    if not image_files:
        print("✗ 画像ファイルが見つかりませんでした")
        sys.exit(1)
    
    print(f"✓ {len(image_files)} 個の画像ファイルが見つかりました")
    for i, img_file in enumerate(image_files, 1):
        print(f"  {i}. {img_file.name} ({img_file.stat().st_size / 1024:.1f} KB)")
    
    # Google Drive APIサービスを取得
    print(f"\nGoogle Drive APIに接続しています...")
    service = get_drive_service()
    
    # フォルダへのアクセス権限を確認
    print(f"\nフォルダへのアクセス権限を確認しています...")
    if not verify_folder_access(service, DRIVE_FOLDER_ID):
        sys.exit(1)
    
    # 各画像ファイルをアップロード
    print(f"\n画像ファイルをアップロードしています...")
    success_count = 0
    failed_files = []
    
    for i, img_file in enumerate(image_files, 1):
        print(f"\n[{i}/{len(image_files)}] {img_file.name}")
        
        if upload_file_to_drive(service, img_file, DRIVE_FOLDER_ID):
            # アップロード成功後、元のファイルを削除（移動処理）
            try:
                img_file.unlink()
                print(f"  ✓ 元のファイルを削除しました")
                success_count += 1
            except Exception as e:
                print(f"  ⚠ 警告: 元のファイルの削除に失敗しました: {e}")
                print(f"    ファイルは手動で削除してください: {img_file}")
                success_count += 1  # アップロードは成功しているのでカウント
        else:
            failed_files.append(img_file)
    
    # 結果を表示
    print("\n" + "=" * 60)
    print(f"処理完了: {success_count}/{len(image_files)} 個のファイルを移動しました")
    if failed_files:
        print(f"\n⚠ 以下のファイルのアップロードに失敗しました:")
        for failed_file in failed_files:
            print(f"  - {failed_file.name}")
    print("=" * 60)
    
    return 0 if success_count == len(image_files) else 1


if __name__ == "__main__":
    sys.exit(main())
