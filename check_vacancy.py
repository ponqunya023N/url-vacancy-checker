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

def judge_vacancy(browser, url: str) -> dict:
    """
    空室判定ロジック:
    - 高速化のため要素の出現を待機する。
    - 空室時は家賃・共益費・間取図URLを抽出する。
    """
    page = browser.new_page()
    result = {"status": "unknown", "details": []}
    try:
        # タイムアウトを15秒に設定
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        
        # 状態が判明するまで最大8秒待機
        try:
            page.wait_for_selector("tbody.rep_room tr, .err-box.err-box--empty-room", timeout=8000)
        except TimeoutError:
            pass 

        # 1. 空室あり判定
        rows = page.query_selector_all("tbody.rep_room tr")
        if rows:
            result["status"] = "available"
            for row in rows:
                try:
                    # 家賃(rent)と共益費(common)を抽出
                    # URのHTML構造に合わせて、クラス内のテキストを柔軟に取得
                    rent_val = row.query_selector("td.rent .item-val") or row.query_selector("td.rent")
                    common_val = row.query_selector("td.common .item-val") or row.query_selector("td.common")
                    
                    rent = rent_val.inner_text().strip() if rent_val else "不明"
                    common = common_val.inner_text().strip() if common_val else "不明"
                    
                    # 間取図のサムネイルURLを抽出
                    # aタグのリンク先ではなく、imgタグのsrc(サムネイル)を取得
                    img_elem = row.query_selector("td.floor_plan img")
                    img_url = img_elem.get_attribute("src") if img_elem else "なし"
                    if img_url and img_url.startswith("/"):
                        img_url = "https://www.ur-net.go.jp" + img_url

                    result["details"].append(f"・家賃: {rent} / 共益費: {common}\n  間取図(小): {img_url}")
                except Exception as inner_e:
                    print(f"Detail extraction error: {inner_e}")
                    continue
            return result

        # 2. 空室なし判定
        empty_box = page.query_selector("div.err-box.err-box--empty-room")
        if empty_box:
            text = (empty_box.inner_text() or "").strip()
            if "ございません" in text:
                result["status"] = "not_available"
                return result

        return result
    except Exception as e:
        print(f"Error accessing {url}: {e}")
        result["status"] = "error"
        return result
    finally:
        page.close()

def check_targets() -> dict:
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, url in TARGETS.items():
            res_dict = judge_vacancy(browser, url)
            print(f"[{timestamp()}] {name}: {res_dict['status']}")
            results[name] = res_dict
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

def save_status(status_dict: dict) -> None:
    save_data = {n: s["status"] if isinstance(s, dict) else s for n, s in status_dict.items()}
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

def send_mail(name: str, url: str, prev_state: str, current_res: dict) -> None:
    current_state = current_res["status"]
    details_text = "\n".join(current_res["details"]) if current_res["details"] else "詳細データの抽出に失敗しました。"
    
    subject = f"UR空き {name}"
    body = (
        f"物件名: {name}\n"
        f"URL: {url}\n"
        f"判定: {prev_state} → {current_state}\n\n"
        f"【空室詳細情報】\n{details_text}\n\n"
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
    current_results = check_targets()

    next_status_data = {}

    for n, res in current_results.items():
        s = res["status"]
        if s in ["error", "unknown"]:
            next_status_data[n] = prev.get(n, "not_available")
            continue

        prev_state = prev.get(n, "not_available")
        if prev_state == "not_available" and s == "available":
            send_mail(n, TARGETS[n], prev_state, res)
        
        next_status_data[n] = s

    save_status(next_status_data)
    print(f"[{timestamp()}] Status file updated.")

if __name__ == "__main__":
    main()
