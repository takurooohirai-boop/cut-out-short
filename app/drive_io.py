"""Google Drive ダウンロード/アップロード機能"""
import time
from pathlib import Path
from typing import Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

from app.config import config
from app.logging_utils import log_info, log_error, log_warning


class DriveIOError(Exception):
    """Drive I/O 例外"""
    pass


def _get_drive_service():
    """Google Drive APIサービスを取得"""
    if not config.GOOGLE_APPLICATION_CREDENTIALS:
        raise DriveIOError("GOOGLE_APPLICATION_CREDENTIALS is not set")

    credentials = service_account.Credentials.from_service_account_file(
        config.GOOGLE_APPLICATION_CREDENTIALS,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    return service


def download_from_drive(
    file_id: str,
    output_path: str,
    job_id: Optional[str] = None
) -> str:
    """
    Google Driveからファイルをダウンロード

    Args:
        file_id: DriveファイルID
        output_path: 保存先パス
        job_id: ジョブID（ログ用）

    Returns:
        保存先パス

    Raises:
        DriveIOError: ダウンロード失敗時
    """
    log_info(f"Downloading from Drive: {file_id}", job_id=job_id, stage="downloading")

    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            service = _get_drive_service()

            # ファイルメタデータ取得
            file_metadata = service.files().get(fileId=file_id, fields="name,mimeType,size").execute()
            file_name = file_metadata.get("name", "unknown")
            file_size = int(file_metadata.get("size", 0))

            log_info(
                f"File metadata: {file_name} ({file_size} bytes)",
                job_id=job_id,
                meta={"file_name": file_name, "size": file_size}
            )

            # ダウンロード
            request = service.files().get_media(fileId=file_id)
            fh = io.FileIO(output_path, "wb")
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    if progress % 20 == 0:  # 20%ごとにログ
                        log_info(f"Download progress: {progress}%", job_id=job_id)

            fh.close()

            log_info(f"Download completed: {output_path}", job_id=job_id)
            return output_path

        except Exception as e:
            log_error(
                f"Download attempt {attempt}/{config.MAX_RETRIES} failed: {e}",
                job_id=job_id,
                exc_info=True
            )

            if attempt < config.MAX_RETRIES:
                sleep_time = config.RETRY_BACKOFF_BASE ** attempt
                log_warning(f"Retrying in {sleep_time}s...", job_id=job_id)
                time.sleep(sleep_time)
            else:
                raise DriveIOError(f"Failed to download file after {config.MAX_RETRIES} attempts: {e}") from e

    raise DriveIOError("Unexpected error in download_from_drive")


def upload_to_drive(
    local_path: str,
    folder_id: Optional[str] = None,
    job_id: Optional[str] = None
) -> str:
    """
    ファイルをGoogle Driveにアップロード

    Args:
        local_path: ローカルファイルパス
        folder_id: アップロード先フォルダID（Noneの場合はDRIVE_READY_FOLDER_ID使用）
        job_id: ジョブID（ログ用）

    Returns:
        共有リンクURL

    Raises:
        DriveIOError: アップロード失敗時
    """
    if folder_id is None:
        folder_id = config.DRIVE_READY_FOLDER_ID

    file_name = Path(local_path).name
    log_info(f"Uploading to Drive: {file_name}", job_id=job_id, stage="uploading")

    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            service = _get_drive_service()

            # ファイルメタデータ
            # writersCanShareをTrueにして、Service Accountでもアップロード可能に
            file_metadata = {
                "name": file_name,
                "parents": [folder_id],
                "writersCanShare": True
            }

            # メディアアップロード
            media = MediaFileUpload(
                local_path,
                mimetype="video/mp4",
                resumable=True
            )

            # アップロード実行
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id,name,webViewLink",
                supportsAllDrives=True
            ).execute()

            file_id = file.get("id")
            web_link = file.get("webViewLink")

            log_info(
                f"Upload completed: {file_name}",
                job_id=job_id,
                meta={"file_id": file_id, "web_link": web_link}
            )

            # 共有リンクを有効化（誰でも閲覧可能）
            try:
                service.permissions().create(
                    fileId=file_id,
                    body={"type": "anyone", "role": "reader"},
                    supportsAllDrives=True
                ).execute()
                log_info(f"Sharing enabled for {file_name}", job_id=job_id)
            except Exception as e:
                log_warning(f"Failed to enable sharing: {e}", job_id=job_id)

            return web_link or f"https://drive.google.com/file/d/{file_id}/view"

        except Exception as e:
            log_error(
                f"Upload attempt {attempt}/{config.MAX_RETRIES} failed: {e}",
                job_id=job_id,
                exc_info=True
            )

            if attempt < config.MAX_RETRIES:
                sleep_time = config.RETRY_BACKOFF_BASE ** attempt
                log_warning(f"Retrying in {sleep_time}s...", job_id=job_id)
                time.sleep(sleep_time)
            else:
                raise DriveIOError(f"Failed to upload file after {config.MAX_RETRIES} attempts: {e}") from e

    raise DriveIOError("Unexpected error in upload_to_drive")


def list_files_in_folder(
    folder_id: str,
    job_id: Optional[str] = None
) -> list[dict]:
    """
    フォルダ内のファイル一覧を取得（デバッグ用）

    Args:
        folder_id: フォルダID
        job_id: ジョブID（ログ用）

    Returns:
        ファイル情報のリスト
    """
    try:
        service = _get_drive_service()
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id, name, mimeType, createdTime)"
        ).execute()
        files = results.get("files", [])
        log_info(f"Found {len(files)} files in folder {folder_id}", job_id=job_id)
        return files
    except Exception as e:
        log_error(f"Failed to list files: {e}", job_id=job_id, exc_info=True)
        return []


def move_file_to_folder(
    file_id: str,
    folder_id: str,
    job_id: Optional[str] = None
) -> None:
    """
    ファイルを別のフォルダに移動

    Args:
        file_id: 移動するファイルのID
        folder_id: 移動先フォルダID
        job_id: ジョブID（ログ用）

    Raises:
        DriveIOError: 移動失敗時
    """
    try:
        service = _get_drive_service()

        # 現在の親フォルダを取得
        file = service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents', []))

        # ファイルを移動（親フォルダを変更）
        service.files().update(
            fileId=file_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()

        log_info(f"Moved file {file_id} to folder {folder_id}", job_id=job_id)

    except Exception as e:
        log_error(f"Failed to move file: {e}", job_id=job_id, exc_info=True)
        raise DriveIOError(f"Failed to move file: {e}") from e
