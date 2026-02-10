#!/usr/bin/env python3
# -- coding: utf-8 --

import os
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright, TimeoutError

# タイムゾーン／状態ファイル
JST = timezone(timedelta(hours=9))
STATUS_FILE = "status.json"

# 監視対象（名前→URL）
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

def judge_vacancy(browser, url: str) -> str:
    """
    空室判定ロジック:
    - 高速化のため要素の出現を待機する。
    """
    page = browser.new_page()
    try:
        # タイムアウトを15秒に設定
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        
        # 状態が判明するまで最大8秒待機
        try:
            page.wait_for_selector("tbody.rep_room tr, .err-box.err-box--empty-room", timeout=8000)
        except TimeoutError:
            pass 

        # 1. 空室あり判定
        if page.query_selector("tbody.rep_room tr") or page.query_selector("a.rep_room-link"):
            return "available"

        # 2. 空室なし判定
        empty_box = page.query_selector("div.err-box.err-box--empty-room")
        if empty_box:
            text = (empty_box.inner_text() or "").strip()
            if "ございません" in text:
                return "not_available"

        return "unknown"
    except Exception as e:
        print(f"Error accessing {url}: {e}")
        return "error"
    finally:
        page.close()

def check_targets() -> dict:
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, url in TARGETS.items():
            status = judge_vacancy(browser, url)
            print(f"[{timestamp()}] {name}: {status}")
            results[name] = status
        browser.close()
    return results

def load_status() -> dict:
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {name: "not_available" for name in TARGETS.keys()}

def save_status(status: dict) -> None:
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

def send_mail(name: str, url: str, prev_state: str, current_state: str) -> None:
    subject = f"UR空き {name}"
    body = (
        f"物件名: {name}\n"
        f"URL: {url}\n"
        f"判定: {prev_state} → {current_state}\n"
        f"確認日時: {timestamp()}"
    )
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = os.getenv("FROM_EMAIL")
    msg["To"] = os.getenv("TO_EMAIL")

    try:
        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = os.getenv("SMTP_PORT")
        if not all([smtp_server, smtp_port]):
            return

        with smtplib.SMTP(smtp_server, int(smtp_port)) as server:
            server.starttls()
            server.login(os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD"))
            server.send_message(msg)
        print(f"[{timestamp()}] Mail sent for {name}")
    except Exception as e:
        print(f"Mail error: {e}")

def main() -> None:
    prev = load_status()
    current = check_targets()

    # manual_run = os.getenv("MANUAL_RUN") == "true"

    for n, s in current.items():
        if s in ["error", "unknown"]:
            current[n] = prev.get(n, "not_available")
            continue

        # Cloudflareからの実行も通常の定期監視として扱う
        # if manual_run:
        #     if s == "available":
        #         send_mail(n, TARGETS[n], "manual_check", s)
        # else:
        prev_state = prev.get(n, "not_available")
        if prev_state == "not_available" and s == "available":
            send_mail(n, TARGETS[n], prev_state, s)

    save_status(current)
    print(f"[{timestamp()}] Status file updated.")

if __name__ == "__main__":
    main()
