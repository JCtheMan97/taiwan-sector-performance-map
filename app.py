import streamlit as st
import os
import re
import time
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
        padding-top: 1.5rem;
        padding-bottom: 0rem;
        padding-left: 0.5rem;
        padding-right: 0.5rem;
    }
    iframe {
        border: none !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    }
    </style>
""", unsafe_allow_html=True)

html_file = "daily_sector_performance.html"
md_file_check = "daily_sector_performance.md"
lock_file = "update.lock"
min_interval_seconds = 300  # 5 minutes cooldown to avoid rate-limiting

# Define Taiwan Timezone (UTC+8) and current Taiwan time
tw_tz = timezone(timedelta(hours=8))
now_tw = datetime.now(timezone.utc).astimezone(tw_tz)

# --- Helper: read ACTUAL data date from HTML and MD reports ---
def get_data_date():
    """Parse statistics date from both HTML and MD reports.
    Returns the date object or None. If HTML date is older than MD, returns the older date to force sync!
    """
    md_date = None
    html_date = None
    
    # 1. Parse MD date
    if os.path.exists(md_file_check):
        try:
            with open(md_file_check, "r", encoding="utf-8") as f:
                first_line = f.readline()
            m = re.search(r'\((\d{4}-\d{2}-\d{2})\)', first_line)
            if m:
                md_date = datetime.strptime(m.group(1), '%Y-%m-%d').date()
        except Exception:
            pass
            
    # 2. Parse HTML subtitle date
    if os.path.exists(html_file):
        try:
            with open(html_file, "r", encoding="utf-8") as f:
                content = f.read(10000)
            m = re.search(r'<p class="subtitle">統計日期[\s：:]*(\d{4}-\d{2}-\d{2})', content)
            if m:
                html_date = datetime.strptime(m.group(1), '%Y-%m-%d').date()
        except Exception:
            pass
            
    if html_date and md_date:
        return min(html_date, md_date)
    return html_date or md_date or None

# Check last update time (file mtime – used for display and cooldown)
last_update_dt = None
if os.path.exists(html_file):
    mtime = os.path.getmtime(html_file)
    last_update_dt = datetime.fromtimestamp(mtime, tz=tw_tz)
    last_update = last_update_dt.strftime('%Y-%m-%d %H:%M:%S')
    time_since_update = (now_tw - last_update_dt).total_seconds()
else:
    last_update = "無歷史數據"
    time_since_update = 999999

# Actual data date (read from HTML / MD files)
data_date = get_data_date()

# Calculate expected latest trading date
def get_expected_latest_trading_date(now_dt):
    """Calculates the date of the latest expected TWSE/TPEX trading session.
    Market closes at 13:30 TW Time, data fully available after 14:00.
    """
    dt = now_dt
    if dt.hour < 14:
        dt = dt - timedelta(days=1)
    
    # Roll back weekends (Saturday=5, Sunday=6) to Friday
    while dt.weekday() >= 5:
        dt = dt - timedelta(days=1)
        
    return dt.date()

expected_trading_date = get_expected_latest_trading_date(now_tw)

# Check if data is stale
is_data_stale = False
if data_date is None:
    is_data_stale = True
elif data_date < expected_trading_date:
    is_data_stale = True

# Clean stale lock file (> 5 minutes)
if os.path.exists(lock_file):
    try:
        lock_mtime = os.path.getmtime(lock_file)
        if (time.time() - lock_mtime) > 300:
            os.remove(lock_file)
    except Exception:
        pass

is_locked = os.path.exists(lock_file)

# Function to run the tracker pipeline
def run_update(ignore_cooldown=False):
    if os.path.exists(lock_file):
        st.error("⚠️ 系統目前正由其他程序更新中，請稍候 1-2 分鐘再試。")
        return False
        
    if not ignore_cooldown and time_since_update < min_interval_seconds:
        st.warning(f"📊 數據在 5 分鐘內已更新過（最後更新：{last_update}），請勿頻繁下載以免被 API 限制。")
        return False

    # Create lock file
    with open(lock_file, "w") as f:
        now_tw_lock = datetime.now(timezone.utc).astimezone(tw_tz)
        f.write(str(now_tw_lock))

    success = False
    try:
        import sys
        result = subprocess.run([sys.executable, "track_daily_performance.py"], capture_output=True, text=True, encoding="utf-8")
        if result.returncode == 0:
            success = True
        else:
            st.error(f"❌ 數據更新失敗！\nError:\n{result.stderr}")
    except Exception as e:
        st.error(f"❌ 執行更新時發生錯誤: {e}")
    finally:
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass
    return success

# Sidebar controls
st.sidebar.header("👑 台股產業資金流向圖")

data_date_str = data_date.strftime('%Y-%m-%d') if data_date else "未知"
if not is_data_stale:
    st.sidebar.success(f"📊 **資料統計日期：** `{data_date_str}`（最新）")
else:
    st.sidebar.warning(f"📊 **資料統計日期：** `{data_date_str}`（待同步）")

st.sidebar.caption(f"📅 **檔案生成時間：** `{last_update}`")
st.sidebar.caption(f"🎯 **目標最新交易日：** `{expected_trading_date}`")

if not is_data_stale:
    if st.sidebar.button("🔄 手動刷新最新數據", use_container_width=True, key="sb_refresh"):
        if run_update(ignore_cooldown=True):
            st.toast("✅ 數據已成功刷新！", icon="🎉")
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
### 💡 看板功能指引
* **21 大核心產業與 81 個細分子族群**：全市場 2,045 檔標的精準分類，同族群連動一目瞭然。
* **平滑週期切換 (1D / 5D / 10D / 20D)**：各板塊位置穩定不跳動，即時反映各週期漲跌排名與法人籌碼。
* **ECharts Treemap 產業地圖**：區塊大小代表市值規模，顏色深淺代表資金漲跌強度。
""")

# ── Main Content Area ──
# If data is stale, DO NOT show the old 7/27 data!
# Automatically execute update with a clear loading status screen
if is_data_stale and not st.session_state.get("force_view_stale", False):
    st.title("👑 台股產業資金流向圖")
    with st.status(f"🚀 正在自動更新至最新收盤數據（最新交易日：{expected_trading_date}）...", expanded=True) as status_box:
        st.write(f"📊 檢測到本地快取日期為舊版 `{data_date_str}`，為確保數據即時性，即刻自動同步至最新收盤行情。")
        st.write("⏳ 正在下載全市場 1,980+ 檔標的行情、運算 21 大產業與 81 個細分子板塊各週期指標與法人買賣超...")
        st.write("💡 預計約需 1 ~ 2 分鐘，請稍候片刻...")
        
        update_success = run_update(ignore_cooldown=True)
        if update_success:
            status_box.update(label="✅ 最新收盤數據已同步完成！正在呈現最新看板...", state="complete")
            time.sleep(0.5)
            st.rerun()
        else:
            status_box.update(label="⚠️ 自動更新暫時遇到問題", state="error")
            st.error("行情數據伺服器連線異常或暫無資料，您可以點擊下方按鈕重新嘗試：")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 立即重新嘗試更新", type="primary", use_container_width=True):
                    st.rerun()
            with col2:
                if os.path.exists(html_file):
                    if st.button("👁️ 仍查看歷史快取看板", use_container_width=True):
                        st.session_state["force_view_stale"] = True
                        st.rerun()

elif os.path.exists(html_file):
    # Render fresh HTML directly with full screen height
    with open(html_file, "r", encoding="utf-8") as f:
        html_content = f.read()
    st.components.v1.html(html_content, height=2400, scrolling=True)

else:
    # First time initialization if no HTML exists
    st.title("👑 台股產業資金流向圖")
    st.info("💡 尚未生成 HTML 看板，即刻為您拉取台股最新收盤行情：")
    if st.button("🚀 立即下載數據並生成看板 (約需 1-2 分鐘)", type="primary", use_container_width=True, key="main_init_btn"):
        if run_update(ignore_cooldown=True):
            st.rerun()
