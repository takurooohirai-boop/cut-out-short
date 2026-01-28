# 認証情報のセットアップ手順

このシステムは**マルチYouTuber対応**です。各YouTuberがGASの認証ページでログインし、リフレッシュトークンがスプレッドシートに保存されます。

## 必要なファイル

### 1. Service Account JSON（Google Drive / Google Sheets用）
**ファイル名**: プロジェクトルートに配置（例: `cutoutshort-xxx.json`）

**取得方法**:
1. [Google Cloud Console](https://console.cloud.google.com/)にアクセス
2. プロジェクトを選択（または新規作成）
3. 「APIとサービス」→「認証情報」
4. 「認証情報を作成」→「サービスアカウント」
5. サービスアカウントを作成
6. 「キー」タブ → 「鍵を追加」→「JSON」
7. ダウンロードしたJSONファイルをプロジェクトルートに配置

**有効化が必要なAPI**:
- Google Drive API
- Google Sheets API
- Google Docs API

**権限設定**:
- Google Driveのフォルダをサービスアカウントのメールアドレスと共有（編集者権限）
- Google Sheetsもサービスアカウントのメールアドレスと共有（編集者権限）

---

### 2. YouTube OAuth設定（.env）

YouTube APIの認証には`.env`ファイルで設定します。

```env
YOUTUBE_CLIENT_ID=your_client_id.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=GOCSPX-xxxxx
```

**取得方法**:
1. [Google Cloud Console](https://console.cloud.google.com/)にアクセス
2. 同じプロジェクトで「APIとサービス」→「認証情報」
3. 「認証情報を作成」→「OAuth 2.0 クライアントID」
4. アプリケーションの種類: **「ウェブアプリケーション」**
5. リダイレクトURIに**GASのデプロイURL**を追加
6. 作成後、クライアントIDとシークレットを`.env`に設定

**有効化が必要なAPI**:
- YouTube Data API v3

---

## OAuth同意画面の設定（重要！）

403エラーが発生する場合は、以下を確認してください。

### テストモードの場合
1. Google Cloud Console →「APIとサービス」→「OAuth同意画面」
2. 「ユーザーの種類」が「外部」の場合、**テストユーザー**を追加する必要があります
3. 「テストユーザー」セクションで、認証を許可するGoogleアカウントを追加

### 本番公開する場合
1. OAuth同意画面で「アプリを公開」をクリック
2. Googleの審査が必要な場合があります

### スコープ設定
以下のスコープが必要です：
- `https://www.googleapis.com/auth/youtube.upload`
- `https://www.googleapis.com/auth/youtube.readonly`

---

## GAS（Google Apps Script）のセットアップ

### 1. GASファイルをデプロイ
1. [Google Apps Script](https://script.google.com/)で新しいプロジェクトを作成
2. `gas/YouTubeAuth.gs`の内容をコピー
3. `CLIENT_ID`と`CLIENT_SECRET`を`.env`と同じ値に設定
4. 「デプロイ」→「新しいデプロイ」→「ウェブアプリ」
5. アクセスできるユーザー: 「全員」

### 2. リダイレクトURIを登録
1. GASのデプロイURLをコピー（例: `https://script.google.com/macros/s/xxx/exec`）
2. Google Cloud Console →「認証情報」→ OAuthクライアントを編集
3. 「承認済みのリダイレクトURI」にGASのURLを追加

---

## GitHub Actions Secrets設定

GitHubリポジトリの「Settings」→「Secrets and variables」→「Actions」で以下を設定:

| Secret名 | 説明 |
|---------|------|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Service AccountのJSON内容全体 |
| `DRIVE_OUTPUT_FOLDER_ID` | Google Driveの出力フォルダID |
| `GEMINI_API_KEY` | Gemini APIキー |
| `SPREADSHEET_ID` | GoogleスプレッドシートID |
| `YOUTUBE_CLIENT_ID` | YouTube OAuthクライアントID |
| `YOUTUBE_CLIENT_SECRET` | YouTube OAuthクライアントシークレット |

---

## スプレッドシートの構成

### YouTubersシート
各YouTuberの情報を管理します。GASの認証ページでログインすると自動的に行が追加されます。

| 列 | 内容 |
|----|------|
| A | YouTuber名 |
| B | チャンネルID |
| C | 有効フラグ（TRUE/FALSE） |
| D | 最終処理動画ID |
| E | 最終処理日 |
| F | refresh_token |

---

## トラブルシューティング

### 403エラー（GASログインボタン）
1. **テストユーザーの追加**: OAuth同意画面でログインするGoogleアカウントをテストユーザーに追加
2. **リダイレクトURIの確認**: GASのデプロイURLがOAuthクライアントのリダイレクトURIに登録されているか確認
3. **スコープの確認**: youtube.uploadとyoutube.readonlyスコープが有効か確認

### Service Accountでアクセスできない
- DriveフォルダとSheetsがサービスアカウントと共有されているか確認
- サービスアカウントのメールアドレス: `xxx@xxx.iam.gserviceaccount.com`

### リフレッシュトークンが取得できない
- 一度Googleアカウントの[アプリの権限](https://myaccount.google.com/permissions)からこのアプリを削除
- 再度GASの認証ページからログイン
