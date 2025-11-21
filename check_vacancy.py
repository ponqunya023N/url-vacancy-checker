import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import json
import time
import asyncio
# ❗ Playwright版に必要なモジュール
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# --- 監視対象リスト (変更なし) ---
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

# --- メール設定/状態管理 (変更なし) ---
SMTP_SERVER = os.environ.get('SMTP_SERVER')
SMTP_PORT = os.environ.get('SMTP_PORT')
SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
FROM_EMAIL = os.environ.get('FROM_EMAIL')
TO_EMAIL = FROM_EMAIL

def get_current_status():
    initial_status = {d['danchi_name']: 'not_available' for d in MONITORING_TARGETS}
    try:
        with open('status.json', 'r') as f:
            saved_status = json.load(f)
            return {name: saved_status.get(name, 'not_available') for name in initial_status}
    except (FileNotFoundError, json.JSONDecodeError):
        print("⚠ status.jsonが見つからない、または破損しているため、初期状態を使用します。")
        return initial_status
    except Exception as e:
        print(f"🚨 状態ファイル読み込み中の予期せぬエラー: {e}")
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

# --- Playwright版 空室チェック (最終確定版) ---
async def check_vacancy_playwright(danchi, page):
    danchi_name = danchi["danchi_name"]
    url = danchi["url"]
    print(f"\n--- チェック開始: {danchi_name} ---")
    print(f"URL: {url}")

    # 部屋リストのテーブルが存在する領域のCSSセレクタ
    ROOM_LIST_CONTAINER_SELECTOR = "div.search-conditions" 

    try:
        # ページへ移動。タイムアウトは30秒。
        await page.goto(url, timeout=30000)
        
        # ページコンテンツ全体を取得 (判定1用)
        page_source = await page.content()

        # 【判定1】 空きなしの決定的証拠 (Negative Confirmation)
        if "当サイトからすぐにご案内できるお部屋がございません" in page_source:
            print("✅ 空きなし確認 (メッセージ検出)")
            return f"空きなし: {danchi_name}", False

        # 【判定2】 空きありの決定的証拠 (Positive Confirmation - 構造と文字列を複合)
        try:
            # 部屋リストコンテナのロケーターを取得
            room_list_locator = page.locator(ROOM_LIST_CONTAINER_SELECTOR)
            
            # コンテナ内のテキストを非同期で取得
            room_list_text = await room_list_locator.inner_text(timeout=10000) 
            
            # コンテナ内に「間取り」という文字列が存在するかを確認
            if "間取り" in room_list_text:
                print("🚨 空きあり確認 (部屋リストの構造・文字列検出)")
                return f"空きあり: {danchi_name}", True
        except PlaywrightTimeoutError:
            # ロケーター内のテキスト取得がタイムアウトした場合、空きなしまたはページロード失敗とみなし、次の判定へ
            pass
        except Exception:
            # その他のロケーター関連エラー
            pass

        # 【判定3】 どちらでもない場合 (安全装置)
        print("❓ 判定不能 (構造不明) -> 通知しません")
        return f"判定不能: {danchi_name}", False

    except PlaywrightTimeoutError:
        print("⚠ ページロードタイムアウト (スキップ)")
        return f"判定不能(ロードエラー): {danchi_name}", False
    except Exception as e:
        print(f"🚨 予期せぬエラー発生: {e}")
        return f"エラー: {danchi_name}", False


# --- メイン処理 (非同期化) ---
async def main():
    print(f"=== UR空き情報監視開始 ({len(MONITORING_TARGETS)}件) ===")
    current_statuses = get_current_status()
    print(f"⭐ 現在ステータス: {current_statuses}")

    all_new_statuses = current_statuses.copy()
    newly_available = []
    results = []
    
    # Playwrightの非同期コンテキストマネージャを使用
    async with async_playwright() as p:
        # headlessモードでChromiumブラウザを起動
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for danchi in MONITORING_TARGETS:
            # 非同期関数を呼び出し
            res_text, is_available = await check_vacancy_playwright(danchi, page)
            results.append(res_text)
            
            # 団地ごとの処理を短く待機
            await asyncio.sleep(1) 
            
            name = danchi['danchi_name']
            
            if is_available:
                all_new_statuses[name] = 'available'
                if current_statuses.get(name) == 'not_available':
                    newly_available.append(danchi)
            else:
                all_new_statuses[name] = 'not_available'

        await browser.close()
    
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
            time.sleep(5) # メール送信間隔

    if all_new_statuses != current_statuses or newly_available:
        update_status(all_new_statuses)
        print("✅ 状態ファイル更新完了")
    else:
        print("✅ 状態に変化なし。状態ファイルの更新はスキップします。")

if __name__ == "__main__":
    # Python 3.7+ の標準的な非同期実行
    asyncio.run(main())
