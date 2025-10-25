"""Drive フォルダ診断スクリプト"""
import os
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

def check_drive_folders():
    """Drive フォルダの内容を確認"""

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    input_folder_id = os.getenv("DRIVE_INPUT_FOLDER_ID")
    ready_folder_id = os.getenv("DRIVE_READY_FOLDER_ID")

    print(f"認証ファイル: {credentials_path}")
    print(f"入力フォルダID: {input_folder_id}")
    print(f"準備完了フォルダID: {ready_folder_id}")
    print()

    # Drive API接続
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)

    # 入力フォルダの内容を確認
    print("=" * 80)
    print("【入力フォルダの内容】")
    print("=" * 80)

    results = service.files().list(
        q=f"'{input_folder_id}' in parents and trashed=false",
        fields="files(id, name, mimeType, createdTime)",
        orderBy="createdTime desc"
    ).execute()

    files = results.get("files", [])
    print(f"合計: {len(files)} 個のファイル/フォルダ")
    print()

    if not files:
        print("⚠️ 入力フォルダは空です！")
    else:
        for f in files:
            print(f"名前: {f['name']}")
            print(f"  ID: {f['id']}")
            print(f"  種類: {f['mimeType']}")
            print(f"  作成日時: {f['createdTime']}")

            # フォルダの場合は中身も確認
            if f['mimeType'] == 'application/vnd.google-apps.folder':
                folder_contents = service.files().list(
                    q=f"'{f['id']}' in parents and trashed=false",
                    fields="files(id, name, mimeType)"
                ).execute().get("files", [])

                print(f"  📁 フォルダ内容: {len(folder_contents)} 個")
                for item in folder_contents:
                    print(f"    - {item['name']} ({item['mimeType']})")
            print()

    # 準備完了フォルダの内容を確認
    print("=" * 80)
    print("【準備完了フォルダの内容】")
    print("=" * 80)

    results = service.files().list(
        q=f"'{ready_folder_id}' in parents and trashed=false",
        fields="files(id, name, mimeType, createdTime)",
        orderBy="createdTime desc"
    ).execute()

    files = results.get("files", [])
    print(f"合計: {len(files)} 個のファイル/フォルダ")
    print()

    if not files:
        print("準備完了フォルダは空です")
    else:
        for f in files:
            print(f"名前: {f['name']}")
            print(f"  ID: {f['id']}")
            print(f"  種類: {f['mimeType']}")
            print(f"  作成日時: {f['createdTime']}")

            # フォルダの場合は中身も確認
            if f['mimeType'] == 'application/vnd.google-apps.folder':
                folder_contents = service.files().list(
                    q=f"'{f['id']}' in parents and trashed=false",
                    fields="files(id, name, mimeType)"
                ).execute().get("files", [])

                print(f"  📁 フォルダ内容: {len(folder_contents)} 個")
                for item in folder_contents:
                    print(f"    - {item['name']} ({item['mimeType']})")
            print()

    # 診断結果
    print("=" * 80)
    print("【診断結果】")
    print("=" * 80)

    input_results = service.files().list(
        q=f"'{input_folder_id}' in parents and trashed=false",
        fields="files(id, name, mimeType)"
    ).execute()

    input_files = input_results.get("files", [])
    input_folders = [f for f in input_files if f['mimeType'] == 'application/vnd.google-apps.folder']

    if not input_folders:
        print("❌ 入力フォルダに処理対象のフォルダがありません")
        print()
        print("次のステップ:")
        print("1. 入力フォルダにフォルダを作成")
        print("2. フォルダ内にMP4ファイルをアップロード")
        print("3. （オプション）Googleドキュメントで元動画URLを記載")
    else:
        print(f"✅ {len(input_folders)} 個のフォルダが見つかりました")

        # 各フォルダの詳細チェック
        for folder in input_folders:
            folder_id = folder['id']
            folder_name = folder['name']

            folder_contents = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType)"
            ).execute().get("files", [])

            mp4_files = [f for f in folder_contents if f.get('name', '').lower().endswith('.mp4')]
            google_docs = [f for f in folder_contents if f.get('mimeType') == 'application/vnd.google-apps.document']

            print(f"\nフォルダ: {folder_name}")
            if mp4_files:
                print(f"  ✅ MP4ファイル: {mp4_files[0]['name']}")
            else:
                print(f"  ❌ MP4ファイルなし")

            if google_docs:
                print(f"  ✅ Googleドキュメント: {google_docs[0]['name']}")
            else:
                print(f"  ⚠️ Googleドキュメントなし（オプション）")

            if mp4_files:
                print(f"  ➡️ このフォルダは処理可能です")
            else:
                print(f"  ❌ MP4ファイルがないため処理できません")

if __name__ == "__main__":
    check_drive_folders()
