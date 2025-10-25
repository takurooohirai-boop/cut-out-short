
def read_google_doc_content(doc_id: str, job_id: Optional[str] = None) -> str:
    """
    Googleドキュメントの内容を読み取る

    Args:
        doc_id: GoogleドキュメントのID
        job_id: ジョブID（ログ用）

    Returns:
        ドキュメントの内容（プレーンテキスト）
    """
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
        
        credentials = service_account.Credentials.from_service_account_file(
            config.GOOGLE_APPLICATION_CREDENTIALS,
            scopes=["https://www.googleapis.com/auth/documents.readonly"]
        )
        docs_service = build("docs", "v1", credentials=credentials, cache_discovery=False)
        
        document = docs_service.documents().get(documentId=doc_id).execute()
        
        # ドキュメントの内容を抽出
        content = []
        for element in document.get('body', {}).get('content', []):
            if 'paragraph' in element:
                for text_run in element['paragraph'].get('elements', []):
                    if 'textRun' in text_run:
                        content.append(text_run['textRun'].get('content', ''))
        
        text = ''.join(content).strip()
        log_info(f"Read Google Doc content: {len(text)} characters", job_id=job_id)
        return text
        
    except Exception as e:
        log_warning(f"Failed to read Google Doc: {e}", job_id=job_id)
        return ""


def get_video_folders_from_input(job_id: Optional[str] = None) -> list[dict]:
    """
    入力フォルダ内の動画フォルダ一覧を取得

    Returns:
        [
            {
                "folder_id": "フォルダID",
                "folder_name": "フォルダ名",
                "video_file_id": "動画ファイルID",
                "video_file_name": "動画ファイル名",
                "source_url": "元動画URL（オプション）"
            },
            ...
        ]
    """
    try:
        service = _get_drive_service()
        
        # 入力フォルダ内のフォルダ一覧を取得
        results = service.files().list(
            q=f"'{config.DRIVE_INPUT_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)",
            orderBy="createdTime desc"
        ).execute()
        
        folders = results.get("files", [])
        log_info(f"Found {len(folders)} folders in input folder", job_id=job_id)
        
        video_folders = []
        
        for folder in folders:
            folder_id = folder['id']
            folder_name = folder['name']
            
            # フォルダ内のファイルを取得
            files_in_folder = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType)"
            ).execute().get("files", [])
            
            # MP4ファイルを探す
            video_file = next(
                (f for f in files_in_folder if f.get('name', '').lower().endswith('.mp4')),
                None
            )
            
            if not video_file:
                log_warning(f"No MP4 file found in folder: {folder_name}", job_id=job_id)
                continue
            
            # Googleドキュメントを探す
            google_doc = next(
                (f for f in files_in_folder if f.get('mimeType') == 'application/vnd.google-apps.document'),
                None
            )
            
            source_url = None
            if google_doc:
                # ドキュメントの内容を読み取ってURLを抽出
                doc_content = read_google_doc_content(google_doc['id'], job_id=job_id)
                
                # YouTube URLを正規表現で抽出
                import re
                url_pattern = r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+'
                urls = re.findall(url_pattern, doc_content)
                if urls:
                    source_url = urls[0]
                    log_info(f"Found source URL in {folder_name}: {source_url}", job_id=job_id)
            
            video_folders.append({
                "folder_id": folder_id,
                "folder_name": folder_name,
                "video_file_id": video_file['id'],
                "video_file_name": video_file['name'],
                "source_url": source_url
            })
        
        return video_folders
        
    except Exception as e:
        log_error(f"Failed to get video folders: {e}", job_id=job_id, exc_info=True)
        return []
