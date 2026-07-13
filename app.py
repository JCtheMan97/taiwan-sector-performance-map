import streamlit as st
import os
import subprocess
from datetime import datetime

st.set_page_config(
    page_title="台股產業資金流向圖",
    page_icon="👑",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS to hide Streamlit UI footers/menus and maximize screen space
# Note: We do NOT hide the header completely so the sidebar collapse/expand toggle button remains visible.
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {
        padding-top: 2rem;
        padding-bottom: 0rem;
        padding-left: 0rem;
        padding-right: 0rem;
    }
    iframe {
        border: none !important;
        border-radius: 0px !important;
    }
    </style>
""", unsafe_allow_html=True)

# Function to run the tracker pipeline
def run_update():
    # If called from main page, we show a spinner there; if from sidebar, we show it there.
    # To keep it simple, we wrap it in a spinner
    with st.spinner("🚀 正在下載最新個股數據並生成看板... (約需 1-2 分鐘)"):
        try:
            # Run the python script
            result = subprocess.run(["python", "track_daily_performance.py"], capture_output=True, text=True, encoding="utf-8")
            if result.returncode == 0:
                st.toast("數據已更新", icon="✅")
            else:
                st.error(f"❌ 數據更新失敗！\nError:\n{result.stderr}")
        except Exception as e:
            st.error(f"❌ 執行更新時發生錯誤: {e}")

# Sidebar controls
st.sidebar.header("👑 台股產業資金流向圖")

# Last updated time
html_file = "daily_sector_performance.html"
if os.path.exists(html_file):
    mtime = os.path.getmtime(html_file)
    last_update = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
else:
    last_update = "無歷史數據"

st.sidebar.write(f"📅 **數據更新時間：**\n`{last_update}`")

if st.sidebar.button("🔄 立即更新數據", use_container_width=True):
    run_update()
    st.rerun()

# Expandable sidebar for markdown report
md_file = "daily_sector_performance.md"
if os.path.exists(md_file):
    with open(md_file, "r", encoding="utf-8") as f:
        md_content = f.read()
    with st.sidebar.expander("📝 每日主產業統計簡報", expanded=False):
        st.markdown(md_content)

st.sidebar.markdown("---")
st.sidebar.markdown("""
### 💡 說明
* 本看板整合 **ECharts 產業資金流向圖 (Treemap)** 與 **個股漲跌熱力圖 (Heatmap)**。
* **ECharts Treemap** 區域大小代表市值，顏色代表漲跌。點擊可縮放、點擊個股可自動篩選下方個股熱力圖。
* **批次分析** 可同時輸入多檔個股代碼，快速分析其在板塊中的分佈。
""")

# Render the HTML directly on the main page (taking up the entire viewport)
if os.path.exists(html_file):
    with open(html_file, "r", encoding="utf-8") as f:
        html_content = f.read()
    st.components.v1.html(html_content, height=2200, scrolling=True)
else:
    st.warning("⚠️ 尚未生成 HTML 看板。")
    st.info("💡 由於這是您第一次在雲端部署或尚未生成數據，請點擊下方按鈕開始拉取台股收盤行情：")
    if st.button("🚀 立即下載數據並生成看板 (約需 1-2 分鐘)", type="primary", use_container_width=True):
        run_update()
        st.rerun()
