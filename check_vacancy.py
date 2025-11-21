import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import json
import time
from playwright.sync_api import sync_playwright

# --- 監視対象リスト ---
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

# --- メール設定 ---
SMTP_SERVER = os.environ.get('SMTP_SERVER')
SMTP_PORT = os.environ.get('SMTP_PORT')
SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
FROM_EMAIL = os.environ.get('FROM_EMAIL')
TO_EMAIL = FROM_EMAIL

# --- 状態管理 ---
def get_current_status():
    initial_status = {d['danchi_name']: 'not_available' for d in MONITORING_TARGETS}
    try:
        with open('status.json', 'r') as f:
            saved_status = json.load(f)
            return {name: saved_status.get(name, 'not_available') for name in initial_status}
    except (FileNotFoundError, json.JSONDecodeError):
        return initial_status
    except Exception as e:
        print(f"🚨 状態ファイルエラー: {e}")
        return initial_status

def update_status(new_statuses):
    try:
        with open('status.json', 'w') as f:
            json.dump(new_statuses, f, indent=4, ensure_ascii=False)
        print("📄 状態ファイルを更新しました。")
    except Exception as e:
        print(f"🚨 状態ファイル更新失敗: {e}")

def send_alert_email(subject, body):
    try:
        now_jst = datetime.now().strftime('%Y-%m-%d %H:%M:%S JST')
        msg = MIMEText(f"{body}\n\n(実行時刻: {now_jst})", 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL

        with smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"✅ メール送信: {TO_EMAIL}（件名: {subject}）")
    except Exception as e:
        print(f"🚨 メール送信エラー: {e}")

# --- 空室チェック (Playwright) ---
def check_vacancy(danchi, page):
    danchi_name = danchi["danchi_name"]
    url = danchi["url"]
    print(f"\n--- チェック開始: {danchi_name} ---")
    print(f"URL: {url}")

    try:
        # タイムアウト60秒でアクセス
        page.goto(url, timeout=60000)
        
        # ページロード待機（メインコンテンツが表示されるまで）
        try:
            page.wait_for_selector("div#main-contents", timeout=60000)
            print("🌐 ページロード確認OK")
        except Exception:
            print("⚠ ページロードタイムアウト")

        # 空きなし要素の確認 (div.list-none)
        if page.is_visible("div.list-none"):
            print("✅ 空きなし確認")
            return f"空きなし: {danchi_name}", False
        
        # 空きありの確認 (テキスト判定)
        content = page.content()
        if "募集戸数" in content:
            print("🚨 空きあり確認")
            return f"空きあり: {danchi_name}", True
        else:
            print("❓ 空き不確実")
            return f"空きあり: {danchi_name} (不確実)", True

    except Exception as e:
        print(f"🚨 エラー: {e}")
        return f"エラー: {danchi_name}", False

# --- メイン ---
if __name__ == "__main__":
    print(f"=== UR空き情報監視開始 (Playwright) ({len(MONITORING_TARGETS)}件) ===")
    current_statuses = get_current_status()
    print(f"⭐ 現在ステータス: {current_statuses}")

    all_new_statuses = current_statuses.copy()
    newly_available = []
    results = []

    # Playwrightブラウザの起動
    with sync_playwright() as p:
        # Chromiumをヘッドレスモードで起動
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for danchi in MONITORING_TARGETS:
            res_text, is_available = check_vacancy(danchi, page)
            results.append(res_text)
            time.sleep(1) # マナー待機
            
            name = danchi['danchi_name']
            if is_available:
                all_new_statuses[name] = 'available'
                if current_statuses.get(name) == 'not_available':
                    newly_available.append(danchi)
            else:
                all_new_statuses[name] = 'not_available'
        
        browser.close()

    print("\n=== チェック完了 ===")
    for r in results:
        print(f"- {r}")

    if newly_available:
        print(f"🚨 新規空き: {len(newly_available)}件")
        for d in newly_available:
            subject = f"【UR空き情報アラート】🚨 空きが出ました！ {d['danchi_name']}"
            body = (
                f"以下の団地で空き情報が出た可能性があります！\n\n"
                f"・【団地名】: {d['danchi_name']}\n"
                f"  【URL】: {d['url']}\n"
            )
            send_alert_email(subject, body)
            time.sleep(5)

    if all_new_statuses != current_statuses or newly_available:
        update_status(all_new_statuses)
        print("✅ 状態ファイル更新完了")
    else:
        print("✅ 状態に変化なし。状態ファイルの更新はスキップします。")
