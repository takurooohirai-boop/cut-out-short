# GitHub Secrets設定ガイド

GitHub ActionsでCutoutShortを動作させるために必要なSecretsの設定方法を説明します。

---

## 方法1: YouTube認証を含む完全セットアップ（推奨）

YouTubeへの自動アップロード機能を使う場合はこちら。

### 前提条件

- Google Cloud Consoleで作成した `client_secret.json`
- 動画をアップロードするYouTubeアカウントへのアクセス
- Python環境

### 手順

#### 1. リポジトリをクローン・更新

```bash
git clone https://github.com/takurooohirai-boop/cut-out-short.git
cd cut-out-short
git pull
```

#### 2. 必要なライブラリをインストール

```bash
pip install google-auth-oauthlib google-auth-httplib2
```

#### 3. client_secret.json を配置

Google Cloud Consoleからダウンロードした `client_secret_xxx.json` を `client_secret.json` という名前でリポジトリのルートディレクトリに配置します。

```bash
# 例: ダウンロードフォルダから移動
mv ~/Downloads/client_secret_92224762251-*.json ./client_secret.json
```

#### 4. YouTube認証トークンを生成

```bash
python generate_youtube_token.py
```

- ブラウザが自動的に開きます
- **動画をアップロードするYouTubeアカウント**でログイン
- 「このアプリは確認されていません」→「詳細」→「移動」
- アクセス権限を「許可」

成功すると、以下のような1行のJSONが表示されます:

```json
{"token": "ya29.a0...", "refresh_token": "1//0e...", "token_uri": "https://oauth2.googleapis.com/token", ...}
```

**この1行全体をコピーしてください**（後でGitHub Secretsに設定します）

#### 5. client_secret.json を1行に圧縮

```bash
python -c "import json; print(json.dumps(json.load(open('client_secret.json'))))"
```

出力された1行のJSONをコピーしてください。

#### 6. Service Account JSON を1行に圧縮

Google Cloud Consoleからダウンロードした `youtubeauto-476205-*.json`（サービスアカウントの認証情報）を1行に圧縮:

```bash
python -c "import json; print(json.dumps(json.load(open('youtubeauto-476205-3f2e20f04c30.json'))))"
```

出力された1行のJSONをコピーしてください。

#### 7. GitHub Secretsに設定

1. GitHubリポジトリ: https://github.com/takurooohirai-boop/cut-out-short
2. **Settings** → **Secrets and variables** → **Actions**
3. 以下の3つのSecretを設定:

| Secret名 | 値 |
|---------|-----|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | 手順6でコピーした1行のJSON |
| `YOUTUBE_CLIENT_SECRET_JSON` | 手順5でコピーした1行のJSON |
| `YOUTUBE_TOKEN_JSON` | 手順4でコピーした1行のJSON |

その他、以下のSecretsも必要です（既に設定済みの場合はスキップ）:

| Secret名 | 説明 | 例 |
|---------|-----|-----|
| `DRIVE_INPUT_FOLDER_ID` | Google Driveの入力フォルダID | `1AbCdEfGhIjKlMnOpQrStUvWxYz` |
| `DRIVE_READY_FOLDER_ID` | Google Driveの出力フォルダID | `1ZyXwVuTsRqPoNmLkJiHgFeDcBa` |
| `GEMINI_API_KEY` | Gemini APIキー | `AIzaSy...` |
| `SPREADSHEET_ID` | Googleスプレッドシート ID | `1AbC...xyz` |

#### 8. GitHub Actionsを手動実行

1. リポジトリの **Actions** タブ
2. **Auto Shorts Scheduler** を選択
3. **Run workflow** → **Run workflow**

成功すれば完了です！

---

## 方法2: YouTube認証を一旦スキップ（テスト用）

YouTube機能は後回しにして、まずDrive部分だけ動作確認したい場合はこちら。

### 手順

#### 1. ワークフローファイルを編集

`.github/workflows/auto-shorts.yml` を開いて、YouTube関連のステップをスキップするように修正します。

以下の2つのステップをコメントアウト（または削除）:

```yaml
      # - name: Set up YouTube client secret
      #   env:
      #     YOUTUBE_CLIENT_SECRET_JSON: ${{ secrets.YOUTUBE_CLIENT_SECRET_JSON }}
      #   run: |
      #     if [ -z "$YOUTUBE_CLIENT_SECRET_JSON" ]; then
      #       echo "Error: YOUTUBE_CLIENT_SECRET_JSON secret is empty or not set"
      #       exit 1
      #     fi
      #     echo "$YOUTUBE_CLIENT_SECRET_JSON" > credentials/youtube-client-secret.json
      #     if ! python -m json.tool credentials/youtube-client-secret.json > /dev/null 2>&1; then
      #       echo "Error: youtube-client-secret.json is not valid JSON"
      #       exit 1
      #     fi
      #     echo "youtube-client-secret.json created successfully"

      # - name: Set up YouTube token
      #   env:
      #     YOUTUBE_TOKEN_JSON: ${{ secrets.YOUTUBE_TOKEN_JSON }}
      #   run: |
      #     if [ -z "$YOUTUBE_TOKEN_JSON" ]; then
      #       echo "Error: YOUTUBE_TOKEN_JSON secret is empty or not set"
      #       exit 1
      #     fi
      #     echo "$YOUTUBE_TOKEN_JSON" > credentials/youtube-token.json
      #     if ! python -m json.tool credentials/youtube-token.json > /dev/null 2>&1; then
      #       echo "Error: youtube-token.json is not valid JSON"
      #       exit 1
      #     fi
      #     echo "youtube-token.json created successfully"
```

#### 2. YouTube機能を無効化するための空ファイルを作成

ワークフローに以下のステップを追加（YouTube関連ステップの代わり）:

```yaml
      - name: Create dummy YouTube credentials (skip YouTube upload)
        run: |
          echo '{"installed": {"client_id": "dummy"}}' > credentials/youtube-client-secret.json
          echo '{"token": "dummy"}' > credentials/youtube-token.json
          echo "YouTube upload is disabled for testing"
```

#### 3. GitHub Secretsに最低限の設定

YouTube関連以外のSecretsを設定:

| Secret名 | 説明 |
|---------|-----|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | サービスアカウントJSON（1行） |
| `DRIVE_INPUT_FOLDER_ID` | 入力フォルダID |
| `DRIVE_READY_FOLDER_ID` | 出力フォルダID |
| `GEMINI_API_KEY` | Gemini APIキー |
| `SPREADSHEET_ID` | スプレッドシートID |

#### 4. コミット・プッシュして実行

```bash
git add .github/workflows/auto-shorts.yml
git commit -m "Temporarily disable YouTube upload for testing"
git push
```

GitHub Actionsを手動実行すると、YouTube部分をスキップして実行されます。

**注意**: この方法だと動画は生成されますが、YouTubeにはアップロードされません。Google Driveには保存されます。

---

## トラブルシューティング

### 「service-account.json is not valid JSON」エラー

- JSONをコピーする際に余計な改行やスペースが入っている
- 必ず**1行のJSON形式**で設定してください
- 上記の圧縮コマンドを使うと確実です

### 「このアプリは確認されていません」

- 自分で作成したアプリなので「詳細」→「移動」で進んでOK
- Googleの審査は不要です

### ブラウザが開かない

```bash
# URLが表示されるので、手動でブラウザにコピペしてください
python generate_youtube_token.py
```

### トークン生成後も認証エラーが出る

- `refresh_token` が含まれているか確認
- トークン生成時に**初回認証**である必要があります（既存の token.json を削除してから再実行）

---

## まとめ

- **本番運用**: 方法1で完全セットアップ
- **動作テスト**: 方法2でYouTubeをスキップ

YouTube認証は先方の環境でのみ可能なので、先方に方法1を実行してもらう必要があります。
