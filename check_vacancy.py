import requests
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os
import datetime

# --- 固定設定 ---
# 通知先メールアドレス (sawa38da@gmail.com に変更)
TO_EMAIL = "sawa38da@gmail.com"
# 判定文字列
SEARCH_STRING = "空室情報"

# --- 監視対象リスト (ここを編集してください) ---
MONITORING_TARGETS = [
    {
        "danchi_name": "光が丘パークタウン プロムナード十番街",
        "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4350.html"
    },
    # 団地を追加する場合は、この下に辞書形式で追加してください
    # {
    #     "danchi_name": "新しい団地名",
    #     "url": "新しいURL"
    # },
]

# 環境変数からSMTP設定を取得 (GitHub Secretsで設定)
SMTP_SERVER = os.environ.get("SMTP_SERVER")
SMTP_PORT = os.environ.get("SMTP_PORT", 587)
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
FROM_EMAIL = os.environ.get("FROM_EMAIL", SMTP_USERNAME)

def send_notification_email(danchi_name, url, message_body):
    """
    指定された団地情報と内容でメールを送信する
    """
    if not all([SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD]):
        print("🚨 エラー: SMTP設定情報が不足しています。メール送信をスキップします。")
        return

    subject = f"【UR空き情報アラート】{danchi_name}の空き情報"
    
    try:
        msg = MIMEText(message_body, 'plain', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL

        # SMTPサーバーに接続
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())
        
        print(f"✅ メールを {TO_EMAIL} に送信しました。（件名: {subject}）")

    except Exception as e:
        print(f"🚨 メール送信中にエラーが発生しました: {e}")

def check_vacancy_for_target(target):
    """
    個別の団地をチェックする
    """
    danchi_name = target["danchi_name"]
    url = target["url"]
    
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n--- 団地チェック開始: {danchi_name} ---")
    print(f"➡️ 対象URL: {url}")
    print(f"🔍 検索文字列: '{SEARCH_STRING}'")
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        html_content = response.text

        if SEARCH_STRING not in html_content:
            print("🚨 検出: 検索文字列 '空室情報' が**存在しません**。空きが出た可能性があります！")
            
            email_body = (
                f"【UR空き情報アラート】\n\n"
                f"団地名: {danchi_name}\n"
                f"日時: {current_time} JST\n\n"
                f"監視対象のページに「{SEARCH_STRING}」という文字列が存在しませんでした。\n"
                f"これは、何らかの空き情報が表示されている可能性があります。\n\n"
                f"以下のURLをすぐに確認してください。\n"
                f"{url}"
            )
            
            send_notification_email(danchi_name, url, email_body)
            print("✅ 実行結果: 通知メール送信済み")

        else:
            print(f"✅ 検出: 検索文字列 '{SEARCH_STRING}' が存在します。空きなし。")
            print("✅ 実行結果: 通知スキップ")

    except requests.exceptions.RequestException as e:
        print(f"🚨 エラー: ウェブページへのアクセスに失敗しました: {e}")
        print("✅ 実行結果: 処理中断")
        
def main():
    """
    全ての監視対象に対してチェックを実行する
    """
    print(f"=== UR空き情報 監視スクリプト実行開始 ({len(MONITORING_TARGETS)}件) ===")
    
    if not MONITORING_TARGETS:
        print("⚠️ 警告: 監視対象が設定されていません。")
        return

    for target in MONITORING_TARGETS:
        check_vacancy_for_target(target)
        
    print(f"\n=== 全ての監視対象のチェックが完了しました ===")


if __name__ == "__main__":
    main()