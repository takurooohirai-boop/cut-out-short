"""マルチYouTuber対応スケジューラー

各YouTuberのチャンネルから最新動画を取得し、
ショート動画を生成して本人のチャンネルにアップロードする。
"""

import asyncio
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import config
from app.logging_utils import log_info, log_error, log_warning
from app.models import CreateJobRequest, JobOptions, Job, JobArtifacts
from app.worker import run_job
from app.sheets import (
    get_youtubers,
    update_youtuber_last_video,
    record_upload
)
from app.youtube_channel import (
    get_latest_video,
    refresh_access_token,
    get_video_url,
    download_thumbnail,
    VideoInfo,
    YouTuberInfo
)


# YouTube API Key（チャンネル情報取得用、Gemini APIと共通）
YOUTUBE_API_KEY = os.getenv("GEMINI_API_KEY", "")

# OAuth クライアント情報
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")


async def main():
    """
    メイン処理:
    1. スプシからYouTuberリストを取得
    2. 各YouTuberの最新動画をチェック
    3. 新しい動画があればショート化
    4. 本人のチャンネルにアップロード
    """
    log_info("=== Multi-YouTuber Auto Shorts Scheduler Started ===")

    if not YOUTUBE_API_KEY:
        log_error("GEMINI_API_KEY (YouTube API Key) is not set")
        return

    if not YOUTUBE_CLIENT_ID or not YOUTUBE_CLIENT_SECRET:
        log_error("YOUTUBE_CLIENT_ID or YOUTUBE_CLIENT_SECRET is not set")
        return

    try:
        # 1. スプシからYouTuberリストを取得
        youtubers = get_youtubers()

        if not youtubers:
            log_info("No active YouTubers found. Exiting.")
            return

        log_info(f"Found {len(youtubers)} active YouTuber(s)")

        # 2. 各YouTuberを処理
        for youtuber in youtubers:
            try:
                await process_youtuber(youtuber)
            except Exception as e:
                log_error(
                    f"Failed to process YouTuber {youtuber.name}: {e}",
                    exc_info=True
                )
                continue

        log_info("=== Multi-YouTuber Auto Shorts Scheduler Completed ===")

    except Exception as e:
        log_error(f"Scheduler failed: {e}", exc_info=True)
        raise


async def process_youtuber(youtuber: YouTuberInfo):
    """
    1人のYouTuberを処理

    Args:
        youtuber: YouTuber情報
    """
    log_info(f"Processing YouTuber: {youtuber.name} ({youtuber.channel_id})")

    # 1. 最新動画を取得
    latest_video = get_latest_video(youtuber.channel_id, YOUTUBE_API_KEY)

    if not latest_video:
        log_warning(f"No videos found for {youtuber.name}")
        return

    log_info(f"Latest video: {latest_video.title} ({latest_video.video_id})")

    # 2. 既に処理済みかチェック
    if youtuber.last_video_id == latest_video.video_id:
        log_info(f"Video already processed: {latest_video.video_id}")
        return

    # 3. 動画をダウンロードしてショート化
    output_files = await create_shorts_from_video(
        video_info=latest_video,
        youtuber_name=youtuber.name
    )

    if not output_files:
        log_warning(f"No shorts created for {youtuber.name}")
        return

    # 4. アクセストークンを取得
    access_token = refresh_access_token(
        youtuber.refresh_token,
        YOUTUBE_CLIENT_ID,
        YOUTUBE_CLIENT_SECRET
    )

    if not access_token:
        log_error(f"Failed to get access token for {youtuber.name}")
        return

    # 5. ショート動画をアップロード（1本だけ）
    # 複数本アップする場合は予約投稿にする
    try:
        short_url = await upload_short(
            video_path=output_files[0]["path"],
            title=output_files[0]["title"],
            description=output_files[0]["description"],
            access_token=access_token
        )

        if short_url:
            log_info(f"Uploaded short: {short_url}")

            # 6. スプシに記録
            record_upload(
                youtuber_name=youtuber.name,
                channel_id=youtuber.channel_id,
                source_video_id=latest_video.video_id,
                short_title=output_files[0]["title"],
                short_url=short_url
            )

            # 7. 最終処理動画IDを更新
            update_youtuber_last_video(
                row_index=youtuber.row_index,
                video_id=latest_video.video_id
            )

    except Exception as e:
        log_error(f"Failed to upload short for {youtuber.name}: {e}", exc_info=True)


async def create_shorts_from_video(
    video_info: VideoInfo,
    youtuber_name: str
) -> list[dict]:
    """
    動画からショート動画を生成

    Args:
        video_info: 動画情報
        youtuber_name: YouTuber名

    Returns:
        生成されたショート動画のリスト
        [{"path": str, "title": str, "description": str}, ...]
    """
    log_info(f"Creating shorts from: {video_info.title}")

    # YouTube URLを生成
    video_url = get_video_url(video_info.video_id)

    # ジョブリクエストを作成
    job_request = CreateJobRequest(
        source_type="youtube_url",
        youtube_url=video_url,
        title_hint=video_info.title,
        options=JobOptions(
            target_count=1,  # 1本だけ生成（API Quota節約）
            min_sec=30,
            max_sec=45
        )
    )

    # ジョブを実行
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

    log_info(f"Starting job {job_id}")

    await run_job(job_id, job_request, JOBS)

    result = JOBS[job_id]

    if result.status != "done":
        log_error(f"Job failed: {result.message}")
        return []

    log_info(f"Job completed: {len(result.outputs)} clips generated")

    # 出力ファイルの情報を収集
    output_files = []

    for idx, output in enumerate(result.outputs):
        video_file = output.file_name
        if not video_file:
            continue

        video_path = Path(video_file)
        if not video_path.is_absolute():
            video_path = Path(config.TMP_DIR) / video_file

        # AI生成タイトルと説明文
        from app.content_generator import generate_title_and_description
        from app.scheduler import _extract_segment_transcript

        segment_start = output.segment.get("start", 0) if output.segment else 0
        segment_end = output.segment.get("end", 0) if output.segment else 0

        segment_text = _extract_segment_transcript(
            result.artifacts.srt_path,
            segment_start,
            segment_end
        )

        content = generate_title_and_description(
            transcript_text=segment_text,
            source_url=video_url,
            fallback_title=f"{video_info.title} - Short {idx+1}"
        )

        output_files.append({
            "path": str(video_path.resolve()),
            "title": content["title"],
            "description": content["description"]
        })

    return output_files


async def upload_short(
    video_path: str,
    title: str,
    description: str,
    access_token: str
) -> Optional[str]:
    """
    ショート動画をYouTubeにアップロード

    Args:
        video_path: 動画ファイルパス
        title: タイトル
        description: 説明文
        access_token: アクセストークン

    Returns:
        アップロードされた動画のURL
    """
    from app.youtube_upload import upload_video

    try:
        video_id = upload_video(
            video_path=video_path,
            title=title,
            description=description,
            access_token=access_token,
            privacy_status="public",  # 公開
            is_short=True
        )

        if video_id:
            return f"https://youtube.com/shorts/{video_id}"

    except Exception as e:
        log_error(f"Upload failed: {e}", exc_info=True)

    return None


if __name__ == "__main__":
    asyncio.run(main())
