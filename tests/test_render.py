"""render.pyのユニットテスト"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from app.render import (
    render_clipset,
    _render_single_clip,
    get_video_resolution,
    RenderError
)
from app.models import SegmentInfo


class TestGetVideoResolution:
    """get_video_resolution関数のテスト"""

    @patch('app.render.subprocess.run')
    def test_get_resolution_success(self, mock_run):
        """解像度取得が成功する場合"""
        mock_run.return_value = Mock(stdout="1920,1080\n", returncode=0)
        width, height = get_video_resolution("/fake/video.mp4")
        assert width == 1920
        assert height == 1080

    @patch('app.render.subprocess.run')
    def test_get_resolution_failure(self, mock_run):
        """解像度取得が失敗する場合"""
        mock_run.side_effect = Exception("ffprobe error")
        with pytest.raises(RenderError):
            get_video_resolution("/fake/video.mp4")


class TestRenderSingleClip:
    """_render_single_clip関数のテスト"""

    @patch('app.render.subprocess.run')
    @patch('app.render.Path')
    def test_render_success(self, mock_path_class, mock_run, temp_dir):
        """正常にレンダリングできる場合"""
        # ファイル存在チェックのモック
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.stat.return_value.st_size = 1024 * 1024  # 1MB
        mock_path_class.return_value = mock_path

        # ffmpegコマンドが成功
        mock_run.return_value = Mock(returncode=0)

        output_path = temp_dir / "clip_01.mp4"

        # 実行
        _render_single_clip(
            in_mp4="/fake/input.mp4",
            srt_path="/fake/input.srt",
            start=10.0,
            end=40.0,
            output_path=str(output_path),
            job_id="test_job"
        )

        # ffmpegが呼ばれたことを確認
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "ffmpeg" in call_args[0][0]
        assert "-ss" in call_args[0][0]
        assert "10.0" in call_args[0][0]

    @patch('app.render.subprocess.run')
    def test_render_timeout(self, mock_run, temp_dir):
        """タイムアウトする場合"""
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired("ffmpeg", 600)

        output_path = temp_dir / "clip_timeout.mp4"

        with pytest.raises(RenderError, match="timeout"):
            _render_single_clip(
                in_mp4="/fake/input.mp4",
                srt_path="/fake/input.srt",
                start=0.0,
                end=30.0,
                output_path=str(output_path),
                job_id="test_job"
            )

    @patch('app.render.subprocess.run')
    @patch('app.render.Path')
    def test_render_output_too_small(self, mock_path_class, mock_run, temp_dir):
        """出力ファイルが小さすぎる場合（異常）"""
        # ファイルは存在するが小さすぎる
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.stat.return_value.st_size = 100  # 100 bytes（小さすぎる）
        mock_path_class.return_value = mock_path

        mock_run.return_value = Mock(returncode=0)

        output_path = temp_dir / "clip_small.mp4"

        with pytest.raises(RenderError, match="too small"):
            _render_single_clip(
                in_mp4="/fake/input.mp4",
                srt_path="/fake/input.srt",
                start=0.0,
                end=30.0,
                output_path=str(output_path),
                job_id="test_job"
            )


class TestRenderClipset:
    """render_clipset関数のテスト"""

    @patch('app.render._render_single_clip')
    def test_render_multiple_clips(self, mock_render_single, temp_dir):
        """複数のクリップをレンダリング"""
        segments = [
            SegmentInfo(start=0.0, end=30.0, score=0.8, method="llm"),
            SegmentInfo(start=35.0, end=65.0, score=0.7, method="llm"),
            SegmentInfo(start=70.0, end=100.0, score=0.6, method="rule"),
        ]

        rendered_files = render_clipset(
            in_mp4="/fake/input.mp4",
            srt_path="/fake/input.srt",
            segments=segments,
            output_dir=str(temp_dir),
            job_id="test_job"
        )

        # 3つのクリップがレンダリングされた
        assert len(rendered_files) == 3
        assert mock_render_single.call_count == 3

        # ファイル名が正しいか確認
        for i, file_path in enumerate(rendered_files, start=1):
            assert f"clip_{i:02d}.mp4" in file_path

    @patch('app.render._render_single_clip')
    def test_render_with_partial_failure(self, mock_render_single, temp_dir):
        """一部のクリップが失敗しても続行"""
        segments = [
            SegmentInfo(start=0.0, end=30.0, score=0.8, method="llm"),
            SegmentInfo(start=35.0, end=65.0, score=0.7, method="llm"),
            SegmentInfo(start=70.0, end=100.0, score=0.6, method="rule"),
        ]

        # 2番目のクリップでエラー
        def side_effect(*args, **kwargs):
            if "clip_02" in args[3]:
                raise Exception("Render error")
            return None

        mock_render_single.side_effect = side_effect

        rendered_files = render_clipset(
            in_mp4="/fake/input.mp4",
            srt_path="/fake/input.srt",
            segments=segments,
            output_dir=str(temp_dir),
            job_id="test_job"
        )

        # 2つのクリップが成功（1つ失敗）
        assert len(rendered_files) == 2

    @patch('app.render._render_single_clip')
    def test_render_all_failed(self, mock_render_single, temp_dir):
        """全てのクリップが失敗する場合"""
        segments = [
            SegmentInfo(start=0.0, end=30.0, score=0.8, method="llm"),
        ]

        mock_render_single.side_effect = Exception("All render failed")

        with pytest.raises(RenderError, match="No clips were successfully rendered"):
            render_clipset(
                in_mp4="/fake/input.mp4",
                srt_path="/fake/input.srt",
                segments=segments,
                output_dir=str(temp_dir),
                job_id="test_job"
            )


class TestRenderIntegration:
    """統合テスト（実際のファイルがある場合のみ）"""

    @pytest.mark.skip(reason="実際の動画ファイルとffmpegが必要")
    def test_render_real_video(self, test_data_dir, temp_dir):
        """実際の動画ファイルでレンダリングをテスト"""
        video_path = test_data_dir / "sample_video.mp4"
        srt_path = test_data_dir / "sample_video.srt"

        if not video_path.exists() or not srt_path.exists():
            pytest.skip("テストファイルが存在しません")

        segments = [
            SegmentInfo(start=5.0, end=35.0, score=0.8, method="llm", reason="test")
        ]

        rendered_files = render_clipset(
            in_mp4=str(video_path),
            srt_path=str(srt_path),
            segments=segments,
            output_dir=str(temp_dir),
            job_id="test_job"
        )

        assert len(rendered_files) == 1
        output_file = Path(rendered_files[0])
        assert output_file.exists()
        assert output_file.stat().st_size > 1000  # 1KB以上

        # 解像度を確認（9:16 = 1080x1920であるべき）
        width, height = get_video_resolution(str(output_file))
        assert width == 1080
        assert height == 1920
