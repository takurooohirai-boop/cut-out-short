"""フォルダを準備完了から入力に戻すスクリプト"""
import os
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

def move_folder_back(folder_name: str):
    """フォルダを準備完了フォルダから入力フォルダに移動"""

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    input_folder_id = os.getenv("DRIVE_INPUT_FOLDER_ID")
    ready_folder_id = os.getenv("DRIVE_READY_FOLDER_ID")

    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)

    # 準備完了フォルダ内のフォルダを検索
    results = service.files().list(
        q=f"'{ready_folder_id}' in parents and name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)"
    ).execute()

    folders = results.get("files", [])

    if not folders:
        print(f"Folder '{folder_name}' not found in READY folder")
        return

    folder = folders[0]
    folder_id = folder["id"]

    print(f"Moving folder: {folder['name']} ({folder_id})")

    # 現在の親フォルダを取得
    file = service.files().get(fileId=folder_id, fields='parents').execute()
    previous_parents = ",".join(file.get('parents', []))

    # フォルダを移動（入力フォルダに戻す）
    service.files().update(
        fileId=folder_id,
        addParents=input_folder_id,
        removeParents=previous_parents,
        fields='id, parents'
    ).execute()

    print(f"Successfully moved '{folder_name}' back to INPUT folder")

if __name__ == "__main__":
    # フォルダ「1」を入力フォルダに戻す
    move_folder_back("1")
