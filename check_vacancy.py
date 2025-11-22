#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

RUN_MODE = os.getenv("RUN_MODE", "scheduled").lower()
JST = timezone(timedelta(hours=9))
STATUS_FILE = "status.json"

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

def timestamp():
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

def judge_vacancy(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=30000)
        page.wait_for_selector("body")

        if page.query_selector("div.err-box.err-box--empty-room"):
            return "not_available"

        rows = page.query_selector_all("tbody.rep_room tr")
        if rows:
            return "available"

        return "unknown"

def check_targets():
    results = {}
    for name, url in TARGETS.items():
        status = judge_vacancy(url)
        print(f"[{timestamp()}] {name}: {status}")
        results[name] = status
    return results

def load_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_status(status):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

def send_mail(name, url):
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

def main():
    prev = load_status()
    current = check_targets()

    if RUN_MODE == "manual":
        available_now = [(n, TARGETS[n]) for n, s in current.items() if s == "available"]
        for name, url in available_now:
            send_mail(name, url)
        save_status(current)
        return

    if not prev:
        print(f"[{timestamp()}] 初回実行: 状態保存のみ")
        save_status(current)
        return

    new_vacancies = [(n, TARGETS[n]) for n, s in current.items() if prev.get(n) == "not_available" and s == "available"]
    for name, url in new_vacancies:
        send_mail(name, url)

    save_status(current)

if __name__ == "__main__":
    main()
