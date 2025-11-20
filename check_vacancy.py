import os
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

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
VACANCY_STRING = '空室情報'

def send_alert_email(danchi_name, url):
    """空き情報が見つかった場合にメールを送信する"""
    try:
        # TZ: Asia/Tokyo設定が適用される
        now_jst = datetime.now().strftime('%Y-%m-%d %H:%M:%S JST') 
        
        msg = MIMEText(f"""
        UR賃貸に空き情報が出た可能性があります！
        
        【団地名】: {danchi_name}
        【URL】: {url}
        
        今すぐUR公式サイトでご確認ください。
        
        (実行時刻: {now_jst})
        """, 'plain', 'utf-8')
        
        msg['Subject'] = f'【UR空き情報アラート】{danchi_name}の空き情報'
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL

        with smtplib.SMTP_SSL(SMTP_SERVER, int(SMTP_PORT)) as server:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            print(f"✅ メールを {TO_EMAIL} に送信しました。（件名: {msg['Subject']}）")
            return "通知メール送信済み"

    except Exception as e:
        print(f"🚨 エラー: メール送信中にエラーが発生しました: {e}")
        return "メール送信失敗"

def check_vacancy(danchi):
    """団地ごとの空き情報をチェックする"""
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
            print(f"🚨 検出: 検索文字列 '{VACANCY_STRING}' が**存在しません**。空きが出た可能性があります！")
            result = send_alert_email(danchi_name, url)
            return result
        else:
            print(f"✅ 検出: 検索文字列 '{VACANCY_STRING}' が存在します。空きなし。")
            print("✅ 実行結果: 通知スキップ")
            return "通知スキップ"

    except requests.exceptions.HTTPError as e:
        print(f"🚨 エラー: HTTPエラーが発生しました (ステータスコード: {response.status_code})。URLを確認してください。")
        return "HTTPエラー"
    except requests.exceptions.RequestException as e:
        print(f"🚨 エラー: ネットワークまたはリクエストのエラーが発生しました: {e}")
        return "リクエストエラー"
    except Exception as e:
        print(f"🚨 エラー: その他の予期せぬエラーが発生しました: {e}")
        return "予期せぬエラー"

if __name__ == "__main__":
    print(f"=== UR空き情報監視スクリプト実行開始 ({len(MONITORING_TARGETS)} 件) ===")
    
    results = []
    for danchi_info in MONITORING_TARGETS:
        result = check_vacancy(danchi_info)
        results.append(f"{danchi_info['danchi_name']}: {result}")
        
    print("\n=== 全ての監視対象のチェックが完了しました ===")
    for res in results:
        print(f"- {res}")
