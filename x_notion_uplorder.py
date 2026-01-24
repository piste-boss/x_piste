#!/usr/bin/env python3
"""
x_post.mdの内容をNotionデータベースに転記するスクリプト

MDファイルの構造:
- タイトル → プロパティ名：タイトル
- 投稿予定日時 → プロパティ名：投稿日
- 本文 → プロパティ名：本文
- コメント欄 → プロパティ名：コメント欄
- ステータス → 全て「未着手」を選択
"""

import os
import sys
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
from notion_client import Client
import requests

# .envファイルを読み込む（90_System/.envから）
env_path = Path("/Users/ishikawasuguru/Threads_piste/90_System/.env")
load_dotenv(env_path)

# Notion APIトークン（環境変数から読み込む）
NOTION_API_KEY = os.getenv("NOTION_API_KEY")

# MDファイルのパス
MARKDOWN_FILE = Path("/Users/ishikawasuguru/x_piste/x_post.md")

# NotionデータベースURL
NOTION_DATABASE_URL = "https://www.notion.so/2f2c991b527b803eaa40df67788a9df7?v=2f2c991b527b8046a921000c186c175f&source=copy_link"


def extract_database_id_from_url(url):
    """Notion URLからデータベースIDを抽出し、ハイフン付き形式に変換"""
    # URLから32文字のIDを抽出（v=の前の部分）
    match = re.search(r'notion\.so/([a-f0-9]{32})', url)
    if not match:
        raise ValueError(f"Notion URLからデータベースIDを抽出できませんでした: {url}")
    
    db_id_no_hyphens = match.group(1)
    # ハイフン付き形式に変換
    db_id = f"{db_id_no_hyphens[:8]}-{db_id_no_hyphens[8:12]}-{db_id_no_hyphens[12:16]}-{db_id_no_hyphens[16:20]}-{db_id_no_hyphens[20:]}"
    
    return db_id, db_id_no_hyphens


def parse_markdown_posts(markdown_content):
    """Markdownファイルから投稿案を抽出（x_post.md形式に対応）"""
    posts = []
    
    # 日付セクションで分割（## で始まるセクション）
    sections = re.split(r'^## ', markdown_content, flags=re.MULTILINE)
    
    for section in sections[1:]:  # 最初のセクション（ヘッダー）をスキップ
        if not section.strip():
            continue
        
        lines = section.split('\n')
        # 日付行を抽出（例: "1/25 (日)"）
        date_line = lines[0].strip()
        
        # 日付を抽出（例: "1/25"）
        date_match = re.search(r'(\d{1,2})/(\d{1,2})', date_line)
        if not date_match:
            continue
        
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        # 年は2026年と仮定（必要に応じて調整）
        year = 2026
        
        # 時間セクションで分割（### で始まるセクション）
        time_sections = re.split(r'^### ', section, flags=re.MULTILINE)
        
        for time_section in time_sections[1:]:  # 最初のセクション（日付行）をスキップ
            if not time_section.strip():
                continue
            
            time_lines = time_section.split('\n')
            # 時間行を抽出（例: "09:00：プライベート/日常（画像1枚）"）
            time_line = time_lines[0].strip()
            
            # 時間を抽出（例: "09:00"）
            time_match = re.search(r'(\d{1,2}):(\d{2})', time_line)
            if not time_match:
                continue
            
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            
            # 投稿予定日時を作成
            try:
                scheduled_date = datetime(year, month, day, hour, minute, tzinfo=timezone(timedelta(hours=9)))
            except ValueError:
                continue
            
            post = {
                "title": "",
                "scheduled_date": scheduled_date,
                "text": "",
                "comment": ""
            }
            
            current_section = None
            content_lines = []
            
            for i, line in enumerate(time_lines[1:], 1):
                line = line.strip()
                
                # タイトル
                if line.startswith('**タイトル**'):
                    # タイトルを抽出（同じ行にタイトルがある場合）
                    title_match = re.search(r'\*\*タイトル\*\*:\s*(.+)', line)
                    if title_match:
                        post["title"] = title_match.group(1).strip()
                    else:
                        # 次の行にタイトルがある場合
                        if i < len(time_lines) - 1:
                            next_line = time_lines[i + 1].strip()
                            if next_line and not next_line.startswith('**'):
                                post["title"] = next_line
                    current_section = None
                    content_lines = []
                
                # 種別（スキップ）
                elif line.startswith('**種別**'):
                    current_section = None
                    content_lines = []
                
                # 本文
                elif line == "**【本文】**" or line == "**本文**":
                    # 既存のセクションの内容を保存
                    if current_section == "comment" and content_lines:
                        post["comment"] = "\n".join(content_lines).strip()
                    
                    current_section = "text"
                    content_lines = []
                
                # コメント欄
                elif "**【コメント欄】**" in line or "**コメント欄**" in line or "**コメント**" in line:
                    # 既存の本文を保存
                    if current_section == "text" and content_lines:
                        post["text"] = "\n".join(content_lines).strip()
                    
                    current_section = "comment"
                    content_lines = []
                
                # 区切り線
                elif line.startswith('---'):
                    # 現在のセクションの内容を保存
                    if current_section == "text" and content_lines:
                        post["text"] = "\n".join(content_lines).strip()
                    elif current_section == "comment" and content_lines:
                        post["comment"] = "\n".join(content_lines).strip()
                    break
                
                # コンテンツ行
                else:
                    if current_section and line:
                        content_lines.append(line)
            
            # 最後のセクションの内容を保存
            if current_section == "text" and content_lines:
                post["text"] = "\n".join(content_lines).strip()
            elif current_section == "comment" and content_lines:
                post["comment"] = "\n".join(content_lines).strip()
            
            # タイトルが空の場合、時間と種別から生成
            if not post["title"]:
                # 時間行から種別を抽出（例: "プライベート/日常"）
                category_match = re.search(r'：(.+?)(?:（|$)', time_line)
                if category_match:
                    post["title"] = f"{time_line.split('：')[0]} - {category_match.group(1)}"
                else:
                    post["title"] = f"{hour:02d}:{minute:02d} 投稿"
            
            # 有効な投稿のみ追加（タイトルと投稿予定日時があればOK）
            if post["title"] and post["scheduled_date"]:
                posts.append(post)
    
    return posts


def find_database_by_id(notion, database_id):
    """データベースIDでデータベースを取得"""
    try:
        database = notion.databases.retrieve(database_id=database_id)
        return database
    except Exception as e:
        print(f"✗ データベースIDでの取得に失敗しました: {e}")
        return None


def find_database_by_search(notion):
    """検索でデータベースを探す"""
    try:
        print("  全体検索でデータベースを検索しています...")
        search_results = notion.search(page_size=100)
        
        databases = []
        for result in search_results.get("results", []):
            if result.get("object") == "database":
                title = ""
                if result.get("title"):
                    title_list = result["title"]
                    if title_list:
                        title = "".join([text.get("plain_text", "") for text in title_list])
                
                databases.append({
                    "id": result.get("id"),
                    "title": title,
                    "url": result.get("url", "")
                })
        
        if databases:
            print(f"  見つかったデータベース数: {len(databases)}")
            for db in databases[:5]:  # 最初の5つを表示
                print(f"    - {db['title']}: {db['id']}")
        
        return databases
    except Exception as e:
        print(f"  検索中にエラーが発生しました: {e}")
        return []


def get_property_name_mapping(database):
    """データベースのプロパティ情報を取得し、マッピングを作成"""
    properties = database.get("properties", {})
    mapping = {}
    
    # プロパティ名のマッピング（ユーザー指定のプロパティ名を探す）
    target_properties = {
        "タイトル": "title",
        "投稿日": "date",
        "本文": "rich_text",
        "コメント欄": "rich_text",
        "コメント": "rich_text",
        "ステータス": "select"
    }
    
    for prop_name, prop_info in properties.items():
        prop_type = prop_info.get("type", "")
        # ユーザー指定のプロパティ名と一致するものを探す
        for target_name, expected_type in target_properties.items():
            if prop_name == target_name and prop_type == expected_type:
                mapping[target_name] = prop_name
                break
    
    return mapping, properties


def create_post_in_database(notion, database_id, post, property_mapping, all_properties):
    """データベースに投稿を作成"""
    try:
        # プロパティ情報が空の場合は再取得
        if not all_properties:
            try:
                database = notion.databases.retrieve(database_id=database_id)
                all_properties = database.get("properties", {})
            except:
                pass
        
        properties = {}
        
        # タイトルプロパティ
        if "タイトル" in property_mapping:
            title_prop_name = property_mapping["タイトル"]
            properties[title_prop_name] = {
                "title": [{
                    "text": {"content": post["title"]}
                }]
            }
        else:
            # タイトルプロパティが見つからない場合、title型のプロパティを探す
            for prop_name, prop_info in all_properties.items():
                if prop_info.get("type") == "title":
                    properties[prop_name] = {
                        "title": [{
                            "text": {"content": post["title"]}
                        }]
                    }
                    break
        
        # 投稿日プロパティ
        if post["scheduled_date"]:
            if "投稿日" in property_mapping:
                date_prop_name = property_mapping["投稿日"]
                properties[date_prop_name] = {
                    "date": {
                        "start": post["scheduled_date"].isoformat()
                    }
                }
            else:
                # 投稿日プロパティが見つからない場合、date型のプロパティを探す
                found = False
                for prop_name, prop_info in all_properties.items():
                    if prop_info.get("type") == "date":
                        # 「投稿」を含むか、または最初のdate型プロパティを使用
                        if "投稿" in prop_name or not found:
                            properties[prop_name] = {
                                "date": {
                                    "start": post["scheduled_date"].isoformat()
                                }
                            }
                            found = True
                            if "投稿" in prop_name:
                                break
        
        # 本文プロパティ
        if post["text"]:
            if "本文" in property_mapping:
                text_prop_name = property_mapping["本文"]
                properties[text_prop_name] = {
                    "rich_text": [{
                        "text": {"content": post["text"][:2000]}  # Notionの制限
                    }]
                }
            else:
                # 本文プロパティが見つからない場合、rich_text型のプロパティを探す
                found = False
                for prop_name, prop_info in all_properties.items():
                    if prop_info.get("type") == "rich_text":
                        # 「本文」を含むか、または最初のrich_text型プロパティを使用（ただしコメントっぽくないもの）
                        if "本文" in prop_name:
                             properties[prop_name] = {
                                "rich_text": [{
                                    "text": {"content": post["text"][:2000]}
                                }]
                            }
                             found = True
                             break
                        elif not found and "コメント" not in prop_name:
                            properties[prop_name] = {
                                "rich_text": [{
                                    "text": {"content": post["text"][:2000]}
                                }]
                            }
                            found = True
        
        # コメント欄プロパティ
        if post["comment"]:
            if "コメント欄" in property_mapping:
                comment_prop_name = property_mapping["コメント欄"]
                properties[comment_prop_name] = {
                    "rich_text": [{
                        "text": {"content": post["comment"][:2000]}  # Notionの制限
                    }]
                }
            elif "コメント" in property_mapping:
                comment_prop_name = property_mapping["コメント"]
                properties[comment_prop_name] = {
                    "rich_text": [{
                        "text": {"content": post["comment"][:2000]}  # Notionの制限
                    }]
                }
            else:
                # コメント欄プロパティが見つからない場合、rich_text型のプロパティを探す
                found = False
                for prop_name, prop_info in all_properties.items():
                    if prop_info.get("type") == "rich_text":
                        # 「コメント」を含むか、または最初のrich_text型プロパティを使用（ただし本文っぽくないもの）
                        if "コメント" in prop_name:
                             properties[prop_name] = {
                                "rich_text": [{
                                    "text": {"content": post["comment"][:2000]}
                                }]
                            }
                             found = True
                             break
                        elif not found and "本文" not in prop_name:
                            properties[prop_name] = {
                                "rich_text": [{
                                    "text": {"content": post["comment"][:2000]}
                                }]
                            }
                            found = True
        
        # ステータスプロパティ（全て「未着手」を選択）
        if "ステータス" in property_mapping:
            status_prop_name = property_mapping["ステータス"]
            # status型とselect型の両方に対応
            prop_info = all_properties.get(status_prop_name, {})
            if prop_info.get("type") == "status":
                properties[status_prop_name] = {
                    "status": {
                        "name": "未着手"
                    }
                }
            else:
                properties[status_prop_name] = {
                    "select": {
                        "name": "未着手"
                    }
                }
        else:
            # ステータスプロパティが見つからない場合、status型またはselect型のプロパティを探す
            for prop_name, prop_info in all_properties.items():
                prop_type = prop_info.get("type", "")
                if prop_type in ["status", "select"] and ("ステータス" in prop_name or "Status" in prop_name):
                    if prop_type == "status":
                        properties[prop_name] = {
                            "status": {
                                "name": "未着手"
                            }
                        }
                    else:
                        # select型の場合、選択肢に「未着手」があるか確認
                        select_options = prop_info.get("select", {}).get("options", [])
                        if any(opt.get("name") == "未着手" for opt in select_options):
                            properties[prop_name] = {
                                "select": {
                                    "name": "未着手"
                                }
                            }
                    break
        
        # デバッグ情報：設定されるプロパティを表示
        if properties:
            print(f"  設定するプロパティ: {list(properties.keys())}")
        else:
            print(f"  警告: プロパティが設定されていません")
            print(f"  利用可能なプロパティ: {list(all_properties.keys())}")
        
        # ページを作成
        response = notion.pages.create(
            parent={"database_id": database_id},
            properties=properties
        )
        
        return response.get("id")
    except Exception as e:
        print(f"  エラー: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """メイン処理"""
    if not NOTION_API_KEY:
        print("✗ エラー: NOTION_API_KEYが設定されていません")
        print(f"  90_System/.envファイルにNOTION_API_KEYを設定してください")
        sys.exit(1)
    
    # Markdownファイルが存在するか確認
    if not MARKDOWN_FILE.exists():
        print(f"✗ エラー: ファイルが見つかりません: {MARKDOWN_FILE}")
        sys.exit(1)
    
    # Markdownファイルを読み込む
    print(f"Markdownファイルを読み込んでいます: {MARKDOWN_FILE}")
    try:
        with open(MARKDOWN_FILE, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        print(f"✓ {len(markdown_content)} 文字のコンテンツを読み込みました")
    except Exception as e:
        print(f"✗ ファイル読み込みエラー: {e}")
        sys.exit(1)
    
    # Markdownから投稿案を抽出
    print(f"\nMarkdownファイルから投稿案を抽出しています...")
    try:
        posts = parse_markdown_posts(markdown_content)
        print(f"✓ {len(posts)} 件の投稿案を抽出しました")
        for i, post in enumerate(posts, 1):
            print(f"  {i}. {post['title']} ({post['scheduled_date']})")
    except Exception as e:
        print(f"✗ Markdown解析エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # URLからデータベースIDを抽出
    print(f"\nNotion URLからデータベースIDを抽出しています...")
    try:
        database_id, database_id_no_hyphens = extract_database_id_from_url(NOTION_DATABASE_URL)
        print(f"✓ データベースID（ハイフン付き）: {database_id}")
        print(f"✓ データベースID（ハイフンなし）: {database_id_no_hyphens}")
    except Exception as e:
        print(f"✗ エラー: {e}")
        sys.exit(1)
    
    # Notionクライアントを初期化
    print("\nNotion API接続を開始します...")
    try:
        notion = Client(auth=NOTION_API_KEY)
        print("✓ Notionクライアントの初期化に成功しました")
    except Exception as e:
        print(f"✗ Notionクライアントの初期化に失敗しました: {e}")
        sys.exit(1)
    
    # データベースの存在確認とプロパティ情報を取得
    print(f"\nデータベース情報を取得しています...")
    database = None
    
    # まずハイフン付き形式で試す
    try:
        database = find_database_by_id(notion, database_id)
    except:
        pass
    
    # ハイフン付きで取得できない場合、ハイフンなしで試す
    if not database:
        try:
            print(f"  ハイフンなし形式で再試行しています...")
            database = find_database_by_id(notion, database_id_no_hyphens)
            if database:
                database_id = database_id_no_hyphens  # 成功したIDを使用
        except:
            pass
    
    if not database:
        print(f"\nデータベースIDで直接取得できませんでした。")
        print(f"考えられる原因:")
        print(f"  1. データベースがインテグレーションと共有されていない")
        print(f"  2. データベースIDが正しくない")
        print(f"\n利用可能なデータベースを検索しています...")
        
        available_dbs = find_database_by_search(notion)
        if available_dbs:
            print(f"\n利用可能なデータベースが見つかりました:")
            for db in available_dbs:
                print(f"  - {db['title']}: {db['id']}")
            print(f"\nデータベースを共有するか、正しいデータベースIDを使用してください。")
        else:
            print(f"\n利用可能なデータベースが見つかりませんでした。")
            print(f"Notionインテグレーションがデータベースにアクセスできるように共有してください。")
        
        sys.exit(1)
    
    # データベースが見つかった場合の処理
    try:
        # データベース情報を再取得してプロパティ情報を確実に取得
        try:
            database = notion.databases.retrieve(database_id=database_id)
        except:
            try:
                database = notion.databases.retrieve(database_id=database_id_no_hyphens)
            except:
                pass
        
        title_blocks = database.get("title", [])
        database_title = ""
        if title_blocks:
            database_title = "".join([block.get("plain_text", "") for block in title_blocks])
        print(f"✓ データベース: {database_title if database_title else '(タイトルなし)'}")
        
        all_properties = database.get("properties", {})
        
        # プロパティ情報が取得できない場合、既存のページからプロパティ構造を推測
        if not all_properties:
            print(f"  警告: プロパティ情報が取得できませんでした。既存のページからプロパティ構造を推測します...")
            try:
                # データベースのページを1つ取得（requestsを使用）
                headers = {
                    "Authorization": f"Bearer {NOTION_API_KEY}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28"
                }
                url = f"https://api.notion.com/v1/databases/{database_id}/query"
                response = requests.post(url, headers=headers, json={})
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])
                
                if results:
                    page = results[0]
                    page_properties = page.get("properties", {})
                    # ページのプロパティ情報からデータベースのプロパティ構造を推測
                    all_properties = {}
                    for prop_name, prop_info in page_properties.items():
                        prop_type = prop_info.get("type", "unknown")
                        all_properties[prop_name] = {"type": prop_type}
                    print(f"  ✓ 既存のページから {len(all_properties)} 個のプロパティを検出しました")
            except Exception as e:
                print(f"  ✗ 既存のページからのプロパティ取得に失敗: {e}")
        
        print(f"✓ プロパティ数: {len(all_properties)}")
        if all_properties:
            for prop_name, prop_info in all_properties.items():
                prop_type = prop_info.get("type", "unknown")
                print(f"  - {prop_name}: {prop_type}")
        else:
            print(f"  警告: プロパティ情報が取得できませんでした")
            print(f"  データベース情報のキー: {list(database.keys())}")
        
        # プロパティマッピングを取得
        # all_propertiesが空の場合は、databaseから取得を試みる
        if not all_properties:
            all_properties = database.get("properties", {})
        
        if all_properties:
            property_mapping, _ = get_property_name_mapping(database)
        else:
            # プロパティ情報がない場合、空のマッピングを作成
            property_mapping = {}
        
        print(f"\nプロパティマッピング:")
        if property_mapping:
            for target_name, prop_name in property_mapping.items():
                print(f"  - {target_name} → {prop_name}")
        else:
            print(f"  (マッピングなし)")
    except Exception as e:
        print(f"✗ データベースの取得に失敗しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 各投稿案をデータベースに追加
    print(f"\nデータベースに投稿案を追加しています...")
    success_count = 0
    for i, post in enumerate(posts, 1):
        print(f"\n[{i}/{len(posts)}] {post['title']}")
        print(f"  投稿予定日時: {post['scheduled_date']}")
        print(f"  本文: {post['text'][:50]}..." if post['text'] else "  本文: (空)")
        print(f"  コメント: {post['comment'][:50]}..." if post['comment'] else "  コメント: (空)")
        
        page_id = create_post_in_database(notion, database_id, post, property_mapping, all_properties)
        if page_id:
            print(f"  ✓ 追加成功")
            success_count += 1
        else:
            print(f"  ✗ 追加失敗")
    
    print(f"\n" + "="*50)
    print(f"✓ 処理完了: {success_count}/{len(posts)} 件の投稿案を追加しました")
    print("="*50)
    
    return 0 if success_count == len(posts) else 1


if __name__ == "__main__":
    sys.exit(main())
