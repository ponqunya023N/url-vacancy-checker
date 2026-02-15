#!/usr/bin/env python3
# -- coding: utf-8 --

import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright, TimeoutError

# タイムゾーン／状態ファイル
JST = timezone(timedelta(hours=9))
STATUS_FILE = "status.json"

# 監視対象
TARGETS = {
    "【S/A】光が丘パークタウン プロムナード十番街": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4350.html",
    "【A/C】光が丘パークタウン 公園南": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3500.html",
    "【A/B】光が丘パークタウン 四季の香弐番街": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4100.html",
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
        # 強制終了を避けるためタイムアウト設定を適切に
        page.goto(url, timeout=40000, wait_until="load")
        
        try:
            page.wait_for_selector("tbody.rep_room tr", timeout=15000)
        except TimeoutError:
            pass

        rows = page.query_selector_all("tbody.rep_room tr")
        print(f"[{timestamp()}] [DEBUG] {name}: {len(rows)}件検出")

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

                    # 画像取得：以前の成功パターンに戻しつつクラス指定を維持
                    img_url = ""
                    img_elem = row.query_selector("img.rep_room-madori-src")
                    if not img_elem:
                        img_elem = row.query_selector("div.item_image img")

                    if img_elem:
                        src = img_elem.get_attribute("src")
                        if src and "icn_" not in src and "button" not in src:
                            img_url = urllib.parse.urljoin("https://www.ur-net.go.jp", src)

                    # 部屋名（建物名含む）をIDとして保持し、詳細データを作成
                    result["details"].append({
                        "room_id": room_name, 
                        "text": f"🏢 <b>{room_name}</b>\n家賃: {rent} (共益費: {common})",
                        "img_url": img_url
                    })
                except Exception as e:
                    print(f"  [DEBUG] 部屋{i} エラー: {e}")
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

# 新しい部屋のみを送信するように引数を変更
def send_telegram(name: str, url: str, new_rooms_details: list) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return

    def call_api(method, payload):
        api_url = f"https://api.telegram.org/bot{token}/{method}"
        req = urllib.request.Request(api_url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as response:
            return response.read()

    try:
        # メッセージの見出し（新しい空室のみであることを明記）
        call_api("sendMessage", {
            "chat_id": chat_id,
            "text": f"🌟 <b>UR空室発見（新着）！</b>\n\n物件: <b>{name}</b>\n🔗 <a href='{url}'>物件詳細ページ</a>\n⏰ {timestamp()}",
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        })
        # 新しい部屋の分だけを通知
        for detail in new_rooms_details:
            if detail["img_url"]:
                try:
                    call_api("sendPhoto", {"chat_id": chat_id, "photo": detail["img_url"], "caption": detail["text"], "parse_mode": "HTML"})
                except:
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
            
            # 過去に通知済みの部屋リストを取得（古い形式のデータだった場合は空リストにする）
            prev_rooms = prev.get(name, [])
            if not isinstance(prev_rooms, list):
                prev_rooms = []

            # 現在見つかった部屋のID（部屋名）リスト
            current_rooms = [d["room_id"] for d in res["details"]]

            print(f"[{timestamp()}] {name}: {s} (現在{len(current_rooms)}件 / 前回保存{len(prev_rooms)}件)")

            if s in ["error", "unknown"]:
                # エラー時は前回のリストをそのまま引き継ぐ（不用意に空にしない）
                next_status_data[name] = prev_rooms
            elif s == "not_available":
                # 空室なしの場合はリストを空にする（これで次に出た時に新着扱いになる）
                # ただし、URの不安定対策として、一時的に空になっただけなら前回の情報を残す判断もあり
                # ここでは仕様通り、空室なしとして記録する
                next_status_data[name] = []
            else:
                # 「現在ある部屋」の中で「前回保存されたリスト」に入っていないものだけを抽出
                new_rooms_details = [d for d in res["details"] if d["room_id"] not in prev_rooms]

                if new_rooms_details:
                    # 新しい部屋がある場合のみ通知
                    send_telegram(name, url, new_rooms_details)
                
                # 最新の部屋リストを保存用データにセット
                next_status_data[name] = current_rooms

        browser.close()
    
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(next_status_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
