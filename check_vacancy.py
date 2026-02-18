001 #!/usr/bin/env python3
002 # -- coding: utf-8 --
003
004 import os
005 import json
006 import urllib.request
007 import urllib.parse
008 import hashlib
009 import re
010 from datetime import datetime, timedelta, timezone
011 from playwright.sync_api import sync_playwright, TimeoutError
012
013 # タイムゾーン／状態ファイル
014 JST = timezone(timedelta(hours=9))
015 STATUS_FILE = "status.json"
016
017 def timestamp() -> str:
018     return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
019
020 # 暗号化（ハッシュ化）用の関数
021 def make_hash(text: str) -> str:
022     # 前後の空白による揺らぎを防ぐためstrip()を適用
023     clean_text = text.strip()
024     return hashlib.sha256(clean_text.encode('utf-8')).hexdigest()[:12]
025
026 # Secretsから読み込んだ文字列をリストに変換
027 def parse_targets(raw_str: str) -> list:
028     targets = []
029     if not raw_str: return targets
030     parts = raw_str.split(',')
031     for part in parts:
032         if '|' in part:
033             name, url = part.strip().split('|', 1)
034             targets.append((name.strip(), url.strip()))
035     return targets
036
037 def judge_vacancy(browser, name: str, url: str) -> dict:
038     page = browser.new_page()
039     result = {"status": "unknown", "details": []}
040     try:
041         # 強制終了を避けるためタイムアウト設定を適切に
042         page.goto(url, timeout=40000, wait_until="load")
043         
044         try:
045             page.wait_for_selector("tbody.rep_room tr", timeout=15000)
046         except TimeoutError:
047             pass
048
049         rows = page.query_selector_all("tbody.rep_room tr")
050         
051         # ログには名前を出さず、プレフィックスのみ出力する
052         match = re.match(r'(【.*?】)', name)
053         prefix = match.group(1) if match else "【不明】"
054         # 検出件数のみまず出力（ハッシュ詳細はmain側で判定後にログ出力）
055         print(f"[{timestamp()}] [DEBUG] {prefix}***: {len(rows)}件検出")
056
057         if rows:
058             found_valid_room = False
059             for i, row in enumerate(rows, 1):
060                 try:
061                     rent_elem = row.query_selector("span.rep_room-price")
062                     if not rent_elem: continue
063                     rent = rent_elem.inner_text().strip()
064                     if not rent or rent == "不明": continue
065
066                     found_valid_room = True
067                     common_elem = row.query_selector("span.rep_room-commonfee")
068                     room_name_elem = row.query_selector("td.rep_room-name")
069                     
070                     common = common_elem.inner_text().strip() if common_elem else ""
071                     room_name = room_name_elem.inner_text().strip() if room_name_elem else f"部屋{i}"
072
073                     # 画像取得
074                     img_url = ""
075                     img_elem = row.query_selector("img.rep_room-madori-src")
076                     if not img_elem:
077                         img_elem = row.query_selector("div.item_image img")
078
079                     if img_elem:
080                         src = img_elem.get_attribute("src")
081                         if src and "icn_" not in src and "button" not in src:
082                             img_url = urllib.parse.urljoin("https://www.ur-net.go.jp", src)
083
084                     # 部屋名（建物名含む）の詳細データを作成し、json保存用の暗号化IDも持たせる
085                     result["details"].append({
086                         "room_hash": make_hash(room_name), 
087                         "text": f"🏢 <b>{room_name}</b>\n家賃: {rent} (共益費: {common})",
088                         "img_url": img_url
089                     })
090                 except Exception:
091                     # エラーログの隠蔽
092                     print(f"  [DEBUG] 部屋データ取得エラー（詳細は秘匿されています）")
093                     continue
094             
095             if found_valid_room:
096                 result["status"] = "available"
097                 return result
098
099         if "ございません" in page.content() or page.query_selector(".err-box"):
100             result["status"] = "not_available"
101         
102         return result
103     except Exception:
104         # エラーログの徹底的な隠蔽
105         print(f"[{timestamp()}] 通信エラー発生（対象URL等の詳細は秘匿されています）")
106         result["status"] = "error"
107         return result
108     finally:
109         page.close()
110
111 def send_telegram(name: str, url: str, new_rooms_details: list) -> None:
112     token = os.getenv("TELEGRAM_BOT_TOKEN")
113     chat_id = os.getenv("TELEGRAM_CHAT_ID")
114     if not token or not chat_id: return
115
116     def call_api(method, payload):
117         api_url = f"https://api.telegram.org/bot{token}/{method}"
118         req = urllib.request.Request(api_url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
119         with urllib.request.urlopen(req) as response:
120             return response.read()
121
122     try:
123         call_api("sendMessage", {
124             "chat_id": chat_id,
125             "text": f"🌟 <b>UR空室発見（新着）！</b>\n\n物件: <b>{name}</b>\n🔗 <a href='{url}'>物件詳細ページ</a>\n⏰ {timestamp()}",
126             "parse_mode": "HTML",
127             "disable_web_page_preview": True
128         })
129         for detail in new_rooms_details:
130             if detail["img_url"]:
131                 try:
132                     call_api("sendPhoto", {"chat_id": chat_id, "photo": detail["img_url"], "caption": detail["text"], "parse_mode": "HTML"})
133                 except:
134                     call_api("sendMessage", {"chat_id": chat_id, "text": detail["text"], "parse_mode": "HTML"})
135             else:
136                 call_api("sendMessage", {"chat_id": chat_id, "text": detail["text"], "parse_mode": "HTML"})
137     except Exception:
138         print("Telegram送信エラー（詳細は秘匿されています）")
139
140 def main() -> None:
141     if os.path.exists(STATUS_FILE):
142         try:
143             with open(STATUS_FILE, "r", encoding="utf-8") as f:
144                 prev = json.load(f)
145         except:
146             prev = {}
147     else:
148         prev = {}
149
150     next_status_data = {}
151     
152     raw_targets = os.getenv("TARGET_URLS", "")
153     targets_list = parse_targets(raw_targets)
154
155     with sync_playwright() as p:
156         browser = p.chromium.launch(headless=True)
157         for name, url in targets_list:
158             match = re.match(r'(【.*?】)', name)
159             prefix = match.group(1) if match else "【不明】"
160             safe_key = f"{prefix}{make_hash(name)}"
161
162             res = judge_vacancy(browser, name, url)
163             s = res["status"]
164             
165             # 過去に通知済みの部屋ハッシュリストを取得
166             prev_notified_hashes = prev.get(safe_key, [])
167             if not isinstance(prev_notified_hashes, list):
168                 prev_notified_hashes = []
169
170             # 現在見つかった部屋のハッシュリスト
171             current_rooms_hashes = [d["room_hash"] for d in res["details"]]
172             
173             # 【変更点】ログにハッシュ値を表示するように追加
174             hash_log = ", ".join(current_rooms_hashes) if current_rooms_hashes else "なし"
175             print(f"[{timestamp()}] {safe_key}: {s} (現在ハッシュ: {hash_log} / 保存済み数: {len(prev_notified_hashes)}件)")
176
177             if s in ["error", "unknown"]:
178                 # エラー時はこれまでの履歴をそのまま維持
179                 next_status_data[safe_key] = prev_notified_hashes
180             elif s == "not_available":
181                 # 【重要】空室なしでも、過去に通知した履歴は消さずに保持し続ける
182                 next_status_data[safe_key] = prev_notified_hashes
183             else:
184                 # 現在ある部屋の中で、まだ過去の履歴に含まれていないもの（＝本当の新着）だけを抽出
185                 new_rooms_details = [d for d in res["details"] if d["room_hash"] not in prev_notified_hashes]
186
187                 if new_rooms_details:
188                     send_telegram(name, url, new_rooms_details)
189                 
190                 # 【重要】今回見つかったハッシュを既存の履歴に統合（重複は排除）して保存
191                 # これにより「一度でも見つけた部屋」は永続的に記憶される
192                 updated_history = list(set(prev_notified_hashes + current_rooms_hashes))
193                 next_status_data[safe_key] = updated_history
194
195         browser.close()
196     
197     with open(STATUS_FILE, "w", encoding="utf-8") as f:
198         json.dump(next_status_data, f, ensure_ascii=False, indent=2)
199
200 if __name__ == "__main__":
201     main()
