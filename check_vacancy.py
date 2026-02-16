#!/usr/bin/env python3
# -- coding: utf-8 --

import os
import json
import urllib.request
import urllib.parse
import hashlib
import re
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright, TimeoutError

# タイムゾーン／状態ファイル
JST = timezone(timedelta(hours=9))
STATUS_FILE = "status.json"

def timestamp() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

# 暗号化（ハッシュ化）用の関数を追加
def make_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]

# Secretsから読み込んだ文字列をリストに変換する関数を追加
def parse_targets(raw_str: str) -> list:
    targets = []
    if not raw_str: return targets
    parts = raw_str.split(',')
    for part in parts:
        if '|' in part:
            name, url = part.strip().split('|', 1)
            targets.append((name.strip(), url.strip()))
    return targets

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
        
        # ログには名前を出さず、プレフィックスのみ出力する
        match = re.match(r'(【.*?】)', name)
        prefix = match.group(1) if match else "【不明】"
        print(f"[{timestamp()}] [DEBUG] {prefix}***: {len(rows)}件検出")

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

                    # 部屋名（建物名含む）の詳細データを作成し、json保存用の暗号化IDも持たせる
                    result["details"].append({
                        "room_hash": make_hash(room_name), 
                        "text": f"🏢 <b>{room_name}</b>\n家賃: {rent} (共益費: {common})",
                        "img_url": img_url
                    })
                except Exception:
                    # エラーログの隠蔽（詳細は出さない）
                    print(f"  [DEBUG] 部屋データ取得エラー（詳細は秘匿されています）")
                    continue
            
            if found_valid_room:
                result["status"] = "available"
                return result

        if "ございません" in page.content() or page.query_selector(".err-box"):
            result["status"] = "not_available"
        
        return result
    except Exception:
        # エラーログの徹底的な隠蔽（URLや物件名は出さない）
        print(f"[{timestamp()}] 通信エラー発生（対象URL等の詳細は秘匿されています）")
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
    except Exception:
        # エラーログの隠蔽
        print("Telegram送信エラー（詳細は秘匿されています）")

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
    
    # Secretsから物件リストを取得
    raw_targets = os.getenv("TARGET_URLS", "")
    targets_list = parse_targets(raw_targets)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, url in targets_list:
            # json記録用の暗号化キー（【プレフィックス】＋ハッシュ）を作成
            match = re.match(r'(【.*?】)', name)
            prefix = match.group(1) if match else "【不明】"
            safe_key = f"{prefix}{make_hash(name)}"

            res = judge_vacancy(browser, name, url)
            s = res["status"]
            
            # 過去に通知済みの部屋リストを取得（暗号化された部屋番号のリスト）
            prev_rooms_hashes = prev.get(safe_key, [])
            if not isinstance(prev_rooms_hashes, list):
                prev_rooms_hashes = []

            # 現在見つかった部屋の暗号化IDリスト
            current_rooms_hashes = [d["room_hash"] for d in res["details"]]

            print(f"[{timestamp()}] {safe_key}: {s} (現在{len(current_rooms_hashes)}件 / 前回保存{len(prev_rooms_hashes)}件)")

            if s in ["error", "unknown"]:
                # エラー時は前回のリストをそのまま引き継ぐ（不用意に空にしない）
                next_status_data[safe_key] = prev_rooms_hashes
            elif s == "not_available":
                # 空室なしの場合はリストを空にする
                next_status_data[safe_key] = []
            else:
                # 「現在ある部屋」の中で「前回保存されたリスト」に入っていないものだけを抽出
                new_rooms_details = [d for d in res["details"] if d["room_hash"] not in prev_rooms_hashes]

                if new_rooms_details:
                    # 新しい部屋がある場合のみ通知（通知には実際の名前を渡す）
                    send_telegram(name, url, new_rooms_details)
                
                # 最新の暗号化された部屋リストを保存用データにセット
                next_status_data[safe_key] = current_rooms_hashes

        browser.close()
    
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(next_status_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
