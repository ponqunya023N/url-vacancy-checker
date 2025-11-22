#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# JST ログ、status.json に状態を保存
JST = timezone(timedelta(hours=9))
STATUS_FILE = "status.json"

# 対象一覧（名前→URL）
TARGETS = {
    "【S】光が丘パークタウン プロムナード十番街": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4350.html",
    "【A】光が丘パークタウン 公園南": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3500.html",
    "【A】光が丘パークタウン 四季の香弐番街": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4100.html",
    "【B】光が丘パークタウン 大通り中央": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4550.html",
    "【B】光が丘パークタウン いちょう通り八番街": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3910.html",
    "【C】光が丘パークタウン 大通り南": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3690.html",
    "【D】グリーンプラザ高松": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4650.html",
    "【E】(赤塚)アーバンライフゆりの木通り東": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4590.html",
    "【F】(赤塚古い)むつみ台": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_2410.html",
}

def timestamp() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

def judge_vacancy(url: str) -> str:
    """
    判定仕様:
    - 空室あり: tbody.rep_room > tr が存在すれば available
                 または a.rep_room-link が存在すれば available
    - 空室なし: div.err-box.err-box--empty-room が「ございません」を含む場合 not_available
    - 上記のどちらでも確定できない場合: unknown
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=30000)
        page.wait_for_timeout(5000)  # JS描画待ち

        # 空室あり判定を最優先
        if page.query_selector("tbody.rep_room tr"):
            return "available"
        if page.query_selector("a.rep_room-link"):
            return "available"

        # 空室なし判定
        empty_box = page.query_selector("div.err-box.err-box--empty-room")
        if empty_box:
            text = (empty_box.inner_text() or "").strip()
            if "ございません" in text or "ご案内できるお部屋がございません" in text:
                return "not_available"

        return "unknown"

def check_targets() -> dict:
    results = {}
    for name, url in TARGETS.items():
        status = judge_vacancy(url)
        print(f"[{timestamp()}] {name}: {status}")
        results[name] = status
    return results

def initialize_status() -> dict:
    # 初回は全物件を not_available で初期化
    status = {name: "not_available" for name in TARGETS.keys()}
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    print(f"[{timestamp()}] 初回実行: 状態を not_available で初期化")
    return status

def load_status() -> dict:
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return initialize_status()

def save_status(status: dict) -> None:
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

def send_mail(name: str, url: str) -> None:
    subject = f"【UR空き物件】{name}"
    body = f"{name}\n{url}\n解析日時: {timestamp()}"
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = os.getenv("FROM_EMAIL")
    msg["To"] = os.getenv("TO_EMAIL")

    with smtplib.SMTP(os.getenv("SMTP_SERVER"), int(os.getenv("SMTP_PORT"))) as server:
        server.starttls()
        server.login(os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD"))
        server.send_message(msg)
    print(f"[{timestamp()}] メール送信完了: {subject}")

def main() -> None:
    prev = load_status()
    current = check_targets()

    # 差分通知（前回 not_available → 今回 available）
    new_vacancies = [(n, TARGETS[n]) for n, s in current.items()
                     if prev.get(n) == "not_available" and s == "available"]
    for name, url in new_vacancies:
        send_mail(name, url)

    save_status(current)

if __name__ == "__main__":
    main()
