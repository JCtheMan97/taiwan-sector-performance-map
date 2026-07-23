from fetch_institutional_data import get_institutional_data
import time
# -*- coding: utf-8 -*-
"""
track_daily_performance.py
Downloads prices for all 1979 stocks over a 20-day window, calculates:
1. Multi-period nested Treemap datasets (1D, 5D, 10D).
2. Collapsible grid heatmap with dynamic tab switching and float-to-top search.
3. Market breadth stats and Leaders/Laggards ranks.
Outputs:
- daily_sector_performance.md (1D, 5D, 10D sector tables).
- daily_sector_performance.html (Premium ECharts Treemap + Collapsible Grid Heatmap dashboard).
"""

import os
import json
import re
import sys
import io
import hashlib
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf

# Standardize output encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Constants
STOCK_LIST_FILE = "stocks_list.txt"
CACHE_FILE = "industry_cache.json"
REPORT_MD = "daily_sector_performance.md"
REPORT_HTML = "daily_sector_performance.html"

# Import mappings from classify_all_database
try:
    from classify_all_database import STOCK_SUBCLASS, CLEAN_SUBCLASS, DETAILED_SECTOR_MAP, clean_stock_name, KEYWORD_THESAURUS, advanced_has_kw, clean_category, get_mid_category
except ImportError:
    print("Warning: Could not import classification mappings. Defining fallbacks...")
    STOCK_SUBCLASS = {}
    CLEAN_SUBCLASS = {}
    DETAILED_SECTOR_MAP = {}
    KEYWORD_THESAURUS = {}
    def clean_stock_name(name):
        return name
    def advanced_has_kw(target_text, category_name):
        return False

def load_stock_list(filepath):
    """Loads all tickers and names from stocks_list.txt."""
    stocks = []
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",", 1)
            if len(parts) >= 2:
                ticker = parts[0].strip().lstrip('\ufeff')
                name = parts[1].strip()
                stocks.append((name, ticker))
    return stocks

def get_safe_id(name):
    """Generates a safe HTML ID string using MD5 to bypass encoding conflicts."""
    return "id_" + hashlib.md5(name.encode('utf-8')).hexdigest()

def get_tick_size(price):
    """Returns official Taiwan TWSE/TPEX tick size for a given price level."""
    if price < 10.0:
        return 0.01
    elif price < 50.0:
        return 0.05
    elif price < 100.0:
        return 0.10
    elif price < 500.0:
        return 0.50
    elif price < 1000.0:
        return 1.00
    else:
        return 5.00

def calc_tw_limit_up(p0):
    """Calculates exact TWSE/TPEX Limit Up Price from previous close p0."""
    if pd.isna(p0) or p0 <= 0:
        return 999999.0
    raw = p0 * 1.10
    tick = get_tick_size(raw)
    limit_up = np.floor(round(raw, 4) / tick + 1e-6) * tick
    return round(limit_up, 2)

def calc_tw_limit_down(p0):
    """Calculates exact TWSE/TPEX Limit Down Price from previous close p0."""
    if pd.isna(p0) or p0 <= 0:
        return 0.0
    raw = p0 * 0.90
    tick = get_tick_size(raw)
    limit_down = np.ceil(round(raw, 4) / tick - 1e-6) * tick
    return round(limit_down, 2)

def get_categories(name, data, ticker):
    """Categorizes stock using cache details."""
    ticker_num = ticker.split(".")[0].strip()
    raw_industry = data.get("industry", "Other")
    longName = data.get("longName", "")
    search_text = (name + " " + longName).upper()
    summary = data.get("longBusinessSummary", "").lower()
    
    def has_kw(kws, in_summary=True):
        target = summary if in_summary else search_text
        for w in kws:
            w_lower = w.lower()
            if len(w_lower) <= 3:
                if re.search(r'\b' + re.escape(w_lower) + r'\b', target):
                    return True
            else:
                if w_lower in target:
                    return True
        return False

    is_tech_sector = raw_industry in [
        "Semiconductors", "Semiconductor Equipment & Materials", 
        "Electronic Components", "Computer Hardware", 
        "Communication Equipment", "Software - Application", 
        "Software-Application", "Software - Infrastructure", 
        "Software-Infrastructure", "Information Technology Services", 
        "Electronic Distribution", "Electronics & Computer Distribution"
    ]
    is_industrial_sector = raw_industry in [
        "Electrical Equipment & Parts", "Specialty Industrial Machinery", 
        "Aerospace & Defense", "Engineering & Construction", 
        "Metal Fabrication", "Tools & Accessories"
    ]

    # Determine categories
    if name in STOCK_SUBCLASS:
        main_cat, sub_cat = STOCK_SUBCLASS[name]
    elif clean_stock_name(name) in CLEAN_SUBCLASS:
        main_cat, sub_cat = CLEAN_SUBCLASS[clean_stock_name(name)]
    else:
        # Custom overrides using advanced synonym matching (Thesaurus-based)
        if advanced_has_kw(summary, "離岸風電與風力發電") or advanced_has_kw(search_text, "離岸風電與風力發電"):
            main_cat, sub_cat = ("綠能、環保與化學工業", "離岸風電與風力發電")
        elif advanced_has_kw(summary, "重電與電網") or advanced_has_kw(search_text, "重電與電網"):
            main_cat, sub_cat = ("綠能、環保與化學工業", "重電與電線電纜")
        elif advanced_has_kw(summary, "矽光子與CPO") or advanced_has_kw(search_text, "矽光子與CPO"):
            main_cat, sub_cat = ("通訊、線材與連接器", "光通訊與光模組")
        elif advanced_has_kw(summary, "散熱模組") or advanced_has_kw(search_text, "散熱模組"):
            main_cat, sub_cat = ("工業電腦與電腦週邊", "散熱模組與元件")
        elif advanced_has_kw(summary, "先進封裝與設備") or advanced_has_kw(search_text, "先進封裝與設備"):
            if "equipment" in raw_industry.lower() or "machinery" in raw_industry.lower() or any(kw in summary for kw in ["equipment", "tool", "machine", "wet process", "probe card", "lead frame"]):
                main_cat, sub_cat = ("半導體與 PCB 設備/材料", "半導體設備與材料")
            else:
                main_cat, sub_cat = ("半導體產業", "IC 封測 (OSAT)")
        
        # Raw industry defaults to clean up general categories before keyword check
        elif raw_industry in ["Electronic Distribution", "Electronics & Computer Distribution"]:
            main_cat, sub_cat = ("傳統工業與其它", "電子通路")
        elif raw_industry == "Communication Equipment":
            main_cat, sub_cat = ("通訊、線材與連接器", "通信與網路設備")
        
        # Non-tech and non-industrial traditional sectors bypass custom tech checks
        elif not is_tech_sector and not is_industrial_sector:
            normalized_ind = raw_industry.replace("X", " - ").replace("\u2013", " - ").replace("\u2014", " - ").strip()
            if normalized_ind in DETAILED_SECTOR_MAP:
                main_cat, sub_cat = DETAILED_SECTOR_MAP[normalized_ind]
            elif raw_industry in DETAILED_SECTOR_MAP:
                main_cat, sub_cat = DETAILED_SECTOR_MAP[raw_industry]
            else:
                main_cat = "其他未分類"
                sub_cat = raw_industry
        
        # 2. Machinery, Equipment and Engineering Override
        elif raw_industry in ["Specialty Industrial Machinery", "Engineering & Construction", "Tools & Accessories"] and has_kw(["semiconductor", "wafer", "pcb", "printed circuit", "ic"]):
            main_cat, sub_cat = ("半導體與 PCB 設備/材料", "半導體與 PCB 製程設備")
            
        # 4. Semiconductors
        elif raw_industry == "Semiconductors" or raw_industry == "Semiconductor Equipment & Materials" or has_kw(["semiconductor", "integrated circuit", "wafer", "microchip"]):
            if has_kw(["foundry", "wafer fabrication", "wafer manufacturing"]):
                main_cat, sub_cat = ("半導體產業", "晶圓代工")
            elif has_kw(["packaging", "semiconductor testing", "osat", "assembly service"]):
                main_cat, sub_cat = ("半導體產業", "IC 封測 (OSAT)")
            elif has_kw(["dram", "flash memory", "sram", "eeprom", "nor flash", "memory product", "memory module", "ssd", "solid state drive", "flash drive"]):
                main_cat, sub_cat = ("半導體產業", "記憶體 (DRAM/Flash)")
            elif has_kw(["semiconductor equipment", "photolithography", "etching", "chemical mechanical", "probe card", "lead frame"]):
                main_cat, sub_cat = ("半導體與 PCB 設備/材料", "半導體設備與材料")
            elif has_kw(["mosfet", "diode", "igbt", "rectifier", "power semiconductor"]):
                main_cat, sub_cat = ("半導體產業", "功率半導體 (MOSFET/二極體)")
            elif has_kw(["gallium arsenide", "gaas", "rf ic", "radio frequency"]):
                main_cat, sub_cat = ("半導體產業", "化合物半導體與射頻晶片")
            elif has_kw(["ic design", "chip design", "fabless", "asic", "chipset"]) or has_kw(["設計", "DESIGN", "晶片", "矽", "IC"], in_summary=False):
                if has_kw(["power management", "pmic", "analog ic"]):
                    main_cat, sub_cat = ("半導體產業", "IC 設計 - 類比與電源管理")
                elif has_kw(["driver ic", "lcd driver"]):
                    main_cat, sub_cat = ("半導體產業", "IC 設計 - 顯示驅動 IC")
                elif has_kw(["microcontroller", "mcu"]):
                    main_cat, sub_cat = ("半導體產業", "IC 設計 - MCU")
                elif has_kw(["asic", "soc", "intellectual property", "ip core", "ip"]):
                    main_cat, sub_cat = ("半導體產業", "IC 設計 - ASIC/IP")
                else:
                    main_cat, sub_cat = ("半導體產業", "IC 設計")
            else:
                main_cat, sub_cat = ("半導體產業", "IC 設計")
        
        # 5. PCB & CCL
        elif has_kw(["printed circuit board", "pcb", "copper clad laminate", "ccl", "flexible printed", "fccl", "abf", "bt", "ic carrier", "carrier board"]) or has_kw(["電路板", "PCB", "載板", "CCL", "銅箔基板", "軟板", "硬板"], in_summary=False):
            if has_kw(["carrier board", "ic carrier", "ic substrate", "package substrate", "abf", "bt"]) or has_kw(["載板", "ABF", "BT"], in_summary=False):
                main_cat, sub_cat = ("PCB 與銅箔基板", "IC 載板")
            elif has_kw(["ccl", "copper clad laminate"]) or has_kw(["銅箔", "CCL", "基板"], in_summary=False):
                main_cat, sub_cat = ("PCB 與銅箔基板", "銅箔基板 (CCL)")
            elif has_kw(["flexible printed", "fpc", "fccl"]) or has_kw(["軟性", "FCCL", "軟板"], in_summary=False):
                main_cat, sub_cat = ("PCB 與銅箔基板", "軟性銅箔基板 (FCCL)/軟板")
            else:
                main_cat, sub_cat = ("PCB 與銅箔基板", "印刷電路板 (PCB)")
        
        # 6. Passive Components & Quartz
        elif has_kw(["resistor", "capacitor", "inductor", "choke", "varistor", "thermistor", "quartz", "oscillator", "crystal"]) or has_kw(["電阻", "電容", "電感", "被動", "陶瓷", "石英", "晶體", "振盪", "晶振"], in_summary=False):
            if has_kw(["quartz", "crystal", "oscillator", "resonator"]) or has_kw(["石英", "晶體", "振盪", "晶振"], in_summary=False):
                main_cat, sub_cat = ("被動元件與石英元件", "石英元件")
            elif has_kw(["varistor", "thermistor", "fuse", "protection device"]) or has_kw(["保護元件", "防護", "保險絲"], in_summary=False):
                main_cat, sub_cat = ("被動元件與石英元件", "被動元件 - 保護元件")
            elif has_kw(["electrolytic capacitor", "aluminum capacitor"]) or has_kw(["電解電容"], in_summary=False):
                main_cat, sub_cat = ("被動元件與石英元件", "被動元件 - 電解電容")
            elif has_kw(["solid capacitor", "polymer capacitor"]) or has_kw(["固態電容"], in_summary=False):
                main_cat, sub_cat = ("被動元件與石英元件", "被動元件 - 固態電容")
            elif has_kw(["inductor", "choke", "magnetic", "coil"]) or has_kw(["電感", "磁性"], in_summary=False):
                main_cat, sub_cat = ("被動元件與石英元件", "被動元件 - 電感與磁性元件")
            else:
                main_cat, sub_cat = ("被動元件與石英元件", "被動元件 (電阻/電容/電感)")
        
        # 3. LED & Optoelectronics
        elif has_kw(["led", "light-emitting diode", "optoelectronic", "display panel", "optical lens", "camera module"]):
            main_cat, sub_cat = ("光電與顯示面板", "光電與光學鏡頭")
        
        # 7. Cooling
        elif has_kw(["thermal module", "cooling fan", "heat sink", "vapor chamber", "heat pipe"]) or has_kw(["散熱", "風扇", "熱"], in_summary=False):
            main_cat, sub_cat = ("工業電腦與電腦週邊", "散熱模組與元件")
        
        # 8. Server Rails & Chassis
        elif (has_kw(["slide rail", "guide rail"]) and has_kw(["server"])) or has_kw(["server chassis"]) or has_kw(["導軌", "滑軌", "機殼"], in_summary=False):
            main_cat, sub_cat = ("伺服器與資訊週邊", "伺服器導軌與滑軌")
        
        # 9. Industrial PC (IPC)
        elif has_kw(["industrial computer", "industrial pc", "single board computer", "ipc"]) or has_kw(["工業電腦", "IPC"], in_summary=False):
            main_cat, sub_cat = ("工業電腦與電腦週邊", "工業電腦 (IPC)")
        
        # 10. Server / EMS / ODM
        elif has_kw(["notebook computer", "server manufacturing", "pcb assembly", "ems"]):
            main_cat, sub_cat = ("伺服器與資訊週邊", "伺服器與筆電代工")
        
        else:
            normalized_ind = raw_industry.replace("X", " - ").replace("\u2013", " - ").replace("\u2014", " - ").strip()
            if normalized_ind in DETAILED_SECTOR_MAP:
                main_cat, sub_cat = DETAILED_SECTOR_MAP[normalized_ind]
            elif raw_industry in DETAILED_SECTOR_MAP:
                main_cat, sub_cat = DETAILED_SECTOR_MAP[raw_industry]
            else:
                main_cat = "其他未分類"
                sub_cat = raw_industry
                
    return clean_category(main_cat, sub_cat)

def run_pipeline():
    global inst_data
    try:
        inst_data = get_institutional_data()
    except Exception as e:
        print(f"⚠️ Institutional fetch skipped: {e}")
        inst_data = {}
    print("=" * 60)
    print("🚀 Starting Daily Sector Performance Tracker & Dashboard")
    print("=" * 60)
    
    # 1. Load stocks list and industry cache
    stocks = load_stock_list(STOCK_LIST_FILE)
    if not stocks:
        print("Error: No stocks parsed from stocks_list.txt.")
        return
        
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    print(f"Loaded {len(stocks)} stocks and {len(cache)} cached profiles.")
    
    # 2. Map tickers to names and industry categories
    print("Categorizing stocks...")
    stock_mapping = {}
    for name, ticker in stocks:
        profile = cache.get(ticker, {})
        main_cat, sub_cat = get_categories(name, profile, ticker)
        # market_cap will be updated later with real data (shares × price)
        mid_cat = get_mid_category(name, main_cat, sub_cat)
        stock_mapping[ticker] = {
            "name": name,
            "main_cat": main_cat,
            "mid_cat": mid_cat,
            "sub_cat": sub_cat,
            "market_cap": 1_000_000_000  # temporary placeholder
        }
        
    # 3. Batch download prices and volumes (period=20d to cover 10 trading days)
    tickers = list(stock_mapping.keys())
    chunk_size = 500
    all_closes = []
    all_volumes = []
    all_closes_today = []
    all_volumes_today = []
    
    print(f"Downloading prices and volumes for {len(tickers)} tickers in chunks of {chunk_size}...")
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i+chunk_size]
        print(f"Downloading chunk {i // chunk_size + 1} / {(len(tickers) + chunk_size - 1) // chunk_size}...")
        try:
            df = yf.download(chunk, period="45d", progress=False, group_by='column')
            time.sleep(2.0) # Prevent Yahoo Rate Limit
            df_today = yf.download(chunk, period="1d", progress=False, group_by='column')
            time.sleep(2.0)
            
            if df.empty:
                print(f"Warning: Empty data in chunk {i // chunk_size + 1}")
                continue

            # Efficient vectorized column extraction for 45d historical
            if isinstance(df.columns, pd.MultiIndex):
                closes_chunk = df['Close'] if 'Close' in df.columns.levels[0] else (df['Adj Close'] if 'Adj Close' in df.columns.levels[0] else pd.DataFrame())
                volumes_chunk = df['Volume'] if 'Volume' in df.columns.levels[0] else pd.DataFrame()
            else:
                closes_chunk = df[['Close']] if 'Close' in df.columns else pd.DataFrame()
                volumes_chunk = df[['Volume']] if 'Volume' in df.columns else pd.DataFrame()

            # Efficient vectorized column extraction for 1d real-time
            if not df_today.empty:
                if isinstance(df_today.columns, pd.MultiIndex):
                    closes_today_chunk = df_today['Close'] if 'Close' in df_today.columns.levels[0] else (df_today['Adj Close'] if 'Adj Close' in df_today.columns.levels[0] else pd.DataFrame())
                    volumes_today_chunk = df_today['Volume'] if 'Volume' in df_today.columns.levels[0] else pd.DataFrame()
                else:
                    closes_today_chunk = df_today[['Close']] if 'Close' in df_today.columns else pd.DataFrame()
                    volumes_today_chunk = df_today[['Volume']] if 'Volume' in df_today.columns else pd.DataFrame()
                
                if not closes_today_chunk.empty:
                    all_closes_today.append(closes_today_chunk)
                    all_volumes_today.append(volumes_today_chunk)

            if not closes_chunk.empty and not volumes_chunk.empty:
                all_closes.append(closes_chunk)
                all_volumes.append(volumes_chunk)
        except Exception as e:
            print(f"Error downloading chunk: {e}")
            
    if not all_closes or not all_volumes:
        print("Error: No pricing or volume data downloaded.")
        return
        
    combined_closes = pd.concat(all_closes, axis=1)
    combined_volumes = pd.concat(all_volumes, axis=1)
    
    # Merge today's 1d real-time quotes into combined_closes and combined_volumes
    if all_closes_today:
        combined_closes_today = pd.concat(all_closes_today, axis=1)
        combined_volumes_today = pd.concat(all_volumes_today, axis=1) if all_volumes_today else pd.DataFrame()
        
        today_date = combined_closes_today.index[-1]
        last_date = combined_closes.index[-1]
        
        if today_date.date() > last_date.date():
            # Today's quote is newer than historical download's last date -> Append today's row!
            closes_row = combined_closes_today.iloc[-1]
            volumes_row = combined_volumes_today.iloc[-1] if not combined_volumes_today.empty else pd.Series(1, index=closes_row.index)
            combined_closes.loc[today_date] = closes_row
            combined_volumes.loc[today_date] = volumes_row
        else:
            # Same date -> Fill NaNs in the last row vectorised for both closes and volumes
            combined_closes.loc[last_date] = combined_closes.loc[last_date].combine_first(combined_closes_today.loc[today_date])
            if not combined_volumes_today.empty:
                combined_volumes.loc[last_date] = combined_volumes.loc[last_date].combine_first(combined_volumes_today.loc[today_date])
    
    # Mask close prices where volume is 0 (prevents stale prices on holidays/closures)
    combined_closes = combined_closes.mask(combined_volumes == 0)
    
    # Extract valid trading rows (drop trailing rows where all values are NaN)
    valid_df = combined_closes.dropna(how='all')
    
    # Cleanly drop trailing dates that have incomplete/empty price data
    while len(valid_df) >= 2:
        last_row = valid_df.iloc[-1]
        non_nan_count = last_row.notna().sum()
        total_count = len(last_row)
        if non_nan_count < (total_count * 0.5):
            valid_df = valid_df.iloc[:-1]
        else:
            break
            
    # ── Market Cap Calculation ─────────────────────────────────────────────────
    # Use shares_outstanding × last close price to compute real-time market cap.
    # Shares are cached in mcap_cache.json so we don't refetch every single day.
    MCAP_CACHE_FILE = "mcap_cache.json"
    mcap_cache = {}
    if os.path.exists(MCAP_CACHE_FILE):
        with open(MCAP_CACHE_FILE, "r", encoding="utf-8") as f:
            mcap_cache = json.load(f)

    last_prices = valid_df.iloc[-1]  # today's close prices
    tickers_needing_shares = [t for t in stock_mapping.keys() if t not in mcap_cache]

    if tickers_needing_shares:
        print(f"Fetching shares_outstanding for {len(tickers_needing_shares)} new tickers (first time only)...")
        for i in range(0, len(tickers_needing_shares), 200):
            chunk = tickers_needing_shares[i:i+200]
            for t in chunk:
                try:
                    fi = yf.Ticker(t).fast_info
                    shares = getattr(fi, 'shares', None) or getattr(fi, 'shares_outstanding', None)
                    if shares and shares > 0:
                        mcap_cache[t] = int(shares)
                except Exception:
                    pass
        with open(MCAP_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(mcap_cache, f)
        print(f"Saved shares_outstanding for {len(mcap_cache)} tickers to {MCAP_CACHE_FILE}")

    # Now compute real market cap = shares × last close price
    updated_count = 0
    for ticker in stock_mapping:
        price = last_prices.get(ticker, None)
        shares = mcap_cache.get(ticker, None)
        if price and shares and pd.notna(price) and price > 0:
            stock_mapping[ticker]["market_cap"] = int(shares * price)
            updated_count += 1
        # else: keep the 1B placeholder (will look small but not cause crash)
    print(f"Market cap updated for {updated_count}/{len(stock_mapping)} stocks using shares × price.")
    # ──────────────────────────────────────────────────────────────────────────

    num_days = len(valid_df)
    if num_days < 2:
        print("Error: Insufficient historical trading dates found.")
        return

    date_str = str(valid_df.index[-1].date())
    prev_date_str = str(valid_df.index[-2].date())
    print(f"Trading date: {date_str}. Total valid trading days loaded: {num_days}.")
    
    # Calculate returns vectorised for 1D, 5D, 10D, and 20D
    change_1d = ((valid_df.iloc[-1] - valid_df.iloc[-2]) / valid_df.iloc[-2]) * 100
    
    idx_5d = -6 if num_days >= 6 else 0
    change_5d = ((valid_df.iloc[-1] - valid_df.iloc[idx_5d]) / valid_df.iloc[idx_5d]) * 100
    
    idx_10d = -11 if num_days >= 11 else 0
    change_10d = ((valid_df.iloc[-1] - valid_df.iloc[idx_10d]) / valid_df.iloc[idx_10d]) * 100
    
    idx_20d = -21 if num_days >= 21 else 0
    change_20d = ((valid_df.iloc[-1] - valid_df.iloc[idx_20d]) / valid_df.iloc[idx_20d]) * 100
    
    # Clean anomalies (e.g. capital reduction multipliers)
    change_1d = change_1d[(change_1d >= -11) & (change_1d <= 11)].dropna()
    change_5d = change_5d[(change_5d >= -45) & (change_5d <= 80)].dropna()
    change_10d = change_10d[(change_10d >= -60) & (change_10d <= 120)].dropna()
    change_20d = change_20d[(change_20d >= -75) & (change_20d <= 180)].dropna()
    
    # Pack returns into dictionaries
    dict_1d = change_1d.to_dict()
    dict_5d = change_5d.to_dict()
    dict_10d = change_10d.to_dict()
    dict_20d = change_20d.to_dict()
    
    p_yesterday = valid_df.iloc[-2] if len(valid_df) >= 2 else pd.Series()
    p_today = valid_df.iloc[-1] if len(valid_df) >= 1 else pd.Series()

    # Create unified master records
    all_records = []
    for ticker, mapping in stock_mapping.items():
        val_1d = dict_1d.get(ticker, None)
        val_5d = dict_5d.get(ticker, None)
        val_10d = dict_10d.get(ticker, None)
        val_20d = dict_20d.get(ticker, None)
        
        p0 = p_yesterday.get(ticker, None)
        p1 = p_today.get(ticker, None)
        is_limit_up = False
        is_limit_down = False
        if pd.notna(p0) and pd.notna(p1) and p0 > 0:
            l_up = calc_tw_limit_up(p0)
            l_dn = calc_tw_limit_down(p0)
            is_limit_up = bool(p1 >= l_up - 1e-4)
            is_limit_down = bool(p1 <= l_dn + 1e-4)
        elif val_1d is not None and pd.notna(val_1d):
            is_limit_up = bool(val_1d >= 9.85)
            is_limit_down = bool(val_1d <= -9.85)
            
        mid_cat = mapping.get("mid_cat") or get_mid_category(mapping["name"], mapping["main_cat"], mapping["sub_cat"])
        all_records.append({
            "ticker": ticker,
            "name": mapping["name"],
            "main_cat": mapping["main_cat"],
            "mid_cat": mid_cat,
            "sub_cat": mapping["sub_cat"],
            "market_cap": mapping["market_cap"],
            "change_1d": val_1d,
            "change_5d": val_5d,
            "change_10d": val_10d,
            "change_20d": val_20d,
            "is_limit_up": is_limit_up,
            "is_limit_down": is_limit_down
        })
        
    df_all = pd.DataFrame(all_records)
    
    # ── Volume and Money Flow Calculations ──
    aligned_volumes = combined_volumes.loc[valid_df.index]
    dollar_vol = valid_df * aligned_volumes
    
    ticker_to_mid = {t: stock_mapping[t]["mid_cat"] for t in valid_df.columns if t in stock_mapping}
    common_cols = [c for c in valid_df.columns if c in ticker_to_mid]
    
    dollar_vol_filtered = dollar_vol[common_cols]
    valid_df_filtered = valid_df[common_cols]
    
    # Sector total dollar volume over time (shape: Date, mid_cat)
    sector_dollar_vol = dollar_vol_filtered.T.groupby(ticker_to_mid).sum().T
    
    # Sector daily returns (simple average of stock daily returns, shape: Date, mid_cat)
    daily_returns = valid_df_filtered.pct_change() * 100
    sector_returns = daily_returns.T.groupby(ticker_to_mid).mean().T
    
    # Sector volume shares over time
    market_total_vol = sector_dollar_vol.sum(axis=1)
    sector_vol_share = sector_dollar_vol.div(market_total_vol, axis=0) * 100
    # ─────────────────────────────────────────
    
    # 4. Multi-period statistics calculation (1D, 5D, 10D, 20D)
    periods = {
        "1d": dict_1d,
        "5d": dict_5d,
        "10d": dict_10d,
        "20d": dict_20d
    }
    
    payload = {}
    md_reports = {} # cache main sector averages for md generation
    
    for key, p_dict in periods.items():
        # Compute volume share and volume expansion ratio (VER)
        if key == "1d":
            ver = sector_dollar_vol.iloc[-1] / sector_dollar_vol.iloc[-5:].mean()
            share = sector_vol_share.iloc[-1]
            tci = pd.Series(1.0, index=sector_dollar_vol.columns)
            vol = pd.Series(0.0, index=sector_dollar_vol.columns)
        elif key == "5d":
            ver = sector_dollar_vol.iloc[-5:].mean() / sector_dollar_vol.mean()
            share = sector_vol_share.iloc[-5:].mean()
            tci = (sector_returns.iloc[-5:] > 0).sum() / 5
            vol = sector_returns.iloc[-5:].std()
        elif key == "10d":
            ver = sector_dollar_vol.iloc[-10:].mean() / sector_dollar_vol.mean()
            share = sector_vol_share.iloc[-10:].mean()
            tci = (sector_returns.iloc[-10:] > 0).sum() / 10
            vol = sector_returns.iloc[-10:].std()
        else: # 20d
            ver = sector_dollar_vol.iloc[-20:].mean() / sector_dollar_vol.mean()
            share = sector_vol_share.iloc[-20:].mean()
            tci = (sector_returns.iloc[-20:] > 0).sum() / 20
            vol = sector_returns.iloc[-20:].std()
            
        ver = ver.fillna(1.0).replace([np.inf, -np.inf], 1.0)
        share = share.fillna(0.0)
        tci = tci.fillna(1.0)
        vol = vol.fillna(0.0)
        
        ver_dict = ver.to_dict()
        share_dict = share.to_dict()
        tci_dict = tci.to_dict()
        vol_dict = vol.to_dict()

        records = []
        for ticker, change in p_dict.items():
            mapping = stock_mapping.get(ticker)
            if not mapping:
                continue
            mid_cat = mapping.get("mid_cat") or get_mid_category(mapping["name"], mapping["main_cat"], mapping["sub_cat"])
            records.append({
                "ticker": ticker,
                "name": mapping["name"],
                "main_cat": mapping["main_cat"],
                "mid_cat": mid_cat,
                "sub_cat": mapping["sub_cat"],
                "market_cap": mapping["market_cap"],
                "change": change
            })
        df_rec = pd.DataFrame(records)
        if len(df_rec) == 0:
            continue
            
        # Sort Leaders and Laggards
        leaders = df_rec.sort_values(by="change", ascending=False).head(15)
        laggards = df_rec.sort_values(by="change", ascending=True).head(15)
        
        # Vectorized market-cap weighted average calculation (50x faster)
        df_rec['weighted_change'] = df_rec['change'] * df_rec['market_cap']
        
        # Calculate Main sector average
        main_g = df_rec.groupby("main_cat")
        main_sum_w = main_g['weighted_change'].sum()
        main_sum_mc = main_g['market_cap'].sum()
        main_count = main_g['change'].count()
        main_wavg = (main_sum_w / main_sum_mc.replace(0, 1)).where(main_sum_mc > 0, main_g['change'].mean())
        
        main_perf = pd.DataFrame({
            'main_cat': main_wavg.index,
            'avg_change': main_wavg.values,
            'count': main_count.values
        }).sort_values(by="avg_change", ascending=False)
        
        # Calculate Mid sector average
        mid_g = df_rec.groupby(["main_cat", "mid_cat"])
        mid_sum_w = mid_g['weighted_change'].sum()
        mid_sum_mc = mid_g['market_cap'].sum()
        mid_count = mid_g['change'].count()
        mid_wavg = (mid_sum_w / mid_sum_mc.replace(0, 1)).where(mid_sum_mc > 0, mid_g['change'].mean())
        
        mid_perf = pd.DataFrame({
            'main_cat': [idx[0] for idx in mid_wavg.index],
            'mid_cat': [idx[1] for idx in mid_wavg.index],
            'avg_change': mid_wavg.values,
            'count': mid_count.values
        })
        
        mid_perf['ver'] = mid_perf['mid_cat'].map(ver_dict).fillna(1.0)
        mid_perf['share'] = mid_perf['mid_cat'].map(share_dict).fillna(0.0)
        mid_perf['tci'] = mid_perf['mid_cat'].map(tci_dict).fillna(1.0)
        mid_perf['vol'] = mid_perf['mid_cat'].map(vol_dict).fillna(0.0)
        mid_perf['mfs'] = mid_perf['avg_change'] * mid_perf['ver']
        
        # Calculate Quiet Risers
        if key != "1d":
            min_change = 0.8 if key == "5d" else (1.5 if key == "10d" else 3.0)
            max_change = 8.0 if key == "5d" else (15.0 if key == "10d" else 25.0)
            min_tci = 0.6
            max_vol = 2.5 if key != "20d" else 3.0
            
            qr_df = mid_perf[
                (mid_perf['avg_change'] >= min_change) &
                (mid_perf['avg_change'] <= max_change) &
                (mid_perf['tci'] >= min_tci) &
                (mid_perf['vol'] <= max_vol) &
                (mid_perf['ver'] >= 0.8) &
                (mid_perf['count'] >= 3)
            ].copy()
            qr_df['qrs'] = qr_df['avg_change'] * qr_df['tci'] * qr_df['ver']
            qr_df = qr_df.sort_values(by='qrs', ascending=False)
        else:
            qr_df = pd.DataFrame()
            
        mid_perf_filtered = mid_perf[mid_perf['count'] >= 2]
        mid_leaders = mid_perf_filtered.sort_values(by="avg_change", ascending=False).head(10)
        mid_laggards = mid_perf_filtered.sort_values(by="avg_change", ascending=True).head(10)
        
        md_reports[key] = {
            "main": main_perf.copy(),
            "mid_leaders": mid_leaders.copy(),
            "mid_laggards": mid_laggards.copy(),
            "df_rec": df_rec.copy()
        }
        
        # Calculate Sub sector average (FILTER: count >= 3 to prevent single-stock noise!)
        sub_perf = df_rec.groupby(["main_cat", "sub_cat"]).agg(
            avg_change=('change', 'mean'),
            count=('change', 'count')
        ).reset_index()
        sub_perf_filtered = sub_perf[sub_perf['count'] >= 3]
        
        # Sort leading/lagging sub-sectors
        sub_leaders = sub_perf_filtered.sort_values(by="avg_change", ascending=False).head(10)
        sub_laggards = sub_perf_filtered.sort_values(by="avg_change", ascending=True).head(10)
        
        # Build sub_cat -> mid_cat lookup for linking sub ranking rows to mid grid sections
        sub_to_mid_lookup = df_rec.drop_duplicates(subset=["main_cat", "sub_cat"])[["main_cat", "sub_cat", "mid_cat"]].set_index(["main_cat", "sub_cat"])["mid_cat"].to_dict()
        
        # Treemap 3-Level Data Structure (Main -> Mid -> Sub -> Stock)
        treemap_data = []
        for main_name, main_group in df_rec.groupby("main_cat"):
            main_children = []
            for mid_name, mid_group in main_group.groupby("mid_cat"):
                mid_children = []
                for sub_name, sub_group in mid_group.groupby("sub_cat"):
                    sub_children = []
                    for _, row in sub_group.iterrows():
                        sub_children.append({
                            "name": f"{row['name']}\n({row['change']:+.2f}%)" if pd.notna(row['change']) else f"{row['name']}\n(--%)",
                            "value": [int(row['market_cap'] / 1_000_000), row['change'] if pd.notna(row['change']) else 0],
                            "change": row['change'] if pd.notna(row['change']) else 0,
                            "ticker": str(row['ticker']).split(".")[0].strip()
                        })
                    sub_children = sorted(sub_children, key=lambda x: x['value'][0], reverse=True)
                    sub_avg_change = sub_group['change'].mean()
                    if pd.isna(sub_avg_change):
                        sub_avg_change = 0
                    mid_children.append({
                        "name": f"{sub_name} ({sub_avg_change:+.2f}%)",
                        "value": [sum([x['value'][0] for x in sub_children]), sub_avg_change],
                        "change": sub_avg_change,
                        "children": sub_children
                    })
                mid_children = sorted(mid_children, key=lambda x: x['value'][0], reverse=True)
                mid_avg_change = mid_group['change'].mean()
                if pd.isna(mid_avg_change):
                    mid_avg_change = 0
                main_children.append({
                    "name": f"{mid_name} ({mid_avg_change:+.2f}%)",
                    "value": [sum([x['value'][0] for x in mid_children]), mid_avg_change],
                    "change": mid_avg_change,
                    "children": mid_children
                })
            main_children = sorted(main_children, key=lambda x: x['value'][0], reverse=True)
            main_avg_change = main_group['change'].mean()
            if pd.isna(main_avg_change):
                main_avg_change = 0
            treemap_data.append({
                "name": f"{main_name} ({main_avg_change:+.2f}%)",
                "value": [sum([x['value'][0] for x in main_children]), main_avg_change],
                "change": main_avg_change,
                "children": main_children
            })
            
        # Map averages with safe hashes for HTML badges
        main_gp_map = {}
        for rank, (_, row) in enumerate(main_perf.iterrows()):
            mName = row["main_cat"]
            main_gp_map[mName] = {
                "avg": row["avg_change"],
                "safe_id": get_safe_id(mName),
                "rank": rank + 1
            }
            
        sub_gp_map = {}
        for _, row in sub_perf.iterrows():
            mName = row["main_cat"]
            sName = row["sub_cat"]
            mdName = sub_to_mid_lookup.get((mName, sName), sName)
            sub_gp_map[f"{mName} - {sName}"] = {
                "avg": row["avg_change"],
                "safe_id": get_safe_id(mName + "_" + mdName + "_" + sName)
            }
            
        mid_gp_map = {}
        for _, row in mid_perf.iterrows():
            mName = row["main_cat"]
            mdName = row["mid_cat"]
            
            # 5-day volume share sparkline data
            spark = []
            if mdName in sector_vol_share.columns:
                spark = [round(float(x), 2) for x in sector_vol_share[mdName].iloc[-5:].tolist()]
                
            is_quiet_riser = bool(mdName in qr_df['mid_cat'].values) if not qr_df.empty else False
            
            mid_gp_map[f"{mName} - {mdName}"] = {
                "avg": row["avg_change"],
                "safe_id": get_safe_id(mName + "_" + mdName),
                "spark": spark,
                "is_quiet_riser": is_quiet_riser,
                "ver": float(row["ver"]),
                "share": float(row["share"]),
                "tci": float(row["tci"])
            }

        payload[key] = {
            "treemap": treemap_data,
            "main_gp": main_gp_map,
            "mid_gp": mid_gp_map,
            "sub_gp": sub_gp_map,
            "capital_inflow": [
                {
                    "main_cat": r["main_cat"],
                    "mid_cat": r["mid_cat"],
                    "mfs": float(r["mfs"]),
                    "avg_change": float(r["avg_change"]),
                    "ver": float(r["ver"]),
                    "share": float(r["share"]),
                    "safe_id": get_safe_id(r["main_cat"] + "_" + r["mid_cat"])
                } for _, r in mid_perf[(mid_perf['mfs'] > 0) & (mid_perf['count'] >= 3)].sort_values(by='mfs', ascending=False).head(10).iterrows()
            ],
            "capital_outflow": [
                {
                    "main_cat": r["main_cat"],
                    "mid_cat": r["mid_cat"],
                    "mfs": float(r["mfs"]),
                    "avg_change": float(r["avg_change"]),
                    "ver": float(r["ver"]),
                    "share": float(r["share"]),
                    "safe_id": get_safe_id(r["main_cat"] + "_" + r["mid_cat"])
                } for _, r in mid_perf[(mid_perf['mfs'] < 0) & (mid_perf['count'] >= 3)].sort_values(by='mfs', ascending=True).head(10).iterrows()
            ],
            "quiet_risers": [
                {
                    "main_cat": r["main_cat"],
                    "mid_cat": r["mid_cat"],
                    "qrs": float(r["qrs"]) if "qrs" in r else 0.0,
                    "avg_change": float(r["avg_change"]),
                    "tci": float(r["tci"]),
                    "vol": float(r["vol"]),
                    "ver": float(r["ver"]),
                    "safe_id": get_safe_id(r["main_cat"] + "_" + r["mid_cat"])
                } for _, r in qr_df.head(10).iterrows()
            ] if key != "1d" else [],
            "mid_leaders": [
                {
                    "main_cat": r["main_cat"],
                    "mid_cat": r["mid_cat"],
                    "avg_change": r["avg_change"],
                    "count": int(r["count"]),
                    "safe_id": get_safe_id(r["main_cat"] + "_" + r["mid_cat"])
                } for _, r in mid_leaders.iterrows()
            ],
            "mid_laggards": [
                {
                    "main_cat": r["main_cat"],
                    "mid_cat": r["mid_cat"],
                    "avg_change": r["avg_change"],
                    "count": int(r["count"]),
                    "safe_id": get_safe_id(r["main_cat"] + "_" + r["mid_cat"])
                } for _, r in mid_laggards.iterrows()
            ],
            "leaders": [{"ticker": r["ticker"].split('.')[0], "name": r["name"], "change": r["change"], "sub_cat": r["sub_cat"]} for _, r in leaders.iterrows()],
            "laggards": [{"ticker": r["ticker"].split('.')[0], "name": r["name"], "change": r["change"], "sub_cat": r["sub_cat"]} for _, r in laggards.iterrows()],
            "sub_leaders": [
                {
                    "main_cat": r["main_cat"],
                    "sub_cat": r["sub_cat"],
                    "avg_change": r["avg_change"],
                    "count": int(r["count"]),
                    "safe_id": get_safe_id(r["main_cat"] + "_" + sub_to_mid_lookup.get((r["main_cat"], r["sub_cat"]), r["sub_cat"]))
                } for _, r in sub_leaders.iterrows()
            ],
            "sub_laggards": [
                {
                    "main_cat": r["main_cat"],
                    "sub_cat": r["sub_cat"],
                    "avg_change": r["avg_change"],
                    "count": int(r["count"]),
                    "safe_id": get_safe_id(r["main_cat"] + "_" + sub_to_mid_lookup.get((r["main_cat"], r["sub_cat"]), r["sub_cat"]))
                } for _, r in sub_laggards.iterrows()
            ],
            "stats": {
                "total": len(df_rec),
                "up": int((df_rec['change'] > 0).sum()),
                "down": int((df_rec['change'] < 0).sum()),
                "flat": int((df_rec['change'] == 0).sum()),
                "limit_up": int(df_all['is_limit_up'].sum()) if (key == "1d" and 'is_limit_up' in df_all) else int((df_rec['change'] >= 9.85).sum()),
                "limit_down": int(df_all['is_limit_down'].sum()) if (key == "1d" and 'is_limit_down' in df_all) else int((df_rec['change'] <= -9.85).sum())
            }
        }
        
    cat_averages_json = json.dumps(payload, ensure_ascii=False)
    
    # 5. Generate Multi-Period Markdown Report (1D, 5D, 10D)
    print(f"Generating Markdown summary: {REPORT_MD}")
    md_lines = []
    md_lines.append(f"# 📊 每日族群漲跌與資金流向看板 ({date_str})")
    md_lines.append(f"統計自 `stocks_list.txt` 中的個股收盤價，相較於前一交易日、週前與雙週前的累積漲跌幅。\n")
    
    for p_key in ["1d", "5d", "10d"]:
        p_name = "1日 (1D)" if p_key == "1d" else ("5日 (5D)" if p_key == "5d" else "10日 (10D)")
        p_data = md_reports.get(p_key)
        if not p_data:
            continue
        
        md_main = p_data["main"]
        df_rec = p_data["df_rec"]
        
        md_lines.append(f"## 📊 {p_name} 主產業板塊漲跌統計")
        md_lines.append("| 主產業名稱 | 平均漲跌 | 包含個股數 |")
        md_lines.append("| :--- | :--- | :--- |")
        for _, row in md_main.iterrows():
            emoji = "🔴" if row['avg_change'] > 0 else ("🟢" if row['avg_change'] < 0 else "⚪")
            sign = "+" if row['avg_change'] > 0 else ""
            md_lines.append(f"| {row['main_cat']} | {emoji} {sign}{row['avg_change']:.2f}% | {int(row['count'])} 檔 |")
        md_lines.append("\n")
        
        mid_leaders = p_data.get("mid_leaders")
        if mid_leaders is not None and not mid_leaders.empty:
            md_lines.append(f"### 🔥 {p_name} 強勢領漲【中型概念族群】 Top 10")
            md_lines.append("| 排名 | 主產業分類 | 中型概念族群 | 平均漲跌 | 包含個股數 |")
            md_lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for r_idx, (_, row) in enumerate(mid_leaders.iterrows(), 1):
                emoji = "🔴" if row['avg_change'] > 0 else ("🟢" if row['avg_change'] < 0 else "⚪")
                sign = "+" if row['avg_change'] > 0 else ""
                md_lines.append(f"| #{r_idx} | {row['main_cat']} | **{row['mid_cat']}** | {emoji} {sign}{row['avg_change']:.2f}% | {int(row['count'])} 檔 |")
            md_lines.append("\n")
        
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"Markdown report generated successfully.")
    
    # 6. Build HTML structure for All Stocks Master Map Grid (Organized by Main Category -> Mid Concept Cluster)
    print("Generating HTML layout for All Stocks Master Map Grid with Mid Concept Clusters...")
    grid_html = []
    
    # Sort main categories by 1D performance descending
    sorted_main_cats = md_reports["1d"]["main"]["main_cat"].tolist()
    
    for main_name in sorted_main_cats:
        main_group = df_all[df_all["main_cat"] == main_name]
        main_safe_id = get_safe_id(main_name)
        
        main_html = []
        main_html.append(f"""
        <div class="main-card" id="{main_safe_id}">
            <div class="main-card-header" onclick="toggleMainCard('{main_safe_id}')" style="cursor: pointer; user-select: none;">
                <span class="main-title"><span class="toggle-main-arrow">\u25b6</span> {main_name}</span>
                <span class="main-change-badge" id="badge-{main_safe_id}">--</span>
            </div>
            <div class="sub-category-list" style="display: none; flex-direction: column; gap: 12px;">
        """)
        
        grouped_mid = main_group.groupby("mid_cat")
        for mid_name, mid_group in grouped_mid:
            mid_safe_id = get_safe_id(main_name + "_" + mid_name)
            mid_group_sorted = mid_group.sort_values(by="market_cap", ascending=False)
            
            # Compute 5-day volume share sparkline SVG
            spark_svg = ""
            if mid_name in sector_vol_share.columns:
                shares = sector_vol_share[mid_name].iloc[-5:].tolist()
                max_share = max(shares) if max(shares) > 0 else 1.0
                bar_width = 6
                bar_gap = 2
                height = 14
                svg_width = 5 * bar_width + 4 * bar_gap
                
                svg_parts = [f'<svg class="vol-spark" width="{svg_width}" height="{height}" title="5日資金比重走勢" style="vertical-align: middle; margin-left: 8px;">']
                for idx, val in enumerate(shares):
                    h = (val / max_share) * height
                    h = max(h, 2.0)
                    y = height - h
                    x = idx * (bar_width + bar_gap)
                    op = round(0.35 + (idx / 4) * 0.65, 2)
                    svg_parts.append(f'<rect x="{x}" y="{y}" width="{bar_width}" height="{h}" fill="var(--primary-accent)" opacity="{op}"></rect>')
                svg_parts.append('</svg>')
                spark_svg = "".join(svg_parts)
            
            main_html.append(f"""
                <div class="sub-section" id="{mid_safe_id}">
                    <div class="sub-header" onclick="toggleSubSection('{mid_safe_id}')" style="cursor: pointer; user-select: none;">
                        <span class="sub-title"><span class="toggle-arrow">\u25b6</span> \U0001f4c1 {mid_name}{spark_svg} <span class="quiet-riser-badge" id="qr-badge-{mid_safe_id}" style="display: none; margin-left: 6px; font-size: 0.75rem; background: rgba(16, 185, 129, 0.15); color: var(--taiwan-up); border: 1px solid rgba(16, 185, 129, 0.3); padding: 1px 6px; border-radius: 4px; font-weight: bold; font-family: \'Outfit\', sans-serif;">🐢 緩漲黑馬</span></span>
                        <div>
                            <span class="sub-count-badge">{len(mid_group_sorted)} \u6a94\u500b\u80a1</span>
                            <span class="sub-change-badge" id="badge-{mid_safe_id}">--</span>
                        </div>
                    </div>
                    <div class="mid-content" style="display: none; flex-direction: column; gap: 8px; padding: 4px 0 0 8px;">
            """)
            
            # Group stocks within this mid_cat by sub_cat
            grouped_sub = mid_group_sorted.groupby("sub_cat", sort=False)
            sub_cats_in_mid = list(grouped_sub.groups.keys())
            
            # If only 1 sub_cat inside this mid, skip sub header, show stocks directly
            if len(sub_cats_in_mid) == 1:
                sub_name = sub_cats_in_mid[0]
                sub_group = grouped_sub.get_group(sub_name).sort_values(by="market_cap", ascending=False)
                sub_safe_id = get_safe_id(main_name + "_" + mid_name + "_" + sub_name)
                
                main_html.append(f"""
                        <div class="stock-grid" id="{sub_safe_id}" style="display: grid;">
                """)
                
                for _, row in sub_group.iterrows():
                    ticker_clean = row["ticker"].replace(".", "_")
                    ticker_short = row["ticker"].split('.')[0]
                    c_1d = f"{row['change_1d']:.2f}" if pd.notna(row['change_1d']) else "null"
                    c_5d = f"{row['change_5d']:.2f}" if pd.notna(row['change_5d']) else "null"
                    c_10d = f"{row['change_10d']:.2f}" if pd.notna(row['change_10d']) else "null"
                    c_20d = f"{row['change_20d']:.2f}" if pd.notna(row['change_20d']) else "null"
                    
                    pure_ticker = str(row['ticker']).split('.')[0]
                    i_info = inst_data.get(pure_ticker, {})
                    inst_foreign = i_info.get("foreign", 0)
                    inst_trust = i_info.get("trust", 0)
                    inst_dealer = i_info.get("dealer", 0)
                    
                    f_str = f"+{inst_foreign}" if inst_foreign > 0 else str(inst_foreign)
                    t_str = f"+{inst_trust}" if inst_trust > 0 else str(inst_trust)
                    d_str = f"+{inst_dealer}" if inst_dealer > 0 else str(inst_dealer)
                    inst_str = f"\n--- 🏛️ 三大法人買賣超 (張) ---\n外資: {f_str} 張\n投信: {t_str} 張\n自營: {d_str} 張"
                    title_tooltip = f"股名: {row['name']}\n代號: {row['ticker']}\n中型族群: {mid_name}\n細分次產業: {row['sub_cat']}\n1D: {c_1d}%\n5D: {c_5d}%\n10D: {c_10d}%\n20D: {c_20d}%" + inst_str
                    
                    limit_cls = ""
                    if row.get('is_limit_up', False):
                        limit_cls = " limit-up"
                    elif row.get('is_limit_down', False):
                        limit_cls = " limit-down"
                    
                    main_html.append(f"""
                            <div class="stock-pill{limit_cls}" id="stock-{ticker_clean}" data-ticker="{ticker_short}" data-name="{row['name']}" data-main-cat="{main_name}" data-mid-cat="{mid_name}" data-sub-cat="{row['sub_cat']}" data-1d="{c_1d}" data-5d="{c_5d}" data-10d="{c_10d}" data-20d="{c_20d}" data-foreign="{inst_foreign}" data-trust="{inst_trust}" data-dealer="{inst_dealer}" title="{title_tooltip}">
                                 <span class="s-name">{row['name']}</span>
                                 <span class="s-change" id="change-text-{ticker_clean}">--</span>
                            </div>
                    """)
                
                main_html.append("</div>")
            else:
                # Multiple sub_cats: show sub-category headers
                for sub_name in sub_cats_in_mid:
                    sub_group = grouped_sub.get_group(sub_name).sort_values(by="market_cap", ascending=False)
                    sub_safe_id = get_safe_id(main_name + "_" + mid_name + "_" + sub_name)
                    
                    main_html.append(f"""
                        <div class="sub-sub-section" id="{sub_safe_id}">
                            <div class="sub-sub-header" onclick="toggleSubSubSection('{sub_safe_id}')" style="cursor: pointer; user-select: none;">
                                <span class="sub-sub-title"><span class="toggle-sub-arrow">▶</span> 🏷️ {sub_name}</span>
                                <div>
                                    <span class="sub-count-badge" style="font-size: 0.7rem;">{len(sub_group)} 檔</span>
                                    <span class="sub-sub-change-badge" id="badge-{sub_safe_id}">--</span>
                                </div>
                            </div>
                            <div class="stock-grid" style="display: none;">
                    """)
                    
                    for _, row in sub_group.iterrows():
                        ticker_clean = row["ticker"].replace(".", "_")
                        ticker_short = row["ticker"].split('.')[0]
                        c_1d = f"{row['change_1d']:.2f}" if pd.notna(row['change_1d']) else "null"
                        c_5d = f"{row['change_5d']:.2f}" if pd.notna(row['change_5d']) else "null"
                        c_10d = f"{row['change_10d']:.2f}" if pd.notna(row['change_10d']) else "null"
                        c_20d = f"{row['change_20d']:.2f}" if pd.notna(row['change_20d']) else "null"
                        
                        pure_ticker = str(row['ticker']).split('.')[0]
                        i_info = inst_data.get(pure_ticker, {})
                        inst_foreign = i_info.get("foreign", 0)
                        inst_trust = i_info.get("trust", 0)
                        inst_dealer = i_info.get("dealer", 0)
                        
                        f_str = f"+{inst_foreign}" if inst_foreign > 0 else str(inst_foreign)
                        t_str = f"+{inst_trust}" if inst_trust > 0 else str(inst_trust)
                        d_str = f"+{inst_dealer}" if inst_dealer > 0 else str(inst_dealer)
                        inst_str = f"\n--- 🏛️ 三大法人買賣超 (張) ---\n外資: {f_str} 張\n投信: {t_str} 張\n自營: {d_str} 張"
                        title_tooltip = f"股名: {row['name']}\n代號: {row['ticker']}\n中型族群: {mid_name}\n細分次產業: {row['sub_cat']}\n1D: {c_1d}%\n5D: {c_5d}%\n10D: {c_10d}%\n20D: {c_20d}%" + inst_str
                        
                        limit_cls = ""
                        if row.get('is_limit_up', False):
                            limit_cls = " limit-up"
                        elif row.get('is_limit_down', False):
                            limit_cls = " limit-down"
                        
                        main_html.append(f"""
                                <div class="stock-pill{limit_cls}" id="stock-{ticker_clean}" data-ticker="{ticker_short}" data-name="{row['name']}" data-main-cat="{main_name}" data-mid-cat="{mid_name}" data-sub-cat="{row['sub_cat']}" data-1d="{c_1d}" data-5d="{c_5d}" data-10d="{c_10d}" data-20d="{c_20d}" data-foreign="{inst_foreign}" data-trust="{inst_trust}" data-dealer="{inst_dealer}" title="{title_tooltip}">
                                     <span class="s-name">{row['name']}</span>
                                     <span class="s-change" id="change-text-{ticker_clean}">--</span>
                                </div>
                        """)
                    
                    main_html.append("""
                            </div>
                        </div>
                    """)
            
            main_html.append("""
                    </div>
                </div>
            """)
            
        main_html.append("""
            </div>
        </div>
        """)
        grid_html.append("".join(main_html))

    # 7. Write complete updated HTML dashboard to file
    print(f"Writing updated HTML dashboard: {REPORT_HTML}")
    if os.path.exists(REPORT_HTML):
        with open(REPORT_HTML, "r", encoding="utf-8") as f:
            base_html = f.read()
            
        grid_start_tag = '<main class="master-grid">'
        idx_grid_start = base_html.find(grid_start_tag)
        main_end_tag = '</main>'
        idx_main_end = base_html.find(main_end_tag, idx_grid_start)
        payload_tag = 'const payload = '
        idx_payload = base_html.find(payload_tag, idx_main_end)
        idx_payload_end = base_html.find(';\n', idx_payload)
        if idx_payload_end == -1:
            idx_payload_end = base_html.find(';', idx_payload)
            
        if idx_grid_start != -1 and idx_main_end != -1 and idx_payload != -1 and idx_payload_end != -1:
            header_part = base_html[:idx_grid_start + len(grid_start_tag)] + "\n"
            middle_part = "\n" + base_html[idx_main_end:idx_payload + len(payload_tag)]
            footer_part = base_html[idx_payload_end:]
            
            final_html = header_part + "".join(grid_html) + middle_part + cat_averages_json + footer_part
            with open(REPORT_HTML, "w", encoding="utf-8") as f:
                f.write(final_html)
            print("HTML dashboard generated and saved successfully!")
        else:
            print(f"⚠️ Template placeholders not found in {REPORT_HTML}, HTML update skipped.")
    else:
        print(f"⚠️ Base HTML file {REPORT_HTML} not found.")

run_pipeline()

