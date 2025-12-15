import streamlit as st
import feedparser
import google.generativeai as genai
from datetime import datetime
import time
import re

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
    
    /* 表格樣式優化 */
    div[data-testid="stMarkdownContainer"] table {
        width: 100%; border-collapse: collapse; margin: 25px 0;
        font-size: 16px; box-shadow: 0 0 20px rgba(0,0,0,0.08); border-radius: 10px; overflow: hidden;
    }
    div[data-testid="stMarkdownContainer"] thead tr { background-color: #2e86de; color: #ffffff; text-align: left; }
    div[data-testid="stMarkdownContainer"] th, div[data-testid="stMarkdownContainer"] td {
        padding: 12px 15px; border-bottom: 1px solid #eeeeee; line-height: 1.5;
    }
    div[data-testid="stMarkdownContainer"] tbody tr:nth-of-type(even) { background-color: #f8f9fa; }
    div[data-testid="stMarkdownContainer"] tbody tr:hover { background-color: #e6f7ff; }

    .debug-info { font-size: 12px; color: #999; margin-top: 50px; text-align: center; border-top: 1px solid #eee; padding-top: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 設定 AI (雙鑰匙架構) ---
api_key_news = st.secrets.get("GEMINI_API_KEY_NEWS") or st.secrets.get("GEMINI_API_KEY")
api_key_summary = st.secrets.get("GEMINI_API_KEY_SUMMARY") or st.secrets.get("GEMINI_API_KEY")

if api_key_news:
    genai.configure(api_key=api_key_news)

# --- 核心功能 0：自動尋找可用的模型 (強制鎖定穩定版) ---
@st.cache_resource
def get_valid_model_name():
    if not api_key_news: return None
    genai.configure(api_key=api_key_news)
    try:
        # 強制指定目前最穩定且免費額度較高的 1.5 Flash
        # 避免自動抓到 2.5 Flash 或其他實驗版導致 429 錯誤
        target_model = 'models/gemini-1.5-flash'
        
        # 檢查該模型是否在可用清單中
        valid_models = [m.name for m in genai.list_models()]
        
        if target_model in valid_models:
            return target_model
        
        # 如果找不到 1.5-flash，才嘗試其他模型
        for m in valid_models:
            if 'flash' in m.lower() and '1.5' in m.lower(): return m
        for m in valid_models:
            if 'flash' in m.lower(): return m
            
        return 'models/gemini-1.5-flash' # 保底回傳
    except:
        return 'models/gemini-1.5-flash'

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

# --- 核心功能 2：AI 批次分析 (極速版核心) ---
@st.cache_data(show_spinner=False)
def analyze_news_batch(news_titles, model_name):
    if not api_key_news: return {}
    genai.configure(api_key=api_key_news)
    
    # 組合批次指令
    titles_list_str = ""
    for idx, title in enumerate(news_titles):
        titles_list_str += f"第{idx+1}則：{title}\n"
    
    prompt = f"""
    你是一位專業房產分析師。請一次分析以下 {len(news_titles)} 則新聞標題。
    
    新聞清單：
    {titles_list_str}

    請依序輸出分析，格式必須嚴格如下（請勿改變格式，方便程式讀取）：
    
    ===第1則===
    **【產業觀點】**...內容...
    **【受眾畫像】**...內容...
    ===第2則===
    **【產業觀點】**...內容...
    **【受眾畫像】**...內容...
    
    (以此類推直到第{len(news_titles)}則)
    請保持簡潔，每點分析約 80 字。
    """
    
    # 加入重試機制
    max_retries = 3
    for attempt in range(max_retries):
        try:
            time.sleep(1) 
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            text = response.text
            
            # 解析回傳的文字
            analysis_dict = {}
            parts = re.split(r"===第\d+則===", text)
            for i, part in enumerate(parts[1:]):
                if i < len(news_titles):
                    analysis_dict[news_titles[i]] = part.strip()
            return analysis_dict
            
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep(5) # 遇到忙碌多等5秒
                continue
            if attempt == max_retries - 1:
                return {"error": str(e)}
    return {}

# --- 核心功能 3：AI 總結行銷策略表 ---
@st.cache_data(show_spinner=False)
def generate_marketing_summary(all_titles, model_name):
    if not api_key_summary: return "無法生成總結"
    genai.configure(api_key=api_key_summary) # 切換 Key 2
    
    titles_text = "\n".join([f"- {t}" for t in all_titles])
    prompt = f"""
    你是一位數位行銷顧問。請根據以下今日房地產新聞：
    {titles_text}
    
    彙整出一份「今日廣告投放策略建議表」。
    請將建議分為六個區域（六都）：台北、新北、桃園、台中、台南、高雄。
    
    直接輸出 Markdown 表格，欄位包含：
    1. **六都區域**
    2. **Google廣告關鍵字**
    3. **Google聯播網受眾**
    4. **FB廣告受眾**
    """
    
    # 加入重試機制
    max_retries = 3
    for attempt in range(max_retries):
        try:
            time.sleep(2)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep(10) # 總結如果失敗，等久一點
                continue
            if attempt == max_retries - 1:
                return f"⚠️ 總結生成失敗: {e}"
    return "⚠️ 無法生成總結"

# --- 主程式 ---
st.title("🧠 六都房市 AI 戰情室")
model_name = get_valid_model_name()
st.caption(f"資料來源：Google News | 🚀 極速批次核心 | AI 模型：{model_name or '未偵測'}")

if st.button("🔄 強制刷新 (清除快取)"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

try:
    with st.spinner('正在搜尋新聞...'):
        news_data = get_six_capital_news()
    
    if not news_data:
        st.warning("目前沒有最新新聞。")
    else:
        # 1. 執行極速批次分析
        with st.spinner('🚀 AI 正在批次分析 10 則新聞...'):
            all_titles = [n['title'] for n in news_data]
            if model_name:
                batch_results = analyze_news_batch(all_titles, model_name)
            else:
                batch_results = {}

        # 2. 顯示結果
        for news in news_data:
            st.markdown(f"""
            <div class="news-card">
                <a href="{news['link']}" target="_blank" class="news-title">{news['title']}</a>
                <div style="color:#666; font-size:13px; margin-bottom:10px;">
                    📰 {news['source']} | 🕒 {news['date']}
                </div>
            """, unsafe_allow_html=True)
            
            analysis = batch_results.get(news['title'], "⚠️ 分析資料讀取失敗 (可能 AI 回傳格式有誤)")
            if "error" in batch_results:
                analysis = f"⚠️ AI 忙碌中，請稍後再試 ({batch_results['error']})"
            
            st.markdown(f"""
                <div class="ai-box">
                    <div class="ai-label">✨ AI 智能解析</div>
                    <div style="font-size: 15px; line-height: 1.6; color: #2d3436;">
                        {analysis.replace(chr(10), '<br>')}
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # 3. 顯示總結表
        st.markdown("---")
        st.markdown("### 📊 AI 每日行銷策略總結 (六都分區)")
        with st.spinner('AI 正在制定全台廣告策略...'):
            if model_name:
                summary = generate_marketing_summary(all_titles, model_name)
                st.markdown(summary)
            else:
                st.error("無法生成總結")
        
        st.success("✅ 全部分析完成！")

except Exception as e:
    st.error(f"系統發生錯誤：{e}")

# --- 底部資訊 ---
try: ver = genai.__version__
except: ver = "Unknown"
st.markdown(f'<div class="debug-info">System: Streamlit v{st.__version__} | GenAI v{ver}</div>', unsafe_allow_html=True)
