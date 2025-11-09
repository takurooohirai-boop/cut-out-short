"""YouTube API 予約投稿機能"""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from app.logging_utils import log_info, log_error, log_warning
from app.config import config


# YouTube API のスコープ
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']


def get_authenticated_service():
    """
    YouTube API の認証済みサービスを取得

    Returns:
        YouTube API サービスオブジェクト
    """
    creds = None
    token_path = Path("./credentials/youtube-token.json")
    client_secret_path = Path("./credentials/youtube-client-secret.json")

    # トークンが存在する場合は読み込む
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # 認証情報が無効または存在しない場合
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log_info("Refreshing YouTube API token")
            creds.refresh(Request())
        else:
            if not client_secret_path.exists():
                raise FileNotFoundError(
                    f"YouTube client secret not found at {client_secret_path}. "
                    "Please download it from Google Cloud Console."
                )

            log_info("Starting YouTube OAuth flow")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secret_path), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # トークンを保存
        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
        log_info(f"Saved YouTube token to {token_path}")

    return build('youtube', 'v3', credentials=creds)


def upload_to_youtube_scheduled(
    video_path: str,
    title: str,
    description: str,
    scheduled_time: datetime,
    privacy_status: str = "private",
    category_id: str = "22",
    tags: Optional[list[str]] = None
) -> str:
    """
    YouTubeに動画を予約投稿

    Args:
        video_path: 動画ファイルパス
        title: 動画タイトル
        description: 説明文
        scheduled_time: 公開予定日時（UTC）
        privacy_status: プライバシー設定 (public/private/unlisted)
        category_id: カテゴリID (デフォルト: 22 = People & Blogs)
        tags: タグリスト

    Returns:
        YouTube動画URL

    Raises:
        FileNotFoundError: 動画ファイルが見つからない場合
        HttpError: YouTube API エラー
    """
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    log_info(f"Uploading to YouTube: {title}")

    try:
        youtube = get_authenticated_service()

        # 動画メタデータ
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags or ['shorts', 'auto-generated'],
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': privacy_status,
                'publishAt': scheduled_time.isoformat() + 'Z',  # ISO 8601 UTC
                'selfDeclaredMadeForKids': False
            }
        }

        # アップロード
        media = MediaFileUpload(
            video_path,
            chunksize=-1,  # 一括アップロード
            resumable=True,
            mimetype='video/mp4'
        )

        log_info(f"Starting upload to YouTube...")

        request = youtube.videos().insert(
            part='snippet,status',
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                log_info(f"Upload progress: {int(status.progress() * 100)}%")

        video_id = response['id']
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        log_info(f"Upload complete: {video_url}")
        log_info(f"Scheduled for: {scheduled_time.isoformat()}")

        return video_url

    except HttpError as e:
        log_error(f"YouTube API error: {e}", exc_info=True)
        raise
    except Exception as e:
        log_error(f"Upload failed: {e}", exc_info=True)
        raise


def upload_to_youtube_immediate(
    video_path: str,
    title: str,
    description: str,
    privacy_status: str = "public",
    category_id: str = "22",
    tags: Optional[list[str]] = None
) -> str:
    """
    YouTubeに動画を即座に公開

    Args:
        video_path: 動画ファイルパス
        title: 動画タイトル
        description: 説明文
        privacy_status: プライバシー設定
        category_id: カテゴリID
        tags: タグリスト

    Returns:
        YouTube動画URL
    """
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    log_info(f"Uploading to YouTube (immediate): {title}")

    try:
        youtube = get_authenticated_service()

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags or ['shorts', 'auto-generated'],
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False
            }
        }

        media = MediaFileUpload(
            video_path,
            chunksize=-1,
            resumable=True,
            mimetype='video/mp4'
        )

        request = youtube.videos().insert(
            part='snippet,status',
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                log_info(f"Upload progress: {int(status.progress() * 100)}%")

        video_id = response['id']
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        log_info(f"Upload complete: {video_url}")

        return video_url

    except HttpError as e:
        log_error(f"YouTube API error: {e}", exc_info=True)
        raise
    except Exception as e:
        log_error(f"Upload failed: {e}", exc_info=True)
        raise
