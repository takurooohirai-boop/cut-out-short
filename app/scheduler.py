"""GitHub Actions用の自動実行スケジューラー"""
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional

from app.config import config
from app.logging_utils import log_info, log_error, log_warning
from app.models import CreateJobRequest, JobOptions, Job, JobArtifacts
from app.worker import run_job
from app.drive_io import list_files_in_folder, move_file_to_folder
from app.youtube_upload import upload_to_youtube_scheduled
from app.sheets import record_to_sheet


async def main():
    """メイン処理: Drive監視 → 動画処理 → YouTube予約投稿 → スプシ記録"""
    log_info("=== Auto Shorts Scheduler Started ===")

    try:
        # 0. スプレッドシートのヘッダーを初期化（初回のみ）
        try:
            from app.sheets import initialize_sheet_headers
            log_info("Initializing spreadsheet headers...")
            initialize_sheet_headers()
        except Exception as e:
            # ヘッダーが既に存在する場合などはスキップ
            log_warning(f"Header initialization skipped or failed: {e}")

        # 1. Google Driveの入力フォルダ（フォルダ構造）をチェック
        log_info(f"Checking Drive folder: {config.DRIVE_INPUT_FOLDER_ID}")
        from app.drive_io import get_video_folders_from_input
        video_folders = get_video_folders_from_input()

        if not video_folders:
            log_info("No video folders found in input folder. Exiting.")
            return

        log_info(f"Found {len(video_folders)} video folder(s) to process")

        # 処理するフォルダごとの情報を収集
        for folder_info in video_folders:
            try:
                folder_id = folder_info['folder_id']
                folder_name = folder_info['folder_name']
                video_file_id = folder_info['video_file_id']
                video_file_name = folder_info['video_file_name']
                source_url = folder_info.get('source_url')

                log_info(f"Processing folder: {folder_name} | Video: {video_file_name} | Source: {source_url or 'None'}")

                from app.transcribe import get_video_duration
                from pathlib import Path
                
                # 一時ダウンロードして長さチェック
                temp_check_path = config.get_tmp_path(f"check_{video_file_id}.mp4")
                try:
                    from app.drive_io import download_from_drive
                    download_from_drive(video_file_id, temp_check_path, job_id=None)
                    
                    video_duration = get_video_duration(temp_check_path)
                    
                    # 最小必要秒数（min_sec）より短い場合はスキップ
                    MIN_REQUIRED_DURATION = 30  # 秒
                    if video_duration < MIN_REQUIRED_DURATION:
                        log_warning(f"Video too short ({video_duration:.1f}s < {MIN_REQUIRED_DURATION}s), skipping folder: {folder_name}")
                        
                        # フォルダを処理済みに移動
                        if config.DRIVE_READY_FOLDER_ID:
                            move_file_to_folder(folder_id, config.DRIVE_READY_FOLDER_ID)
                            log_info(f"Moved short video folder to processed: {folder_name}")
                        
                        Path(temp_check_path).unlink(missing_ok=True)
                        continue
                    
                    Path(temp_check_path).unlink(missing_ok=True)
                    
                except Exception as e:
                    log_warning(f"Failed to check video duration: {e}")
                    Path(temp_check_path).unlink(missing_ok=True)
                    
                # 2. ジョブリクエストを作成
                job_request = CreateJobRequest(
                    source_type="drive",
                    drive_file_id=video_file_id,
                    title_hint=folder_name,
                    options=JobOptions(
                        target_count=5,  # 5本生成
                        min_sec=30,
                        max_sec=45
                    )
                )

                # 3. ジョブを実行（同期的に）
                job_id = str(uuid.uuid4())
                JOBS = {}

                job = Job(
                    job_id=job_id,
                    status="queued",
                    progress=0.0,
                    message="Job queued",
                    inputs=job_request,
                    artifacts=JobArtifacts(),
                    outputs=[],
                    trace_id=f"trace-{job_id[:12]}",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    attempt=1
                )

                JOBS[job_id] = job

                log_info(f"Starting job {job_id} for {folder_name}")

                await run_job(job_id, job_request, JOBS)

                result = JOBS[job_id]

                if result.status != "done":
                    log_error(f"Job failed: {result.message}")
                    continue

                log_info(f"Job completed: {len(result.outputs)} clips generated")

                # 4. YouTubeに予約投稿（既存予約と被らないように）
                upload_dates = generate_upload_schedule(
                    start_date=datetime.now(),
                    count=len(result.outputs)
                )

                for idx, (output, upload_date) in enumerate(zip(result.outputs, upload_dates)):
                    video_file = output.file_name

                    if not video_file:
                        log_warning(f"No file_name in output {idx+1}, skipping")
                        continue

                    # フルパスを取得（file_nameがファイル名のみの場合はTMP_DIRと結合）
                    from pathlib import Path
                    video_path_obj = Path(video_file)

                    # 絶対パスでない場合はTMP_DIRからの相対パスとして扱う
                    if not video_path_obj.is_absolute():
                        video_path_obj = Path(config.TMP_DIR) / video_file

                    video_path = str(video_path_obj.resolve())

                    log_info(f"Scheduling upload {idx+1}/{len(result.outputs)}: {video_path} at {upload_date}")

                    try:
                        # AI生成タイトルと説明文を作成
                        from app.content_generator import generate_title_and_description

                        # セグメントの文字起こしテキストを取得
                        segment_start = output.segment.get("start", 0) if output.segment else 0
                        segment_end = output.segment.get("end", 0) if output.segment else 0

                        # SRTファイルから該当セグメントのテキストを抽出
                        segment_text = _extract_segment_transcript(
                            result.artifacts.srt_path,
                            segment_start,
                            segment_end
                        )

                        # AI生成
                        content = generate_title_and_description(
                            transcript_text=segment_text,
                            source_url=source_url,
                            fallback_title=f"{folder_name} - Part {idx+1}"
                        )

                        title = content["title"]
                        description = content["description"]

                        log_info(f"Generated title: {title}")

                        # YouTube予約投稿
                        youtube_url = upload_to_youtube_scheduled(
                            video_path=video_path,
                            title=title,
                            description=description,
                            scheduled_time=upload_date,
                            privacy_status="private"
                        )

                        log_info(f"Uploaded to YouTube: {youtube_url}")

                        # 5. Googleスプレッドシートに記録
                        record_to_sheet(
                            data={
                                "date": upload_date.strftime("%Y-%m-%d %H:%M"),
                                "title": title,
                                "youtube_url": youtube_url,
                                "duration": output.duration_sec,
                                "segment_start": segment_start,
                                "segment_end": segment_end,
                                "method": output.method,
                                "status": "scheduled",
                                "input_tokens": content.get("input_tokens", 0),
                                "output_tokens": content.get("output_tokens", 0),
                                "total_tokens": content.get("total_tokens", 0),
                                "cost_jpy": content.get("cost_jpy", 0.0)
                            }
                        )

                        log_info(f"Recorded to spreadsheet: {youtube_url}")

                    except Exception as e:
                        log_error(f"Failed to upload/record clip {idx+1}: {e}", exc_info=True)
                        continue

                # 6. 処理済みフォルダを別フォルダに移動
                if config.DRIVE_READY_FOLDER_ID:
                    log_info(f"Moving folder {folder_name} to processed folder")
                    move_file_to_folder(folder_id, config.DRIVE_READY_FOLDER_ID)

                log_info(f"Successfully processed: {folder_name}")

            except Exception as e:
                log_error(f"Failed to process folder {folder_info.get('folder_name', 'unknown')}: {e}", exc_info=True)
                continue

        log_info("=== Auto Shorts Scheduler Completed ===")

    except Exception as e:
        log_error(f"Scheduler failed: {e}", exc_info=True)
        raise


def generate_upload_schedule(start_date: datetime, count: int) -> list[datetime]:
    """
    1日1本ペースでYouTube予約投稿の日時を生成
    既存の予約と被らないように調整

    Args:
        start_date: 基準日時（通常は現在時刻）
        count: 動画本数

    Returns:
        投稿日時のリスト
    """
    from app.sheets import get_sheet
    
    try:
        # スプレッドシートから既存の予約を取得
        sheet = get_sheet()
        last_scheduled = get_last_scheduled_date(sheet)
        
        # 最後の予約の翌日から開始
        if last_scheduled > start_date:
            start_date = last_scheduled
        
        log_info(f"Scheduling starts from: {start_date}")
        
    except Exception as e:
        log_warning(f"Failed to get existing schedules, using start_date as base: {e}")
    
    # スケジュールを生成
    schedule = []
    for i in range(count):
        upload_time = start_date + timedelta(days=i + 1)  # 翌日から開始
        # 時刻を12:00に固定
        upload_time = upload_time.replace(hour=12, minute=0, second=0, microsecond=0)
        schedule.append(upload_time)

    return schedule


def get_last_scheduled_date(sheet):
    """
    スプレッドシートから最後の予約日時を取得
    予約がない場合は現在時刻を返す
    """
    try:
        all_records = sheet.get_all_records()
        
        scheduled_dates = []
        for record in all_records:
            date_str = record.get('date', '')
            if date_str and date_str != '':
                try:
                    # "YYYY-MM-DD HH:MM" 形式をパース
                    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                    scheduled_dates.append(dt)
                except Exception as e:
                    log_warning(f"Failed to parse date: {date_str}, error: {e}")
        
        if scheduled_dates:
            last_date = max(scheduled_dates)
            log_info(f"Last scheduled date found: {last_date}")
            return last_date
        else:
            log_info("No existing schedules found, starting from now")
            return datetime.now()
    
    except Exception as e:
        log_warning(f"Failed to get last scheduled date: {e}")
        return datetime.now()


def _extract_segment_transcript(srt_path: str, start_sec: float, end_sec: float) -> str:
    """
    SRTファイルから指定時間範囲のテキストを抽出

    Args:
        srt_path: SRTファイルパス
        start_sec: 開始時刻（秒）
        end_sec: 終了時刻（秒）

    Returns:
        該当範囲のテキスト
    """
    try:
        import re
        from pathlib import Path

        if not Path(srt_path).exists():
            log_warning(f"SRT file not found: {srt_path}")
            return ""

        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # SRT形式のパース
        pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\Z)'
        matches = re.findall(pattern, content, re.DOTALL)

        def srt_time_to_seconds(time_str: str) -> float:
            """SRT時刻を秒に変換"""
            h, m, s = time_str.split(':')
            s, ms = s.split(',')
            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

        # 該当範囲のテキストを収集
        texts = []
        for _, start_time, end_time, text in matches:
            start = srt_time_to_seconds(start_time)
            end = srt_time_to_seconds(end_time)

            # 範囲内のテキストのみ追加
            if start >= start_sec and end <= end_sec:
                texts.append(text.strip())

        return ' '.join(texts)

    except Exception as e:
        log_error(f"Failed to extract segment transcript: {e}", exc_info=True)
        return ""


if __name__ == "__main__":
    asyncio.run(main())
