"""
YouTube認証トークンを生成するスクリプト

使い方:
1. Google Cloud Consoleからダウンロードしたclient_secret.jsonを用意
2. このスクリプトを実行: python generate_youtube_token.py
3. ブラウザが開くので、YouTubeアカウントでログイン・許可
4. 生成されたtoken.jsonの内容をGitHub Secretsに設定
"""

import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# YouTube APIのスコープ
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def generate_token(client_secret_path='client_secret.json', token_path='token.json'):
    """
    OAuth認証フローを実行してトークンを生成

    Args:
        client_secret_path: クライアントシークレットファイルのパス
        token_path: 生成するトークンファイルのパス
    """

    if not os.path.exists(client_secret_path):
        print(f"Error: {client_secret_path} が見つかりません")
        print("Google Cloud Consoleからダウンロードしたclient_secret.jsonを配置してください")
        return

    creds = None

    # 既存のトークンがあれば読み込む
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # 有効なトークンがない場合は新規作成
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("トークンをリフレッシュしています...")
            creds.refresh(Request())
        else:
            print("ブラウザが開きます。YouTubeアカウントでログインして許可してください...")
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)

        # トークンを保存
        with open(token_path, 'w') as token:
            token.write(creds.to_json())

        print(f"\n✓ トークンが生成されました: {token_path}")
    else:
        print(f"✓ 既存のトークンは有効です: {token_path}")

    # トークンの内容を表示
    print("\n" + "="*60)
    print("GitHub Secretsに設定する内容（YOUTUBE_TOKEN_JSON）:")
    print("="*60)

    with open(token_path, 'r') as f:
        token_data = json.load(f)

    # 1行のJSON形式で表示
    print(json.dumps(token_data))

    print("\n" + "="*60)
    print("この1行をコピーして、GitHub SecretsのYOUTUBE_TOKEN_JSONに設定してください")
    print("="*60)

if __name__ == '__main__':
    import sys

    client_secret = 'client_secret.json'

    # コマンドライン引数でファイルパスを指定可能
    if len(sys.argv) > 1:
        client_secret = sys.argv[1]

    generate_token(client_secret)
