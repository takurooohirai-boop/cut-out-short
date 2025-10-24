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
        # 1. Google Driveの入力フォルダをチェック
        log_info(f"Checking Drive folder: {config.DRIVE_INPUT_FOLDER_ID}")
        files = list_files_in_folder(config.DRIVE_INPUT_FOLDER_ID)

        if not files:
            log_info("No files found in input folder. Exiting.")
            return

        log_info(f"Found {len(files)} file(s) to process")

        # 処理するファイルの情報を収集
        for file_info in files:
            try:
                file_id = file_info['id']
                file_name = file_info['name']

                log_info(f"Processing file: {file_name} (ID: {file_id})")

                # 2. ジョブリクエストを作成
                job_request = CreateJobRequest(
                    source_type="drive",
                    drive_file_id=file_id,
                    title_hint=file_name,
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

                log_info(f"Starting job {job_id} for {file_name}")

                await run_job(job_id, job_request, JOBS)

                result = JOBS[job_id]

                if result.status != "done":
                    log_error(f"Job failed: {result.message}")
                    continue

                log_info(f"Job completed: {len(result.outputs)} clips generated")

                # 4. YouTubeに予約投稿（1日1本ペース）
                upload_dates = generate_upload_schedule(
                    start_date=datetime.now() + timedelta(days=1),
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
                        # YouTube予約投稿
                        youtube_url = upload_to_youtube_scheduled(
                            video_path=video_path,
                            title=f"{file_name.replace('.mp4', '')} - Part {idx+1}",
                            description="自動生成されたショート動画\n\n#Shorts",
                            scheduled_time=upload_date,
                            privacy_status="private"
                        )

                        log_info(f"Uploaded to YouTube: {youtube_url}")

                        # 5. Googleスプレッドシートに記録
                        record_to_sheet(
                            data={
                                "date": upload_date.strftime("%Y-%m-%d %H:%M"),
                                "title": f"{file_name.replace('.mp4', '')} - Part {idx+1}",
                                "youtube_url": youtube_url,
                                "duration": output.duration_sec,
                                "segment_start": output.segment.get("start", 0) if output.segment else 0,
                                "segment_end": output.segment.get("end", 0) if output.segment else 0,
                                "method": output.method,
                                "status": "scheduled"
                            }
                        )

                        log_info(f"Recorded to spreadsheet: {youtube_url}")

                    except Exception as e:
                        log_error(f"Failed to upload/record clip {idx+1}: {e}", exc_info=True)
                        continue

                # 6. 処理済みファイルを別フォルダに移動
                if config.DRIVE_READY_FOLDER_ID:
                    log_info(f"Moving {file_name} to processed folder")
                    move_file_to_folder(file_id, config.DRIVE_READY_FOLDER_ID)

                log_info(f"Successfully processed: {file_name}")

            except Exception as e:
                log_error(f"Failed to process {file_info.get('name', 'unknown')}: {e}", exc_info=True)
                continue

        log_info("=== Auto Shorts Scheduler Completed ===")

    except Exception as e:
        log_error(f"Scheduler failed: {e}", exc_info=True)
        raise


def generate_upload_schedule(start_date: datetime, count: int) -> list[datetime]:
    """
    1日1本ペースでYouTube予約投稿の日時を生成

    Args:
        start_date: 最初の投稿日時
        count: 動画本数

    Returns:
        投稿日時のリスト
    """
    # 毎日12:00 JSTに投稿するように調整
    schedule = []
    for i in range(count):
        upload_time = start_date + timedelta(days=i)
        # 時刻を12:00に固定
        upload_time = upload_time.replace(hour=12, minute=0, second=0, microsecond=0)
        schedule.append(upload_time)

    return schedule


if __name__ == "__main__":
    asyncio.run(main())
