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
    body { font-family: 'Noto Sans TC', sans-serif; }
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

# --- 核心功能 0：終極模型搜尋 (解決 404 問題) ---
@st.cache_resource
def get_working_model():
    if not api_key:
        return None, "未設定 API Key"
    
    status_text = []
    
    # 策略 1: 嘗試熱門模型 (優先順序)
    candidates = [
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-pro"
    ]
    
    for model_name in candidates:
        try:
            model = genai.GenerativeModel(model_name)
            model.generate_content("Hi")
            return model_name, f"測試成功：{model_name}"
        except Exception as e:
            status_text.append(f"{model_name} ❌")
            continue

    # 策略 2: 如果指定名稱都失敗，直接問 API 有什麼能用的 (List Models)
    try:
        status_text.append("啟動自動搜尋...")
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                # 找到一個支援生成的模型，直接拿來用
                test_name = m.name # 這裡會包含 'models/' 前綴
                try:
                    model = genai.GenerativeModel(test_name)
                    model.generate_content("Hi")
                    return test_name, f"自動搜尋成功：{test_name}"
                except:
                    continue
    except Exception as e:
        status_text.append(f"搜尋失敗: {str(e)}")

    # 策略 3: 真的都不行，回傳保底 (雖然可能也會失敗)
    return "models/gemini-pro", " | ".join(status_text)

# 初始化模型
CURRENT_MODEL_NAME, MODEL_STATUS = get_working_model()

# --- 核心功能 1：抓取新聞 ---
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
        title_text = title.rsplit(" - ", 1)[0] if " - " in title else title
        source = title.rsplit(" - ", 1)[1] if " - " in title else "新聞媒體"
        news_items.append({"title": title_text, "link": link, "source": source, "date": pub_date})
    return news_items

# --- 核心功能 2：AI 分析 (4秒慢速緩衝) ---
@st.cache_data(show_spinner=False)
def analyze_with_ai(news_title):
    if not api_key: return "無法分析 (缺少 API Key)"
    
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
            time.sleep(4) # 慢速緩衝
            model = genai.GenerativeModel(CURRENT_MODEL_NAME)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep(10)
                continue
            if attempt == max_retries - 1:
                return f"⚠️ 分析失敗 ({str(e)})"
    return "⚠️ 未知錯誤"

# --- 主程式 ---
st.title("🧠 六都房市 AI 戰情室")

# 顯示模型狀態
if "成功" in MODEL_STATUS:
    st.markdown(f'<div class="model-tag">✅ {MODEL_STATUS}</div>', unsafe_allow_html=True)
else:
    st.error(f"⚠️ 模型連線異常：{MODEL_STATUS}。請檢查 API Key 或網路狀態。")

st.caption(f"資料來源：Google News | 自動節流模式")

if st.button("🔄 強制刷新 (清除快取)"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

try:
    with st.spinner('正在搜尋並分析新聞... (每則需等待 4 秒)'):
        news_data = get_six_capital_news()
        if not news_data:
            st.warning("目前沒有最新新聞。")
        else:
            progress_bar = st.progress(0)
            for i, news in enumerate(news_data):
                st.markdown(f"""
                <div class="news-card">
                    <a href="{news['link']}" target="_blank" class="news-title">{news['title']}</a>
                    <div style="color:#666; font-size:13px; margin-bottom:10px;">
                        📰 {news['source']} | 🕒 {news['date']}
                    </div>
                """, unsafe_allow_html=True)
                
                ai_result = analyze_with_ai(news['title'])
                
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
            st.success("✅ 分析完成！")

except Exception as e:
    st.error(f"系統發生錯誤：{e}")

# --- 顯示套件版本 (Debug用) ---
try: ver = genai.__version__
except: ver = "Unknown"
st.markdown(f'<div class="debug-info">System: Streamlit v{st.__version__} | GenAI v{ver} (若版本低於0.7.0請更新requirements.txt)</div>', unsafe_allow_html=True)
