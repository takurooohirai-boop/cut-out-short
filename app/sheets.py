"""Google Sheets 記録機能"""
from typing import Dict, Any, Optional
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import config
from app.logging_utils import log_info, log_error, log_warning


# Google Sheets API のスコープ
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


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
        range_name: 書き込み先の範囲（デフォルト: Sheet1!A:L）

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
    range_name: str = "Sheet1!C:H"
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
                update_range = f"Sheet1!H{idx}"

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
