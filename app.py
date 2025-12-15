import streamlit as st
import feedparser
import google.generativeai as genai
from datetime import datetime
import time
import sys

# --- 設定網頁基本資訊 ---
st.set_page_config(
    page_title="六都房市 AI 戰情室",
    page_icon="🧠",
    layout="centered"
)

# --- CSS 美化樣式 ---
st.markdown("""
    <style>
    .news-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        border-left: 5px solid #2e86de;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .news-title {
        font-size: 20px;
        font-weight: bold;
        color: #1f1f1f;
        text-decoration: none;
        display: block;
        margin-bottom: 10px;
    }
    .news-title:hover {
        text-decoration: underline;
        color: #2e86de;
    }
    .ai-box {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 15px;
        margin-top: 10px;
        border: 1px solid #e9ecef;
    }
    .ai-label {
        font-weight: bold;
        color: #6c5ce7;
        margin-bottom: 5px;
        font-size: 14px;
    }
    .marketing-table table {
        width: 100%;
        border-collapse: collapse;
    }
    .marketing-table th {
        background-color: #2e86de;
        color: white;
        padding: 10px;
        text-align: left;
    }
    .marketing-table td {
        border-bottom: 1px solid #ddd;
        padding: 10px;
    }
    .debug-info {
        font-size: 12px;
        color: #999;
        margin-top: 50px;
        text-align: center;
        border-top: 1px solid #eee;
        padding-top: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 設定 AI ---
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# --- 核心功能 0：自動尋找可用的模型 (防呆機制) ---
@st.cache_resource
def get_valid_model_name():
    if not api_key:
        return None
    
    try:
        valid_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                valid_models.append(m.name)
        
        preferences = [
            'models/gemini-1.5-flash',
            'models/gemini-1.5-pro', 
            'models/gemini-1.0-pro', 
            'models/gemini-pro'
        ]
        
        for pref in preferences:
            if pref in valid_models:
                return pref
        
        for m in valid_models:
            if 'flash' in m.lower() and 'exp' not in m.lower():
                return m
                
        for m in valid_models:
            if 'pro' in m.lower() and 'exp' not in m.lower():
                return m

        return 'models/gemini-1.5-flash'
        
    except Exception as e:
        print(f"List models failed: {e}")
        return 'models/gemini-1.5-flash'

# --- 核心功能 1：抓取新聞 (快取 1 小時) ---
@st.cache_data(ttl=3600)
def get_six_capital_news():
    base_url = "https://news.google.com/rss/search?q="
    query = "(房地產+OR+房市+OR+建案+OR+重劃區)+AND+(台北+OR+新北+OR+桃園+OR+台中+OR+台南+OR+高雄)+when:1d"
    params = "&hl=zh-TW&gl=TW&ceid=TW:zh-TW"
    
    feed = feedparser.parse(base_url + query + params)
    news_items = []

    for entry in feed.entries[:10]:
        title = entry.title
        link = entry.link
        published = entry.published_parsed
        
        if published:
            pub_date = datetime(*published[:6]).strftime('%m/%d %H:%M')
        else:
            pub_date = "最新"

        if " - " in title:
            title_text, source = title.rsplit(" - ", 1)
        else:
            title_text = title
            source = "新聞媒體"

        news_items.append({
            "title": title_text,
            "link": link,
            "source": source,
            "date": pub_date
        })
    
    return news_items

# --- 核心功能 2：AI 單則分析 ---
@st.cache_data(show_spinner=False)
def analyze_with_ai(news_title, model_name):
    if not api_key:
        return "無法分析 (缺少 API Key)"
        
    prompt = f"""
    你是一位專業的台灣房地產分析師。請針對以下新聞標題進行分析：
    新聞標題：「{news_title}」
    
    請簡潔分析（各約100字）：
    1. **【產業觀點】**：對市場的影響或趨勢。
    2. **【受眾畫像】**：誰會對這則新聞最有感？
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            time.sleep(2)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            error_str = str(e)
            if "429" in error_str and attempt < max_retries - 1:
                time.sleep(5)
                continue
            if attempt == max_retries - 1:
                if "429" in error_str:
                    return "⚠️ AI 分析忙碌中 (流量限制)，請稍後再試。"
                return f"⚠️ 分析失敗 ({error_str})"
    return "⚠️ 未知錯誤"

# --- 核心功能 3：AI 總結行銷策略表 (新功能) ---
@st.cache_data(show_spinner=False)
def generate_marketing_summary(all_titles, model_name):
    if not api_key:
        return "無法生成總結"

    # 將所有標題組合成一個清單
    titles_text = "\n".join([f"- {t}" for t in all_titles])
    
    prompt = f"""
    你是一位資深的數位行銷顧問，專精於房地產廣告投放。
    請閱讀以下今日的熱門房地產新聞標題：
    {titles_text}

    請根據這些新聞內容，彙整出一份「今日廣告投放策略建議表」。
    請將建議分為三個區域：「北部 (北北桃)」、「中部 (台中)」、「南部 (台南/高雄)」。
    如果新聞內容沒有特定區域，請根據其屬性歸類到最適合的區域，或列為通用建議。

    請直接輸出一個 Markdown 表格，表格欄位必須包含：
    1. **區域** (北部/中部/南部)
    2. **Google廣告關鍵字建議** (請列出3-5組高潛力關鍵字)
    3. **Google聯播網受眾建議** (請具體描述興趣、意向或瀏覽習慣)
    4. **FB廣告受眾建議** (請建議興趣標籤、行為或人口統計特徵)

    請確保內容具體且可執行，不需要開場白，直接給我表格。
    """

    max_retries = 3
    for attempt in range(max_retries):
        try:
            time.sleep(2)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            error_str = str(e)
            if "429" in error_str and attempt < max_retries - 1:
                time.sleep(5)
                continue
            if attempt == max_retries - 1:
                return f"⚠️ 總結生成失敗: {error_str}"
    return "⚠️ 無法生成總結"

# --- 網頁介面呈現 ---
st.title("🧠 六都房市 AI 戰情室")

# 1. 取得目前可用的模型名稱
current_model_name = get_valid_model_name()
st.caption(f"資料來源：Google News | 🤖 AI 模型：{current_model_name or '未偵測'}")

# 手動刷新按鈕
if st.button("🔄 強制刷新 (清除快取)"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

# 主程式流程
try:
    with st.spinner('正在搜尋並分析新聞... (首次載入約需 40~60 秒)'):
        news_data = get_six_capital_news()
        
        if not news_data:
            st.warning("目前沒有最新新聞。")
        else:
            # 1. 顯示單則新聞分析
            progress_bar = st.progress(0)
            all_titles_for_summary = [] # 收集標題給總結用

            for i, news in enumerate(news_data):
                all_titles_for_summary.append(news['title']) # 收集標題
                
                st.markdown(f"""
                <div class="news-card">
                    <a href="{news['link']}" target="_blank" class="news-title">{news['title']}</a>
                    <div style="color:#666; font-size:13px; margin-bottom:10px;">
                        📰 {news['source']} | 🕒 {news['date']}
                    </div>
                """, unsafe_allow_html=True)
                
                if current_model_name:
                    ai_result = analyze_with_ai(news['title'], current_model_name)
                else:
                    ai_result = "⚠️ 無法連接 AI 模型"

                st.markdown(f"""
                    <div class="ai-box">
                        <div class="ai-label">✨ AI 智能解析</div>
                        <div style="font-size: 15px; line-height: 1.6; color: #2d3436;">
                            {ai_result.replace(chr(10), '<br>')}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                progress_bar.progress((i + 1) / len(news_data))
            
            progress_bar.empty()
            
            # 2. 顯示行銷策略總表 (新增區塊)
            st.markdown("---") # 分隔線
            st.markdown("### 📊 AI 每日行銷策略總結 (北中南)")
            
            with st.spinner('AI 正在彙整全台廣告策略建議...'):
                if current_model_name and all_titles_for_summary:
                    marketing_summary = generate_marketing_summary(all_titles_for_summary, current_model_name)
                    st.markdown(f'<div class="marketing-table">{marketing_summary}</div>', unsafe_allow_html=True)
                else:
                    st.error("無法生成行銷總結")

            st.success("✅ 所有分析完成！")

except Exception as e:
    st.error(f"系統發生錯誤：{e}")

# --- 底部診斷資訊 ---
try:
    genai_version = genai.__version__
except:
    genai_version = "未知"

st.markdown(f"""
<div class="debug-info">
    系統診斷資訊：Streamlit v{st.__version__} | Google GenAI v{genai_version}<br>
</div>
""", unsafe_allow_html=True)
```

### 這次的升級內容：
1.  **新增 `generate_marketing_summary` 函數**：專門負責把所有新聞標題收集起來，一次丟給 AI 做綜合分析。
2.  **指定的輸出格式**：我明確要求 AI 用 **Markdown 表格** 呈現，並強制分為「北部、中部、南部」三個類別。
3.  **指定的行銷欄位**：包括 Google 關鍵字、GDN 受眾、FB 受眾建議，完全符合你的需求。
4.  **UI 整合**：在所有新聞卡片跑完後，會在最下方自動生成這個大表格。

現在，你只要等待網頁跑完，拉到最下面，就可以直接把那張表複製下來給行銷團隊執行了！🚀
