#!/usr/bin/env python3
# -- coding: utf-8 --

import os
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright, TimeoutError

# タイムゾーン／状態ファイル
JST = timezone(timedelta(hours=9))
STATUS_FILE = "status.json"

# 監視対象（URLは一切変更なし）
TARGETS = {
    "【S/A】光が丘パークタウン プロムナード十番街": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4350.html",
    "【A/C】光が丘パークタウン 公園南": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3500.html",
    "【A/B】光が丘パークタウン 四季の香弐番街": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4100.html",
    "【Eテスト】千葉ニュータウン小室ハイランド": "https://www.ur-net.go.jp/chintai/kanto/chiba/30_3300.html",
    "【A/A】光が丘パークタウン 大通り中央": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4550.html",
    "【B/B】光が丘パークタウン いちょう通り八番街": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3910.html",
    "【C/B】光が丘パークタウン 大通り南": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3690.html",
    "【D/A】(赤塚)アーバンライフゆりの木通り東": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4590.html",
    "【D/C】(赤塚)光が丘パークタウン ゆりの木通り３３番街": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_6801.html",
    "【D/D】(赤塚)むつみ台": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_2410.html",
    "【D/C】(赤塚)光が丘パークタウン ゆりの木通り北": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3470.html",
    "【E/A】(遠い)グリーンプラザ高松": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4650.html",
}

def timestamp() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

def judge_vacancy(browser, name: str, url: str) -> dict:
    page = browser.new_page()
    result = {"status": "unknown", "details": []}
    try:
        # 読み込み待機時間を少し長めに
        page.goto(url, timeout=30000, wait_until="networkidle")
        
        # 部屋一覧が出るまで待機
        try:
            page.wait_for_selector("tbody.rep_room tr", timeout=10000)
        except TimeoutError:
            pass

        rows = page.query_selector_all("tbody.rep_room tr")
        print(f"[{timestamp()}] [DEBUG] {name}: {len(rows)}件の行を検出")

        if rows:
            found_valid_room = False
            for i, row in enumerate(rows, 1):
                try:
                    rent_elem = row.query_selector("span.rep_room-price")
                    if not rent_elem: continue
                    rent = rent_elem.inner_text().strip()
                    if not rent or rent == "不明": continue

                    found_valid_room = True
                    common_elem = row.query_selector("span.rep_room-commonfee")
                    room_name_elem = row.query_selector("td.rep_room-name")
                    
                    common = common_elem.inner_text().strip() if common_elem else ""
                    room_name = room_name_elem.inner_text().strip() if room_name_elem else f"部屋{i}"

                    # 画像取得：一番上の部屋（i=1）は特に慎重に待機
                    img_url = ""
                    # 複数候補のセレクタ（クラス名優先）
                    selectors = ["img.rep_room-madori-src", "div.item_image img", ".rep_room-image img"]
                    
                    img_elem = None
                    for sel in selectors:
                        img_elem = row.query_selector(sel)
                        if img_elem: break

                    if img_elem:
                        # 最大5秒間、srcが有効になるまでチェック（特に1番上の部屋対策）
                        src = ""
                        for _ in range(10):
                            src = img_elem.get_attribute("src") or ""
                            if src.startswith("http") or (src.startswith("/") and "icn_" not in src):
                                break
                            time.sleep(0.5) # 0.5秒待機して再確認

                        if src and "icn_" not in src and "button" not in src:
                            img_url = urllib.parse.urljoin("https://www.ur-net.go.jp", src)
                        else:
                            print(f"  [DEBUG] 部屋{i}({room_name}): 画像URLが取得できませんでした (src: {src})")

                    print(f"  [DEBUG] 部屋{i}({room_name}): 取得 (家賃: {rent}, 画像: {img_url})")

                    result["details"].append({
                        "text": f"🏢 <b>{room_name}</b>\n家賃: {rent} (共益費: {common})",
                        "img_url": img_url
                    })
                except Exception as e:
                    print(f"  [DEBUG] 部屋{i} 抽出エラー: {e}")
                    continue
            
            if found_valid_room:
                result["status"] = "available"
                return result

        if "ございません" in page.content() or page.query_selector(".err-box"):
            result["status"] = "not_available"
        
        return result
    except Exception as e:
        print(f"[{timestamp()}] {name} 全体エラー: {e}")
        result["status"] = "error"
        return result
    finally:
        page.close()

# --- send_telegram, main 以降は変更なしのため省略せず全文表示を維持 ---

def send_telegram(name: str, url: str, current_res: dict) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return

    def call_api(method, payload):
        api_url = f"https://api.telegram.org/bot{token}/{method}"
        req = urllib.request.Request(
            api_url, 
            data=json.dumps(payload).encode("utf-8"), 
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            return response.read()

    try:
        call_api("sendMessage", {
            "chat_id": chat_id,
            "text": f"🌟 <b>UR空室発見！</b>\n\n物件: <b>{name}</b>\n🔗 <a href='{url}'>物件詳細ページ</a>\n⏰ {timestamp()}",
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        })

        for detail in current_res["details"]:
            if detail["img_url"]:
                try:
                    call_api("sendPhoto", {
                        "chat_id": chat_id,
                        "photo": detail["img_url"],
                        "caption": detail["text"],
                        "parse_mode": "HTML"
                    })
                except Exception as e:
                    print(f"  [DEBUG] Telegram画像送信失敗: {detail['img_url']} - {e}")
                    call_api("sendMessage", {"chat_id": chat_id, "text": detail["text"], "parse_mode": "HTML"})
            else:
                call_api("sendMessage", {"chat_id": chat_id, "text": detail["text"], "parse_mode": "HTML"})
    except Exception as e:
        print(f"Telegram全体送信エラー: {e}")

def main() -> None:
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                prev = json.load(f)
        except:
            prev = {}
    else:
        prev = {}

    next_status_data = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, url in TARGETS.items():
            res = judge_vacancy(browser, name, url)
            s = res["status"]
            print(f"[{timestamp()}] {name}: {s}")

            if s in ["error", "unknown"]:
                next_status_data[name] = prev.get(name, "not_available")
            else:
                if prev.get(name) == "not_available" and s == "available":
                    send_telegram(name, url, res)
                next_status_data[name] = s
        browser.close()

    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(next_status_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
