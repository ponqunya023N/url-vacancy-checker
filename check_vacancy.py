import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException

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
TO_EMAIL = FROM_EMAIL

# --- 状態管理関数 (団地ごとに管理) ---
def get_current_status():
    """status.jsonから現在の通知状態を団地ごとに読み込む"""
    initial_status = {d['danchi_name']: 'not_available' for d in MONITORING_TARGETS}
    try:
        with open('status.json', 'r') as f:
            saved_status = json.load(f)
            return {name: saved_status.get(name, 'not_available') for name in initial_status}
    except (FileNotFoundError, json.JSONDecodeError):
        return initial_status

def update_status(new_statuses):
    """status.jsonを団地ごとの新しい通知状態に更新する"""
    try:
        with open('status.json', 'w') as f:
            json.dump(new_statuses, f, indent=4, ensure_ascii=False)
        print(f"📄 状態ファイル(status.json)を団地ごとの状態に更新しました。")
    except Exception as e:
        print(f"🚨 エラー: 状態ファイルの書き込みに失敗しました: {e}")

def send_alert_email(subject, body):
    """空き情報が見つかった場合にメールを送信する (STARTTLS方式を使用)"""
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
            
            print(f"✅ メールを {TO_EMAIL} に送信しました。（件名: {subject}）")
            return "通知メール送信済み"

    except Exception as e:
        print(f"🚨 エラー: メール送信中にエラーが発生しました: {e}")
        return "メール送信失敗"


def setup_driver():
    """Chrome WebDriverをヘッドレスモードでセットアップする"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def check_vacancy_selenium(danchi, driver):
    """Seleniumを使用して空き情報をチェックする (複合安定検出ロジック)"""
    danchi_name = danchi["danchi_name"]
    url = danchi["url"]

    print(f"\n--- 団地チェック開始: {danchi_name} ---")
    print(f"🔍 対象URL (Selenium): {url}")

    try:
        driver.get(url)
        
        # 待ち時間を設定 (最大90秒に延長)
        wait = WebDriverWait(driver, 90)
        
        # 安定化ステップ: ページメインコンテンツのロード完了を待つ
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div#main-contents")))
            print("🌐 安定化ステップ: メインコンテンツのロードを確認しました。")
        except TimeoutException:
            print("🚨 エラー: メインコンテンツのロードが90秒以内に完了しませんでした。ネットワークエラーの可能性。")
        
        # 判定ステップ: 空きなしの固有要素 (div.list-none) の検出
        no_vacancy_selector = "div.list-none"
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, no_vacancy_selector)))
            print(f"✅ 検出: 空きなしメッセージ要素（{no_vacancy_selector}）を確認しました。空きなし。")
            return f"空きなし: {danchi_name}", False
        except TimeoutException:
            vacancy_indicator_text = "募集戸数"
            if vacancy_indicator_text in driver.page_source:
                print(f"🚨 検出: 空きなし要素が見つからず、ページソースに「{vacancy_indicator_text}」を確認しました。空きあり。")
                return f"空きあり: {danchi_name}", True
            else:
                print(f"❓ 不確実: 空きなし要素が見つからず、かつ「{vacancy_indicator_text}」も見つかりませんでした。空きありの可能性。")
                return f"空きあり: {danchi_name} (不確実)", True
    except Exception as e:
        print(f"🚨 エラー: Seleniumまたはネットワークの致命的なエラーが発生しました: {e}")
        return f"エラー: {danchi_name}", False


if __name__ == "__main__":
    
    try:
        driver = setup_driver()
    except Exception as e:
        print(f"🚨 重大エラー: WebDriverのセットアップに失敗しました。YML設定を確認してください: {e}")
        exit(1)

    print(f"=== UR空き情報監視スクリプト実行開始 (Selenium使用, {len(MONITORING_TARGETS)} 件) ===")
    
    current_statuses = get_current_status()
    print(f"⭐ 現在の通知状態 (status.jsonから読み込み):")
    for name, status in current_statuses.items():
        print(f"  - {name}: {status}")

    all_new_statuses = current_statuses.copy()
    newly_available_danchis = []
    results = []
    
    for danchi_info in MONITORING_TARGETS:
        result_text, is_available = check_vacancy_selenium(danchi_info, driver)
        results.append(result_text)
        time.sleep(1)
        
        danchi_name = danchi_info['danchi_name']
        
        if is_available:
            all_new_statuses[danchi_name] = 'available'
            if current_statuses.get(danchi_name) == 'not_available':
                newly_available_danchis.append(danchi_info)
        else:
            all_new_statuses[danchi_name] = 'not_available'

    driver.quit()
        
    print("\n=== 全ての監視対象のチェックが完了しました ===")
    for res in results:
        print(f"- {res}")
        
    if newly_available_danchis:
        print(f"🚨 新しい空き情報が {len(newly_available_danchis)} 団地で検出されました。団地ごとにメールを送信します。")
        
        for danchi in newly_available_danchis:
            subject = f"【UR空き情報】{danchi['danchi_name']}"
            body = (
                f"以下の団地で空き情報が出た可能性があります！\n\n"
                f"・【団地名】: {danchi['danchi_name']}\n"
                f"  【URL】: {danchi['url']}\n"
            )
            send_alert_email(subject, body)
            time.sleep(5)
            
        update_status(all_new_statuses)
    else:
        if all_new_statuses != current_statuses:
            update_status(all_new_statuses)
            print("✅ 団地ごとの状態が更新されましたが、新規の空き情報はありませんでした。（available -> not_available への変化など）")
        else:
            print("✅ 状態に変化なし。メール送信と状態ファイルの更新はスキップします。")
    
    print("\n=== 監視終了 ===")
    
#EOF
