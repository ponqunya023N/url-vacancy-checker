# ... (省略: import, SMTP設定などは変更なし)

# --- Playwright版 空室チェック (最終確定版 V3 - セレクタと待機時間を修正) ---
async def check_vacancy_playwright(danchi, page):
    danchi_name = danchi["danchi_name"]
    url = danchi["url"]
    print(f"\n--- チェック開始: {danchi_name} ---")
    print(f"URL: {url}")

    # ★変更点 1: 部屋リストのテーブルが存在する領域のCSSセレクタを修正
    ROOM_LIST_CONTAINER_SELECTOR = "section#room-list" 
    
    # ★変更点 2: タイムアウトを15秒 (15000ミリ秒) に延長
    TIMEOUT_MS = 15000 

    try:
        # ページへ移動。タイムアウトは30秒。
        await page.goto(url, timeout=30000)
        
        # 【判定2】 空きありの決定的証拠 (Positive Confirmation - 構造と文字列を複合)
        try:
            # 部屋リストコンテナのロケーターを取得
            room_list_locator = page.locator(ROOM_LIST_CONTAINER_SELECTOR)
            
            # コンテナ内のテキストを非同期で取得
            # 要素が見つかるまで最大15秒待機
            # タイムアウト時にPlaywrightTimeoutErrorが発生
            room_list_text = await room_list_locator.inner_text(timeout=TIMEOUT_MS) 
            
            # コンテナ内に「間取り」という文字列が存在するかを確認
            if "間取り" in room_list_text:
                print("🚨 空きあり確認 (部屋リストの構造・文字列検出)")
                return f"空きあり: {danchi_name}", True
            else:
                # 要素は見つかったが「間取り」がない場合 (部屋リストの構造が崩れた場合など)
                print("✅ 空きなし確認 (要素内テキストに間取りが見当たらない)")
                return f"空きなし: {danchi_name}", False
        except PlaywrightTimeoutError:
            # ロケーター内のテキスト取得がタイムアウトした場合、空きなしとみなす
            print("✅ 空きなし確認 (部屋リスト要素がタイムアウト)")
            return f"空きなし: {danchi_name}", False
        except Exception as e:
            # その他のロケーター関連エラー
            print(f"🚨 ロケーター関連エラー: {e}")
            return f"エラー: {danchi_name}", False

        # ... (以下省略: 判定3は到達しない)
    
    # ... (省略: 例外処理は変更なし)

# ... (省略: main関数は変更なし)
