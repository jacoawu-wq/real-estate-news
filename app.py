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
    </style>
    """, unsafe_allow_html=True)

# --- 設定 AI ---
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# --- 核心功能 1：抓取新聞 (加上快取：1小時更新一次) ---
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

# --- 核心功能 2：AI 分析 (加上快取與緩衝) ---
@st.cache_data(show_spinner=False)
def analyze_with_ai(news_title):
    if not api_key:
        return "無法分析 (缺少 API Key)"
        
    prompt = f"""
    你是一位專業的台灣房地產分析師。請針對以下新聞標題進行分析：
    新聞標題：「{news_title}」

    請依照以下邏輯分析，並嚴格遵守字數限制：
    1. **判斷類型**：先判斷這是「一般新聞」還是「建案廣編/廣告」。
    2. **產業分析 (約100字)**：這則消息對房地產市場的影響、趨勢或觀察。
    3. **受眾分析 (約100字)**：
       - 如果是新聞：分析哪個族群（如首購、投資客、換屋族）看到會最有感？
       - 如果是廣編/建案：分析這是在跟什麼樣的族群（如小資、豪宅客、退休族）對話？

    請直接輸出分析結果，格式如下：
    **【產業觀點】** ...內容...
    **【受眾畫像】** ...內容...
    """
    
    try:
        # 安全緩衝：休息 1 秒，避免瞬間請求過快觸發限制
        time.sleep(1)
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 分析暫時休息中 ({str(e)})"

# --- 網頁介面呈現 ---
st.title("🧠 六都房市 AI 戰情室")
st.caption(f"資料來源：Google News | 更新頻率：每小時自動刷新 | 支援多人同時瀏覽")

# 手動刷新按鈕：加上清除快取的功能
if st.button("🔄 強制刷新 (清除快取)"):
    st.cache_data.clear()
    st.rerun()

# 執行流程
try:
    # 這裡只會顯示第一次載入的轉圈圈，之後都會秒開
    with st.spinner('正在彙整最新房市情報... (首次載入約需 20 秒)'):
        news_data = get_six_capital_news()
        
        if not news_data:
            st.warning("目前沒有最新新聞。")
        else:
            for news in news_data:
                st.markdown(f"""
                <div class="news-card">
                    <a href="{news['link']}" target="_blank" class="news-title">{news['title']}</a>
                    <div style="color:#666; font-size:13px; margin-bottom:10px;">
                        📰 {news['source']} | 🕒 {news['date']}
                    </div>
                """, unsafe_allow_html=True)
                
                # 這裡會優先讀取快取，如果有快取則 0 秒顯示
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
            
            st.success("✅ 今日情報彙整完成！")
            
except Exception as e:
    st.error(f"系統發生錯誤：{e}")

