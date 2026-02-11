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

        # ★【解析の要】実際に読み込まれたHTMLの「部屋リスト部分」をログに出力します
        html_content = page.query_selector("tbody.rep_room")
        if html_content:
            print(f"--- [DEBUG] HTML STRUCTURE START ---")
            print(html_content.inner_html())
            print(f"--- [DEBUG] HTML STRUCTURE END ---")

        rows = page.query_selector_all("tbody.rep_room tr")
        if rows:
            result["status"] = "available"
            for row in rows:
                # 現状の当てずっぽうロジック
                rent_val = row.query_selector("td.rent .item-val") or row.query_selector("td.rent")
                common_val = row.query_selector("td.common .item-val") or row.query_selector("td.common")
                rent = rent_val.inner_text().strip() if rent_val else "不明"
                common = common_val.inner_text().strip() if common_val else "不明"
                img_elem = row.query_selector("td.floor_plan img")
                img_url = img_elem.get_attribute("src") if img_elem else "なし"
                result["details"].append(f"・家賃: {rent} / 共益費: {common}\n  間取図(小): {img_url}")
            return result

        return result
    except Exception as e:
        print(f"Error accessing {url}: {e}")
        return result
    finally:
        page.close()

def main() -> None:
    # デバッグ用に1件だけチェック
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        name = list(TARGETS.keys())[0]
        url = TARGETS[name]
        print(f"--- Debug Checking: {name} ---")
        judge_vacancy(browser, url)
        browser.close()

if __name__ == "__main__":
    main()
