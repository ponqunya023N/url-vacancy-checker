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

# --- 状態管理関数 ---
def get_current_status():
    """status.jsonから現在の通知状態を読み込む"""
    try:
        with open('status.json', 'r') as f:
            return json.load(f).get('status')
    except (FileNotFoundError, json.JSONDecodeError):
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
    """空き情報が見つかった場合にメールを送信する (STARTTLS方式に修正)"""
    try:
        now_jst = datetime.now().strftime('%Y-%m-%d %H:%M:%S JST')
        
        msg = MIMEText(f"{body}\n\n(実行時刻: {now_jst})", 'plain', 'utf-8')
        
        msg['Subject'] = subject
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL

        # SSLエラー[WRONG_VERSION_NUMBER]対策として、SMTP + starttls方式を使用
        with smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT)) as server:
            server.starttls() # ここでTLS暗号化を要求
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

    # WebDriverManagerでWebDriverのインストールを自動化
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def check_vacancy_selenium(danchi, driver):
    """Seleniumを使用して空き情報をチェックする (WebDriverWaitで空きなしメッセージの有無を判定)"""
    danchi_name = danchi["danchi_name"]
    url = danchi["url"]

    print(f"\n--- 団地チェック開始: {danchi_name} ---")
    print(f"🔍 対象URL (Selenium): {url}")

    try:
        driver.get(url)
        
        # --- 判定ロジック (WebDriverWaitを使用し、JavaScriptのロードを待つ) ---
        no_vacancy_text = "ただいま、ご紹介できるお部屋がございません。"
        
        # 待ち時間を設定 (最大60秒に延長)
        wait = WebDriverWait(driver, 60)
        
        # XPathで特定のテキストを含む要素をチェック
        # contains()で部分一致でテキストを検出します
        xpath_no_vacancy = f"//*[contains(text(), '{no_vacancy_text}')]"
        
        try:
            # 最大60秒間、「空きなし」メッセージが表示されるのを待つ
            wait.until(EC.presence_of_element_located((By.XPATH, xpath_no_vacancy)))
            
            # メッセージが検出された = 空きなし
            print(f"✅ 検出: '空きなし' メッセージを確認しました。空きなし。 (WebDriverWait検出)")
            return f"空きなし: {danchi_name}", False
            
        except TimeoutException:
            # 60秒待ってもメッセージが表示されない = 空きあり 
            print(f"🚨 検出: '空きなし' メッセージがありません！空きが出た可能性があります。 (WebDriverWaitタイムアウト)")
            return f"空きあり: {danchi_name}", True
            

    except Exception as e:
        print(f"🚨 エラー: Seleniumまたはネットワークのエラーが発生しました: {e}")
        return f"エラー: {danchi_name}", False


if __name__ == "__main__":
    
    try:
        driver = setup_driver()
    except Exception as e:
        print(f"🚨 重大エラー: WebDriverのセットアップに失敗しました。YML設定を確認してください: {e}")
        exit(1)

    
    print(f"=== UR空き情報監視スクリプト実行開始 (Selenium使用, {len(MONITORING_TARGETS)} 件) ===")
    
    current_status = get_current_status()
    print(f"⭐ 現在の通知状態 (status.json): {current_status}")
    
    vacancy_detected = False
    available_danchis = []
    results = []
    
    for danchi_info in MONITORING_TARGETS:
        result_text, is_available = check_vacancy_selenium(danchi_info, driver)
        results.append(result_text)
        
        time.sleep(1) 
        
        if is_available:
            vacancy_detected = True
            available_danchis.append(danchi_info)
    
    driver.quit()
        
    print("\n=== 全ての監視対象のチェックが完了しました ===")
    for res in results:
        print(f"- {res}")
        
    new_status = 'available' if vacancy_detected else 'not_available'

    if new_status == current_status:
        print(f"✅ 状態に変化なし ('{new_status}')。メール送信はスキップします。")
    else:
        print(f"🚨 状態が変化しました ('{current_status}' -> '{new_status}')。")
        
        if new_status == 'available':
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
            update_status(new_status)
            print("✅ '空きなし' への変化を確認しました。通知は行わず状態のみを更新します。")
    
    print("\n=== 監視終了 ===")
    
#EOF
