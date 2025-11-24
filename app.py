import streamlit as st
import feedparser
import pandas as pd
from datetime import datetime

# --- 設定網頁基本資訊 ---
st.set_page_config(
    page_title="六都房市速報",
    page_icon="🏙️",
    layout="centered"
)

# --- CSS 美化樣式 ---
st.markdown("""
    <style>
    .news-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 15px;
        border-left: 5px solid #2e86de; /* 改成專業藍色 */
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .news-title {
        font-size: 18px;
        font-weight: bold;
        color: #1f1f1f;
        text-decoration: none;
    }
    .news-title:hover {
        text-decoration: underline;
        color: #2e86de;
    }
    .news-meta {
        color: #666;
        font-size: 13px;
        margin-top: 8px;
        display: flex;
        justify-content: space-between;
    }
    .tag {
        background-color: #e1f0ff;
        color: #2e86de;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 核心功能：抓取新聞 ---
def get_six_capital_news():
    # 搜尋關鍵字邏輯：
    # (房地產 OR 房市 OR 建案 OR 預售屋) 加上 (台北 OR 新北 OR 桃園 OR 台中 OR 台南 OR 高雄)
    # when:1d 代表只抓過去 24 小時
    base_url = "https://news.google.com/rss/search?q="
    query = "(房地產+OR+房市+OR+建案+OR+重劃區)+AND+(台北+OR+新北+OR+桃園+OR+台中+OR+台南+OR+高雄)+when:1d"
    params = "&hl=zh-TW&gl=TW&ceid=TW:zh-TW"
    
    rss_url = base_url + query + params
    
    feed = feedparser.parse(rss_url)
    news_items = []

    # 改成抓取前 10 則
    for entry in feed.entries[:10]:
        title = entry.title
        link = entry.link
        published = entry.published_parsed
        
        # 格式化時間
        if published:
            pub_date = datetime(*published[:6]).strftime('%m/%d %H:%M')
        else:
            pub_date = "最新"

        # 來源處理
        if " - " in title:
            title_text, source = title.rsplit(" - ", 1)
        else:
            title_text = title
            source = "新聞媒體"

        # 簡單判斷是否可能為建案廣編 (如果標題包含特定字詞)
        is_ad = "建案" in title_text or "公開" in title_text or "登場" in title_text
        tag = "建案/廣編" if is_ad else "房市新聞"

        news_items.append({
            "title": title_text,
            "link": link,
            "source": source,
            "date": pub_date,
            "tag": tag
        })
    
    return news_items

# --- 網頁介面呈現 ---
st.title("🏙️ 六都房地產每日速報")
st.caption("鎖定：台北、新北、桃園、台中、台南、高雄 | 最新 10 則")

current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
st.write(f"更新時間：{current_time}")

st.write("---")

if st.button("🔄 刷新最新消息"):
    st.rerun()

# 執行抓取
try:
    with st.spinner('正在搜尋六都最新建案與新聞...'):
        news_data = get_six_capital_news()
        
    if news_data:
        for news in news_data:
            # 根據標籤改變顏色
            tag_color = "#e1f0ff" if news['tag'] == "房市新聞" else "#fff0e1"
            text_color = "#2e86de" if news['tag'] == "房市新聞" else "#e67e22"
            
            st.markdown(f"""
            <div class="news-card">
                <a href="{news['link']}" target="_blank" class="news-title">{news['title']}</a>
                <div class="news-meta">
                    <span>📰 {news['source']}</span>
                    <span style="background-color:{tag_color}; color:{text_color}; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{news['tag']}</span>
                    <span>🕒 {news['date']}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        st.success("✅ 已為您整理 10 則六都最新房產動態！")
    else:
        st.warning("目前六都範圍內剛好沒有最新新聞，請稍晚再試。")

except Exception as e:
    st.error(f"發生錯誤：{e}")