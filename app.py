import streamlit as st
import feedparser
import google.generativeai as genai
from datetime import datetime
import time

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
    .error-msg {
        color: #e17055;
        font-size: 12px;
        margin-top: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 設定 AI ---
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

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

# --- 核心功能 2：AI 分析 (智能切換模型) ---
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
    
    # 策略：優先使用 gemini-1.5-flash (快)，失敗則切換 gemini-pro (穩)
    try:
        time.sleep(1) # 安全緩衝
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e_flash:
        try:
            # 如果 Flash 失敗，切換到 Pro 模型
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            return response.text + "\n\n*(備註：使用相容模式生成)*"
        except Exception as e_pro:
            # 顯示詳細錯誤，方便除錯
            return f"⚠️ 分析失敗\nFlash 錯誤: {e_flash}\nPro 錯誤: {e_pro}"

# --- 網頁介面呈現 ---
st.title("🧠 六都房市 AI 戰情室")
st.caption(f"資料來源：Google News | 智能模型：Gemini Auto-Switch")

# 手動刷新按鈕
if st.button("🔄 強制刷新 (清除快取)"):
    st.cache_data.clear()
    st.rerun()

# 主程式流程
try:
    with st.spinner('正在搜尋並分析新聞... (首次載入可能需要 30 秒)'):
        news_data = get_six_capital_news()
        
        if not news_data:
            st.warning("目前沒有最新新聞。")
        else:
            for news in news_data:
                # 顯示新聞卡片
                st.markdown(f"""
                <div class="news-card">
                    <a href="{news['link']}" target="_blank" class="news-title">{news['title']}</a>
                    <div style="color:#666; font-size:13px; margin-bottom:10px;">
                        📰 {news['source']} | 🕒 {news['date']}
                    </div>
                """, unsafe_allow_html=True)
                
                # 呼叫 AI 分析 (有快取)
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
            
            st.success("✅ 分析完成！")
            
except Exception as e:
    st.error(f"系統發生錯誤：{e}")
