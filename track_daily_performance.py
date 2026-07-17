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
    from classify_all_database import STOCK_SUBCLASS, CLEAN_SUBCLASS, DETAILED_SECTOR_MAP, clean_stock_name, KEYWORD_THESAURUS, advanced_has_kw, clean_category
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
        stock_mapping[ticker] = {
            "name": name,
            "main_cat": main_cat,
            "sub_cat": sub_cat,
            "market_cap": 1_000_000_000  # temporary placeholder
        }
        
    # 3. Batch download prices and volumes (period=20d to cover 10 trading days)
    tickers = list(stock_mapping.keys())
    chunk_size = 400
    all_closes = []
    all_volumes = []
    all_closes_today = []
    
    print(f"Downloading prices and volumes for {len(tickers)} tickers in chunks of {chunk_size}...")
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i+chunk_size]
        print(f"Downloading chunk {i // chunk_size + 1} / {len(tickers) // chunk_size + 1}...")
        try:
            df = yf.download(chunk, period="20d", progress=False, group_by='column')
            
            closes_chunk = pd.DataFrame(index=df.index)
            volumes_chunk = pd.DataFrame(index=df.index)
            for col in chunk:
                if ('Adj Close', col) in df.columns:
                    closes_chunk[col] = df[('Adj Close', col)]
                elif ('Close', col) in df.columns:
                    closes_chunk[col] = df[('Close', col)]
                if ('Volume', col) in df.columns:
                    volumes_chunk[col] = df[('Volume', col)]
            
            if not closes_chunk.empty and not volumes_chunk.empty:
                all_closes.append(closes_chunk)
                all_volumes.append(volumes_chunk)
            else:
                print(f"Warning: Empty data in chunk {i // chunk_size + 1}")
                
            # Fetch the real-time quote for today to patch any incomplete/NaN close prices
            df_today = yf.download(chunk, period="1d", progress=False, group_by='column')
            closes_today_chunk = pd.DataFrame(index=df_today.index)
            for col in chunk:
                if ('Adj Close', col) in df_today.columns:
                    closes_today_chunk[col] = df_today[('Adj Close', col)]
                elif ('Close', col) in df_today.columns:
                    closes_today_chunk[col] = df_today[('Close', col)]
            
            if not closes_today_chunk.empty:
                all_closes_today.append(closes_today_chunk)
        except Exception as e:
            print(f"Error downloading chunk: {e}")
            
    if not all_closes or not all_volumes:
        print("Error: No pricing or volume data downloaded.")
        return
        
    combined_closes = pd.concat(all_closes, axis=1)
    combined_volumes = pd.concat(all_volumes, axis=1)
    
    # Fill NaN values in the last row of combined_closes using 1d real-time quotes
    if all_closes_today:
        combined_closes_today = pd.concat(all_closes_today, axis=1)
        last_date = combined_closes.index[-1]
        for col in combined_closes.columns:
            if pd.isna(combined_closes.loc[last_date, col]) and col in combined_closes_today.columns:
                # only fill if the volume is not zero on the latest day
                if col in combined_volumes.columns and combined_volumes.loc[last_date, col] > 0:
                    val = combined_closes_today.loc[combined_closes_today.index[-1], col]
                    if pd.notna(val):
                        combined_closes.loc[last_date, col] = val
    
    # Mask close prices where volume is 0 (prevents stale prices on holidays/closures)
    combined_closes = combined_closes.mask(combined_volumes == 0)
    
    # Extract valid trading rows
    valid_df = combined_closes.dropna(how='all')
    
    # Auto-rollback if today's yfinance closing prices are not yet fully updated (mostly NaN)
    while len(valid_df) >= 2:
        last_row = valid_df.iloc[-1]
        non_nan_count = last_row.notna().sum()
        total_count = len(last_row)
        if non_nan_count < (total_count * 0.5):
            print(f"Warning: Latest day ({valid_df.index[-1].date()}) has incomplete price data ({non_nan_count}/{total_count} tickers). Rolling back to previous trading day...")
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
    
    # Calculate returns vectorised for 1D, 5D, and 10D
    change_1d = ((valid_df.iloc[-1] - valid_df.iloc[-2]) / valid_df.iloc[-2]) * 100
    
    idx_5d = -6 if num_days >= 6 else 0
    change_5d = ((valid_df.iloc[-1] - valid_df.iloc[idx_5d]) / valid_df.iloc[idx_5d]) * 100
    
    idx_10d = -11 if num_days >= 11 else 0
    change_10d = ((valid_df.iloc[-1] - valid_df.iloc[idx_10d]) / valid_df.iloc[idx_10d]) * 100
    
    # Clean anomalies (e.g. capital reduction multipliers)
    change_1d = change_1d[(change_1d >= -11) & (change_1d <= 11)].dropna()
    change_5d = change_5d[(change_5d >= -45) & (change_5d <= 80)].dropna()
    change_10d = change_10d[(change_10d >= -60) & (change_10d <= 120)].dropna()
    
    # Pack returns into dictionaries
    dict_1d = change_1d.to_dict()
    dict_5d = change_5d.to_dict()
    dict_10d = change_10d.to_dict()
    
    # Create unified master records
    all_records = []
    for ticker, mapping in stock_mapping.items():
        val_1d = dict_1d.get(ticker, None)
        val_5d = dict_5d.get(ticker, None)
        val_10d = dict_10d.get(ticker, None)
        
        all_records.append({
            "ticker": ticker,
            "name": mapping["name"],
            "main_cat": mapping["main_cat"],
            "sub_cat": mapping["sub_cat"],
            "market_cap": mapping["market_cap"],
            "change_1d": val_1d,
            "change_5d": val_5d,
            "change_10d": val_10d
        })
        
    df_all = pd.DataFrame(all_records)
    
    # 4. Multi-period statistics calculation (1D, 5D, 10D)
    periods = {
        "1d": dict_1d,
        "5d": dict_5d,
        "10d": dict_10d
    }
    
    payload = {}
    md_reports = {} # cache main sector averages for md generation
    
    for key, p_dict in periods.items():
        records = []
        for ticker, change in p_dict.items():
            mapping = stock_mapping.get(ticker)
            if not mapping:
                continue
            records.append({
                "ticker": ticker,
                "name": mapping["name"],
                "main_cat": mapping["main_cat"],
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
        
        # Calculate Main sector average
        main_perf = df_rec.groupby("main_cat").agg(
            avg_change=('change', 'mean'),
            count=('change', 'count')
        ).reset_index().sort_values(by="avg_change", ascending=False)
        
        md_reports[key] = {
            "main": main_perf.copy(),
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
        
        # Treemap data structure
        treemap_data = []
        for main_name, main_group in df_rec.groupby("main_cat"):
            main_children = []
            for sub_name, sub_group in main_group.groupby("sub_cat"):
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
                main_children.append({
                    "name": f"{sub_name} ({sub_avg_change:+.2f}%)",
                    "value": [sum([x['value'][0] for x in sub_children]), sub_avg_change],
                    "change": sub_avg_change,
                    "children": sub_children
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
            sub_gp_map[f"{mName} - {sName}"] = {
                "avg": row["avg_change"],
                "safe_id": get_safe_id(mName + "_" + sName)
            }
            
        payload[key] = {
            "treemap": treemap_data,
            "main_gp": main_gp_map,
            "sub_gp": sub_gp_map,
            "leaders": [{"ticker": r["ticker"].split('.')[0], "name": r["name"], "change": r["change"], "sub_cat": r["sub_cat"]} for _, r in leaders.iterrows()],
            "laggards": [{"ticker": r["ticker"].split('.')[0], "name": r["name"], "change": r["change"], "sub_cat": r["sub_cat"]} for _, r in laggards.iterrows()],
            "sub_leaders": [
                {
                    "main_cat": r["main_cat"],
                    "sub_cat": r["sub_cat"],
                    "avg_change": r["avg_change"],
                    "count": int(r["count"]),
                    "safe_id": get_safe_id(r["main_cat"] + "_" + r["sub_cat"])
                } for _, r in sub_leaders.iterrows()
            ],
            "sub_laggards": [
                {
                    "main_cat": r["main_cat"],
                    "sub_cat": r["sub_cat"],
                    "avg_change": r["avg_change"],
                    "count": int(r["count"]),
                    "safe_id": get_safe_id(r["main_cat"] + "_" + r["sub_cat"])
                } for _, r in sub_laggards.iterrows()
            ],
            "stats": {
                "total": len(df_rec),
                "up": int((df_rec['change'] > 0).sum()),
                "down": int((df_rec['change'] < 0).sum()),
                "flat": int((df_rec['change'] == 0).sum())
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
        
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"Markdown report generated successfully.")
    
    # 6. Build HTML structure for All Stocks Master Map Grid
    print("Generating HTML layout for All Stocks Master Map Grid...")
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
                <span class="main-title"><span class="toggle-main-arrow">▶</span> {main_name}</span>
                <span class="main-change-badge" id="badge-{main_safe_id}">--</span>
            </div>
            <div class="sub-category-list" style="display: none; flex-direction: column; gap: 12px;">
        """)
        
        grouped_sub = main_group.groupby("sub_cat")
        for sub_name, sub_group in grouped_sub:
            sub_safe_id = get_safe_id(main_name + "_" + sub_name)
            sub_group_sorted = sub_group.sort_values(by="market_cap", ascending=False)
            
            main_html.append(f"""
                <div class="sub-section" id="{sub_safe_id}">
                    <div class="sub-header" onclick="toggleSubSection('{sub_safe_id}')" style="cursor: pointer;">
                        <span class="sub-title"><span class="toggle-arrow">▶</span> {sub_name}</span>
                        <div>
                            <span class="sub-count-badge">{len(sub_group_sorted)} 檔</span>
                            <span class="sub-change-badge" id="badge-{sub_safe_id}">--</span>
                        </div>
                    </div>
                    <div class="stock-grid" style="display: none;">
            """)
            
            for _, row in sub_group_sorted.iterrows():
                ticker_clean = row["ticker"].replace(".", "_")
                ticker_short = row["ticker"].split('.')[0]
                
                c_1d = f"{row['change_1d']:.2f}" if pd.notna(row['change_1d']) else "null"
                c_5d = f"{row['change_5d']:.2f}" if pd.notna(row['change_5d']) else "null"
                c_10d = f"{row['change_10d']:.2f}" if pd.notna(row['change_10d']) else "null"
                
                title_tooltip = f"股名: {row['name']}\\n代號: {row['ticker']}\\n1D: {c_1d}%\\n5D: {c_5d}%\\n10D: {c_10d}%"
                
                main_html.append(f"""
                        <div class="stock-pill" 
                             id="stock-{ticker_clean}" 
                             data-ticker="{ticker_short}" 
                             data-name="{row['name']}"
                             data-main-cat="{main_name}"
                             data-sub-cat="{sub_name}"
                             data-1d="{c_1d}" 
                             data-5d="{c_5d}" 
                             data-10d="{c_10d}" 
                             title="{title_tooltip}">
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
        grid_html.append("".join(main_html))
        
    all_grid_elements_html = "\n".join(grid_html)
    
    # 7. Write HTML Page
    html_content = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>👑 台股產業資金流向熱力圖</title>
    <!-- Google Fonts Outfit & Inter -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">
    <!-- ECharts CDN -->
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 28, 45, 0.7);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --taiwan-up: #ef4444; /* 🔴 台灣紅漲 */
            --taiwan-down: #10b981; /* 🟢 台灣綠跌 */
            --flat-color: #6b7280;
            --primary-accent: #ff9f43;
        }}
        
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            padding: 24px;
            min-height: 100vh;
            background-image: radial-gradient(circle at 10% 20%, rgba(30, 41, 59, 0.4) 0%, transparent 90%),
                              radial-gradient(circle at 90% 80%, rgba(15, 23, 42, 0.6) 0%, transparent 90%);
            background-attachment: fixed;
        }}
        
        header {{
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
        }}
        
        .header-left h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(135deg, #ff9f43 0%, #ff5252 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 4px;
        }}
        
        .subtitle {{
            color: var(--text-secondary);
            font-size: 1rem;
        }}
        
        /* Premium Search Input */
        .search-box {{
            flex: 1;
            max-width: 480px;
            min-width: 280px;
            position: relative;
        }}
        
        .search-box input {{
            width: 100%;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 12px 16px;
            color: var(--text-primary);
            font-size: 0.95rem;
            outline: none;
            transition: all 0.3s;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
        }}
        
        .search-box input:focus {{
            border-color: var(--primary-accent);
            background: rgba(255, 255, 255, 0.08);
            box-shadow: 0 4px 20px rgba(255, 159, 67, 0.15);
        }}
        
        /* Dashboard Container Layout */
        .dashboard-grid {{
            display: grid;
            grid-template-columns: 7fr 3fr;
            gap: 24px;
            align-items: start;
        }}
        
        @media (max-width: 1200px) {{
            .dashboard-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        
        /* Left Column Content */
        .left-content {{
            display: flex;
            flex-direction: column;
            gap: 24px;
        }}
        
        /* Treemap Visualizer Card */
        .treemap-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 24px;
            backdrop-filter: blur(12px);
            box-shadow: 0 10px 32px rgba(0, 0, 0, 0.3);
            height: 600px;
            display: flex;
            flex-direction: column;
        }}
        
        .treemap-card h2 {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.3rem;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .treemap-chart {{
            flex: 1;
            width: 100%;
        }}
        
        /* Grid Heatmap styling */
        .heatmap-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 12px;
            margin-bottom: 12px;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            padding-top: 20px;
        }}
        
        .heatmap-header h2 {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.5rem;
        }}
        
        /* Tab Period Selector */
        .tabs {{
            display: inline-flex;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 4px;
            backdrop-filter: blur(8px);
        }}
        
        .tab-btn {{
            background: transparent;
            border: none;
            color: var(--text-secondary);
            font-family: 'Outfit', sans-serif;
            font-size: 0.9rem;
            font-weight: 600;
            padding: 8px 18px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        
        .tab-btn.active {{
            background: linear-gradient(135deg, #ff9f43 0%, #ff5252 100%);
            color: #ffffff;
            box-shadow: 0 4px 16px rgba(255, 82, 82, 0.3);
        }}
        
        /* Global Collapse/Expand controls */
        .global-controls {{
            display: flex;
            gap: 12px;
        }}
        
        .ctrl-btn {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            font-size: 0.8rem;
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            padding: 6px 14px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        
        .ctrl-btn:hover {{
            background: rgba(255, 255, 255, 0.08);
            color: var(--text-primary);
            border-color: rgba(255, 255, 255, 0.15);
        }}
        
        .master-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 16px;
        }}
        
        .main-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 12px 14px;
            backdrop-filter: blur(12px);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
            transition: border-color 0.3s;
            order: 999;
        }}
        
        .main-card:hover {{
            border-color: rgba(255, 255, 255, 0.15);
        }}
        
        .main-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            padding-bottom: 12px;
            margin-bottom: 16px;
        }}
        
        .main-title {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.2rem;
            font-weight: 700;
            color: #ffffff;
        }}
        
        .main-change-badge {{
            font-family: 'Outfit', sans-serif;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 8px;
            font-size: 0.9rem;
            transition: all 0.3s;
        }}
        
        .sub-category-list {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        
        .sub-section {{
            background: rgba(255, 255, 255, 0.015);
            border-radius: 8px;
            padding: 6px 8px;
            border: 1px solid rgba(255, 255, 255, 0.02);
            transition: all 0.2s;
        }}
        
        .sub-section:hover {{
            background: rgba(255, 255, 255, 0.04);
        }}
        
        .sub-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            user-select: none;
        }}
        
        .sub-title {{
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-primary);
            display: flex;
            align-items: center;
        }}
        
        .toggle-arrow {{
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-right: 8px;
            display: inline-block;
            width: 12px;
        }}
        
        .sub-count-badge {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.06);
            color: var(--text-secondary);
            font-size: 0.75rem;
            padding: 2px 8px;
            border-radius: 6px;
            margin-right: 8px;
            font-weight: 600;
        }}
        
        .sub-change-badge {{
            font-size: 0.85rem;
            font-weight: 600;
            font-family: 'Outfit', sans-serif;
            transition: color 0.3s;
        }}
        
        /* Stock Pills Grid */
        .stock-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
            gap: 4px;
            margin-top: 6px;
            border-top: 1px dashed rgba(255, 255, 255, 0.05);
            padding-top: 6px;
        }}
        
        .stock-pill {{
            background: rgba(75, 85, 99, 0.15);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 4px;
            padding: 3px 4px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            user-select: none;
            text-align: center;
        }}
        
        .stock-pill:hover {{
            transform: translateY(-1px);
            box-shadow: 0 3px 8px rgba(0, 0, 0, 0.4);
            border-color: rgba(255, 255, 255, 0.2) !important;
        }}
        
        .s-name {{
            font-size: 0.72rem;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 0px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            width: 100%;
        }}
        
        .s-change {{
            font-size: 0.65rem;
            font-weight: 700;
            font-family: 'Outfit', sans-serif;
        }}
        
        /* Side Panel (Right Column) */
        .side-panel {{
            display: flex;
            flex-direction: column;
            gap: 24px;
        }}
        
        .side-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 20px;
            backdrop-filter: blur(12px);
            box-shadow: 0 10px 32px rgba(0, 0, 0, 0.3);
        }}
        
        .side-card h2 {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.15rem;
            margin-bottom: 14px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        /* Breadth Grid */
        .breadth-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }}
        
        .b-card {{
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            padding: 10px;
            text-align: center;
        }}
        
        .b-card h4 {{
            font-size: 0.7rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            margin-bottom: 2px;
        }}
        
        .b-card .b-val {{
            font-size: 1.3rem;
            font-weight: 700;
            font-family: 'Outfit', sans-serif;
        }}
        
        /* Tables and Rankings */
        .rank-tabs {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 12px;
            background: rgba(255, 255, 255, 0.03);
            padding: 4px;
            border-radius: 8px;
        }}
        
        .rank-tab-btn {{
            background: transparent;
            border: none;
            color: var(--text-secondary);
            font-family: 'Outfit', sans-serif;
            font-size: 0.85rem;
            font-weight: 600;
            padding: 6px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        
        .rank-tab-btn.active {{
            background: rgba(255, 255, 255, 0.08);
            color: #ffffff;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }}
        
        th, td {{
            padding: 8px 10px;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}
        
        th {{
            color: var(--text-secondary);
            font-size: 0.75rem;
        }}
        
        tbody tr:hover {{
            background: rgba(255, 255, 255, 0.03);
            cursor: pointer;
        }}
        
        .up {{
            color: var(--taiwan-up);
            font-weight: 600;
        }}
        
        .down {{
            color: var(--taiwan-down);
            font-weight: 600;
        }}
        
        .tag {{
            background: rgba(255, 255, 255, 0.05);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.75rem;
            color: var(--text-secondary);
        }}
        
        /* Bulk Analysis panel styling */
        .bulk-stats-header {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }}
        .bulk-tag-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }}
        .bulk-sec-tag {{
            background: rgba(255, 159, 67, 0.15);
            border: 1px solid rgba(255, 159, 67, 0.3);
            color: #ff9f43;
            font-size: 0.75rem;
            padding: 3px 8px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .bulk-sec-tag:hover {{
            background: rgba(255, 159, 67, 0.3);
            border-color: #ff9f43;
        }}
        
        .toggle-main-arrow {{
            cursor: pointer;
            transition: transform 0.2s;
        }}
        
        /* Clear Search Cross Button inside search bar */
        .clear-search-btn {{
            position: absolute;
            right: 12px;
            cursor: pointer;
            color: var(--text-secondary);
            font-size: 1.2rem;
            user-select: none;
            display: none;
            transition: color 0.2s;
            z-index: 10;
        }}
        .clear-search-btn:hover {{
            color: var(--primary-accent);
        }}
        
        /* Floating Back to Map Button */
        .floating-back-btn {{
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: linear-gradient(135deg, #ff9f43 0%, #ff5252 100%);
            color: #fff;
            border: none;
            border-radius: 50px;
            padding: 12px 24px;
            font-size: 0.95rem;
            font-weight: bold;
            box-shadow: 0 4px 20px rgba(255, 82, 82, 0.4);
            cursor: pointer;
            z-index: 9999;
            transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            display: none; /* Hidden by default */
            align-items: center;
            gap: 8px;
        }}
        .floating-back-btn:hover {{
            transform: translateY(-3px) scale(1.05);
            box-shadow: 0 6px 24px rgba(255, 82, 82, 0.6);
        }}
        .floating-back-btn:active {{
            transform: translateY(1px);
        }}
    </style>
</head>
<body>
    <header>
        <div class="header-left">
            <h1>👑 台股產業資金流向圖</h1>
            <p class="subtitle">統計日期：{date_str} (相較於前一交易日 {prev_date_str}) | 跨週期產業板塊熱力圖</p>
        </div>
        <div class="search-box" style="display: flex; align-items: center; gap: 8px;">
            <div style="position: relative; flex: 1; display: flex; align-items: center;">
                <input type="text" id="search-input" placeholder="🔍 搜尋個股名稱、代碼 (如: 台積電 或 2330)..." oninput="searchStocks()" style="width: 100%; padding-right: 32px;">
                <span id="clear-search" class="clear-search-btn" onclick="clearSearch()">&times;</span>
            </div>
            <button class="ctrl-btn" onclick="toggleBulkPanel()" title="適合同時篩選、分析多檔個股（如貼上整份自選股名單）以觀察其板塊分佈時使用" style="white-space: nowrap; height: 100%; padding: 10px 14px;">📋 批次分析</button>
        </div>
    </header>
    
    <!-- Bulk Analysis Panel -->
    <div id="bulk-panel" style="display: none; background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 16px; margin-bottom: 20px; box-shadow: 0 8px 32px rgba(0,0,0,0.4); backdrop-filter: blur(12px);">
        <div style="font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 8px; line-height: 1.6;">
            💡 <strong>適用場景</strong>：當您需要同時查看、分析多檔個股（例如貼上您的<strong>整份自選股名單</strong>）時，使用此功能可一次性篩選，並在下方統計它們分佈在哪些產業板塊與平均表現。<br/>
            📋 請貼上個股代號或名稱，用空格、逗號或換行隔開 (例如: 2330, 欣興, 3583)：
        </div>
        <textarea id="bulk-input" rows="3" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px; color: #fff; font-size: 0.9rem; outline: none; resize: vertical; font-family: inherit;" placeholder="在此貼上代號或股名..." oninput="analyzeBulk()"></textarea>
        <div id="bulk-results" style="margin-top: 12px; display: none;"></div>
    </div>
    
    <div class="dashboard-grid">
        <!-- Left Side: Treemap & Collapsible Heatmap -->
        <div class="left-content">
            <!-- ECharts Treemap Chart -->
            <div class="treemap-card">
                <h2>📈 台股產業資金流向熱力地圖 <span style="font-size: 0.85rem; color: var(--text-secondary); font-weight: normal; margin-left: 8px;">(區域面積代表市值規模，顏色代表該週期漲跌幅)</span></h2>
                <div id="treemap-chart" class="treemap-chart"></div>
            </div>
            
            <!-- Heatmap Title and Filters -->
            <div class="heatmap-header">
                <h2>🗂️ 全個股大師熱力地圖</h2>
                
                <div class="tabs">
                    <button class="tab-btn active" onclick="switchPeriod('1d')">今日漲跌 (1D)</button>
                    <button class="tab-btn" onclick="switchPeriod('5d')">週累積 (5D)</button>
                    <button class="tab-btn" onclick="switchPeriod('10d')">雙週累積 (10D)</button>
                </div>
                
                <div class="global-controls">
                    <button class="ctrl-btn" onclick="toggleAll(true)">展開全部</button>
                    <button class="ctrl-btn" onclick="toggleAll(false)">收合全部</button>
                </div>
            </div>
            
            <!-- Heatmap Cards -->
            <main class="master-grid">
                {all_grid_elements_html}
            </main>
        </div>
        
        <!-- Right Side: Statistics and Rankings -->
        <aside class="side-panel">
            <!-- Market Breadth -->
            <div class="side-card">
                <h2>📊 全市場漲跌家數</h2>
                <div class="breadth-grid">
                    <div class="b-card">
                        <h4>個股總數</h4>
                        <div id="stat-total" class="b-val" style="color: #60a5fa;">0</div>
                    </div>
                    <div class="b-card">
                        <h4>🔴 上漲家數</h4>
                        <div id="stat-up" class="b-val" style="color: var(--taiwan-up);">0</div>
                    </div>
                    <div class="b-card">
                        <h4>🟢 下跌家數</h4>
                        <div id="stat-down" class="b-val" style="color: var(--taiwan-down);">0</div>
                    </div>
                    <div class="b-card">
                        <h4>⚪ 平盤家數</h4>
                        <div id="stat-flat" class="b-val" style="color: var(--flat-color);">0</div>
                    </div>
                </div>
            </div>
            
            <!-- Sub-sectors Averages Rankings -->
            <div class="side-card">
                <div class="rank-tabs">
                    <button class="rank-tab-btn active" id="btn-sub-leaders" onclick="switchSubRank('leaders')">🔥 領漲產業</button>
                    <button class="rank-tab-btn" id="btn-sub-laggards" onclick="switchSubRank('laggards')">❄️ 領跌產業</button>
                </div>
                
                <table>
                    <thead>
                        <tr>
                            <th>次產業分類</th>
                            <th>平均漲跌</th>
                            <th>股數</th>
                        </tr>
                    </thead>
                    <tbody id="sub-rank-table-body">
                        <!-- Dynamic -->
                    </tbody>
                </table>
            </div>
            
            <!-- Leaders/Laggards Ranks -->
            <div class="side-card">
                <div class="rank-tabs">
                    <button class="rank-tab-btn active" onclick="switchRank('leaders')">🔥 領漲排行</button>
                    <button class="rank-tab-btn" onclick="switchRank('laggards')">❄️ 領跌排行</button>
                </div>
                
                <table id="rank-table">
                    <thead>
                        <tr>
                            <th>代號</th>
                            <th>股名</th>
                            <th>幅度 %</th>
                            <th>次產業</th>
                        </tr>
                    </thead>
                    <tbody id="rank-table-body">
                        <!-- Dynamic -->
                    </tbody>
                </table>
            </div>
        </aside>
    </div>
    
    <!-- Floating Back/Clear Button -->
    <button id="floating-clear-btn" class="floating-back-btn" onclick="clearSearch()">
        ↩ 返回資金地圖 (清除篩選)
    </button>
    
    <script>
        // Load datasets
        const payload = {cat_averages_json};
        
        // ECharts Init
        const treemapChart = echarts.init(document.getElementById('treemap-chart'), 'dark');
        
        function getFilteredTreemap(originalData, matchedTickers) {{
            const result = [];
            originalData.forEach(mainNode => {{
                const newMainChildren = [];
                let mainMcapSum = 0;
                let mainChangeSum = 0;
                let mainChangeCount = 0;
                
                mainNode.children.forEach(subNode => {{
                    const newSubChildren = [];
                    let subMcapSum = 0;
                    let subChangeSum = 0;
                    let subChangeCount = 0;
                    
                    subNode.children.forEach(stockNode => {{
                        const ticker = stockNode.ticker;
                        if (matchedTickers.has(ticker)) {{
                            newSubChildren.push(stockNode);
                            subMcapSum += stockNode.value[0];
                            subChangeSum += stockNode.change;
                            subChangeCount++;
                        }}
                    }});
                    
                    if (newSubChildren.length > 0) {{
                        const subAvg = subChangeCount > 0 ? (subChangeSum / subChangeCount) : 0;
                        const subCleanName = subNode.name.split(' (')[0];
                        newMainChildren.push({{
                            name: `${{subCleanName}} (${{subAvg >= 0 ? '+' : ''}}${{subAvg.toFixed(2)}}%)`,
                            value: [subMcapSum, subAvg],
                            change: subAvg,
                            children: newSubChildren.sort((a, b) => b.value[0] - a.value[0])
                        }});
                        
                        mainMcapSum += subMcapSum;
                        mainChangeSum += subAvg;
                        mainChangeCount++;
                    }}
                }});
                
                if (newMainChildren.length > 0) {{
                    const mainAvg = mainChangeCount > 0 ? (mainChangeSum / mainChangeCount) : 0;
                    const mainCleanName = mainNode.name.split(' (')[0];
                    result.push({{
                        name: `${{mainCleanName}} (${{mainAvg >= 0 ? '+' : ''}}${{mainAvg.toFixed(2)}}%)`,
                        value: [mainMcapSum, mainAvg],
                        change: mainAvg,
                        children: newMainChildren.sort((a, b) => b.value[0] - a.value[0])
                    }});
                }}
            }});
            
            return result.sort((a, b) => b.value[0] - a.value[0]);
        }}
        
        let currentPeriod = '1d';
        let currentRankTab = 'leaders';
        let currentSubRankTab = 'leaders';
        
        // Collapsible sector functions
        function toggleMainCard(mainSafeId) {{
            const card = document.getElementById(mainSafeId);
            if (!card) return;
            
            const list = card.querySelector('.sub-category-list');
            const arrow = card.querySelector('.toggle-main-arrow');
            
            if (list.style.display === 'none' || list.style.display === '') {{
                list.style.display = 'flex';
                if (arrow) arrow.innerText = '▼';
            }} else {{
                list.style.display = 'none';
                if (arrow) arrow.innerText = '▶';
            }}
        }}
        
        function toggleSubSection(subSafeId) {{
            const section = document.getElementById(subSafeId);
            if (!section) return;
            
            const grid = section.querySelector('.stock-grid');
            const arrow = section.querySelector('.toggle-arrow');
            
            if (grid.style.display === 'none' || grid.style.display === '') {{
                grid.style.display = 'grid';
                if (arrow) arrow.innerText = '▼';
            }} else {{
                grid.style.display = 'none';
                if (arrow) arrow.innerText = '▶';
            }}
        }}
        
        function toggleAll(expand) {{
            const subLists = document.querySelectorAll('.sub-category-list');
            const mainArrows = document.querySelectorAll('.toggle-main-arrow');
            const grids = document.querySelectorAll('.stock-grid');
            const subArrows = document.querySelectorAll('.toggle-arrow');
            
            subLists.forEach(list => {{
                list.style.display = expand ? 'flex' : 'none';
            }});
            mainArrows.forEach(arrow => {{
                arrow.innerText = expand ? '▼' : '▶';
            }});
            grids.forEach(grid => {{
                grid.style.display = expand ? 'grid' : 'none';
            }});
            subArrows.forEach(arrow => {{
                arrow.innerText = expand ? '▼' : '▶';
            }});
        }}
        
        // Focus and scroll to sector card
        function focusSectorCard(mainSafeId) {{
            const card = document.getElementById(mainSafeId);
            if (card) {{
                card.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                
                // Flash border to draw attention
                card.style.borderColor = 'var(--primary-accent)';
                setTimeout(() => {{
                    card.style.borderColor = 'var(--border-color)';
                }}, 1500);
            }}
        }}
        
        // Search stock function
        function searchStocks() {{
            const query = document.getElementById('search-input').value.toLowerCase().trim();
            const pills = document.querySelectorAll('.stock-pill');
            const cards = document.querySelectorAll('.main-card');
            
            const clearSearch = document.getElementById('clear-search');
            const floatingClearBtn = document.getElementById('floating-clear-btn');
            
            if (query === "") {{
                if (clearSearch) clearSearch.style.display = 'none';
                if (floatingClearBtn) floatingClearBtn.style.display = 'none';
                cards.forEach(card => {{
                    card.style.display = 'block';
                    const mInfo = Object.values(payload[currentPeriod].main_gp).find(m => m.safe_id === card.id);
                    if (mInfo) {{
                        card.style.order = mInfo.rank;
                    }}
                    card.querySelector('.sub-category-list').style.display = 'none';
                    const arrow = card.querySelector('.toggle-main-arrow');
                    if (arrow) arrow.innerText = '▶';
                }});
                toggleAll(false);
                pills.forEach(pill => {{
                    pill.style.opacity = "1";
                    pill.style.border = "1px solid rgba(255, 255, 255, 0.04)";
                }});
                // Restore Treemap
                treemapChart.setOption({{
                    series: [{{
                        data: payload[currentPeriod].treemap
                    }}]
                }});
                return;
            }}
            
            if (clearSearch) clearSearch.style.display = 'block';
            if (floatingClearBtn) floatingClearBtn.style.display = 'flex';
            
            // Check if there is an exact match for the query
            let hasExactMatch = false;
            pills.forEach(pill => {{
                const name = pill.getAttribute('data-name').trim().toLowerCase();
                const ticker = pill.getAttribute('data-ticker').trim().toLowerCase();
                if (name === query || ticker === query) {{
                    hasExactMatch = true;
                }}
            }});
            
            const matchedCardIds = new Set();
            const matchedTickers = new Set();
            
            pills.forEach(pill => {{
                const name = pill.getAttribute('data-name').trim().toLowerCase();
                const ticker = pill.getAttribute('data-ticker').trim().toLowerCase();
                const mainCat = (pill.getAttribute('data-main-cat') || '').trim().toLowerCase();
                const subCat = (pill.getAttribute('data-sub-cat') || '').trim().toLowerCase();
                
                let isMatch = false;
                if (hasExactMatch) {{
                    isMatch = (name === query || ticker === query);
                }} else {{
                    isMatch = (name.includes(query) || 
                               ticker.includes(query) || 
                               mainCat.includes(query) || 
                               subCat.includes(query));
                }}
                
                if (isMatch) {{
                    pill.style.opacity = "1";
                    pill.style.border = "2px solid var(--primary-accent)";
                    matchedTickers.add(ticker);
                    
                    const parentGrid = pill.closest('.stock-grid');
                    if (parentGrid) {{
                        parentGrid.style.display = 'grid';
                        const subSection = parentGrid.closest('.sub-section');
                        if (subSection) {{
                            const arrow = subSection.querySelector('.toggle-arrow');
                            if (arrow) arrow.innerText = '▼';
                        }}
                    }}
                    
                    const mainCard = pill.closest('.main-card');
                    if (mainCard) {{
                        matchedCardIds.add(mainCard.id);
                        mainCard.querySelector('.sub-category-list').style.display = 'flex';
                        const mainArrow = mainCard.querySelector('.toggle-main-arrow');
                        if (mainArrow) mainArrow.innerText = '▼';
                    }}
                }} else {{
                    pill.style.opacity = "0.15";
                    pill.style.border = "1px solid rgba(255, 255, 255, 0.04)";
                }}
            }});
            
            // Reorder and hide cards
            cards.forEach(card => {{
                if (matchedCardIds.has(card.id)) {{
                    card.style.display = 'block';
                    const mInfo = Object.values(payload[currentPeriod].main_gp).find(m => m.safe_id === card.id);
                    if (mInfo) {{
                        card.style.order = mInfo.rank - 1000; // Float to the absolute top!
                    }}
                }} else {{
                    card.style.display = 'none'; // Hide non-matching sectors!
                }}
            }});
            
            // Scroll to the top of the heatmap section smoothly
            const gridContainer = document.querySelector('.master-grid');
            if (gridContainer) {{
                gridContainer.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }}
            
            // Update Treemap
            const filteredTreemapData = getFilteredTreemap(payload[currentPeriod].treemap, matchedTickers);
            treemapChart.setOption({{
                series: [{{
                    data: filteredTreemapData
                }}]
            }});
        }}
        
        // Bulk analysis functions
        function toggleBulkPanel() {{
            const panel = document.getElementById('bulk-panel');
            if (panel.style.display === 'none' || panel.style.display === '') {{
                panel.style.display = 'block';
                document.getElementById('bulk-input').focus();
            }} else {{
                panel.style.display = 'none';
                document.getElementById('bulk-input').value = '';
                analyzeBulk();
            }}
        }}
        
        function analyzeBulk() {{
            const text = document.getElementById('bulk-input').value.trim();
            const pills = document.querySelectorAll('.stock-pill');
            const cards = document.querySelectorAll('.main-card');
            
            if (text === "") {{
                document.getElementById('bulk-results').style.display = 'none';
                cards.forEach(card => {{
                    card.style.display = 'block';
                    const mInfo = Object.values(payload[currentPeriod].main_gp).find(m => m.safe_id === card.id);
                    if (mInfo) {{
                        card.style.order = mInfo.rank;
                    }}
                    card.querySelector('.sub-category-list').style.display = 'none';
                    const arrow = card.querySelector('.toggle-main-arrow');
                    if (arrow) arrow.innerText = '▶';
                }});
                toggleAll(false);
                pills.forEach(pill => {{
                    pill.style.opacity = "1";
                    pill.style.border = "1px solid rgba(255, 255, 255, 0.04)";
                }});
                // Restore Treemap
                treemapChart.setOption({{
                    series: [{{
                        data: payload[currentPeriod].treemap
                    }}]
                }});
                return;
            }}
            
            // Parse tokens: split by spaces, commas, newlines, etc.
            const noiseWords = new Set([
                "電子科技", "加工業", "健康科技", "科技服務", "生產製造", "非能源礦產", "工業服務", 
                "金融", "運輸", "非耐用消費品", "配送服務", "零售業", "消費者服務", "公用事業",
                "無評級", "強力買入", "買入", "中立", "強力賣出", "賣出", "觀察清單", "更改排序",
                "twd", "usd", "cny", "eur", "jpy", "無評", "強力"
            ]);
            const rawTerms = text.split(/[\\s,，\\n、]+/).map(t => t.trim().toLowerCase()).filter(t => t.length > 0);
            const terms = rawTerms.filter(token => {{
                if (token.length <= 1) return false;
                if (/^[-+]?\\d+(\\.\\d+)?%?$/.test(token)) return false; // Exclude numbers with decimals or percentage signs
                if (noiseWords.has(token)) return false;
                return true;
            }});
            if (terms.length === 0) return;
            
            // For each term, check if it matches any name/ticker exactly
            const exactMatches = new Set();
            terms.forEach(term => {{
                pills.forEach(pill => {{
                    const name = pill.getAttribute('data-name').trim().toLowerCase();
                    const ticker = pill.getAttribute('data-ticker').trim().toLowerCase();
                    if (name === term || ticker === term) {{
                        exactMatches.add(term);
                    }}
                }});
            }});
            
            const matchedCardIds = new Set();
            const matchedTickers = new Set();
            const sectorCounts = {{}};
            let totalMatched = 0;
            
            pills.forEach(pill => {{
                const name = pill.getAttribute('data-name').trim().toLowerCase();
                const ticker = pill.getAttribute('data-ticker').trim().toLowerCase();
                
                let isMatch = false;
                terms.forEach(term => {{
                    if (exactMatches.has(term)) {{
                        if (name === term || ticker === term) {{
                            isMatch = true;
                        }}
                    }} else {{
                        if (name.includes(term) || ticker.includes(term)) {{
                            isMatch = true;
                        }}
                    }}
                }});
                
                if (isMatch) {{
                    pill.style.opacity = "1";
                    pill.style.border = "2px solid var(--primary-accent)";
                    totalMatched++;
                    matchedTickers.add(ticker);
                    
                    const mainCard = pill.closest('.main-card');
                    if (mainCard) {{
                        matchedCardIds.add(mainCard.id);
                        const mainTitle = mainCard.querySelector('.main-title').innerText.replace('▶', '').replace('▼', '').trim();
                        sectorCounts[mainTitle] = (sectorCounts[mainTitle] || 0) + 1;
                    }}
                    
                    const parentGrid = pill.closest('.stock-grid');
                    if (parentGrid) {{
                        parentGrid.style.display = 'grid';
                        const subSection = parentGrid.closest('.sub-section');
                        if (subSection) {{
                            const arrow = subSection.querySelector('.toggle-arrow');
                            if (arrow) arrow.innerText = '▼';
                        }}
                    }}
                }} else {{
                    pill.style.opacity = "0.15";
                    pill.style.border = "1px solid rgba(255, 255, 255, 0.04)";
                }}
            }});
            
            // Reorder and show matching cards
            cards.forEach(card => {{
                if (matchedCardIds.has(card.id)) {{
                    card.style.display = 'block';
                    const mInfo = Object.values(payload[currentPeriod].main_gp).find(m => m.safe_id === card.id);
                    if (mInfo) {{
                        card.style.order = mInfo.rank - 1000; // Float to the absolute top!
                    }}
                    card.querySelector('.sub-category-list').style.display = 'flex';
                    const arrow = card.querySelector('.toggle-main-arrow');
                    if (arrow) arrow.innerText = '▼';
                }} else {{
                    card.style.display = 'none';
                }}
            }});
            
            // Scroll to the top of the heatmap section smoothly
            const gridContainer = document.querySelector('.master-grid');
            if (gridContainer) {{
                gridContainer.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }}
            
            // Update Treemap
            const filteredTreemapData = getFilteredTreemap(payload[currentPeriod].treemap, matchedTickers);
            treemapChart.setOption({{
                series: [{{
                    data: filteredTreemapData
                }}]
            }});
            
            // Render sector distribution tags
            const resultsBox = document.getElementById('bulk-results');
            resultsBox.style.display = 'block';
            
            const sortedSectors = Object.entries(sectorCounts).sort((a, b) => b[1] - a[1]);
            
            let resultsHtml = `<div class="bulk-stats-header">🔍 貼上分析結果: 匹配 <strong>${{totalMatched}}</strong> 檔個股，分佈在 <strong>${{sortedSectors.length}}</strong> 個板塊：</div>`;
            resultsHtml += '<div class="bulk-tag-list">';
            sortedSectors.forEach(([secName, count]) => {{
                const pct = ((count / totalMatched) * 100).toFixed(0);
                resultsHtml += `<span class="bulk-sec-tag" onclick="focusSectorByTitle('${{secName}}')">${{secName}}: <strong>${{count}}檔 (${{pct}}%)</strong></span>`;
            }});
            resultsHtml += '</div>';
            resultsBox.innerHTML = resultsHtml;
        }}
        
        function focusSectorByTitle(secTitle) {{
            const cards = document.querySelectorAll('.main-card');
            for (let card of cards) {{
                const titleText = card.querySelector('.main-title').innerText.replace('▶', '').replace('▼', '').trim();
                if (titleText === secTitle) {{
                    focusSectorCard(card.id);
                    break;
                }}
            }}
        }}
        
        function focusStock(stockName) {{
            document.getElementById('search-input').value = stockName;
            searchStocks();
            
            const pills = document.querySelectorAll('.stock-pill');
            for (let pill of pills) {{
                if (pill.getAttribute('data-name') === stockName) {{
                    pill.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    break;
                }}
            }}
        }}
        
        function clearSearch() {{
            document.getElementById('search-input').value = "";
            searchStocks();
            
            // Scroll back to the top header / Treemap smooth
            const header = document.querySelector('header');
            if (header) {{
                header.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }}
        }}
        
        // Color scale mapping (Red for up, Green for down, Taiwan standard)
        function getIntensityColor(change, period) {{
            if (change === undefined || change === null || isNaN(change)) {{
                return 'rgba(75, 85, 99, 0.15)'; 
            }}
            
            let maxVal = 8.0;
            if (period === '5d') maxVal = 18.0;
            if (period === '10d') maxVal = 28.0;
            
            const percent = Math.min(Math.abs(change) / maxVal, 1.0);
            
            if (change > 0) {{
                return `rgba(239, 68, 68, ${{0.15 + percent * 0.85}})`;
            }} else if (change < 0) {{
                return `rgba(16, 185, 129, ${{0.15 + percent * 0.85}})`;
            }} else {{
                return 'rgba(75, 85, 99, 0.35)'; 
            }}
        }}
        
        // Main function to switch periods on Heatmap & Treemap
        function switchPeriod(period) {{
            currentPeriod = period;
            
            const buttons = document.querySelectorAll('.tab-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            event.currentTarget.classList.add('active');
            
            const pData = payload[period];
            
            // 1. Update Breadth Stats
            document.getElementById('stat-total').innerText = pData.stats.total;
            document.getElementById('stat-up').innerText = pData.stats.up;
            document.getElementById('stat-down').innerText = pData.stats.down;
            document.getElementById('stat-flat').innerText = pData.stats.flat;
            
            // 2. Loop and Update stock pills
            const pills = document.querySelectorAll('.stock-pill');
            pills.forEach(pill => {{
                const valStr = pill.getAttribute(`data-${{period}}`);
                const val = valStr !== "null" ? parseFloat(valStr) : null;
                const changeSpan = pill.querySelector('.s-change');
                
                if (val !== null) {{
                    const sign = val >= 0 ? '+' : '';
                    changeSpan.innerText = sign + val.toFixed(2) + '%';
                    pill.style.backgroundColor = getIntensityColor(val, period);
                }} else {{
                    changeSpan.innerText = '--';
                    pill.style.backgroundColor = 'rgba(75, 85, 99, 0.15)';
                }}
            }});
            
            // 3. Update all Card Headers (Main categories and sub categories averages) and re-order cards
            for (const [mName, mInfo] of Object.entries(pData.main_gp)) {{
                const badge = document.getElementById("badge-" + mInfo.safe_id);
                if (badge) {{
                    const sign = mInfo.avg >= 0 ? '+' : '';
                    badge.innerText = `${{sign}}${{mInfo.avg.toFixed(2)}}%`;
                    badge.style.backgroundColor = getIntensityColor(mInfo.avg, period);
                    badge.style.color = '#ffffff';
                }}
                const card = document.getElementById(mInfo.safe_id);
                if (card) {{
                    card.style.order = mInfo.rank;
                }}
            }}
            
            // Sub headers
            for (const [keyStr, sInfo] of Object.entries(pData.sub_gp)) {{
                const badge = document.getElementById("badge-" + sInfo.safe_id);
                if (badge) {{
                    const sign = sInfo.avg >= 0 ? '+' : '';
                    badge.innerText = `${{sign}}${{sInfo.avg.toFixed(2)}}%`;
                    badge.style.color = sInfo.avg >= 0 ? 'var(--taiwan-up)' : 'var(--taiwan-down)';
                    if (sInfo.avg === 0) badge.style.color = 'var(--text-secondary)';
                }}
            }}
            
            // 4. Update Treemap
            const treemapOption = {{
                backgroundColor: 'transparent',
                tooltip: {{
                    formatter: function (info) {{
                        var value = info.value;
                        var name = info.name.split(/\\n| \\(/)[0];
                        var mcap = Array.isArray(value) ? value[0] : value;
                        var change = Array.isArray(value) ? value[1] : info.data.change;
                        var changeStr = change !== undefined ? (change >= 0 ? '▲ +' + change.toFixed(2) + '%' : '▼ ' + change.toFixed(2) + '%') : '';
                        var changeColor = change >= 0 ? 'color: var(--taiwan-up);' : 'color: var(--taiwan-down);';
                        
                        return [
                            '<div class="tooltip-title" style="font-weight:bold;font-size:1.1rem;margin-bottom:6px;">' + name + '</div>',
                            '市值規模: ' + (mcap ? mcap.toLocaleString() : 0) + ' 百萬 TWD<br/>',
                            '該期累積漲跌幅: <span style="font-weight:bold;' + changeColor + '">' + changeStr + '</span>'
                        ].join('');
                    }}
                }},
                series: [{{
                    name: '台股產業地圖',
                    type: 'treemap',
                    visibleMin: 200,
                    roam: true,
                    nodeClick: 'zoomToNode',
                    left: 0,
                    right: 0,
                    top: 10,
                    bottom: 45,
                    label: {{
                        show: true,
                        formatter: '{{b}}',
                        fontSize: 11
                    }},
                    upperLabel: {{
                        show: true,
                        height: 22,
                        color: '#fff',
                        fontWeight: 'bold',
                        fontSize: 12
                    }},
                    breadcrumb: {{
                        show: true,
                        bottom: 45, // Move breadcrumb up to avoid overlapping with visualMap
                        itemStyle: {{
                            color: 'rgba(255, 255, 255, 0.1)',
                            textStyle: {{
                                color: '#e5e7eb',
                                fontSize: 11
                            }}
                        }}
                    }},
                    itemStyle: {{
                        borderColor: '#161c2d',
                        borderWidth: 1.5,
                        gapWidth: 1
                    }},
                    levels: [
                        {{
                            itemStyle: {{
                                borderColor: '#161c2d',
                                borderWidth: 4,
                                gapWidth: 4
                            }},
                            upperLabel: {{
                                show: true
                            }}
                        }},
                        {{
                            itemStyle: {{
                                borderColor: '#161c2d',
                                borderWidth: 2,
                                gapWidth: 2
                            }}
                        }},
                        {{
                            colorMappingBy: 'value',
                            itemStyle: {{
                                gapWidth: 1
                            }}
                        }}
                    ],
                    data: pData.treemap
                }}],
                visualMap: {{
                    type: 'continuous',
                    min: period === '1d' ? -5 : (period === '5d' ? -15 : -25),
                    max: period === '1d' ? 5 : (period === '5d' ? 15 : 25),
                    visualDimension: 1,
                    calculable: true,
                    orient: 'horizontal',
                    left: 'center',
                    bottom: 5, // Positioned slightly above the bottom line
                    inRange: {{
                        color: ['#10b981', '#374151', '#ef4444']
                    }},
                    text: ['漲 ▲', '▼ 跌'],
                    textStyle: {{
                        color: '#9ca3af',
                        fontWeight: 'bold'
                    }}
                }}
            }};
            treemapChart.setOption(treemapOption);
            
            // 5. Update Rank Tables
            switchRank(currentRankTab);
            switchSubRank(currentSubRankTab);
        }}
        
        // Switch between Leaders and Laggards
        function switchRank(tab) {{
            currentRankTab = tab;
            
            const buttons = document.querySelectorAll('.rank-tab-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            if (tab === 'leaders') {{
                buttons[0].classList.add('active');
            }} else {{
                buttons[1].classList.add('active');
            }}
            
            const list = payload[currentPeriod][tab];
            const tbody = document.getElementById('rank-table-body');
            tbody.innerHTML = '';
            
            list.forEach(r => {{
                const classColor = r.change >= 0 ? 'up' : 'down';
                const sign = r.change >= 0 ? '+' : '';
                
                tbody.innerHTML += `
                    <tr onclick="focusStock('${{r.name}}')">
                        <td><code>${{r.ticker}}</code></td>
                        <td><strong>${{r.name}}</strong></td>
                        <td class="${{classColor}}">${{sign}}${{r.change.toFixed(2)}}%</td>
                        <td><span class="tag">${{r.sub_cat}}</span></td>
                    </tr>
                `;
            }});
        }}
        
        // Switch between Sub-sector Leaders and Laggards
        function switchSubRank(tab) {{
            currentSubRankTab = tab;
            
            const btnLeaders = document.getElementById('btn-sub-leaders');
            const btnLaggards = document.getElementById('btn-sub-laggards');
            
            if (tab === 'leaders') {{
                btnLeaders.classList.add('active');
                btnLaggards.classList.remove('active');
            }} else {{
                btnLeaders.classList.remove('active');
                btnLaggards.classList.add('active');
            }}
            
            const list = payload[currentPeriod][tab === 'leaders' ? 'sub_leaders' : 'sub_laggards'];
            const tbody = document.getElementById('sub-rank-table-body');
            tbody.innerHTML = '';
            
            list.forEach(r => {{
                const classColor = r.avg_change >= 0 ? 'up' : 'down';
                const sign = r.avg_change >= 0 ? '+' : '';
                
                tbody.innerHTML += `
                    <tr onclick="focusSubSection('${{r.safe_id}}')" title="點擊展開並捲動定位到該次產業">
                        <td><strong>${{r.sub_cat}}</strong><br/><span style="font-size:0.75rem;color:var(--text-secondary);">${{r.main_cat}}</span></td>
                        <td class="${{classColor}}">${{sign}}${{r.avg_change.toFixed(2)}}%</td>
                        <td><span class="tag">${{r.count}} 檔</span></td>
                    </tr>
                `;
            }});
        }}
        
        // Focus and scroll to sub-sector section row
        function focusSubSection(subSafeId) {{
            const section = document.getElementById(subSafeId);
            if (section) {{
                // Expand parent main card if collapsed
                const mainCard = section.closest('.main-card');
                if (mainCard) {{
                    const list = mainCard.querySelector('.sub-category-list');
                    const arrow = mainCard.querySelector('.toggle-main-arrow');
                    if (list && (list.style.display === 'none' || list.style.display === '')) {{
                        list.style.display = 'flex';
                        if (arrow) arrow.innerText = '▼';
                    }}
                }}
                
                // Expand sub section if collapsed
                const grid = section.querySelector('.stock-grid');
                const arrow = section.querySelector('.toggle-arrow');
                if (grid && (grid.style.display === 'none' || grid.style.display === '')) {{
                    grid.style.display = 'grid';
                    if (arrow) arrow.innerText = '▼';
                }}
                
                // Now scroll to it!
                setTimeout(() => {{
                    section.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                }}, 50);
                
                // Flash border to draw attention
                section.style.borderColor = 'var(--primary-accent)';
                setTimeout(() => {{
                    section.style.borderColor = 'rgba(255, 255, 255, 0.02)';
                }}, 1500);
            }}
        }}
        
        // Treemap node click interaction -> floats card to top and highlights it!
        treemapChart.on('click', function (params) {{
            if (params.data && params.data.name) {{
                const cleanName = params.data.name.split(/\\n| \\(/)[0].trim();
                
                // Filter by name (supports stock names, main sector names, and sub-sector names!)
                focusStock(cleanName);
                
                // If it is a main sector or sub-sector (not a leaf stock), scroll to it specifically
                if (!params.data.ticker) {{
                    setTimeout(() => {{
                        // Check if it is a main sector name
                        const cards = document.querySelectorAll('.main-card');
                        let foundSector = false;
                        for (let card of cards) {{
                            const titleText = card.querySelector('.main-title').innerText.trim();
                            if (titleText === cleanName) {{
                                focusSectorCard(card.id);
                                foundSector = true;
                                break;
                            }}
                        }}
                        
                        // If not a main sector, check if it is a sub-sector name
                        if (!foundSector) {{
                            const subSections = document.querySelectorAll('.sub-section');
                            for (let section of subSections) {{
                                const titleSpan = section.querySelector('.sub-title');
                                if (titleSpan) {{
                                    const titleText = titleSpan.innerText.replace(/[▶▼]/g, '').trim();
                                    if (titleText === cleanName) {{
                                        focusSubSection(section.id);
                                        break;
                                    }}
                                }}
                            }}
                        }}
                    }}, 100);
                }}
            }}
        }});
        
        // Initial load
        switchPeriod('1d');
        
        // Handle window resizing
        window.addEventListener('resize', function() {{
            treemapChart.resize();
        }});
    </script>
</body>
</html>
"""
    
    with open(REPORT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Combined Master Dashboard with Treemap generated successfully.")
    print("=" * 60)
    print("🎉 Pipeline Completed Successfully!")
    print(f"- Summary Report: {REPORT_MD}")
    print(f"- Combined Dashboard: {REPORT_HTML}")
    print("=" * 60)

if __name__ == "__main__":
    run_pipeline()
