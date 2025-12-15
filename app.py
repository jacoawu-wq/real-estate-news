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

# --- CSS 美化樣式 (升級版：專業表格) ---
st.markdown("""
    <style>
    /* 全局字體設定 */
    body {
        font-family: 'Noto Sans TC', sans-serif;
    }

    /* 新聞卡片樣式 */
    .news-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        border-left: 5px solid #2e86de;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: transform 0.2s;
    }
    .news-card:hover {
        transform: translateY(-2px);
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
    
    /* AI 分析框樣式 */
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

    /* --- 表格美化核心 CSS --- */
    /* 針對 Streamlit 渲染出的 Markdown 表格進行美化 */
    div[data-testid="stMarkdownContainer"] table {
        width: 100%;
        border-collapse: collapse;
        margin: 25px 0;
        font-size: 16px;
        font-family: 'Noto Sans TC', sans-serif;
        box-shadow: 0 0 20px rgba(0, 0, 0, 0.08); /* 柔和陰影 */
        border-radius: 10px;
        overflow: hidden; /* 確保圓角不被直角單元格蓋住 */
    }

    /* 表頭樣式 */
    div[data-testid="stMarkdownContainer"] thead tr {
        background-color: #2e86de; /* 專業藍 */
        color: #ffffff;
        text-align: left;
        font-weight: bold;
    }

    /* 單元格間距與格線 */
    div[data-testid="stMarkdownContainer"] th, 
    div[data-testid="stMarkdownContainer"] td {
        padding: 15px 20px; /* 增加呼吸感 */
        border-bottom: 1px solid #eeeeee;
        line-height: 1.6;
    }

    /* 斑馬紋 (偶數行變色) */
    div[data-testid="stMarkdownContainer"] tbody tr:nth-of-type(even) {
        background-color: #f8f9fa; 
    }

    /* 滑鼠懸停效果 */
    div[data-testid="stMarkdownContainer"] tbody tr:hover {
        background-color: #e6f7ff; /* 淺藍色 highlight */
        cursor: default;
        transition: background-color 0.2s;
    }

    /* 最後一行加粗底線 */
    div[data-testid="stMarkdownContainer"] tbody tr:last-of-type {
        border-bottom: 3px solid #2e86de;
    }
    
    /* 底部除錯資訊 */
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
            # 加大緩衝時間至 3 秒，避免流量限制
            time.sleep(3)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            error_str = str(e)
            # 如果遇到 429 錯誤，休息更久 (15秒)
            if "429" in error_str and attempt < max_retries - 1:
                time.sleep(15)
                continue
            if attempt == max_retries - 1:
                if "429" in error_str:
                    return "⚠️ AI 分析忙碌中 (流量限制)，請稍後再試。"
                return f"⚠️ 分析失敗 ({error_str})"
    return "⚠️ 未知錯誤"

# --- 核心功能 3：AI 總結行銷策略表 (修改為六都版) ---
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
    請將建議詳細分為六個區域（六都）：「台北市」、「新北市」、「桃園市」、「台中市」、「台南市」、「高雄市」。
    如果新聞內容沒有特定區域，請根據其屬性歸類到最適合的區域，或列為「全台通用」。

    請直接輸出一個 Markdown 格式的表格 (不要使用 HTML 標籤，也不要包含任何開場白或結語)。
    表格欄位必須包含：
    1. **六都區域**
    2. **Google廣告關鍵字建議** (3-5組)
    3. **Google聯播網受眾建議** (具體描述)
    4. **FB廣告受眾建議** (具體描述)
    """

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 總結功能請求較大，緩衝 5 秒
            time.sleep(5)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            error_str = str(e)
            if "429" in error_str and attempt < max_retries - 1:
                time.sleep(20) # 休息 20 秒
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
    with st.spinner('正在搜尋並分析新聞... (因增加防呆緩衝，載入約需 50~80 秒)'):
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
            st.markdown("### 📊 AI 每日行銷策略總結 (六都分區)")
            
            with st.spinner('AI 正在彙整全台廣告策略建議...'):
                if current_model_name and all_titles_for_summary:
                    marketing_summary = generate_marketing_summary(all_titles_for_summary, current_model_name)
                    # 這裡直接顯示 Markdown，CSS 會自動美化它
                    st.markdown(marketing_summary)
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
