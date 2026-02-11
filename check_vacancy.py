#!/usr/bin/env python3
# -- coding: utf-8 --

import os
from playwright.sync_api import sync_playwright, TimeoutError

def debug_check():
    # 四季の香弐番街のURLをセットしました
    url = "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4100.html"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print(f"--- [START] Accessing: {url} ---")
        
        try:
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            # 部屋のリストが表示されるまで最大10秒待機
            page.wait_for_selector("tbody.rep_room tr", timeout=10000)
            
            # 部屋の1行分（tr）を丸ごと取得
            row = page.query_selector("tbody.rep_room tr")
            if row:
                print("--- [RAW HTML DATA START] ---")
                # ここに家賃、共益費、間取図の「真のタグ名」が含まれています
                print(row.inner_html())
                print("--- [RAW HTML DATA END] ---")
            else:
                print("【警告】空室テーブルが見つかりませんでした。ページ読み込みに失敗した可能性があります。")
                
        except Exception as e:
            print(f"Error during debug: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    debug_check()
