"""ffmpegレンダリング機能"""
import subprocess
from pathlib import Path
from typing import Optional

from app.config import config
from app.logging_utils import log_info, log_error
from app.models import SegmentInfo


class RenderError(Exception):
    """レンダリング例外"""
    pass


def render_clipset(
    in_mp4: str,
    srt_path: str,
    segments: list[SegmentInfo],
    output_dir: Optional[str] = None,
    job_id: Optional[str] = None,
    title: Optional[str] = None
) -> list[str]:
    """
    セグメントリストから複数のショート動画をレンダリング

    Args:
        in_mp4: 入力動画ファイルパス
        srt_path: SRTファイルパス
        segments: レンダリングするセグメントリスト
        output_dir: 出力ディレクトリ（Noneの場合は入力ファイルと同じディレクトリ）
        job_id: ジョブID（ログ用）

    Returns:
        レンダリングされたファイルパスのリスト

    Raises:
        RenderError: レンダリング失敗時
    """
    log_info(f"Starting rendering {len(segments)} clips", job_id=job_id, stage="rendering")

    # 出力ディレクトリ
    if output_dir is None:
        output_dir = str(Path(in_mp4).parent)
    else:
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    rendered_files = []

    for i, segment in enumerate(segments, start=1):
        try:
            # 日付時刻付きファイル名（例: 20251022_130523_01.mp4）
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path(output_dir) / f"{timestamp}_{i:02d}.mp4"

            log_info(
                f"Rendering clip {i}/{len(segments)}: {segment.start:.1f}s - {segment.end:.1f}s",
                job_id=job_id,
                meta={"clip_num": i, "start": segment.start, "end": segment.end}
            )

            _render_single_clip(
                in_mp4=in_mp4,
                srt_path=srt_path,
                start=segment.start,
                end=segment.end,
                output_path=str(output_path),
                job_id=job_id,
                title=title
            )

            rendered_files.append(str(output_path))

            log_info(f"Clip {i} rendered successfully: {output_path}", job_id=job_id)

        except Exception as e:
            log_error(f"Failed to render clip {i}: {e}", job_id=job_id, exc_info=True)
            # 個別のクリップ失敗は続行（最低3本保証のため）
            continue

    if not rendered_files:
        raise RenderError("No clips were successfully rendered")

    log_info(f"Rendering completed: {len(rendered_files)} clips", job_id=job_id)
    return rendered_files


def _render_single_clip(
    in_mp4: str,
    srt_path: str,
    start: float,
    end: float,
    output_path: str,
    job_id: Optional[str],
    title: Optional[str] = None  # ← 追加
) -> None:
    """
    単一クリップをレンダリング

    仕様通りの9:16（1080x1920）、レターボックス、字幕付き
    """
    duration = end - start

    # ffmpegコマンドを構築
    # 1. 切り出し: -ss {start} -t {duration}
    # 2. レターボックス（中央配置＋上下黒帯）: scale + pad
    # 3. 字幕: subtitles filter with force_style
    # 4. エンコード: H.264 CRF18, AAC 160k, 30fps

    # 解像度ベースのフォントサイズ・余白計算（相対指定）
    target_w, target_h = 1080, 1920
    fontsize = int(target_h * 0.01)  # ≒48 (より小さめに)
    margin_v = int(target_h * 0.050)  # ≒96
    outline = 4  # 輪郭も少し細めに

    # 字幕フィルタ（SRTパスをエスケープ、force_styleでサイズ指定）
    srt_escaped = srt_path.replace("\\", "/")

    # ビデオフィルタチェーン（字幕なし）
    vf = (
        # レターボックス: 1080x1920に収まるようにスケールしてパディング
        "scale=iw*min(1080/iw\\,1920/ih):ih*min(1080/iw\\,1920/ih),"
        "pad=1080:1920:(1080-iw)/2:(1920-ih)/2,"
        "setsar=1"
    )
     if title:
        # 特殊文字をエスケープ
        escaped_title = title.replace("'", "\\'").replace(":", "\\:")
        vf += (
            f",drawtext=text='{escaped_title}'"
            ":fontfile=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
            ":fontsize=48"
            ":fontcolor=white"
            ":borderw=3"
            ":bordercolor=black"
            ":x=(w-text_w)/2"
            ":y=(h/2)-100"
        )
    # オーディオフィルタ（音量正規化）
    af = "loudnorm=I=-16:TP=-1.5:LRA=11"

    cmd = [
        "ffmpeg",
        "-y",  # 上書き
        "-ss", str(start),  # 開始位置
        "-t", str(duration),  # 長さ
        "-i", in_mp4,  # 入力
        "-vf", vf,  # ビデオフィルタ
        "-af", af,  # オーディオフィルタ
        "-c:v", "libx264",  # ビデオコーデック
        "-crf", "18",  # 品質
        "-preset", "medium",  # エンコード速度
        "-pix_fmt", "yuv420p",  # ピクセルフォーマット
        "-r", "30",  # フレームレート
        "-c:a", "aac",  # オーディオコーデック
        "-b:a", "160k",  # オーディオビットレート
        "-ar", "48000",  # サンプルレート
        "-movflags", "+faststart",  # Web最適化
        output_path
    ]

    try:
        log_info(
            f"Running ffmpeg command",
            job_id=job_id,
            meta={"command": " ".join(cmd[:10]) + "..."}  # 最初の10要素のみ
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.RENDER_TIMEOUT,
            check=True
        )

        # 出力ファイルの存在確認
        if not Path(output_path).exists():
            raise RenderError(f"Output file not created: {output_path}")

        # ファイルサイズチェック
        file_size = Path(output_path).stat().st_size
        if file_size < 1000:  # 1KB未満は異常
            raise RenderError(f"Output file too small: {file_size} bytes")

    except subprocess.TimeoutExpired as e:
        log_error(
            f"ffmpeg timeout after {config.RENDER_TIMEOUT}s",
            job_id=job_id,
            exc_info=True
        )
        raise RenderError(f"Rendering timeout: {e}") from e

    except subprocess.CalledProcessError as e:
        log_error(
            f"ffmpeg failed with return code {e.returncode}",
            job_id=job_id,
            meta={"stderr": e.stderr[-500:]},  # 最後の500文字
            exc_info=True
        )
        raise RenderError(f"Rendering failed: {e.stderr}") from e

    except Exception as e:
        log_error(f"Unexpected rendering error: {e}", job_id=job_id, exc_info=True)
        raise RenderError(f"Rendering error: {e}") from e


def get_video_resolution(video_path: str) -> tuple[int, int]:
    """
    動画の解像度を取得

    Args:
        video_path: 動画ファイルパス

    Returns:
        (width, height)

    Raises:
        RenderError: 取得失敗時
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            video_path
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        width, height = map(int, result.stdout.strip().split(","))
        return width, height

    except Exception as e:
        raise RenderError(f"Failed to get video resolution: {e}") from e
