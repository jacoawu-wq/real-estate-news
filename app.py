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
    /* 全局字體設定 */
    body { font-family: 'Noto Sans TC', sans-serif; }

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
    .news-card:hover { transform: translateY(-2px); }
    .news-title {
        font-size: 20px;
        font-weight: bold;
        color: #1f1f1f;
        text-decoration: none;
        display: block;
        margin-bottom: 10px;
    }
    .news-title:hover { text-decoration: underline; color: #2e86de; }
    
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
    
    /* 模型資訊標籤 */
    .model-tag {
        background-color: #ffeaa7;
        color: #d35400;
        padding: 5px 10px;
        border-radius: 5px;
        font-size: 12px;
        font-weight: bold;
        margin-bottom: 20px;
        display: inline-block;
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

# --- 核心功能 0：自動尋找可用的模型 (修復 404 錯誤) ---
@st.cache_resource
def get_valid_model_name():
    if not api_key:
        return 'models/gemini-pro' # 預設值
    
    try:
        # 1. 取得所有支援生成的模型清單
        valid_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                valid_models.append(m.name)
        
        # 2. 設定優先順序 (優先找 Flash 系列，若無則找 Pro)
        preferences = [
            'models/gemini-1.5-flash',
            'models/gemini-1.5-flash-latest',
            'models/gemini-1.0-pro', 
            'models/gemini-pro'
        ]
        
        # 3. 嘗試匹配優先清單
        for pref in preferences:
            if pref in valid_models:
                return pref
        
        # 4. 如果都沒抓到，回傳清單中第一個包含 'gemini' 的模型
        for m in valid_models:
            if 'gemini' in m.lower():
                return m

        # 5. 真的都沒找到，回傳 gemini-pro 碰運氣
        return 'models/gemini-pro'
        
    except Exception as e:
        print(f"List models failed: {e}")
        return 'models/gemini-pro'

# 取得目前可用的模型
CURRENT_MODEL_NAME = get_valid_model_name()

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
        pub_date = datetime(*published[:6]).strftime('%m/%d %H:%M') if published else "最新"
        
        if " - " in title:
            title_text = title.rsplit(" - ", 1)[0]
            source = title.rsplit(" - ", 1)[1]
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

# --- 核心功能 2：AI 單則分析 (慢速節流模式) ---
@st.cache_data(show_spinner=False)
def analyze_with_ai(news_title):
    if not api_key:
        return "無法分析 (缺少 API Key)"
        
    prompt = f"""
    你是一位專業的台灣房地產分析師。請針對以下新聞標題進行分析：
    新聞標題：「{news_title}」
    
    請簡潔分析（各約100字）：
    1. **【產業觀點】**：對市場的影響或趨勢。
    2. **【受眾畫像】**：誰會對這則新聞最有感？
    """
    
    # 自動重試機制 (Retry Logic)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # ★ 關鍵修改：將緩衝時間拉長到 4 秒，確保不被 Google 擋
            time.sleep(4)
            model = genai.GenerativeModel(CURRENT_MODEL_NAME)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            error_str = str(e)
            # 如果是流量限制 (429)，休息更久 (10秒) 再試
            if "429" in error_str and attempt < max_retries - 1:
                time.sleep(10)
                continue
            
            if attempt == max_retries - 1:
                if "429" in error_str:
                    return "⚠️ AI 分析忙碌中 (流量限制)，請稍後再試。"
                return f"⚠️ 分析失敗 ({error_str})"
    return "⚠️ 未知錯誤"

# --- 網頁介面呈現 ---
st.title("🧠 六都房市 AI 戰情室")

# 顯示目前使用的模型與狀態
st.markdown(f'<div class="model-tag">🔥 目前使用模型：{CURRENT_MODEL_NAME} (自動偵測 + 節流模式)</div>', unsafe_allow_html=True)
st.caption(f"資料來源：Google News | 更新頻率：每小時自動刷新")

# 手動刷新按鈕
if st.button("🔄 強制刷新 (清除快取)"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

# 主程式流程
try:
    with st.spinner('正在搜尋並分析新聞... (因開啟節流模式，每則需等待 4 秒，請耐心等候)'):
        news_data = get_six_capital_news()
        
        if not news_data:
            st.warning("目前沒有最新新聞。")
        else:
            # 進度條
            progress_bar = st.progress(0)
            
            for i, news in enumerate(news_data):
                # 顯示新聞卡片
                st.markdown(f"""
                <div class="news-card">
                    <a href="{news['link']}" target="_blank" class="news-title">{news['title']}</a>
                    <div style="color:#666; font-size:13px; margin-bottom:10px;">
                        📰 {news['source']} | 🕒 {news['date']}
                    </div>
                """, unsafe_allow_html=True)
                
                # 呼叫 AI 分析
                ai_result = analyze_with_ai(news['title'])

                # 顯示 AI 結果
                st.markdown(f"""
                    <div class="ai-box">
                        <div class="ai-label">✨ AI 智能解析</div>
                        <div style="font-size: 15px; line-height: 1.6; color: #2d3436;">
                            {ai_result.replace(chr(10), '<br>')}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # 更新進度條
                progress_bar.progress((i + 1) / len(news_data))
            
            progress_bar.empty() # 跑完隱藏進度條
            st.success("✅ 分析完成！")

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
