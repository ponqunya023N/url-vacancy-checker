import os
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import json
import time # sleep関数を使うため

# --- 監視対象リスト (ここを編集してください) ---
MONITORING_TARGETS = [
    {
        "danchi_name": "【S】光が丘パークタウン プロムナード十番街",
        "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4350.html"
    },
    {
        "danchi_name": "【A】光が丘パークタウン 公園南",
        "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3500.html"
    },
    {
        "danchi_name": "【A】光が丘パークタウン 四季の香弐番街",
        "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4100.html"
    },
    {
        "danchi_name": "【B】光が丘パークタウン 大通り中央",
        "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4550.html"
    },
    {
        "danchi_name": "【B】光が丘パークタウン いちょう通り八番街",
        "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3910.html"
    },
    {
        "danchi_name": "【C】光が丘パークタウン 大通り南",
        "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3690.html"
    },
    {
        "danchi_name": "【D】グリーンプラザ高松",
        "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4650.html"
    },
    {
        "danchi_name": "【E】(赤塚)アーバンライフゆりの木通り東",
        "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4590.html"
    },
    {
        "danchi_name": "【F】(赤塚古い)むつみ台",
        "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_2410.html"
    }
]

# --- メールの送信設定 ---
SMTP_SERVER = os.environ.get('SMTP_SERVER')
SMTP_PORT = os.environ.get('SMTP_PORT')
SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
FROM_EMAIL = os.environ.get('FROM_EMAIL')
TO_EMAIL = FROM_EMAIL # 自分宛てに送る

# --- 検索設定 ---
VACANCY_STRING = '当サイトからすぐにご案内できるお部屋がございません' # <-- 新しい判定文字列

# --- 状態管理関数 ---
def get_current_status():
    """status.jsonから現在の通知状態を読み込む"""
    try:
        with open('status.json', 'r') as f:
            return json.load(f).get('status')
    except (FileNotFoundError, json.JSONDecodeError):
        # ファイルがないか、内容がおかしい場合は初期状態を返す
        return 'not_available'

def update_status(new_status):
    """status.jsonを新しい通知状態に更新する"""
    try:
        with open('status.json', 'w') as f:
            json.dump({'status': new_status}, f, indent=4)
        print(f"📄 状態ファイル(status.json)を '{new_status}' に更新しました。")
    except Exception as e:
        print(f"🚨 エラー: 状態ファイルの書き込みに失敗しました: {e}")

def send_alert_email(subject, body):
    """空き情報が見つかった場合にメールを送信する"""
    try:
        now_jst = datetime.now().strftime('%Y-%m-%d %H:%M:%S JST')
        
        msg = MIMEText(f"{body}\n\n(実行時刻: {now_jst})", 'plain', 'utf-8')
        
        msg['Subject'] = subject
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL

        with smtplib.SMTP_SSL(SMTP_SERVER, int(SMTP_PORT)) as server:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            print(f"✅ メールを {TO_EMAIL} に送信しました。（件名: {subject}）")
            return "通知メール送信済み"

    except Exception as e:
        print(f"🚨 エラー: メール送信中にエラーが発生しました: {e}")
        return "メール送信失敗"

def check_vacancy(danchi):
    """団地ごとの空き情報をチェックし、結果(文字列とブーリアン)を返す"""
    danchi_name = danchi["danchi_name"]
    url = danchi["url"]

    print(f"\n--- 団地チェック開始: {danchi_name} ---")
    print(f"🔍 対象URL: {url}")

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        response.encoding = response.apparent_encoding 
        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = soup.get_text()

        if VACANCY_STRING not in page_text:
            # 空きあり: 指定文字列（空きなしを示す）が存在しない
            print(f"🚨 検出: 検索文字列 '{VACANCY_STRING}' が**存在しません**。空きが出た可能性があります！")
            return f"空きあり: {danchi_name}", True
        else:
            # 空きなし: 指定文字列（空きなしを示す）が存在する
            print(f"✅ 検出: 検索文字列 '{VACANCY_STRING}' が存在します。空きなし。")
            return f"空きなし: {danchi_name}", False

    except requests.exceptions.HTTPError as e:
        print(f"🚨 エラー: HTTPエラーが発生しました (ステータスコード: {response.status_code})。")
        return f"HTTPエラー: {danchi_name}", False
    except requests.exceptions.RequestException as e:
        print(f"🚨 エラー: ネットワークまたはリクエストのエラーが発生しました: {e}")
        return f"リクエストエラー: {danchi_name}", False
    except Exception as e:
        print(f"🚨 エラー: その他の予期せぬエラーが発生しました: {e}")
        return f"予期せぬエラー: {danchi_name}", False


if __name__ == "__main__":
    print(f"=== UR空き情報監視スクリプト実行開始 ({len(MONITORING_TARGETS)} 件) ===")
    
    current_status = get_current_status()
    print(f"⭐ 現在の通知状態 (status.json): {current_status}")
    
    vacancy_detected = False
    available_danchis = []
    results = []
    
    for danchi_info in MONITORING_TARGETS:
        result_text, is_available = check_vacancy(danchi_info)
        results.append(result_text)
        
        if is_available:
            vacancy_detected = True
            available_danchis.append(danchi_info)
        
        # 連続実行でGitHub Actionsをブロックしないよう、少し待機
        time.sleep(1) 
        
    print("\n=== 全ての監視対象のチェックが完了しました ===")
    for res in results:
        print(f"- {res}")
        
    new_status = 'available' if vacancy_detected else 'not_available'

    if new_status == current_status:
        # 状態が変わっていない場合：通知スキップ
        print(f"✅ 状態に変化なし ('{new_status}')。メール送信はスキップします。")
    else:
        # 状態が変わった場合：メール送信
        print(f"🚨 状態が変化しました ('{current_status}' -> '{new_status}')。")
        
        if new_status == 'available':
            # 状態が not_available -> available に変化した瞬間（空きが出た瞬間）
            
            subject = f"【UR空き情報アラート】🚨 空きが出ました！({len(available_danchis)}団地)"
            body_lines = [
                "UR賃貸に空き情報が出た可能性があります！",
                "以下の団地を確認してください:\n"
            ]
            
            for danchi in available_danchis:
                body_lines.append(f"・【団地名】: {danchi['danchi_name']}")
                body_lines.append(f"  【URL】: {danchi['url']}\n")
            
            body = "\n".join(body_lines)
            
            send_alert_email(subject, body)
            update_status(new_status)
        else:
            # 状態が available -> not_available に変化した瞬間
            # 連続通知防止のため、状態のみ更新し、通知はスキップ
            update_status(new_status)
            print("✅ '空きなし' への変化を確認しました。通知は行わず状態のみを更新します。")
    
    print("\n=== 監視終了 ===")
    
#EOF
