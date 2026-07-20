import streamlit as st
import os
import re
import subprocess
from datetime import datetime, date, timezone, timedelta

st.set_page_config(
    page_title="台股產業資金流向圖",
    page_icon="👑",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS to hide Streamlit UI footers/menus and maximize screen space
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

html_file = "daily_sector_performance.html"
md_file_check = "daily_sector_performance.md"
lock_file = "update.lock"
min_interval_seconds = 600  # 10 minutes cooldown to avoid rate-limiting

# Define Taiwan Timezone (UTC+8)
tw_tz = timezone(timedelta(hours=8))

# --- Helper: read ACTUAL data date from the markdown report ---
def get_data_date():
    """Parse the statistics date from the first line of the MD report.
    Returns a date object or None if the file is missing / unparseable.
    """
    if not os.path.exists(md_file_check):
        return None
    try:
        with open(md_file_check, "r", encoding="utf-8") as f:
            first_line = f.readline()
        # Expected format:  # 📊 每日族群漲跌與資金流向看板 (2026-07-17)
        m = re.search(r'\((\d{4}-\d{2}-\d{2})\)', first_line)
        if m:
            return datetime.strptime(m.group(1), '%Y-%m-%d').date()
    except Exception:
        pass
    return None

# Check last update time (file mtime – used for display and cooldown)
now_tw = datetime.now(timezone.utc).astimezone(tw_tz)
last_update_dt = None
if os.path.exists(html_file):
    mtime = os.path.getmtime(html_file)
    last_update_dt = datetime.fromtimestamp(mtime, tz=tw_tz)
    last_update = last_update_dt.strftime('%Y-%m-%d %H:%M:%S')
    time_since_update = (now_tw - last_update_dt).total_seconds()
else:
    last_update = "無歷史數據"
    time_since_update = 999999

# Actual data date (read from MD file – more reliable than file mtime)
data_date = get_data_date()
today_tw = now_tw.date()

# Function to run the tracker pipeline
def run_update(ignore_cooldown=False):
    if os.path.exists(lock_file):
        st.error("⚠️ 系統目前正由其他使用者更新中，請稍候再試。")
        return False
        
    if not ignore_cooldown and time_since_update < min_interval_seconds:
        st.warning(f"📊 數據在 10 分鐘內已更新過（最後更新：{last_update}），請勿頻繁下載以免被 Yahoo API 限制 IP。")
        return False

    # Create lock file
    with open(lock_file, "w") as f:
        now_tw = datetime.now(timezone.utc).astimezone(tw_tz)
        f.write(str(now_tw))

    success = False
    try:
        import sys
        # Run the python script using the exact same python interpreter path
        result = subprocess.run([sys.executable, "track_daily_performance.py"], capture_output=True, text=True, encoding="utf-8")
        if result.returncode == 0:
            st.toast("數據已更新", icon="✅")
            success = True
        else:
            st.error(f"❌ 數據更新失敗！\nError:\n{result.stderr}")
    except Exception as e:
        st.error(f"❌ 執行更新時發生錯誤: {e}")
    finally:
        # Remove lock file when finished
        if os.path.exists(lock_file):
            os.remove(lock_file)
    return success

# ── Auto-update decision logic ───────────────────────────────────────────────
# Compare ACTUAL DATA DATE (from the MD file) with today's Taiwan date.
is_locked = os.path.exists(lock_file)
past_close = now_tw.hour >= 14  # After 14:00 Taiwan time (market closed)

is_data_stale = False
if data_date is None:
    is_data_stale = True
elif data_date < today_tw:
    if now_tw.weekday() < 5 and past_close:
        # Weekday AND past 14:00 → today's close data should be available
        is_data_stale = True
    elif (now_tw - last_update_dt).total_seconds() > 16 * 3600:
        # Or it's been more than 16 hours regardless
        is_data_stale = True

# Cooldown limits:
# - If data is ALREADY updated to today (data_date == today_tw): 10 minutes (600s) cooldown.
# - If data is STALE (data_date < today_tw): 60 seconds retry lock (to prevent rapid looping on errors).
cooldown_limit = min_interval_seconds if not is_data_stale else 60
is_in_cooldown = time_since_update < cooldown_limit

if is_data_stale and not is_locked and not is_in_cooldown:
    st.info(f"🔄 偵測到有最新的台股收盤數據（目前資料日期：{data_date}），系統正在自動更新看板中，請稍候約 1-2 分鐘...")
    if run_update(ignore_cooldown=True):
        st.rerun()

# Sidebar controls
st.sidebar.header("👑 台股產業資金流向圖")

data_date_str = data_date.strftime('%Y-%m-%d') if data_date else "未知"
st.sidebar.write(f"📊 **資料統計日期：** `{data_date_str}`")
st.sidebar.write(f"📅 **檔案更新時間：** `{last_update}`")

# Render update button on sidebar based on system status
if is_locked:
    st.sidebar.warning("⚠️ 其他使用者正在更新中...")
    st.sidebar.button("🔄 讀取中...", disabled=True, use_container_width=True, key="sb_btn_locked")
elif is_in_cooldown and not is_data_stale:
    st.sidebar.info("✅ 數據已是今日最新 (10分鐘內)")
    st.sidebar.button("🔄 10分鐘內已更新過", disabled=True, use_container_width=True, key="sb_btn_frequent")
elif is_in_cooldown and is_data_stale:
    st.sidebar.warning("⏳ 剛嘗試更新過，請稍候 1 分鐘...")
    st.sidebar.button("🔄 1分鐘內已嘗試過", disabled=True, use_container_width=True, key="sb_btn_stale_retry")
else:
    btn_label = "🚀 立即更新為今日數據" if is_data_stale else "🔄 刷新數據"
    btn_type = "primary" if is_data_stale else "secondary"
    if st.sidebar.button(btn_label, type=btn_type, use_container_width=True, key="sb_btn_active"):
        if run_update(ignore_cooldown=is_data_stale):
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
    
    if is_locked:
        st.warning("⚠️ 系統目前正由其他使用者更新中，請稍候並重新整理網頁。")
    elif is_too_frequent:
        st.info(f"📊 數據剛更新過（最後更新：{last_update}），請重新整理網頁載入。")
    else:
        if st.button("🚀 立即下載數據並生成看板 (約需 1-2 分鐘)", type="primary", use_container_width=True, key="main_btn_active"):
            if run_update():
                st.rerun()
