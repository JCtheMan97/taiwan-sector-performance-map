# -*- coding: utf-8 -*-
import os, sys, json, time, requests
import urllib3
from datetime import datetime, timedelta
urllib3.disable_warnings()

CACHE_FILE = "institutional_cache.json"

def get_latest_trading_date_str():
    now = datetime.now()
    if now.hour < 15:
        now = now - timedelta(days=1)
    while now.weekday() >= 5:
        now = now - timedelta(days=1)
    return now.strftime("%Y%m%d")

def fetch_twse_institutional(date_str):
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALLBUT0999&response=json"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(url, headers=headers, verify=False, timeout=10)
        data = res.json()
        if data.get("stat") != "OK": return {}
        raw_data = data.get("data", [])
        result = {}
        for row in raw_data:
            ticker = row[0].strip()
            def parse_num(v):
                try: return int(str(v).replace(",", ""))
                except: return 0
            foreign_net = parse_num(row[4]) // 1000
            trust_net = parse_num(row[10]) // 1000
            dealer_net = parse_num(row[11]) // 1000
            result[ticker] = {"foreign": foreign_net, "trust": trust_net, "dealer": dealer_net, "total": foreign_net + trust_net + dealer_net}
        print(f"[TWSE] Downloaded {len(result)} stocks")
        return result
    except Exception as e:
        print(f"[TWSE] Error: {e}")
        return {}

def fetch_tpex_institutional(date_str):
    url = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&response=json"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(url, headers=headers, verify=False, timeout=10)
        data = res.json()
        tables = data.get("tables", [])
        result = {}
        if tables and tables[0].get("data"):
            for row in tables[0]["data"]:
                ticker = row[0].strip()
                def parse_num(v):
                    try: return int(str(v).replace(",", ""))
                    except: return 0
                foreign_net = parse_num(row[4]) // 1000 if len(row) > 4 else 0
                trust_net = parse_num(row[7]) // 1000 if len(row) > 7 else 0
                dealer_net = parse_num(row[10]) // 1000 if len(row) > 10 else 0
                result[ticker] = {"foreign": foreign_net, "trust": trust_net, "dealer": dealer_net, "total": foreign_net + trust_net + dealer_net}
        print(f"[TPEX] Downloaded {len(result)} stocks")
        return result
    except Exception as e:
        print(f"[TPEX] Error: {e}")
        return {}

def get_institutional_data():
    today_str = get_latest_trading_date_str()
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
                if cache.get("date") == today_str and cache.get("data") and len(cache.get("data")) > 1500:
                    print(f"[Cache] Loaded {today_str} data ({len(cache['data'])} stocks)")
                    return cache["data"]
        except Exception as e: pass

    print(f"[Downloading] {today_str} institutional data...")
    twse_data = fetch_twse_institutional(today_str)
    time.sleep(0.5)
    tpex_data = fetch_tpex_institutional(today_str)
    combined = {}
    combined.update(twse_data)
    combined.update(tpex_data)
    if combined:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"date": today_str, "data": combined}, f, ensure_ascii=False, indent=2)
        print(f"[Saved] {len(combined)} stocks to {CACHE_FILE}")
    return combined

if __name__ == "__main__":
    data = get_institutional_data()
    print("Sample 2330 (TSMC):", data.get("2330"))
