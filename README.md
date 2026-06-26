# 每日資料摘要小幫手

抓 RSS / arXiv → 用 AI 整理成重點 → 用 Telegram 傳給你，由 GitHub Actions 每天自動跑。
摘要用哪個 AI 可切換（預設 Gemini，免費；之後可切回 Claude）。

## 設定步驟

### 1. 建 Telegram bot
- 在 Telegram 搜尋 `@BotFather`，傳 `/newbot`，照指示命名。
- 完成後它會給你一串 **token**（長得像 `123456:ABC-DEF...`）→ 這是 `TG_TOKEN`。

### 2. 拿你的 chat id
- 先「主動」跟你剛建好的 bot 講一句話（隨便傳什麼）。
- 瀏覽器打開（把 `<TOKEN>` 換成上面那串）：
  `https://api.telegram.org/bot<TOKEN>/getUpdates`
- 在回傳的 JSON 裡找 `"chat":{"id": 數字}` → 那個數字就是 `TG_CHAT_ID`。

### 3. 拿 Gemini API 金鑰（免費）
- 到 aistudio.google.com → 右上 **Get API key** → **Create API key** → 複製。
- 不用綁信用卡。這是 `GEMINI_API_KEY`。
- （之後想切回 Claude，再到 console.anthropic.com 拿 `ANTHROPIC_API_KEY`，
   並把 `daily_digest.py` 最上面的 `PROVIDER` 改成 `"claude"`。）

### 4. 設定 GitHub Secrets
把專案 push 到一個 GitHub repo 後：
- repo → Settings → Secrets and variables → Actions → New repository secret
- 新增三個：`GEMINI_API_KEY`、`TG_TOKEN`、`TG_CHAT_ID`

### 5. 改成你要的資料來源
打開 `daily_digest.py`，改最上面的 `SOURCES`。預設已經幫你設好四條（涵蓋新聞、應用、研究）：

- `MarkTechPost` — AI 論文與新發布的快訊，量大、更新勤
- `The Verge·AI` — 偏消費端、產品面的 AI 新聞
- `MIT科技評論·AI` — 比較深的產業與政策分析
- `arXiv·AI 前沿` — cs.AI 分類的最新論文（研究面）

每條來源兩種寫法：

```python
{"name": "顯示名稱", "rss": "https://某網站/feed.xml", "n": 5}  # 一般網站 RSS
{"name": "顯示名稱", "query": "all:microgrid", "n": 6}          # arXiv 關鍵字搜尋
```

想加回微電網（你的本行），把檔案裡那行註解拿掉即可。其他可用的 AI 新聞 RSS：
- OpenAI 官方：`https://openai.com/news/rss.xml`
- Hugging Face：`https://huggingface.co/blog/feed.xml`
- Google AI：`https://blog.google/technology/ai/rss/`

arXiv 的 query 語法：`all:關鍵字`（任何欄位）、`abs:"片語"`（摘要含片語）、`cat:分類`（如 `cat:eess.SY` 系統與控制），可用 `AND`/`OR`/`ANDNOT` 組合。

### 6. 測試
- repo 的 **Actions** 分頁 → 選 `daily-digest` → 按 **Run workflow** 手動跑一次。
- 成功的話 Telegram 就會收到摘要。確認沒問題後，它就會每天自動跑。

## 本機先測（建議先做這步）
```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...
export TG_TOKEN=...
export TG_CHAT_ID=...
python daily_digest.py
```

## 切換摘要用的 AI
`daily_digest.py` 最上面：
```python
PROVIDER = "gemini"   # 改成 "claude" 就切回 Anthropic
```
切到哪個，就要設好對應的金鑰（`GEMINI_API_KEY` 或 `ANTHROPIC_API_KEY`）。

## 幾個會踩到的雷
- **時間是 UTC**：`daily.yml` 的 cron 用 UTC，台灣要 +8 自己換算。
- **排程會被停用**：repo 連續 60 天沒有任何 commit，GitHub 會自動停掉排程。偶爾推一下就好。
- **排程會延遲**：GitHub 負載高時可能延後幾分鐘到十幾分鐘，別拿它當鬧鐘。
- **Gemini 免費額度**：免費方案有每分鐘/每日請求上限，但你一天只跑一次，完全用不到上限。
