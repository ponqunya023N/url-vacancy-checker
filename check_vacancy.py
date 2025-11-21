import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import smtplib
from email.mime.text import MIMEText

# --- 監視対象 ---
MONITORING_TARGETS = [
    {"danchi_name": "【S】光が丘パークタウン プロムナード十番街", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4350.html"},
    {"danchi_name": "【A】光が丘パークタウン 公園南", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3500.html"},
    {"danchi_name": "【A】光が丘パークタウン 四季の香弐番街", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4100.html"},
    {"danchi_name": "【B】光が丘パークタウン 大通り中央", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4550.html"},
    {"danchi_name": "【B】光が丘パークタウン いちょう通り八番街", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3910.html"},
    {"danchi_name": "【C】光が丘パークタウン 大通り南", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3690.html"},
    {"danchi_name": "【D】グリーンプラザ高松", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4650.html"},
    {"danchi_name": "【E】(赤塚)アーバンライフゆりの木通り東", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4590.html"},
    {"danchi_name": "【F】(赤塚古い)むつみ台", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_2410.html"}
]

# --- メール設定（環境変数） ---
SMTP_SERVER = os.environ.get('SMTP_SERVER')
SMTP_PORT = os.environ.get('SMTP_PORT')
SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
FROM_EMAIL = os.environ.get('FROM_EMAIL')
TO_EMAIL = os.environ.get('TO_EMAIL', FROM_EMAIL)

# --- 状態管理 ---
STATUS_FILE = "status.json"

def load_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {d['danchi_name']: 'not_available' for d in MONITORING_TARGETS}

def save_status(statuses):
    with open(STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(statuses, f, ensure_ascii=False, indent=4)
    print("✅ 状態ファイル更新完了")

# --- メール送信 ---
def send_email(subject, body):
    if not all([SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL, TO_EMAIL]):
        print("🚨 メール送信に必要な環境変数が未設定です。送信をスキップします。")
        return
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL

        with smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"✅ メール送信完了: {TO_EMAIL}（件名: {subject}）")
    except Exception as e:
        print(f"🚨 メール送信エラー: {e}")

# --- 空室チェック ---
def check_vacancy(danchi):
    name = danchi['danchi_name']
    url = danchi['url']
    print(f"--- チェック開始: {name} ---")
    try:
        res = requests.get(url, timeout=30)
        if res.status_code != 200:
            print(f"⚠ HTTPステータス {res.status_code}")
            return name, False
        soup = BeautifulSoup(res.text, 'html.parser')
        phrase = "当サイトからすぐにご案内できるお部屋がございません"
        if phrase in soup.get_text():
            return name, False
        return name, True
    except Exception as e:
        print(f"🚨 取得エラー: {e}")
        return name, False

# --- メイン ---
def main():
    now_jst = datetime.now().strftime("%Y-%m-%d %H:%M:%S JST")
    print(f"[{now_jst}] === UR空き情報監視開始 ===")
    current_status = load_status()
    newly_available = []
    new_status = current_status.copy()

    for danchi in MONITORING_TARGETS:
        name, available = check_vacancy(danchi)
        status = 'available' if available else 'not_available'
        if current_status.get(name) == 'not_available' and available:
            newly_available.append(danchi)
        new_status[name] = status
        print(f"[{now_jst}] {name}: {status}")

    if newly_available:
        for d in newly_available:
            subject = f"【UR空き情報】{d['danchi_name']}"
            body = f"空き情報が出た可能性があります\n\n団地名: {d['danchi_name']}\nURL: {d['url']}"
            send_email(subject, body)

    save_status(new_status)
    print(f"[{now_jst}] === 監視終了 ===")

if __name__ == "__main__":
    main()
