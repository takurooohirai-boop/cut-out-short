# Auto Shorts API

Google Driveに置かれた横長動画から、**完全自動で9:16（上下黒帯）＋字幕付きショート**を3〜8本生成し、Makeから**HTTP**で制御・取得できるAPIを提供します。

## 特徴

- **完全自動**: Drive監視 → 文字起こし → セグメント抽出 → レンダリング → アップロード
- **高品質**: 9:16レターボックス、字幕付き、H.264/AAC
- **柔軟**: LLMベース or 規則ベースの切り出し、フォールバック機能
- **可観測性**: JSON構造ログ、トレースID、進捗管理
- **Make連携**: HTTP APIでシームレスに統合

## アーキテクチャ

```
FastAPI + faster-whisper + ffmpeg + OpenAI + Google Drive API
↓ Cloud Run (or Docker)
```

## ディレクトリ構成

```
auto-shorts/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI エンドポイント
│   ├── worker.py            # ジョブ実行ワーカー
│   ├── config.py            # 環境変数管理
│   ├── models.py            # Pydantic スキーマ
│   ├── logging_utils.py     # JSON ロガー
│   ├── drive_io.py          # Google Drive DL/UL
│   ├── yt.py                # yt-dlp ラッパー
│   ├── transcribe.py        # Whisper 文字起こし
│   ├── cut_finder.py        # セグメント抽出（LLM + 規則）
│   └── render.py            # ffmpeg レンダリング
├── tests/                   # テスト（TODO）
├── requirements.txt         # Python 依存パッケージ
├── Dockerfile               # コンテナイメージ定義
├── .env.sample              # 環境変数サンプル
├── .gitignore
└── README.md
```

## セットアップ

### 1. 前提条件

- Python 3.11+
- ffmpeg（システムにインストール済み）
- yt-dlp（システムにインストール済み）
- Google Cloud Platform アカウント
  - Service Account JSON（Drive API有効化）
  - 対象Driveフォルダに招待

### 2. ローカル開発環境

```bash
# リポジトリをクローン
git clone <repo-url>
cd auto-shorts

# 仮想環境を作成
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存関係をインストール
pip install -r requirements.txt

# 環境変数を設定
cp .env.sample .env
# .envファイルを編集して必要な値を設定

# Google Service Account JSONを配置
# service-account.json を配置し、.env の GOOGLE_APPLICATION_CREDENTIALS に指定

# アプリケーション起動
uvicorn app.main:app --reload --port 8080
```

### 3. Docker

```bash
# イメージをビルド
docker build -t auto-shorts:latest .

# コンテナを起動
docker run -d \
  -p 8080:8080 \
  --env-file .env \
  -v $(pwd)/service-account.json:/app/service-account.json \
  auto-shorts:latest
```

### 4. Cloud Run デプロイ

```bash
# GCPプロジェクトを設定
export PROJECT_ID=your-project-id
gcloud config set project $PROJECT_ID

# Cloud Build でイメージをビルド
gcloud builds submit --tag gcr.io/$PROJECT_ID/auto-shorts:v1

# Cloud Run にデプロイ
gcloud run deploy auto-shorts \
  --image gcr.io/$PROJECT_ID/auto-shorts:v1 \
  --region asia-northeast1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars MAKE_SHARED_SECRET=your_secret \
  --set-env-vars DRIVE_INPUT_FOLDER_ID=your_folder_id \
  --set-env-vars DRIVE_READY_FOLDER_ID=your_folder_id \
  --set-secrets GOOGLE_APPLICATION_CREDENTIALS=service-account-json:latest \
  --memory 2Gi \
  --cpu 2 \
  --timeout 600
```

## 環境変数

`.env.sample` を参照してください。主な設定：

| 変数名 | 説明 | 必須 |
|--------|------|------|
| `MAKE_SHARED_SECRET` | Make→API共有鍵 | ✓ |
| `GOOGLE_APPLICATION_CREDENTIALS` | Service Account JSONパス | ✓ |
| `DRIVE_INPUT_FOLDER_ID` | 入力フォルダID | ✓ |
| `DRIVE_READY_FOLDER_ID` | 出力フォルダID | ✓ |
| `WHISPER_MODEL` | Whisperモデル（tiny/base/small/medium） | - |
| `OPENAI_API_KEY` | OpenAI APIキー（LLM抽出用） | - |
| `MAX_CONCURRENT_JOBS` | 同時実行ジョブ数 | - |

## API エンドポイント

### `POST /jobs` - ジョブ作成

```bash
curl -X POST "http://localhost:8080/jobs" \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: your_secret" \
  -d '{
    "source_type": "drive",
    "drive_file_id": "1Abc...",
    "title_hint": "demo.mp4",
    "options": {
      "target_count": 5,
      "min_sec": 25,
      "max_sec": 45
    }
  }'
```

**Response (201):**
```json
{
  "job_id": "uuid",
  "status": "queued"
}
```

### `GET /jobs/{job_id}` - 状態取得

```bash
curl -H "X-API-KEY: your_secret" "http://localhost:8080/jobs/{job_id}"
```

**Response (200):**
```json
{
  "job_id": "uuid",
  "status": "done",
  "progress": 1.0,
  "message": "Successfully created 5 clips",
  "outputs": [
    {
      "file_name": "clip_01.mp4",
      "drive_link": "https://drive.google.com/...",
      "duration_sec": 32.1,
      "segment": {"start": 123.4, "end": 155.6},
      "method": "llm"
    }
  ],
  "trace_id": "trace-xxxxx"
}
```

### `POST /jobs/{job_id}/retry` - リトライ

```bash
curl -X POST "http://localhost:8080/jobs/{job_id}/retry" \
  -H "X-API-KEY: your_secret" \
  -H "Content-Type: application/json" \
  -d '{"options": {"force_rule_based": true}}'
```

### `GET /healthz` - ヘルスチェック

```bash
curl "http://localhost:8080/healthz"
```

### `GET /version` - バージョン情報

```bash
curl "http://localhost:8080/version"
```

## Make連携シナリオ

1. **Google Drive: Watch files in a folder** (`inbox/`)
2. **HTTP: POST /jobs** → ジョブ作成
3. **Tools: Sleep 45s**（ポーリング）
4. **HTTP: GET /jobs/{job_id}** → `status == done` まで繰り返し
5. **(任意) 承認フロー**
6. **YouTube: Upload a video** (Shorts)
7. **Google Sheets: Add a row** (URL/日時/タイトルを記録)

## フォールバック機能

- **Whisper失敗時**: 固定尺で3本生成（字幕なし）
- **LLM失敗時**: 規則ベース抽出にフォールバック
- **Drive/UL失敗時**: 3回リトライ（指数バックオフ）
- **最低保証**: 必ず最低3本の動画を生成

## ログ

JSON構造化ログで出力（stdout）：

```json
{
  "ts": "2025-10-14T12:34:56.789Z",
  "level": "INFO",
  "trace_id": "trace-xxxxx",
  "job_id": "uuid",
  "stage": "transcribing",
  "msg": "whisper start",
  "meta": {"model": "small", "lang": "ja"}
}
```

## トラブルシューティング

### ffmpeg not found

```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg

# Windows
choco install ffmpeg
```

### yt-dlp not found

```bash
# pip経由
pip install yt-dlp

# システムへの直接インストール
wget -O /usr/local/bin/yt-dlp https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp
chmod +x /usr/local/bin/yt-dlp
```

### Google Drive権限エラー

- Service AccountをDriveフォルダに**編集者**として招待
- Service Account JSONが正しいパスに配置されているか確認

### Whisper遅い

- `WHISPER_MODEL=tiny` または `base` に変更
- `WHISPER_DEVICE=cuda` でGPU使用（要CUDA環境）

## ライセンス

MIT

## 開発者

Generated with Claude Code
