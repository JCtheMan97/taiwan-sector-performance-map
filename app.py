import streamlit as st
import os
import subprocess
from datetime import datetime

st.set_page_config(
    page_title="台股產業資金流向熱力圖",
    page_icon="👑",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Title
st.title("👑 台股產業資金流向熱力圖 Dashboard")

# Function to run the tracker pipeline
def run_update():
    with st.spinner("🚀 正在從 Yahoo Finance 下載最新數據並重新生成看板... (大約需要 1-2 分鐘)"):
        try:
            # Run the python script
            result = subprocess.run(["python", "track_daily_performance.py"], capture_output=True, text=True, encoding="utf-8")
            if result.returncode == 0:
                st.success("🎉 數據更新成功！")
                st.toast("數據已更新", icon="✅")
            else:
                st.error(f"❌ 數據更新失敗！\nError:\n{result.stderr}")
        except Exception as e:
            st.error(f"❌ 執行更新時發生錯誤: {e}")

# Sidebar controls
st.sidebar.header("⚙️ 控制面板")

# Last updated time
html_file = "daily_sector_performance.html"
if os.path.exists(html_file):
    mtime = os.path.getmtime(html_file)
    last_update = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
else:
    last_update = "無歷史數據"

st.sidebar.write(f"📅 **數據最後更新時間：**\n`{last_update}`")

if st.sidebar.button("🔄 立即更新數據", use_container_width=True):
    run_update()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("""
### 💡 說明
* 本看板整合 **ECharts 產業資金流向圖 (Treemap)** 與 **個股漲跌熱力圖 (Heatmap)**。
* **ECharts Treemap** 區域大小代表市值，顏色代表漲跌。點擊可縮放、點擊個股可自動篩選下方個股熱力圖。
* **批次分析** 可同時輸入多檔個股代碼，快速分析其在板塊中的分佈。
""")

# Tabs
tab1, tab2 = st.tabs(["📊 資金流向熱力圖", "📝 每日主產業統計簡報"])

with tab1:
    if os.path.exists(html_file):
        with open(html_file, "r", encoding="utf-8") as f:
            html_content = f.read()
        # Embed the HTML file in Streamlit
        st.components.v1.html(html_content, height=1300, scrolling=True)
    else:
        st.warning("⚠️ 尚未生成 HTML 看板。請點擊左側「🔄 立即更新數據」按鈕來下載數據並生成看板。")

with tab2:
    md_file = "daily_sector_performance.md"
    if os.path.exists(md_file):
        with open(md_file, "r", encoding="utf-8") as f:
            md_content = f.read()
        st.markdown(md_content)
    else:
        st.info("💡 數據更新後，將在此顯示每日產業漲跌幅與個股數統計簡報。")
