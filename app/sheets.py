"""Google Sheets 記録機能 + YouTuber管理"""
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import gspread

from app.config import config
from app.logging_utils import log_info, log_error, log_warning
from app.youtube_channel import YouTuberInfo


# Google Sheets API のスコープ
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


def get_sheets_service():
    """
    Google Sheets API サービスを取得

    Returns:
        Sheets API サービスオブジェクト
    """
    credentials_path = Path(config.GOOGLE_APPLICATION_CREDENTIALS)

    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Google Service Account credentials not found at {credentials_path}. "
            "Please place your service-account.json file there."
        )

    credentials = Credentials.from_service_account_file(
        str(credentials_path),
        scopes=SCOPES
    )

    return build('sheets', 'v4', credentials=credentials)


def get_sheet(spreadsheet_id: Optional[str] = None, worksheet_name: str = "CutoutShort"):
    """
    gspread を使ってワークシートオブジェクトを取得
    
    Args:
        spreadsheet_id: スプレッドシートID（未指定の場合は環境変数から取得）
        worksheet_name: ワークシート名（デフォルト: CutoutShort）
    
    Returns:
        gspread.Worksheet オブジェクト
    """
    if not spreadsheet_id:
        spreadsheet_id = config.SPREADSHEET_ID

    if not spreadsheet_id:
        raise ValueError("Spreadsheet ID is required")

    credentials_path = Path(config.GOOGLE_APPLICATION_CREDENTIALS)

    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Google Service Account credentials not found at {credentials_path}"
        )

    credentials = Credentials.from_service_account_file(
        str(credentials_path),
        scopes=SCOPES
    )

    gc = gspread.authorize(credentials)
    spreadsheet = gc.open_by_key(spreadsheet_id)
    
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.exceptions.WorksheetNotFound:
        # ワークシートが存在しない場合は作成
        log_warning(f"Worksheet '{worksheet_name}' not found, creating new one")
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=12)
        
        # ヘッダーを追加
        headers = [
            '投稿日時', 'タイトル', 'YouTube URL', '動画秒数',
            '開始位置', '終了位置', '抽出方法', 'ステータス',
            'Input Tokens', 'Output Tokens', 'Total Tokens', 'コスト (円)'
        ]
        worksheet.append_row(headers)
        log_info(f"Created new worksheet '{worksheet_name}' with headers")
    
    return worksheet


def record_to_sheet(
    data: Dict[str, Any],
    spreadsheet_id: Optional[str] = None,
    range_name: str = "CutoutShort!A:L"
) -> Dict[str, Any]:
    """
    Googleスプレッドシートに記録を追加

    Args:
        data: 記録するデータ（辞書形式）
        spreadsheet_id: スプレッドシートID（未指定の場合は環境変数から取得）
        range_name: 書き込み先の範囲（デフォルト: CutoutShort!A:L）

    Returns:
        APIレスポンス

    Raises:
        ValueError: spreadsheet_idが指定されていない場合
        HttpError: Google Sheets API エラー
    """
    if not spreadsheet_id:
        spreadsheet_id = config.SPREADSHEET_ID

    if not spreadsheet_id:
        raise ValueError(
            "Spreadsheet ID is required. "
            "Set SPREADSHEET_ID in .env or pass it as an argument."
        )

    log_info(f"Recording to spreadsheet: {spreadsheet_id}")

    try:
        service = get_sheets_service()

        # データを行形式に変換
        values = [[
            data.get('date', ''),
            data.get('title', ''),
            data.get('youtube_url', ''),
            data.get('duration', 0),
            data.get('segment_start', 0),
            data.get('segment_end', 0),
            data.get('method', ''),
            data.get('status', 'pending'),
            data.get('input_tokens', 0),
            data.get('output_tokens', 0),
            data.get('total_tokens', 0),
            f"¥{data.get('cost_jpy', 0.0):.4f}"
        ]]

        body = {
            'values': values
        }

        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()

        log_info(
            f"Recorded to sheet: {result.get('updates', {}).get('updatedRows', 0)} row(s) added"
        )

        return result

    except HttpError as e:
        log_error(f"Google Sheets API error: {e}", exc_info=True)
        raise
    except Exception as e:
        log_error(f"Failed to record to sheet: {e}", exc_info=True)
        raise


def initialize_sheet_headers(
    spreadsheet_id: Optional[str] = None,
    range_name: str = "CutoutShort!A1:L1"
) -> Dict[str, Any]:
    """
    スプレッドシートにヘッダー行を作成

    Args:
        spreadsheet_id: スプレッドシートID
        range_name: ヘッダーを書き込む範囲

    Returns:
        APIレスポンス
    """
    if not spreadsheet_id:
        spreadsheet_id = config.SPREADSHEET_ID

    if not spreadsheet_id:
        raise ValueError("Spreadsheet ID is required")

    log_info(f"Initializing sheet headers: {spreadsheet_id}")

    try:
        service = get_sheets_service()

        headers = [[
            '投稿日時',
            'タイトル',
            'YouTube URL',
            '動画秒数',
            '開始位置',
            '終了位置',
            '抽出方法',
            'ステータス',
            'Input Tokens',
            'Output Tokens',
            'Total Tokens',
            'コスト (円)'
        ]]

        body = {
            'values': headers
        }

        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            body=body
        ).execute()

        log_info("Sheet headers initialized successfully")

        return result

    except HttpError as e:
        log_error(f"Google Sheets API error: {e}", exc_info=True)
        raise
    except Exception as e:
        log_error(f"Failed to initialize headers: {e}", exc_info=True)
        raise


def update_status(
    youtube_url: str,
    new_status: str,
    spreadsheet_id: Optional[str] = None,
    range_name: str = "CutoutShort!C:H"
) -> Optional[Dict[str, Any]]:
    """
    YouTube URLを検索してステータスを更新

    Args:
        youtube_url: 検索するYouTube URL
        new_status: 新しいステータス
        spreadsheet_id: スプレッドシートID
        range_name: 検索範囲

    Returns:
        更新結果（見つからない場合はNone）
    """
    if not spreadsheet_id:
        spreadsheet_id = config.SPREADSHEET_ID

    if not spreadsheet_id:
        raise ValueError("Spreadsheet ID is required")

    log_info(f"Updating status for: {youtube_url} -> {new_status}")

    try:
        service = get_sheets_service()

        # データを取得
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()

        values = result.get('values', [])

        # YouTube URLを検索（C列 = インデックス0）
        for idx, row in enumerate(values, start=2):  # ヘッダー行をスキップ
            if row and len(row) > 0 and row[0] == youtube_url:
                # ステータス列（H列 = 範囲内インデックス5）を更新
                update_range = f"CutoutShort!H{idx}"

                body = {
                    'values': [[new_status]]
                }

                update_result = service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=update_range,
                    valueInputOption='RAW',
                    body=body
                ).execute()

                log_info(f"Status updated for row {idx}")
                return update_result

        log_warning(f"YouTube URL not found in sheet: {youtube_url}")
        return None

    except HttpError as e:
        log_error(f"Google Sheets API error: {e}", exc_info=True)
        raise
    except Exception as e:
        log_error(f"Failed to update status: {e}", exc_info=True)
        raise


# ===========================================
# YouTuber管理機能
# ===========================================

def get_youtubers(
    spreadsheet_id: Optional[str] = None,
    sheet_name: str = "YouTubers"
) -> List[YouTuberInfo]:
    """
    YouTubersシートから有効な契約者リストを取得

    Args:
        spreadsheet_id: スプレッドシートID
        sheet_name: シート名

    Returns:
        YouTuberInfoのリスト
    """
    if not spreadsheet_id:
        spreadsheet_id = config.SPREADSHEET_ID

    if not spreadsheet_id:
        raise ValueError("Spreadsheet ID is required")

    log_info(f"Fetching YouTubers from sheet: {sheet_name}")

    try:
        worksheet = get_sheet(spreadsheet_id, sheet_name)
        all_values = worksheet.get_all_values()

        if len(all_values) <= 1:
            log_info("No YouTubers found in sheet")
            return []

        youtubers = []
        # ヘッダー行をスキップ（index 0）
        for row_idx, row in enumerate(all_values[1:], start=2):
            if len(row) < 6:
                continue

            # 有効フラグをチェック（C列）
            enabled = str(row[2]).upper() in ('TRUE', '1', 'YES', 'はい')

            if not enabled:
                continue

            youtuber = YouTuberInfo(
                name=row[0],
                channel_id=row[1],
                enabled=enabled,
                last_video_id=row[3] if len(row) > 3 and row[3] else None,
                last_processed_date=row[4] if len(row) > 4 and row[4] else None,
                refresh_token=row[5] if len(row) > 5 else "",
                row_index=row_idx
            )

            if youtuber.refresh_token:
                youtubers.append(youtuber)
            else:
                log_warning(f"YouTuber {youtuber.name} has no refresh token, skipping")

        log_info(f"Found {len(youtubers)} active YouTubers")
        return youtubers

    except Exception as e:
        log_error(f"Failed to fetch YouTubers: {e}", exc_info=True)
        raise


def update_youtuber_last_video(
    row_index: int,
    video_id: str,
    spreadsheet_id: Optional[str] = None,
    sheet_name: str = "YouTubers"
) -> None:
    """
    YouTuberの最終処理動画IDと日時を更新

    Args:
        row_index: スプシの行番号
        video_id: 処理した動画ID
        spreadsheet_id: スプレッドシートID
        sheet_name: シート名
    """
    if not spreadsheet_id:
        spreadsheet_id = config.SPREADSHEET_ID

    if not spreadsheet_id:
        raise ValueError("Spreadsheet ID is required")

    log_info(f"Updating last video for row {row_index}: {video_id}")

    try:
        worksheet = get_sheet(spreadsheet_id, sheet_name)

        # D列（最終処理動画ID）とE列（最終処理日）を更新
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        worksheet.update(f"D{row_index}:E{row_index}", [[video_id, now]])

        log_info(f"Updated row {row_index}: video_id={video_id}, date={now}")

    except Exception as e:
        log_error(f"Failed to update YouTuber last video: {e}", exc_info=True)
        raise


def record_upload(
    youtuber_name: str,
    channel_id: str,
    source_video_id: str,
    short_title: str,
    short_url: str,
    spreadsheet_id: Optional[str] = None,
    sheet_name: str = "UploadLog"
) -> None:
    """
    アップロード記録をUploadLogシートに追加

    Args:
        youtuber_name: YouTuber名
        channel_id: チャンネルID
        source_video_id: 元動画のID
        short_title: ショート動画のタイトル
        short_url: ショート動画のURL
        spreadsheet_id: スプレッドシートID
        sheet_name: シート名
    """
    if not spreadsheet_id:
        spreadsheet_id = config.SPREADSHEET_ID

    if not spreadsheet_id:
        raise ValueError("Spreadsheet ID is required")

    log_info(f"Recording upload: {short_title}")

    try:
        worksheet = get_sheet(spreadsheet_id, sheet_name)

        # ヘッダーがなければ追加
        headers = worksheet.row_values(1)
        if not headers:
            worksheet.append_row([
                'アップロード日時',
                'YouTuber名',
                'チャンネルID',
                '元動画ID',
                'ショートタイトル',
                'ショートURL'
            ])

        # 記録を追加
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        worksheet.append_row([
            now,
            youtuber_name,
            channel_id,
            source_video_id,
            short_title,
            short_url
        ])

        log_info(f"Upload recorded: {short_url}")

    except Exception as e:
        log_error(f"Failed to record upload: {e}", exc_info=True)
        raise
