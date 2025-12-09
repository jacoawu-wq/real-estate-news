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
        # 1. 取得所有支援生成的模型清單
        valid_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                valid_models.append(m.name)
        
        # 2. 設定優先順序 (強制鎖定穩定版，避開 exp 模型)
        preferences = [
            'models/gemini-1.5-flash',
            'models/gemini-1.5-pro', 
            'models/gemini-1.0-pro', 
            'models/gemini-pro'
        ]
        
        # 3. 嘗試匹配優先清單
        for pref in preferences:
            if pref in valid_models:
                return pref
        
        # 4. 如果優先清單都沒抓到，嘗試找任何 "Flash" 模型 (且不能是 exp 實驗版)
        for m in valid_models:
            if 'flash' in m.lower() and 'exp' not in m.lower():
                return m
                
        # 5. 再找不到，找任何 "Pro" 模型 (且不能是 exp 實驗版)
        for m in valid_models:
            if 'pro' in m.lower() and 'exp' not in m.lower():
                return m

        # 6. 保底回傳
        return 'models/gemini-1.5-flash'
        
    except Exception as e:
        print(f"List models failed: {e}")
        return 'models/gemini-1.5-flash'

# --- 核心功能 1：抓取新聞 (快取 1 小時) ---
@st.cache_data(ttl=3600)
def get_six_capital_news():
    base_url = "https://news.google.com/rss/search?q="
    # 搜尋條件：六都 + 房地產關鍵字 + 過去24小時
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

# --- 核心功能 2：AI 分析 (加入自動重試機制) ---
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
    
    # --- 自動重試機制 (Retry Logic) ---
    max_retries = 3  # 最多試 3 次
    
    for attempt in range(max_retries):
        try:
            # 1. 基礎緩衝：每次請求前先休息 2 秒 (比之前的 1.5 秒更長)
            time.sleep(2)
            
            # 2. 呼叫 AI
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
            
        except Exception as e:
            error_str = str(e)
            
            # 如果是流量限制 (429)，且還有重試機會
            if "429" in error_str and attempt < max_retries - 1:
                # 遇到忙碌，休息久一點 (5秒) 再試
                time.sleep(5)
                continue # 跳回迴圈開頭再試一次
            
            # 如果試了 3 次還是不行，或者遇到其他錯誤，才回傳失敗訊息
            if attempt == max_retries - 1:
                if "429" in error_str:
                    return "⚠️ AI 分析忙碌中 (Google 流量限制)，請稍後再試。"
                return f"⚠️ 分析失敗 ({error_str})"
    
    return "⚠️ 未知錯誤"

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
    with st.spinner('正在搜尋並分析新聞... (首次載入約需 40 秒，請耐心等候)'):
        news_data = get_six_capital_news()
        
        if not news_data:
            st.warning("目前沒有最新新聞。")
        else:
            # 建立進度條，讓使用者知道還在跑，比較不會焦慮
            progress_bar = st.progress(0)
            
            for i, news in enumerate(news_data):
                st.markdown(f"""
                <div class="news-card">
                    <a href="{news['link']}" target="_blank" class="news-title">{news['title']}</a>
                    <div style="color:#666; font-size:13px; margin-bottom:10px;">
                        📰 {news['source']} | 🕒 {news['date']}
                    </div>
                """, unsafe_allow_html=True)
                
                # 呼叫 AI 分析
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
                
                # 更新進度條
                progress_bar.progress((i + 1) / len(news_data))
            
            # 完成後清空進度條
            progress_bar.empty()
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
