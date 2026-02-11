#!/usr/bin/env python3
# -- coding: utf-8 --

import os
from playwright.sync_api import sync_playwright, TimeoutError

def debug_check():
    # 最も空室が出やすい「公園南」をターゲットに解析します
    url = "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3500.html"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print(f"--- [START] Accessing: {url} ---")
        
        try:
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            # 部屋のリストが表示されるまで待機
            page.wait_for_selector("tbody.rep_room tr", timeout=10000)
            
            # 部屋の1行分（tr）を丸ごと取得
            row = page.query_selector("tbody.rep_room tr")
            if row:
                print("--- [RAW HTML DATA START] ---")
                # ここで家賃や画像が隠れている「タグ名」や「クラス名」をすべて出力します
                print(row.inner_html())
                print("--- [RAW HTML DATA END] ---")
            else:
                print("空室が見つかりませんでした。テストのために空室がある物件URLに変えて実行してください。")
                
        except Exception as e:
            print(f"Error during debug: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    debug_check()
