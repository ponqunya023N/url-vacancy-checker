#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from typing import Tuple, Dict, List

import requests
from bs4 import BeautifulSoup

# ---------------------------
# 設定（編集可）
# ---------------------------
MONITORING_TARGETS = [
    {"danchi_name": "【S】光が丘パークタウン プロムナード十番街", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4350.html"},
    {"danchi_name": "【A】光が丘パークタウン 公園南", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3500.html"},
    {"danchi_name": "【A】光が丘パークタウン 四季の香弐番街", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4100.html"},
    {"danchi_name": "【B】光が丘パークタウン 大通り中央", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4550.html"},
    {"danchi_name": "【B】光が丘パークタウン いちょう通り八番街", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3910.html"},
    {"danchi_name": "【C】光が丘パークタウン 大通り南", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_3690.html"},
    {"danchi_name": "【D】グリーンプラザ高松", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4650.html"},
    {"danchi_name": "【E】(赤塚)アーバンライフゆりの木通り東", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_4590.html"},
    {"danchi_name": "【F】(赤塚古い)むつみ台", "url": "https://www.ur-net.go.jp/chintai/kanto/tokyo/20_2410.html"}
]

# 空きなしを示す正確な判定文字列（あなた指定）
NO_VACANCY_PHRASE = "当サイトからすぐにご案内できるお部屋がございません"

# ファイル/ログ名
STATUS_FILE = "status.json"
LOG_FILE = "check_vacancy.log"

# HTTP 設定
REQUEST_TIMEOUT = 15  # 秒
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 3]  # 秒（最初の再試行、2回目の再試行）

# SMTP 環境変数（必須）
SMTP_SERVER = os.environ.get("SMTP_SERVER")
SMTP_PORT = os.environ.get("SMTP_PORT")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
FROM_EMAIL = os.environ.get("FROM_EMAIL")
TO_EMAIL = FROM_EMAIL  # 仕様どおり送信先は FROM_EMAIL を使う


# ---------------------------
# ヘルパー関数
# ---------------------------
def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S JST")


def append_log(message: str) -> None:
    ts = now_iso()
    line = f"[{ts}] {message}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        # ログファイル書き込み失敗でも処理は継続
        pass


def load_status() -> Dict[str, str]:
    initial = {d["danchi_name"]: "not_available" for d in MONITORING_TARGETS}
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
            # Ensure keys exist
            return {name: saved.get(name, "not_available") for name in initial}
    except Exception:
        return initial


def save_status(statuses: Dict[str, str]) -> None:
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(statuses, f, indent=4, ensure_ascii=False)
        append_log("📄 状態ファイルを更新しました。")
    except Exception as e:
        append_log(f"🚨 状態ファイル書き込みエラー: {e}")


def send_alert_email(subject: str, body: str) -> bool:
    if not all([SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL]):
        append_log("🚨 メール送信に必要な環境変数が未設定です。送信をスキップします。")
        return False
    try:
        now = now_iso()
        msg = MIMEText(f"{body}\n\n(実行時刻: {now})", "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = FROM_EMAIL
        msg["To"] = TO_EMAIL

        with smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT), timeout=30) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        append_log(f"✅ メール送信: {TO_EMAIL} (件名: {subject})")
        return True
    except Exception as e:
        append_log(f"🚨 メール送信エラー: {e}")
        return False


# ---------------------------
# ページ取得＆判定ロジック
# ---------------------------
def fetch_page(url: str) -> Tuple[int, str]:
    """GETしてステータスコードとテキストを返す。タイムアウト/例外は再試行する"""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; URVacancyChecker/1.0; +https://github.com/)"
    }
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            append_log(f"HTTP GET: {url} (attempt {attempt})")
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            return resp.status_code, resp.text
        except Exception as e:
            last_exc = e
            append_log(f"⚠ GET error (attempt {attempt}): {e}")
            if attempt <= len(RETRY_BACKOFF):
                time.sleep(RETRY_BACKOFF[attempt - 1])
            else:
                time.sleep(RETRY_BACKOFF[-1])
    append_log(f"🚨 GET failed after {MAX_RETRIES} attempts: {last_exc}")
    return 0, ""


def normalize_text(s: str) -> str:
    if s is None:
        return ""
    return s.replace("\u00A0", " ").strip()


def detect_vacancy_from_html(html: str) -> Tuple[str, str]:
    """
    returns (status, reason)
      status: "available" or "not_available" or "uncertain"
      reason: human-readable reason
    判定ルール（あなた指定）:
      - ページ内に NO_VACANCY_PHRASE が存在する -> not_available
      - それ以外 -> available
    """
    if not html:
        return "uncertain", "no_html"
    text = normalize_text(html)
    if NO_VACANCY_PHRASE in text:
        return "not_available", f"found_phrase:{NO_VACANCY_PHRASE}"
    else:
        return "available", "phrase_not_found"


# ---------------------------
# メイン処理
# ---------------------------
def main():
    append_log("=== UR空き情報監視開始 ===")
    append_log(f"対象団地数: {len(MONITORING_TARGETS)}")

    current_statuses = load_status()
    append_log(f"🔁 現在のステータス読み込み: {current_statuses}")

    all_new_statuses = current_statuses.copy()
    newly_available = []  # list of dicts

    results = []

    for danchi in MONITORING_TARGETS:
        name = danchi["danchi_name"]
        url = danchi["url"]
        append_log(f"--- チェック開始: {name} ---")
        status_code, html = fetch_page(url)
        append_log(f"HTTP status: {status_code}")

        if status_code != 200:
            append_log(f"⚠ {name}: HTTP {status_code} 取得失敗または非200。uncertain として扱います。")
            detected, reason = "uncertain", f"http_{status_code}"
        else:
            detected, reason = detect_vacancy_from_html(html)

        # normalize unsure handling: per spec, treat only exact phrase indicates no vacancy
        if detected == "available":
            append_log(f"{name}: 判定 -> available (理由: {reason})")
            all_new_statuses[name] = "available"
            results.append(f"空きあり: {name} ({reason})")
            if current_statuses.get(name) == "not_available":
                newly_available.append(danchi)
        elif detected == "not_available":
            append_log(f"{name}: 判定 -> not_available (理由: {reason})")
            all_new_statuses[name] = "not_available"
            results.append(f"空きなし: {name} ({reason})")
        else:  # uncertain
            append_log(f"{name}: 判定 -> uncertain (理由: {reason}) -- 通知は行わない")
            all_new_statuses[name] = current_statuses.get(name, "not_available")
            results.append(f"不確実: {name} ({reason})")

        # small pause to be polite
        time.sleep(0.5)

    # 結果ログ出力
    append_log("=== チェック結果 ===")
    for r in results:
        append_log(r)

    # 通知処理（not_available -> available の変化のみ）
    if newly_available:
        append_log(f"🚨 新規空き検出: {len(newly_available)} 件")
        for d in newly_available:
            subject = f"【UR空き情報】{d['danchi_name']}"
            body = (
                f"以下の団地で空き情報が出た可能性があります！\n\n"
                f"・【団地名】: {d['danchi_name']}\n"
                f"  【URL】: {d['url']}\n"
            )
            send_alert_email(subject, body)
            time.sleep(1)
    else:
        append_log("✅ 新規空きはありませんでした。")

    # 状態を書き出す（必ず書き換える）
    save_status(all_new_statuses)
    append_log("=== 監視終了 ===")


if __name__ == "__main__":
    main()
