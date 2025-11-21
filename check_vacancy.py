import os
import requests
import smtplib 
from email.mime.text import MIMEText
from email.header import Header
from bs4 import BeautifulSoup

# --- 設定項目 (環境変数から読み込み) ---
# 環境変数が設定されていない場合、プログラムは実行されません
SMTP_SERVER = os.environ.get("SMTP_SERVER")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
FROM_EMAIL = os.environ.get("FROM_EMAIL") # 送信元メールアドレス
TO_EMAIL = os.environ.get("TO_EMAIL") # 通知を受け取りたいメールアドレス

# 団地URL
UR_DANCI_URL = "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3470.html"

# --- 判定セレクタ ---
AVAILABLE_SELECTOR = "div#js-room-search-result" 

# --- 関数定義 ---

def check_ur_availability(url, selector):
    """
    指定されたURLからHTMLを取得し、特定のセレクタが存在するかどうかを確認します。
    """
    try:
        # User-Agentを設定して、ブラウザからのアクセスに見せかける
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # HTTPエラーがあれば例外を発生させる
        
        # HTMLを解析
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 指定されたセレクタを持つ要素を検索
        is_available = soup.select_one(selector) is not None
        
        return is_available

    except requests.exceptions.RequestException as e:
        print(f"ウェブサイトへのアクセス中にエラーが発生しました: {e}")
        return None

def send_email_notification(subject, body):
    """
    メールで通知を送信します。
    """
    # 環境変数の設定漏れがないかチェック
    if not all([SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL, TO_EMAIL]):
        print("警告: SMTPの環境変数がすべて設定されていません。メール通知はスキップされました。")
        return False

    try:
        # メッセージの作成
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL

        # SMTPサーバーへの接続とメール送信
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() # TLS暗号化
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())
        
        print(f"メール通知を送信しました。件名: {subject}")
        return True

    except Exception as e:
        print(f"メール送信中にエラーが発生しました: {e}")
        print("SMTPサーバー、ポート、ユーザー名、パスワード、受信者アドレスを確認してください。")
        return False

# --- メイン処理 ---

if __name__ == "__main__":
    current_date = "2025-11-22 JST" # 現在日付を必ず明記
    
    # TO_EMAILが未設定の場合、ここで警告を出す (ログで *** が表示されているため、今回は設定済み)
    if not TO_EMAIL:
        print("エラー: TO_EMAIL 環境変数が設定されていません。通知先メールアドレスを設定してください。")
        # GitHub Actionsのログでは「失敗」と表示される
        exit(1)

    # UR団地の空き状況をチェック
    is_available = check_ur_availability(UR_DANCI_URL, AVAILABLE_SELECTOR)

    # メール本文と件名のベース
    base_subject = "UR団地空き状況チェック結果"
    
    if is_available is None:
        # アクセスエラーが発生した場合
        subject = f"🚨 ERROR: {base_subject} (アクセスエラー)"
        body = f"現在日付: {current_date}\nUR団地ページへのアクセスに失敗しました。URLまたはネットワーク接続を確認してください。\n対象URL: {UR_DANCI_URL}"
        send_email_notification(subject, body)
        
    elif is_available:
        # 空きがあった場合
        subject = f"✅ 空きあり: {base_subject}！"
        body = f"現在日付: {current_date}\nUR団地に「空きあり」の可能性が高いです！すぐに確認してください。\n対象URL: {UR_DANCI_URL}"
        send_email_notification(subject, body)
        
    else:
        # 空きがなかった場合（⭐【一時修正】テストのため、強制的にメール送信を実行します）
        print(f"現在、空きはありません。（{current_date}）")

        # ⭐【一時修正】このブロックでメール通知を実行します
        test_subject = f"✅ TEST: {base_subject} (空きなし判定テスト)"
        test_body = f"現在日付: {current_date}\nこのメールは、メール設定（SMTP）が正しく機能しているかを確認するためのテストです。\n空きはありませんが、通知を強制実行しました。\n対象URL: {UR_DANCI_URL}"
        send_email_notification(test_subject, test_body)
        # ⭐【一時修正ここまで】
