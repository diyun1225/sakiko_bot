"""
每日資料摘要小幫手（AI + 智慧微電網版）
流程：抓 arXiv  ->  丟給 Claude 整理成重點  ->  用 Telegram 傳給你

需要的環境變數（在 GitHub Secrets 設定，本機測試可用 export）：
  GEMINI_API_KEY      Gemini API 金鑰（aistudio.google.com，免費）
  ANTHROPIC_API_KEY   Claude API 金鑰（之後切回 Claude 才需要）
  TG_TOKEN            Telegram bot token（跟 @BotFather 拿）
  TG_CHAT_ID          你的 chat id（見 README）
"""

import os
import re
import sys
import time
import sqlite3
import datetime
import urllib.parse
import feedparser
import requests
from dotenv import load_dotenv

# 自動讀取同層的 .env（本機測試用；GitHub Actions 上沒有 .env，會自動略過）
load_dotenv()

# 讓終端機用 UTF-8 輸出，避免 Windows（cp950）印 emoji/中文時報錯
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ============================================================
# 1. 你主要要改的地方：資料來源
#    兩種寫法都支援：
#      {"name": 顯示名稱, "query": arXiv 關鍵字, "n": 抓幾則}   ← arXiv 精準搜尋
#      {"name": 顯示名稱, "rss":   一般 RSS 網址,   "n": 抓幾則}   ← 一般網站 RSS
#
#    arXiv query 語法：
#      all:microgrid                  → 任何欄位含 microgrid
#      abs:"energy management"        → 摘要含這個片語
#      cat:cs.AI                      → cs.AI 分類最新論文
#      用 AND / OR / ANDNOT 組合，例：'all:microgrid AND abs:"reinforcement learning"'
# ============================================================
SOURCES = [
    # 新聞 / 應用面（一般 RSS）
    {"name": "MarkTechPost",   "rss": "https://www.marktechpost.com/feed/", "n": 5},
    {"name": "The Verge·AI",   "rss": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "n": 4},
    {"name": "MIT科技評論·AI", "rss": "https://www.technologyreview.com/topic/artificial-intelligence/feed/", "n": 3},
    # 研究面（arXiv 關鍵字搜尋）
    {"name": "arXiv·AI 前沿",  "query": "cat:cs.AI", "n": 4},
    # 想保留你本行（微電網）就把下面這行的註解拿掉：
    # {"name": "arXiv·微電網",  "query": "all:microgrid", "n": 4},
]

UA = {"User-Agent": "daily-digest/1.0 (personal research digest)"}


def _arxiv_url(query, n):
    params = urllib.parse.urlencode({
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": n,
    })
    return f"http://export.arxiv.org/api/query?{params}"


def _fetch_feed(url):
    resp = requests.get(url, headers=UA, timeout=30)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def scrape():
    """依 SOURCES 抓資料，回傳 [(來源, 標題, 摘要, 連結), ...]，並去除重複連結。"""
    items, seen = [], set()
    for src in SOURCES:
        url = _arxiv_url(src["query"], src["n"]) if "query" in src else src["rss"]
        try:
            feed = _fetch_feed(url)
        except requests.RequestException as e:
            print(f"[警告] 抓 {src['name']} 失敗：{e}")
            continue
        for entry in feed.entries[: src["n"]]:
            link = entry.get("link", "")
            if not link or link in seen:
                continue
            seen.add(link)
            summary = entry.get("summary", "").strip().replace("\n", " ")
            items.append((src["name"], entry.get("title", "").strip(), summary[:500], link))
        time.sleep(3)  # arXiv API 禮貌性間隔，避免被擋
    return items


# ============================================================
# 2. 用哪個 AI 來摘要：改這一行就能切換
#    "gemini" → 用 Google Gemini（有免費額度）
#    "claude" → 用 Anthropic Claude（等驗證好了再切回來）
# ============================================================
PROVIDER = "gemini"

GEMINI_MODEL = "gemini-2.5-flash"   # 免費額度可用、穩定
CLAUDE_MODEL = "claude-sonnet-4-6"


# ============================================================
# 3. 訊息的開頭 / 結尾（想改就改這裡）
#    開頭會自動帶入「今天日期」和「事項數量 N」，例如：
#      今天是 6月27日，豐川客服為您整理了 5 個重要事項：
#    - SENDER_NAME：署名，想換名字就改這裡
#    - FOOTER：結尾固定要講的話，不想要就改成 ""
#    \n 代表換行；想空一行就用兩個 \n。
# ============================================================
SENDER_NAME = "豐川客服"
FOOTER = "\n\n——— 以上，祝你有美好的一天 🙌"


def _build_message(summary):
    """把 AI 摘要包上『今天是X月X日，OOO為您整理了N個重要事項：』開頭和結尾。"""
    # 用台灣時間（UTC+8）算今天日期，跑在 GitHub（UTC）上也會是對的
    tw_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    date_str = f"{tw_now.month}月{tw_now.day}日"
    # 數一下摘要裡有幾個「1. 2. 3.」編號項目，當作 N
    n = len(re.findall(r"(?m)^\s*\d+[.、]", summary))
    header = f"今天是 {date_str}，{SENDER_NAME}為您整理了 {n} 個重要事項：\n\n"
    return header + summary + FOOTER


def _build_prompt(items):
    raw = "\n\n".join(
        f"[{src}] {title}\n{summary}\n{link}" for src, title, summary, link in items
    )
    return (
        "你是幫忙追蹤 AI 動態的助理，讀者對『AI 的各種應用』都有興趣（工程背景，做能源/嵌入式系統/醫療/長照）。\n"
        "以下是今天從新聞網站和 arXiv 抓到的資料，請用繁體中文整理成「編號清單」：\n"
        "- 挑最重要、最有意思的，重複的同一則新聞只留一則。\n"
        "- 每則用「1. 」「2. 」「3. 」這樣的數字編號開頭，一則一段。\n"
        "- 每則：用一句白話講發生什麼事、為什麼值得看，後面附上連結。\n"
        "- 如果有跟能源、電網、嵌入式有關的，可以特別點出來。\n"
        "- 講重點、口語，不要學術腔，不要客套開場白，直接從「1. 」開始。\n\n"
        f"{raw}"
    )


def _summarize_gemini(prompt):
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return resp.text


def _summarize_claude(prompt):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def summarize(items):
    """把抓到的內容丟給 AI，整理成繁體中文重點"""
    if not items:
        return "今天沒抓到新內容。"
    prompt = _build_prompt(items)
    return _summarize_gemini(prompt) if PROVIDER == "gemini" else _summarize_claude(prompt)


def send_telegram(text):
    """用 Telegram bot 發訊息（自動處理 4096 字上限）"""
    token = os.environ["TG_TOKEN"]
    chat_id = os.environ["TG_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    for i in range(0, len(text), 4000):
        r = requests.post(url, data={
            "chat_id": chat_id,
            "text": text[i:i + 4000],
            "disable_web_page_preview": True,
        })
        r.raise_for_status()


# ============================================================
# 4. 存進資料庫（SQLite，存在同層的 digest.db）
#    現在只負責「存」，之後要查詢時直接讀這個檔就好。
#    - articles 表：每篇抓到的文章（用連結去重，同一篇不會重複存）
#    - digests  表：每天 AI 整理好的那份摘要全文
# ============================================================
DB_PATH = os.path.join(os.path.dirname(__file__), "digest.db")


def _init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date   TEXT,                 -- 抓取日期 YYYY-MM-DD（台灣時間）
            source     TEXT,                 -- 來源名稱
            title      TEXT,
            summary    TEXT,
            link       TEXT UNIQUE,          -- 同一篇連結只存一次
            saved_at   TEXT                  -- 存入時間
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS digests (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date   TEXT,                 -- 這份摘要的日期
            content    TEXT,                 -- AI 整理好的全文
            saved_at   TEXT
        )
    """)
    conn.commit()


def save_to_db(items, digest):
    """把今天抓到的文章和整理好的摘要都存進 SQLite。"""
    tw_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    run_date = tw_now.strftime("%Y-%m-%d")
    now_iso = tw_now.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    try:
        _init_db(conn)
        for src, title, summary, link in items:
            # 連結重複就略過（INSERT OR IGNORE 搭配 link UNIQUE）
            conn.execute(
                "INSERT OR IGNORE INTO articles "
                "(run_date, source, title, summary, link, saved_at) VALUES (?, ?, ?, ?, ?, ?)",
                (run_date, src, title, summary, link, now_iso),
            )
        conn.execute(
            "INSERT INTO digests (run_date, content, saved_at) VALUES (?, ?, ?)",
            (run_date, digest, now_iso),
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    items = scrape()
    digest = _build_message(summarize(items))
    send_telegram(digest)
    save_to_db(items, digest)
    print("已送出：")
    print(digest)
