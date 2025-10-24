"""YouTube認証テスト"""
from datetime import datetime, timedelta
from app.youtube_upload import upload_to_youtube_scheduled

# テスト用の動画ファイル（既に生成済み）
test_video = "runout/20251024_234405_01.mp4"

# 明日の12:00に予約
scheduled_time = datetime.now() + timedelta(days=1)
scheduled_time = scheduled_time.replace(hour=12, minute=0, second=0, microsecond=0)

print(f"Testing YouTube authentication...")
print(f"Video: {test_video}")
print(f"Scheduled time: {scheduled_time}")

try:
    youtube_url = upload_to_youtube_scheduled(
        video_path=test_video,
        title="Test Upload - Short Video",
        description="Test upload for authentication\n\n#Shorts",
        scheduled_time=scheduled_time,
        privacy_status="private"
    )

    print(f"\n✅ Success!")
    print(f"YouTube URL: {youtube_url}")
    print(f"Scheduled for: {scheduled_time}")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
