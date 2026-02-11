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

# 監視対象（ご指定の11件 + テスト用1件 = 計12件）
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
    "【Eテスト】千葉ニュータウン小室ハイランド": "https://www.ur-net.go.jp/chintai/kanto/chiba/40_3030.html",
}

def timestamp() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

def judge_vacancy(browser, url: str) -> dict:
    page = browser.new_page()
    result = {"status": "unknown", "details": []}
    try:
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("tbody.rep_room tr, .err-box.err-box--empty-room", timeout=8000)
        except TimeoutError:
            pass 

        rows = page.query_selector_all("tbody.rep_room tr")
        if rows:
            found_valid_room = False
            for row in rows:
                try:
                    rent_elem = row.query_selector("span.rep_room-price")
                    if not rent_elem: continue
                    rent = rent_elem.inner_text().strip()
                    if not rent or rent == "不明": continue

                    found_valid_room = True
                    common_elem = row.query_selector("span.rep_room-commonfee")
                    img_elem = row.query_selector("div.item_image img")
                    room_name_elem = row.query_selector("td.rep_room-name")

                    common = common_elem.inner_text().strip() if common_elem else ""
                    # 画像URLを絶対パスに変換
                    img_url = img_elem.get_attribute("src") if img_elem else ""
                    if img_url and img_url.startswith("/"):
                        img_url = "https://www.ur-net.go.jp" + img_url
                    
                    room_name = room_name_elem.inner_text().strip() if room_name_elem else ""

                    result["details"].append({
                        "text": f"🏢 <b>{room_name}</b>\n家賃: {rent} (共益費: {common})",
                        "img_url": img_url
                    })
                except:
                    continue
            
            if found_valid_room:
                result["status"] = "available"
                return result

        empty_box = page.query_selector("div.err-box.err-box--empty-room")
        if empty_box and "ございません" in (empty_box.inner_text() or ""):
            result["status"] = "not_available"
            return result

        return result
    except Exception:
        result["status"] = "error"
        return result
    finally:
        page.close()

def send_telegram(name: str, url: str, current_res: dict) -> None:
    """Telegram Bot APIを使用して画像付きで通知"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return

    # 1. まずメインの見出しを送信
    head_message = (
        f"🌟 <b>UR空室発見！</b>\n\n"
        f"物件: <b>{name}</b>\n"
        f"🔗 <a href='{url}'>物件詳細ページを開く</a>\n"
        f"⏰ 確認: {timestamp()}"
    )
    
    def call_api(method, payload):
        api_url = f"https://api.telegram.org/bot{token}/{method}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(api_url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as response:
            pass

    try:
        # メイン通知の送信
        call_api("sendMessage", {
            "chat_id": chat_id,
            "text": head_message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        })

        # 2. 部屋ごとの詳細と画像を送信
        for detail in current_res["details"]:
            if detail["img_url"]:
                # 画像がある場合は sendPhoto
                call_api("sendPhoto", {
                    "chat_id": chat_id,
                    "photo": detail["img_url"],
                    "caption": detail["text"],
                    "parse_mode": "HTML"
                })
            else:
                # 画像がない場合は sendMessage
                call_api("sendMessage", {
                    "chat_id": chat_id,
                    "text": detail["text"],
                    "parse_mode": "HTML"
                })
    except Exception as e:
        print(f"Telegram Send Error: {e}")

def main() -> None:
    # ステータスロード
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                prev = json.load(f)
        except:
            prev = {name: "not_available" for name in TARGETS.keys()}
    else:
        prev = {name: "not_available" for name in TARGETS.keys()}

    next_status_data = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, url in TARGETS.items():
            res = judge_vacancy(browser, url)
            s = res["status"]
            print(f"[{timestamp()}] {name}: {s}")

            if s in ["error", "unknown"]:
                next_status_data[name] = prev.get(name, "not_available")
                continue

            # 通知ロジック
            if prev.get(name) == "not_available" and s == "available":
                send_telegram(name, url, res)
            
            next_status_data[name] = s
        browser.close()

    # ステータス保存
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(next_status_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
