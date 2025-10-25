# 認証情報のセットアップ手順

このシステムを動かすには、以下の認証情報ファイルが必要です。

## 必要なファイル

### 1. Service Account JSON（Google Drive / Google Sheets用）
**ファイル名**: `service-account.json`（プロジェクトルートに配置）

**取得方法**:
1. [Google Cloud Console](https://console.cloud.google.com/)にアクセス
2. プロジェクトを選択（または新規作成）
3. 「APIとサービス」→「認証情報」
4. 「認証情報を作成」→「サービスアカウント」
5. サービスアカウントを作成
6. 「キー」タブ → 「鍵を追加」→「JSON」
7. ダウンロードしたJSONファイルを `service-account.json` にリネームしてプロジェクトルートに配置

**有効化が必要なAPI**:
- Google Drive API
- Google Sheets API

**権限設定**:
- Google Driveのフォルダをサービスアカウントのメールアドレスと共有（編集者権限）
- Google Sheetsもサービスアカウントのメールアドレスと共有（編集者権限）

---

### 2. YouTube Client Secret（YouTube API用）
**ファイル名**: `credentials/youtube-client-secret.json`

**取得方法**:
1. [Google Cloud Console](https://console.cloud.google.com/)にアクセス
2. 同じプロジェクトで「APIとサービス」→「認証情報」
3. 「認証情報を作成」→「OAuth 2.0 クライアントID」
4. アプリケーションの種類: 「デスクトップアプリ」
5. 作成後、JSONをダウンロード
6. `credentials/youtube-client-secret.json` として保存

**有効化が必要なAPI**:
- YouTube Data API v3

**OAuth同意画面の設定**:
- ユーザーの種類: 外部（テストユーザーに自分のGoogleアカウントを追加）
- スコープ: `https://www.googleapis.com/auth/youtube.upload`

---

### 3. YouTube Token（初回認証で自動生成）
**ファイル名**: `credentials/youtube-token.json`

**生成方法**:
初回実行時に自動的にブラウザが開き、Googleアカウントでログインするとトークンが生成されます。

```bash
python -m app.scheduler
```

ブラウザで認証後、トークンが自動保存され、以降は自動更新されます。

---

## GitHub Actions Secrets設定

GitHubリポジトリの「Settings」→「Secrets and variables」→「Actions」で以下を設定:

| Secret名 | 説明 | 例 |
|---------|------|-----|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Service AccountのJSON内容全体 | `{"type": "service_account", ...}` |
| `YOUTUBE_CLIENT_SECRET_JSON` | YouTube Client SecretのJSON内容全体 | `{"installed": {"client_id": "...", ...}}` |
| `YOUTUBE_TOKEN_JSON` | 初回認証後に生成されたトークンJSON | `{"token": "...", "refresh_token": "...", ...}` |
| `MAKE_SHARED_SECRET` | API認証用の共有シークレット | `your_secret_key` |
| `DRIVE_INPUT_FOLDER_ID` | Google Driveの入力フォルダID | `1AbC123XyZ...` |
| `DRIVE_READY_FOLDER_ID` | Google Driveの処理済みフォルダID | `1XyZ456AbC...` |
| `GEMINI_API_KEY` | Gemini APIキー | `AIzaSy...` |
| `SPREADSHEET_ID` | GoogleスプレッドシートID | `1AbC123XyZ...` |

---

## ローカル開発時の設定

1. `.env.sample` を `.env` にコピー
2. `.env` の各変数に値を設定
3. 認証情報ファイルを配置:
   - `service-account.json` （プロジェクトルート）
   - `credentials/youtube-client-secret.json`
   - 
4. 初回実行時にYouTubeトークンを生成:
   ```bash
   python -m app.scheduler
   ```

---

## トラブルシューティング

### Service Accountでアクセスできない
- DriveフォルダとSheetsがサービスアカウントと共有されているか確認
- サービスアカウントのメールアドレス: `xxx@xxx.iam.gserviceaccount.com`

### YouTube認証エラー
- OAuth同意画面のテストユーザーに自分のアカウントが追加されているか確認
- `youtube-client-secret.json` が正しい形式か確認

### GitHub Actions で失敗する
- Secrets に正しいJSON全体がコピーされているか確認（改行含む）
- YouTube Tokenは初回ローカル実行後に生成されたものをコピー
