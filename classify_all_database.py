# -*- coding: utf-8 -*-
"""
Classify All Database Stocks (classify_all_database.py)
Loads all 1980+ stocks from stocks_list.txt, fetches their industry info in parallel,
caches them, and generates a master industry map.
"""

import os
import json
import sys
import io
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf

# Standardize output encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Constants
STOCK_LIST_FILE = "stocks_list.txt"
CACHE_FILE = "industry_cache.json"
REPORT_MD = "all_stocks_industry_map.md"
REPORT_HTML = "all_stocks_industry_map.html"

# Expert Categorization Database (reused from analyze_trends.py)
STOCK_SUBCLASS = {
    # === 手動高精準度分類覆蓋 ===
    "辛耘": ("半導體與 PCB 設備/材料", "半導體設備與材料"),
    "弘塑": ("半導體與 PCB 設備/材料", "半導體設備與材料"),
    "萬潤": ("半導體與 PCB 設備/材料", "半導體設備與材料"),
    "光寶科": ("伺服器與資訊週邊", "伺服器與資訊週邊"),
    "台達電": ("伺服器與資訊週邊", "伺服器與資訊週邊"),
    "崇越": ("半導體與 PCB 設備/材料", "半導體設備與材料"),
    "長華": ("半導體與 PCB 設備/材料", "半導體設備與材料"),
    "華立": ("半導體與 PCB 設備/材料", "半導體設備與材料"),
    "鴻準": ("車用與傳統工業", "機殼與沖壓件"),
    "力致": ("工業電腦與電腦週邊", "散熱模組與元件"),
    "曜越": ("工業電腦與電腦週邊", "散熱模組與元件"),
    "撼訊": ("工業電腦與電腦週邊", "顯示卡與電腦週邊"),
    "華電": ("綠能、環保與化學工業", "重電與電線電纜"),
    "合機": ("綠能、環保與化學工業", "重電與電線電纜"),
    "百徽": ("被動元件與石英元件", "被動元件 - 電感與磁性元件"),
    "地心引力": ("軟體與資訊服務", "數位廣告與行銷科技"),
    "富爾特": ("軟體與資訊服務", "數位廣告與行銷科技"),
    "冠軍": ("建材營造與房地產", "建材與裝修"),
    "國統": ("綠能、環保與化學工業", "環保綠能與水資源"),
    "成霖": ("傳統工業與其它", "廚衛五金"),
    "桓鼎-KY": ("建材營造與房地產", "建材與裝修"),
    "橋椿": ("傳統工業與其它", "廚衛五金"),
    "福興": ("傳統工業與其它", "鎖具與五金件"),
    "美吉吉-KY": ("建材營造與房地產", "建材與裝修"),
    "青鋼": ("建材營造與房地產", "建材與裝修"),
    "匯僑設計": ("建材營造與房地產", "空間設計與顧問服務"),
    "安葆": ("綠能、環保與化學工業", "能源工程與電力系統"),
    "潤德": ("建材營造與房地產", "空間設計與顧問服務"),
    "久裕": ("生技醫療", "醫藥通路與連鎖藥局"),
    "大樹": ("生技醫療", "醫藥通路與連鎖藥局"),
    "杏一": ("生技醫療", "醫藥通路與連鎖藥局"),
    "勤崴國際": ("軟體與資訊服務", "圖資與導航軟體"),
    "德律": ("半導體與 PCB 設備/材料", "量測儀器與精密檢測"),
    "桓達": ("電子零組件與其它", "感測器與自動化控制"),
    "泰藝": ("被動元件與石英元件", "石英元件"),
    "環天科": ("通訊、線材與連接器", "無線通訊與物聯網裝置"),
    "系統電": ("車用與傳統工業", "車用電子與感測器"),
    "致茂": ("半導體與 PCB 設備/材料", "精密測試設備"),
    "華晶科": ("光電與顯示面板", "數位相機與影像處理"),
    "閎康": ("半導體產業", "IC 研發與分析服務 (MA/FA)"),
    "鼎天": ("車用與傳統工業", "車用電子與導航系統"),
    "神基": ("工業電腦與電腦週邊", "強固型電腦與車用機構件"),
    "廣宇": ("通訊、線材與連接器", "高頻連接器與傳輸線材"),
    "鴻海": ("工業電腦與電腦週邊", "全方位電子代工 (EMS) 龍頭"),
    "仁寶": ("伺服器與資訊週邊", "伺服器與筆電代工"),
    "緯創": ("伺服器與資訊週邊", "伺服器與筆電代工"),
    "廣達": ("伺服器與資訊週邊", "伺服器與筆電代工"),
    "和碩": ("工業電腦與電腦週邊", "筆電與消費電子代工"),
    "富喬": ("半導體與 PCB 設備/材料", "PCB 玻纖紗與玻纖布"),
    "長興": ("綠能、環保與化學工業", "合成樹脂與特用化學品"),
    "金像電": ("PCB 與銅箔基板", "高階伺服器板 (PCB)"),
    "華通": ("PCB 與銅箔基板", "高密度連接板 (HDI) 與軟硬結合板"),
    "健鼎": ("PCB 與銅箔基板", "多層印刷電路板 (PCB)"),
    "敬鵬": ("PCB 與銅箔基板", "車用印刷電路板 (PCB)"),
    "偉訓": ("工業電腦與電腦週邊", "電腦機殼與電源供應器"),
    "中鋼": ("傳統工業與傳統材料", "鋼鐵金屬"),
    "燁輝": ("傳統工業與傳統材料", "鋼鐵金屬"),
    "德麥": ("傳統工業與傳統材料", "食品與麵包烘焙原料"),
    "安可": ("光電與顯示面板", "ITO 導電玻璃"),
    "安可光電": ("光電與顯示面板", "ITO 導電玻璃"),
    "李洲": ("光電與顯示面板", "LED 封裝與代理商"),
    "光鼎": ("光電與顯示面板", "LED 封裝與照明元件"),
    # === 手動高精準度分類覆蓋 ===
    "神基": ("工業電腦與電腦週邊", "強固型電腦與車用機構件"),
    "廣宇": ("通訊、線材與連接器", "高頻連接器與傳輸線材"),
    "鴻海": ("工業電腦與電腦週邊", "全方位電子代工 (EMS) 龍頭"),
    "仁寶": ("伺服器與資訊週邊", "伺服器與筆電代工"),
    "緯創": ("伺服器與資訊週邊", "伺服器與筆電代工"),
    "廣達": ("伺服器與資訊週邊", "伺服器與筆電代工"),
    "和碩": ("工業電腦與電腦週邊", "筆電與消費電子代工"),
    "富喬": ("半導體與 PCB 設備/材料", "PCB 玻纖紗與玻纖布"),
    "長興": ("綠能、環保與化學工業", "合成樹脂與特用化學品"),
    "金像電": ("PCB 與銅箔基板", "高階伺服器板 (PCB)"),
    "華通": ("PCB 與銅箔基板", "高密度連接板 (HDI) 與軟硬結合板"),
    "健鼎": ("PCB 與銅箔基板", "多層印刷電路板 (PCB)"),
    "敬鵬": ("PCB 與銅箔基板", "車用印刷電路板 (PCB)"),
    "偉訓": ("工業電腦與電腦週邊", "電腦機殼與電源供應器"),
    "中鋼": ("傳統工業與傳統材料", "鋼鐵金屬"),
    "燁輝": ("傳統工業與傳統材料", "鋼鐵金屬"),
    "德麥": ("傳統工業與傳統材料", "食品與麵包烘焙原料"),
    "安可": ("光電與顯示面板", "ITO 導電玻璃"),
    "安可光電": ("光電與顯示面板", "ITO 導電玻璃"),
    "李洲": ("光電與顯示面板", "LED 封裝與代理商"),
    "光鼎": ("光電與顯示面板", "LED 封裝與照明元件"),
    # === 被動元件 ===
    "國巨": ("被動元件與石英元件", "電阻/電容/電感多合一龍頭"),
    "華新科": ("被動元件與石英元件", "晶片電阻與電容 (MLCC)"),
    "禾伸堂": ("被動元件與石英元件", "陶瓷電容 (MLCC)"),
    "信昌電陶": ("被動元件與石英元件", "陶瓷電容 (MLCC) 與介電粉末"),
    "立隆電": ("被動元件與石英元件", "電解電容"),
    "金山電子": ("被動元件與石英元件", "電解電容"),
    "凱美": ("被動元件與石英元件", "電解電容與晶片電阻"),
    "鈺邦": ("被動元件與石英元件", "固態電容"),
    "天二科技": ("被動元件與石英元件", "晶片電阻"),
    "光頡科技": ("被動元件與石英元件", "精密與薄膜電阻"),
    "興勤": ("被動元件與石英元件", "保護元件 (熱敏/壓敏電阻)"),
    "臺慶科": ("被動元件與石英元件", "電感器與濾波器"),
    "今展科": ("被動元件與石英元件", "電感器"),
    "千如電機": ("被動元件與石英元件", "電感器"),
    "晶技": ("被動元件與石英元件", "石英元件 (晶體/振盪器)"),
    "希華": ("被動元件與石英元件", "石英元件 (晶體/振盪器)"),
    "加高電子": ("被動元件與石英元件", "石英元件 (晶體/振盪器)"),
    "台灣嘉碩": ("被動元件與石英元件", "石英元件與聲表面波濾波器 (SAW)"),
    "安碁科技": ("被動元件與石英元件", "石英元件 (晶體/振盪器)"),
    "九豪精密": ("被動元件與石英元件", "電阻陶瓷基板 (被動上游)"),
    "立敦科技": ("被動元件與石英元件", "化成箔 (電解電容材料)"),
    "日電貿": ("被動元件與石英元件", "被動元件通路商"),
    "蜜望實": ("被動元件與石英元件", "被動元件通路商"),
    "天正國際": ("被動元件與石英元件", "被動元件測試包裝設備"),
    "雷科": ("被動元件與石英元件", "被動元件雷射修整設備與包裝材"),
    "鈞寶": ("被動元件與石英元件", "磁性元件/電感與電磁干擾濾波器"),
    "華容": ("被動元件與石英元件", "薄膜電容"),
    "越峰電子": ("被動元件與石英元件", "電感鐵芯/錳鋅及鎳鋅鐵氧體電磁材料"),

    # === 半導體產業 ===
    "聯電": ("半導體產業", "晶圓代工"),
    "力積電": ("半導體產業", "晶圓代工"),
    "茂矽": ("半導體產業", "晶圓代工/二極體"),
    "環球晶": ("半導體產業", "矽晶圓材料"),
    "台勝科": ("半導體產業", "矽晶圓材料"),
    "合晶科技": ("半導體產業", "矽晶圓材料"),
    "中美晶": ("半導體產業", "矽晶圓/太陽能"),
    "昇陽半導體": ("半導體產業", "再生晶圓與薄化"),
    "華邦電": ("半導體產業", "記憶體製造 (DRAM/Flash)"),
    "南亞科": ("半導體產業", "記憶體製造 (DRAM)"),
    
    # IC 設計
    "矽創": ("半導體產業", "IC設計 - 驅動 IC"),
    "尼克森": ("半導體產業", "IC設計 - 功率 MOSFET"),
    "大中": ("半導體產業", "IC設計 - 功率 MOSFET"),
    "富鼎": ("半導體產業", "IC設計 - 功率 MOSFET"),
    "力士": ("半導體產業", "IC設計 - 功率 MOSFET"),
    "台半": ("半導體產業", "IC設計 - 功率二極體/MOSFET"),
    "德微": ("半導體產業", "IC設計與封測 - 功率二極體/ESD"),
    "廣閎科": ("半導體產業", "IC設計 - 電機驅動/功率IC"),
    "強茂": ("半導體產業", "IC設計與製造 - 二極體/MOSFET"),
    "麗正": ("半導體產業", "IC設計與封裝 - 二極體"),
    "虹揚-KY": ("半導體產業", "IC設計與製造 - 整流二極體"),
    "微矽電子-創": ("半導體產業", "IC測試及封裝 - 功率元件測試"),
    "應廣": ("半導體產業", "IC設計 - 微控制器 (MCU)"),
    "松翰": ("半導體產業", "IC設計 - 微控制器 (MCU)"),
    "盛群": ("半導體產業", "IC設計 - 微控制器 (MCU)"),
    "凌陽": ("半導體產業", "IC設計 - 多媒體與音訊晶片"),
    "凱鈺科技": ("半導體產業", "IC設計 - 類比與網通 IC"),
    "晶豪科": ("半導體產業", "IC設計 - 利基型記憶體 IC"),
    "鈺創科技": ("半導體產業", "IC設計 - 記憶體 IC 與邏輯晶片"),
    "聯傑": ("半導體產業", "IC設計 - 網通與控制晶片"),
    "瑞昱": ("半導體產業", "IC設計 - 網通與音訊晶片龍頭"),
    "禾瑞亞": ("半導體產業", "IC設計 - 觸控晶片"),
    "界霖": ("半導體產業", "半導體導線架 (封裝材料)"),
    "長科": ("半導體產業", "導線架材料 (封裝材料)"),
    "百容": ("半導體產業", "機電元件 (開關/繼電器) 與半導體導線架"),
    "吉祥全": ("半導體產業", "發光二極體與記憶體代理"),
    "方土昶": ("半導體產業", "電子零組件代理商"),
    "百徽": ("半導體產業", "電子零組件代理商"),
    "全宇昕": ("半導體產業", "功率半導體封裝與設計"),
    "茂達電子": ("半導體產業", "IC設計 - 電源管理 IC"),
    "擎亞": ("半導體產業", "半導體代理通路"),
    "統懋": ("半導體產業", "功率半導體二極體"),

    # 半導體封測 (OSAT)
    "捷敏-KY": ("半導體產業", "半導體封測 - 功率半導體"),
    "日月光投控": ("半導體產業", "半導體封測 - 晶圓級/全方位封測龍頭"),
    "南茂": ("半導體產業", "半導體封測 - 驅動 IC 與記憶體"),
    "矽格": ("半導體產業", "半導體封測 - 射頻/混合訊號/測試"),
    "欣銓科技": ("半導體產業", "半導體封測 - 晶圓測試"),
    "超豐": ("半導體產業", "半導體封測 - 導線架打線封測"),
    "菱生": ("半導體產業", "半導體封測 - 電源管理/感測器封測"),
    "力成": ("半導體產業", "半導體封測 - 記憶體及系統級封裝"),
    "同欣電": ("半導體產業", "半導體封測 - 陶瓷封裝與 CMOS 感測器封測"),
    "福懋科": ("半導體產業", "半導體封測 - 記憶體模組封裝與測試"),
    "精材": ("半導體產業", "半導體封測 - 晶圓級封裝"),

    # 半導體/電子設備、材料與廠務
    "揚博": ("半導體與 PCB 設備/材料", "PCB與半導體濕製程設備/代理"),
    "帆宣": ("半導體與 PCB 設備/材料", "半導體廠務與設備整合服務"),
    "東捷科技": ("半導體與 PCB 設備/材料", "半導體與面板製程設備"),
    "翔名科技": ("半導體與 PCB 設備/材料", "半導體離子植入機耗材"),
    "嘉晶": ("半導體與 PCB 設備/材料", "磊晶片材料"),
    "旺矽科技": ("半導體與 PCB 設備/材料", "半導體探針卡與檢測設備"),
    "聯鈞": ("半導體與 PCB 設備/材料", "光電封裝與半導體雷射代工"),
    "蔚華科": ("半導體與 PCB 設備/材料", "半導體測試設備與代理"),
    "順德": ("半導體與 PCB 設備/材料", "功率半導體導線架與模具"),
    "中砂": ("半導體與 PCB 設備/材料", "半導體鑽石碟與再生晶圓"),
    "朋億": ("半導體與 PCB 設備/材料", "半導體高純度化學品供應系統/廠務"),
    "聖暉": ("半導體與 PCB 設備/材料", "無塵室及機電工程"),
    "亞翔": ("半導體與 PCB 設備/材料", "半導體與生技建廠/廠務工程"),
    "盟立": ("半導體與 PCB 設備/材料", "自動化倉儲與機器人系統整合"),
    "鈦昇": ("半導體與 PCB 設備/材料", "半導體雷射切割與修整設備"),
    "亞泰金屬": ("半導體與 PCB 設備/材料", "PCB/CCL塗佈機與設備"),
    "尖點": ("半導體與 PCB 設備/材料", "PCB 鑽針與鑽孔加工服務"),
    "陽程": ("半導體與 PCB 設備/材料", "自動化物流與貼合設備"),
    "科嶠": ("半導體與 PCB 設備/材料", "PCB 乾燥製程設備"),
    "中釉": ("半導體與 PCB 設備/材料", "陶瓷釉料與半導體材料"),

    # === PCB 與銅箔基板 (CCL) ===
    "台光電": ("PCB 與銅箔基板", "銅箔基板 (CCL)"),
    "騰輝電子-KY": ("PCB 與銅箔基板", "銅箔基板 (CCL)"),
    "台燿科技": ("PCB 與銅箔基板", "銅箔基板 (CCL)"),
    "聯茂": ("PCB 與銅箔基板", "銅箔基板 (CCL)"),
    "南電": ("PCB 與銅箔基板", "IC 載板 (ABF/BT)"),
    "景碩": ("PCB 與銅箔基板", "IC 載板 (BT/ABF)"),
    "臻鼎-KY": ("PCB 與銅箔基板", "硬板、軟板與載板全方位板王"),
    "霖宏科技": ("PCB 與銅箔基板", "多層印刷電路板"),
    "柏承": ("PCB 與銅箔基板", "印刷電路板 (PCB)"),
    "楠梓電": ("PCB 與銅箔基板", "印刷電路板 (PCB)"),
    "亞電": ("PCB 與銅箔基板", "軟性銅箔基板 (FCCL) 與覆蓋膜"),
    "台虹": ("PCB 與銅箔基板", "軟性銅箔基板 (FCCL) 與太陽能背板"),

    # === 光電與顯示面板 ===
    "群創": ("光電與顯示面板", "顯示面板與液晶螢幕"),
    "友達": ("光電與顯示面板", "顯示面板與液晶螢幕"),
    "彩晶": ("光電與顯示面板", "中小尺寸顯示面板"),
    "TPK-KY": ("光電與顯示面板", "觸控感應模組"),
    "安可光電": ("光電與顯示面板", "ITO 導電玻璃"),
    "正達": ("光電與顯示面板", "車用/3D玻片玻璃"),
    "大立光": ("光電與顯示面板", "高階光學鏡頭"),
    "先進光": ("光電與顯示面板", "車用與筆電光學鏡頭"),
    "今國光": ("光電與顯示面板", "玻璃/塑膠光學鏡片"),
    "光鼎": ("光電與顯示面板", "LED封裝與照明元件"),
    "李洲科技": ("光電與顯示面板", "LED封裝與代理商"),
    "光環": ("光電與顯示面板", "光通訊收發模組/主被動元件"),
    "國碩": ("光電與顯示面板", "太陽能材料與導電漿"),

    # === 通訊、線材與連接器 ===
    "佳必琪": ("通訊、線材與連接器", "高頻傳輸連接器與連接線"),
    "聯穎": ("通訊、線材與連接器", "傳輸線與電子線材"),
    "萬泰科技": ("通訊、線材與連接器", "高頻網路線與同軸線"),
    "風青": ("通訊、線材與連接器", "漆包線 (繞線用)"),
    "倉和": ("半導體與 PCB 設備/材料", "太陽能電池網版印刷網版"),

    # === 工業電腦與電腦週邊 ===
    "凌華": ("工業電腦與電腦週邊", "工業電腦 (IPC) 與邊緣運算"),
    "研華": ("工業電腦與電腦週邊", "工業電腦 (IPC) 龍頭"),
    "艾訊": ("工業電腦與電腦週邊", "工業電腦 (IPC)"),
    "全友": ("工業電腦與電腦週邊", "影像掃描器與週邊"),
    "廣穎": ("工業電腦與電腦週邊", "記憶體模組與快閃碟"),
    "映泰": ("工業電腦與電腦週邊", "主機板、顯示卡"),
    "普安": ("工業電腦與電腦週邊", "企業級磁碟存儲系統"),
    "能率網通": ("工業電腦與電腦週邊", "通訊代理與通路服務"),
    "英業達": ("工業電腦與電腦週邊", "筆電、伺服器代工"),
    "金寶": ("工業電腦與電腦週邊", "消費性電子、通訊設備代工"),
    "固緯": ("工業電腦與電腦週邊", "電子測試與量測儀器"),

    # === 軟體、資訊服務與數位雲端 ===
    "GOGOLOOK": ("軟體與資訊服務", "數位信任科技 (Whoscall)"),
    "創新服務": ("軟體與資訊服務", "軟體外包與系統整合"),
    "威潤": ("軟體與資訊服務", "車載衛星定位監控 (Telematics)"),
    "倍微科技": ("軟體與資訊服務", "半導體與通訊軟硬體通路商"),

    # === 軍工、航太與防衛 ===
    "長榮航太": ("軍工與航太", "飛機維修與航太零組件製造"),
    "雷虎": ("軍工與航太", "無人機與遙控模型"),
    "事欣科": ("軍工與航太", "軍工與博弈工業電腦/系統整合"),
    "千附精密": ("軍工與航太", "光電與航太精密機械加工"),

    # === 綠能、環保與化學工業 ===
    "旭然": ("綠能、環保與化學工業", "水處理過濾設備與濾心"),
    "東鹼": ("綠能、環保與化學工業", "硫酸鉀肥料與散裝航運"),
    "中華化": ("綠能、環保與化學工業", "基礎及特用化學品 (酸鹼化學)"),
    "昶昕": ("綠能、環保與化學工業", "PCB特用化學品與銅回收"),
    "雙鍵": ("綠能、環保與化學工業", "特用化學品 (塑膠添加劑/塗料)"),
    "國精化": ("綠能、環保與化學工業", "光固化樹脂材料"),
    "磐亞": ("綠能、環保與化學工業", "非離子界面活性劑原料"),
    "和桐": ("綠能、環保與化學工業", "界面活性劑原料 (LAS/烷基苯)"),
    "台化": ("綠能、環保與化學工業", "石化原料、聚酯與人造纖維"),
    "中纖": ("綠能、環保與化學工業", "人造纖維與石化原料 (EG/EO)"),
    "聯友金屬-創": ("綠能、環保與化學工業", "鎢鈷回收與特用金屬化學"),
    "南亞": ("綠能、環保與化學工業", "塑膠原料與特用化學品(BPA)"),
    "台汽電": ("綠能、環保與化學工業", "汽電共生與綠能開發"),

    # === 金融服務 ===
    "台新新光金": ("金融服務", "金融控股公司 (台新/新光)"),
    "凱基金": ("金融服務", "金融控股公司 (壽險/銀行/證券)"),
    "元大金": ("金融服務", "金融控股公司 (證券/銀行/期貨)"),
    "統一證": ("金融服務", "證券公司"),
    "致和證": ("金融服務", "證券公司"),
    "美好證": ("金融服務", "證券公司"),

    # === 生技醫療 ===
    "藥華藥": ("生技醫療", "罕見疾病新藥研發"),
    "天良": ("生技醫療", "西藥銷售與保健食品"),
    "沛爾生醫-創": ("生技醫療", "細胞療法與免疫製劑"),

    # === 傳統工業與其他 ===
    "百達-KY": ("車用與傳統工業", "汽車精密沖壓與服務機器人"),
    "東浦": ("車用與傳統工業", "汽車與消費電子塑膠外殼/模具"),
    "宏旭-KY": ("車用與傳統工業", "汽車鈑金模具"),
    "智伸科": ("車用與傳統工業", "汽車動力與傳動精密零件"),
    "慶騰精密": ("車用與傳統工業", "粉末冶金與車用齒輪零件"),
    "久陽精密": ("車用與傳統工業", "螺絲螺帽與環保資源回收"),
    "新纖": ("車用與傳統工業", "聚酯纖維與工程塑膠"),
    "日成-KY": ("車用與傳統工業", "精品珠寶設計與製造"),
    "能率亞洲": ("車用與傳統工業", "創業投資與資產管理"),
    "川湖": ("伺服器與資訊週邊", "伺服器導軌與滑軌"),
    "南俊國際": ("伺服器與資訊週邊", "伺服器導軌與滑軌"),
    "欣興": ("PCB 與銅箔基板", "IC 載板 (ABF/BT)"),
    "新盛力": ("車用與傳統工業", "鋰電池模組 (LEV與儲能電池模組)"),
    "泓格科技": ("工業電腦與電腦週邊", "工業乙太網路與遠端監控系統"),
}

def clean_stock_name(name):
    n = name.replace("*", "").replace("-KY", "").replace("-創", "").replace("（", "").replace("）", "").replace("(", "").replace(")", "")
    n = n.replace("台灣", "").replace("台", "")
    n = re.sub(r'(精密|科技|電子|電機|電陶|光電|工業|控股|國際|生醫|生物科技|科|金屬|服務|通路|網通|亞洲)', '', n)
    return n

CLEAN_SUBCLASS = {clean_stock_name(k): v for k, v in STOCK_SUBCLASS.items()}

DETAILED_SECTOR_MAP = {
    "Advertising Agencies": ("軟體與資訊服務", "數位廣告與行銷科技"),
    "Building Products & Equipment": ("建材營造與房地產", "建材與裝修"),
    "Consulting Services": ("建材營造與房地產", "空間設計與顧問服務"),
    "Pharmaceutical Retailers": ("生技醫療", "醫藥通路與連鎖藥局"),
    "Scientific & Technical Instruments": ("半導體與 PCB 設備/材料", "量測儀器與精密檢測"),
    "N/A": ("金融服務", "ETF與基金"),
    # Technology
    "Semiconductors": ("半導體產業", "半導體製造與設備"),
    "Semiconductor Equipment & Materials": ("半導體產業", "半導體設備與材料"),
    "Electronic Components": ("電子零組件與其它", "電子零組件"),
    "Electronic Distribution": ("半導體與電子通路", "電子通路與經銷"),
    "Electronics & Computer Distribution": ("半導體與電子通路", "電子通路與經銷"),
    "Computer Hardware": ("工業電腦與電腦週邊", "電腦及週邊設備"),
    "Consumer Electronics": ("工業電腦與電腦週邊", "消費性電子"),
    "Communication Equipment": ("通訊、線材與連接器", "通信與網路設備"),
    "Software - Application": ("軟體與資訊服務", "資訊服務與軟體外包"),
    "Software-Application": ("軟體與資訊服務", "資訊服務與軟體外包"),
    "Software - Infrastructure": ("軟體與資訊服務", "數位雲端服務"),
    "Software-Infrastructure": ("軟體與資訊服務", "數位雲端服務"),
    "Information Technology Services": ("軟體與資訊服務", "資訊服務與軟體外包"),
    "Internet Content & Information": ("軟體與資訊服務", "數位雲端服務"),
    "Electronic Gaming & Multimedia": ("軟體與資訊服務", "數位娛樂與多媒體"),
    
    # Industrials & Manufacturing
    "Aerospace & Defense": ("軍工與航太", "軍工與航太零組件"),
    "Pollution & Treatment Controls": ("綠能、環保與化學工業", "環保綠能與水處理"),
    "Specialty Industrial Machinery": ("半導體與 PCB 設備/材料", "特殊及精密工業機械"),
    "Electrical Equipment & Parts": ("電子零組件與其它", "電氣設備與零件"),
    "Metal Fabrication": ("車用與傳統工業", "精密機械與金屬加工"),
    "Tools & Accessories": ("車用與傳統工業", "工具與金屬配件"),
    "Industrial Distribution": ("車用與傳統工業", "工業材料通路"),
    "Engineering & Construction": ("半導體與 PCB 設備/材料", "廠務與工程建設"),
    "Business Equipment & Supplies": ("工業電腦與電腦週邊", "辦公與商業設備"),
    "Specialty Business Services": ("車用與傳統工業", "商業與外包服務"),
    "Staffing & Employment Services": ("軟體與資訊服務", "人力資源與資訊外包"),
    "Waste Management": ("綠能、環保與化學工業", "廢棄物處理"),
    "Conglomerates": ("傳統工業與其它", "綜合企業控股"),

    # Auto & Vehicles
    "Auto Parts": ("車用與傳統工業", "汽車零組件"),
    "Auto Manufacturers": ("車用與傳統工業", "汽車製造"),
    "Auto & Truck Dealerships": ("車用與傳統工業", "汽機車經銷"),
    "Recreational Vehicles": ("車用與傳統工業", "休閒車輛"),
    
    # Chemicals & Materials
    "Specialty Chemicals": ("綠能、環保與化學工業", "特用化學品"),
    "Chemicals": ("綠能、環保與化學工業", "化學工業"),
    "Agricultural Inputs": ("綠能、環保與化學工業", "農業與肥料"),
    "Steel": ("傳統工業與傳統材料", "鋼鐵金屬"),
    "Aluminum": ("傳統工業與傳統材料", "鋁業金屬"),
    "Other Industrial Metals & Mining": ("傳統工業與傳統材料", "其它金屬礦產"),
    "Copper": ("傳統工業與傳統材料", "銅業"),
    "Lumber & Wood Production": ("傳統工業與傳統材料", "木材與造紙上游"),
    "Paper & Paper Products": ("傳統工業與傳統材料", "造紙"),
    "Packaging & Containers": ("傳統工業與傳統材料", "包裝與容器"),
    "Building Materials": ("傳統工業與傳統材料", "建材"),

    # Consumer Defensive
    "Beverages - Non-Alcoholic": ("傳統工業與其它", "飲料與非酒精飲料"),
    "Beverages-Non-Alcoholic": ("傳統工業與傳統材料", "食品與飲料"),
    "Packaged Foods": ("傳統工業與其它", "包裝食品"),
    "Food Distribution": ("傳統工業與其它", "食品通路"),
    "Confectioners": ("傳統工業與其它", "食品與糖果"),
    "Farm Products": ("傳統工業與其它", "農產品"),
    "Grocery Stores": ("傳統工業與其它", "超市與量販"),
    "Household & Personal Products": ("傳統工業與其它", "民生與個人清潔用品"),

    # Consumer Cyclical & Retail
    "Luxury Goods": ("傳統工業與其它", "精品珠寶"),
    "Specialty Retail": ("傳統工業與其它", "百貨貿易與零售"),
    "Apparel Retail": ("傳統工業與其它", "服飾零售"),
    "Department Stores": ("傳統工業與其它", "百貨公司"),
    "Internet Retail": ("傳統工業與其它", "電子商務"),
    "Home Improvement Retail": ("傳統工業與其它", "居家生活零售"),
    "Travel Services": ("觀光餐旅與休閒娛樂", "觀光旅遊與票務"),
    "Lodging": ("觀光餐旅與休閒娛樂", "觀光餐旅 - 飯店"),
    "Restaurants": ("觀光餐旅與休閒娛樂", "觀光餐旅 - 餐飲"),
    "Resorts & Casinos": ("觀光餐旅與休閒娛樂", "娛樂與休閒"),
    "Footwear & Accessories": ("傳統工業與其它", "鞋類與配飾"),
    "Furnishings, Fixtures & Appliances": ("傳統工業與其它", "家具與家電"),
    "Apparel Manufacturing": ("傳統工業與傳統材料", "成衣製造"),
    "Textile Manufacturing": ("傳統工業與傳統材料", "紡織纖維"),
    
    # Financials
    "Banks - Regional": ("金融服務", "銀行與金融控股"),
    "Banks-Regional": ("金融服務", "銀行與金融控股"),
    "Capital Markets": ("金融服務", "證券與資本市場"),
    "Asset Management": ("金融服務", "創業投資與資產管理"),
    "Credit Services": ("金融服務", "信用貸款與消費金融"),
    "Financial Conglomerates": ("金融服務", "金融控股公司"),
    "Insurance - Diversified": ("金融服務", "保險業"),
    "Insurance - Life": ("金融服務", "人壽保險"),
    "Insurance - Property & Casualty": ("金融服務", "產物與意外險"),
    "Insurance - Reinsurance": ("金融服務", "再保險"),
    "Insurance Brokers": ("金融服務", "保險經紀人"),

    # Healthcare
    "Biotechnology": ("生技醫療", "生物科技"),
    "Drug Manufacturers - Specialty & Generic": ("生技醫療", "醫療與生技製藥"),
    "Drug Manufacturers-Specialty & Generic": ("生技醫療", "醫療與生技製藥"),
    "Drug Manufacturers - General": ("生技醫療", "醫療與生技製藥"),
    "Drug Manufacturers-General": ("生技醫療", "醫療與生技製藥"),
    "Diagnostics & Research": ("生技醫療", "醫療檢測與研究"),
    "Medical Instruments & Supplies": ("生技醫療", "醫療器材與耗材"),
    "Medical Devices": ("生技醫療", "醫療器材與設備"),
    "Medical Distribution": ("生技醫療", "醫療通路與醫藥分銷"),
    "Medical Care Facilities": ("生技醫療", "醫療照護機構"),
    "Health Information Services": ("生技醫療", "醫療資訊服務"),

    # Real Estate & Utilities & Telecom
    "Real Estate - Development": ("建材營造與房地產", "營建與不動產開發"),
    "Real Estate-Development": ("建材營造與房地產", "營建與不動產開發"),
    "Real Estate - Diversified": ("建材營造與房地產", "不動產綜合"),
    "Real Estate-Diversified": ("建材營造與房地產", "不動產綜合"),
    "Real Estate Services": ("建材營造與房地產", "不動產中介與服務"),
    "Homebuilding": ("建材營造與房地產", "住宅建造"),
    
    "Utilities - Regulated Electric": ("綠能、環保與化學工業", "電力能源公用事業"),
    "Utilities-Regulated Electric": ("綠能、環保與化學工業", "電力能源公用事業"),
    "Utilities - Regulated Gas": ("綠能、環保與化學工業", "油氣公用事業"),
    "Utilities-Regulated Gas": ("綠能、環保與化學工業", "油氣公用事業"),
    "Utilities - Regulated Water": ("綠能、環保與化學工業", "水力公用事業"),
    "Utilities-Regulated Water": ("綠能、環保與化學工業", "水力公用事業"),
    "Utilities - Renewable": ("綠能、環保與化學工業", "綠能環保與再生能源"),
    "Utilities-Renewable": ("綠能、環保與化學工業", "綠能環保與再生能源"),
    "Solar": ("綠能、環保與化學工業", "太陽能綠能"),
    "Thermal Coal": ("綠能、環保與化學工業", "煤炭與傳統能源"),

    "Telecom Services": ("通訊、線材與連接器", "電信與通訊服務"),
    "Broadcasting": ("觀光餐旅與休閒娛樂", "傳播與媒體"),
    "Publishing": ("觀光餐旅與休閒娛樂", "出版與數位媒體"),
    "Entertainment": ("觀光餐旅與休閒娛樂", "娛樂與文創"),
    "Personal Services": ("傳統工業與其它", "生活服務"),
    "Education & Training Services": ("觀光餐旅與休閒娛樂", "教育與培訓"),
    "Leisure": ("觀光餐旅與休閒娛樂", "運動與休閒娛樂"),
    "Security & Protection Services": ("軟體與資訊服務", "資訊安全與保全"),
    
    # Logistics & Transport
    "Integrated Freight & Logistics": ("航運與運輸", "物流與倉儲"),
    "Marine Shipping": ("航運與運輸", "航運 - 散裝/貨櫃"),
    "Airlines": ("航運與運輸", "航空公司"),
    "Railroads": ("航運與運輸", "陸運鐵路"),
    "Trucking": ("航運與運輸", "陸運與物流"),
    "Oil & Gas Refining & Marketing": ("綠能、環保與化學工業", "石油煉製與行銷"),
    "Oil & Gas Equipment & Services": ("綠能、環保與化學工業", "石油與天然氣設備服務"),
    
    # TWSE/TPEx Chinese Fallbacks
    "半導體業": ("半導體產業", "半導體製造與設備"),
    "電腦及週邊設備業": ("工業電腦與電腦週邊", "電腦及週邊設備"),
    "光電業": ("光電與顯示面板", "光電與顯示面板"),
    "化學工業": ("綠能、環保與化學工業", "化學工業"),
    "橡膠工業": ("傳統工業與傳統材料", "橡膠製品"),
    "汽車工業": ("傳統工業與其它", "汽車與零組件"),
    "貿易百貨業": ("傳統工業與其它", "百貨貿易"),
    "觀光餐旅": ("傳統工業與其它", "觀光旅遊與餐飲"),
    "農業科技業": ("傳統工業與其它", "農業與精緻科技"),
    "文化創意業": ("傳統工業與其它", "文創與傳媒"),
    "運動休閒": ("傳統工業與其它", "運動休閒"),
    "居家生活": ("傳統工業與其它", "居家生活"),
    "其他業": ("傳統工業與其它", "其他未分類傳統行業"),
    "綜合": ("傳統工業與其它", "綜合控股"),
    "其他電子業": ("電子零組件與其它", "其它電子組件"),
    "電子工業": ("電子零組件與其它", "電子製造"),
    "臺灣存託憑證(DR)": ("傳統工業與其它", "存託憑證(DR)"),
}

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

def fetch_yfinance_details(name, ticker, cache):
    """Fetches details from yfinance or cache."""
    if ticker in cache:
        return cache[ticker]
    try:
        t_obj = yf.Ticker(ticker)
        info = t_obj.info
        sector = info.get("sector")
        industry = info.get("industry")
        res = {
            "name": name,
            "ticker": ticker,
            "sector": sector if sector else "N/A",
            "industry": industry if industry else "N/A",
            "longName": info.get("longName", name),
            "status": "success"
        }
        return res
    except Exception as e:
        return {
            "name": name,
            "ticker": ticker,
            "sector": "N/A",
            "industry": "N/A",
            "status": "error",
            "error": str(e)
        }

def save_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Warning: Failed to save cache:", e)

def run_pipeline():
    print("=" * 60)
    print("🚀 Starting Master Database Industry Classification")
    print("=" * 60)
    
    # 1. Load Cache
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"Loaded {len(cache)} cached stock profiles.")
        except Exception as e:
            print("Warning: Failed to load cache:", e)
            
    # 2. Load stock list
    stocks = load_stock_list(STOCK_LIST_FILE)
    if not stocks:
        print(f"Please place a valid '{STOCK_LIST_FILE}' in the directory.")
        return
    print(f"Loaded {len(stocks)} stocks from database.")
    
    # 3. Find missing tickers
    to_query = []
    details = {}
    for name, ticker in stocks:
        if ticker in cache:
            details[name] = cache[ticker]
            # Ensure name is synced
            details[name]["name"] = name
        else:
            to_query.append((name, ticker))
            
    print(f"Already cached: {len(details)}. Need to query: {len(to_query)}")
    
    # 4. Fetch missing profiles in parallel
    if to_query:
        print(f"Querying {len(to_query)} stock profiles in parallel...")
        batch_size = 50
        count = 0
        
        # We query in small batches and save cache to prevent loss
        for i in range(0, len(to_query), batch_size):
            batch = to_query[i:i+batch_size]
            with ThreadPoolExecutor(max_workers=30) as executor:
                futures = {executor.submit(fetch_yfinance_details, name, ticker, cache): name for name, ticker in batch}
                for fut in as_completed(futures):
                    res = fut.result()
                    name = res["name"]
                    ticker = res["ticker"]
                    details[name] = res
                    if res.get("status") == "success":
                        cache[ticker] = res
            
            count += len(batch)
            save_cache(cache)
            print(f"Progress: {count}/{len(to_query)} queried and cached.")
            
    # 5. Expert Categorization
    print("Categorizing all database stocks...")
    grouped = {}
    
    for name, data in details.items():
        ticker = data.get("ticker", "N/A")
        clean_name = clean_stock_name(name)
        raw_industry = data.get("industry", "Other")
        longName = data.get("longName", "")
        search_text = (name + " " + longName).upper()
        ticker_num = ticker.split(".")[0].strip()
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
        elif clean_name in CLEAN_SUBCLASS:
            main_cat, sub_cat = CLEAN_SUBCLASS[clean_name]
        else:
            # Programmatic ticker cleanups for crowded Electronic Components category
            if ticker_num in ["3023", "3217", "3322", "3533", "3605", "6205", "6272", "8103", "3492", "3511", "3520", "3526", "3597", "3646", "3689", "3710", "3011", "2460", "6126", "6158", "6185", "6418", "5457", "8147", "6913", "3310", "4943"]:
                main_cat, sub_cat = ("通訊、線材與連接器", "連接器與連接線")
            elif ticker_num in ["3390", "3321", "6153", "6269", "3354"]:
                main_cat, sub_cat = ("PCB 與銅箔基板", "軟性銅箔基板 (FCCL)/軟板")
            elif ticker_num in ["3715", "4927", "5469", "6108", "6191", "8213", "3276", "3645", "5291", "5355", "5439", "6156", "6210", "8155", "8074", "8183", "6278", "6266", "8358", "4909", "6194", "6597", "8291"]:
                main_cat, sub_cat = ("PCB 與銅箔基板", "印刷電路板 (PCB)")
            elif ticker_num in ["3653", "3338", "6230", "6124", "3324", "8996", "6125"]:
                main_cat, sub_cat = ("工業電腦與電腦週邊", "散熱模組與元件")
            elif ticker_num in ["1582", "3548", "3230", "3294", "5243"]:
                main_cat, sub_cat = ("電子零組件與其它", "轉軸與機構五金")
            elif ticker_num in ["3049", "4935", "4960", "6120", "6176", "6456", "3622", "3623", "3666", "8105", "8215", "4933", "5220", "5315", "6246", "4729", "8069", "6899", "3285", "3543", "4942", "6405", "6698", "6854", "6916", "8104", "3523", "6167", "8049", "8111", "8240"]:
                main_cat, sub_cat = ("光電與顯示面板", "面板與觸控模組")
            elif ticker_num in ["3591", "3714", "4956", "5244", "2338"]:
                main_cat, sub_cat = ("光電與顯示面板", "LED與光電元件")
            elif ticker_num in ["6498", "6517", "3630", "5230", "3406", "3019", "3504", "3441", "4976", "6668"]:
                main_cat, sub_cat = ("光電與顯示面板", "光電與光學鏡頭")
            elif ticker_num in ["6203", "6276", "6821", "2431"]:
                main_cat, sub_cat = ("電子零組件與其它", "電源供應器")
            elif ticker_num in ["5228", "6284", "4760", "6224", "6792", "6862", "6204"]:
                main_cat, sub_cat = ("被動元件與石英元件", "被動元件 - 電感與磁性元件")
            elif ticker_num in ["3455", "3563", "3093", "7769", "3490", "3551", "5443", "6261", "6425", "6640", "6735", "6877", "6953", "7751", "7556", "3535", "3402", "6438", "6706", "7795", "3485", "3580", "4568", "6208", "6664", "6217"]:
                main_cat, sub_cat = ("半導體與 PCB 設備/材料", "半導體設備與材料")
            elif ticker_num in ["4749", "1773", "4755", "1785", "5234", "4768", "5434", "8070", "3010", "3444", "3305"]:
                main_cat, sub_cat = ("半導體與 PCB 設備/材料", "半導體材料與特用化學品")
            elif ticker_num in ["6451", "6552"]:
                main_cat, sub_cat = ("半導體產業", "IC 封測 (OSAT)")
            elif ticker_num in ["6830"]:
                main_cat, sub_cat = ("半導體產業", "IC 研發與分析服務 (MA/FA)")
            elif ticker_num in ["6725"]:
                main_cat, sub_cat = ("半導體產業", "分離元件與功率半導體")
            elif ticker_num in ["6756", "6962", "5487", "6732", "6996"]:
                main_cat, sub_cat = ("半導體產業", "IC 設計")
            elif ticker_num in ["3416", "4995", "5474", "6577", "7402"]:
                main_cat, sub_cat = ("工業電腦與電腦週邊", "電腦及週邊設備")
            elif ticker_num in ["5284"]:
                main_cat, sub_cat = ("伺服器與資訊週邊", "伺服器與資訊週邊")
            elif ticker_num in ["6609"]:
                main_cat, sub_cat = ("半導體與 PCB 設備/材料", "特殊及精密工業機械")
            elif ticker_num in ["7744"]:
                main_cat, sub_cat = ("通訊、線材與連接器", "通信與網路設備")
            elif ticker_num in ["2347", "3048", "8112", "3036"]:
                main_cat, sub_cat = ("傳統工業與其它", "電子通路")
            elif ticker_num in ["2480", "3029"]:
                main_cat, sub_cat = ("軟體與資訊服務", "資訊服務與軟體外包")
            elif ticker_num in ["2535"]:
                main_cat, sub_cat = ("建材營造與房地產", "營建與不動產開發")
            elif ticker_num in ["6574", "6703", "4137", "4190", "6523", "1786", "6666", "6658"]:
                main_cat, sub_cat = ("生技醫療", "美容保養與醫美")
                
            # Custom overrides for hot sectors (重電, 光通訊)
            elif ticker_num in ["1519", "1503", "1513", "1514", "2371", "1529", "1618", "1608", "1609", "1612", "1617", "1605", "1615", "1616", "2009", "1504"] or has_kw(["重電", "電線電纜", "變壓器", "配電盤"], in_summary=False) or has_kw(["transformer", "switchgear", "heavy electrical", "power cable", "power distribution"]):
                main_cat, sub_cat = ("綠能、環保與化學工業", "重電與電線電纜")
            elif ticker_num in ["3081", "4979", "3234", "4908", "3163", "4977", "3363", "6426", "6442", "3450"] or has_kw(["光通訊", "光模組", "光收發", "光主動", "光被動"], in_summary=False) or has_kw(["optical communication", "optical transceiver", "fiber optic", "laser diode", "optical module"]):
                main_cat, sub_cat = ("通訊、線材與連接器", "光通訊與光模組")
                
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
                if ticker_num in ["2330", "2303", "5347", "6770"]:
                    main_cat, sub_cat = ("半導體產業", "晶圓代工 (Foundry)")
                elif ticker_num in ["3711", "2449", "6239", "6257", "3265", "3289", "8150", "6147", "3374", "6515", "3581", "3372", "8110", "2369", "6272", "3008"] or has_kw(["packaging", "semiconductor testing", "osat", "assembly service"]):
                    main_cat, sub_cat = ("半導體產業", "IC 封測 (OSAT)")
                elif ticker_num in ["2408", "2344", "2337", "3006", "5351", "2451", "3260", "8271", "4973", "8277"] or has_kw(["dram", "flash memory", "sram", "eeprom", "nor flash"]):
                    main_cat, sub_cat = ("半導體產業", "記憶體 (DRAM/Flash)")
                elif ticker_num in ["3680", "3131", "3583", "6187", "3413", "6683", "6510", "6532", "5434", "3587", "1560", "6196", "3653", "3055", "3580", "8064", "7728", "6937", "8091"] or has_kw(["semiconductor equipment", "photolithography", "etching", "chemical mechanical", "probe card", "lead frame"]):
                    main_cat, sub_cat = ("半導體與 PCB 設備/材料", "半導體設備與材料")
                elif ticker_num in ["2481", "5425", "8261", "6435", "3317", "6525", "3675", "2302", "7712", "6720", "8255"] or has_kw(["mosfet", "diode", "igbt", "rectifier", "power semiconductor"]):
                    main_cat, sub_cat = ("半導體產業", "功率半導體 (MOSFET/二極體)")
                elif ticker_num in ["3105", "8086", "4971", "2455", "3707", "3016", "3221"] or has_kw(["gallium arsenide", "gaas", "rf ic", "radio frequency"]):
                    main_cat, sub_cat = ("半導體產業", "化合物半導體與射頻晶片")
                elif has_kw(["design", "fabless", "asic", "chipset"]) or has_kw(["設計", "DESIGN", "晶片", "矽", "IC"], in_summary=False):
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
        
        if main_cat not in grouped:
            grouped[main_cat] = {}
        if sub_cat not in grouped[main_cat]:
            grouped[main_cat][sub_cat] = []
            
        grouped[main_cat][sub_cat].append((name, ticker))
        
    # 6. Generate Markdown Report
    print(f"Generating Master MD report: {REPORT_MD}")
    md_lines = [
        f"# 👑 全持股/觀測名單產業地圖大師版",
        f"此報告由 `classify_all_database.py` 自動生成。分析對象為 `{STOCK_LIST_FILE}` 中的所有個股，共計 **{len(details)}** 檔。\n",
        "## 📊 產業族群分類統計",
    ]
    
    cat_counts = {}
    for main_cat, sub_cats in grouped.items():
        cat_counts[main_cat] = sum(len(s_list) for s_list in sub_cats.values())
        
    for main_cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        md_lines.append(f"- **{main_cat}**：共 {count} 檔")
        
    md_lines.append("\n---\n")
    
    for main_cat in sorted(grouped.keys()):
        sub_cats = grouped[main_cat]
        total_in_cat = sum(len(s_list) for s_list in sub_cats.values())
        md_lines.append(f"## 📁 {main_cat}（共 {total_in_cat} 檔）\n")
        
        for sub_cat, stocks in sorted(sub_cats.items()):
            md_lines.append(f"### 🔍 {sub_cat}（{len(stocks)} 檔）")
            for name, ticker in sorted(stocks, key=lambda x: x[0]):
                md_lines.append(f"- **{name}** ({ticker})")
            md_lines.append("")
        md_lines.append("")
        
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
        
    # 7. Generate Master HTML Report
    print(f"Generating Master HTML report: {REPORT_HTML}")
    
    chart_bars = ""
    max_count = max(cat_counts.values()) if cat_counts else 1
    for main_cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        pct = (count / max_count) * 100
        chart_bars += f"""
        <div class="chart-row">
            <span class="chart-label">{main_cat}</span>
            <div class="chart-bar-container">
                <div class="chart-bar" style="width: {pct}%;"></div>
            </div>
            <span class="chart-value">{count} 檔</span>
        </div>
        """
        
    html_cards = ""
    for idx, main_cat in enumerate(sorted(grouped.keys())):
        sub_cats = grouped[main_cat]
        total_in_cat = sum(len(s_list) for s_list in sub_cats.values())
        
        sub_html = ""
        for sub_cat, stocks in sorted(sub_cats.items()):
            stock_li = "".join(f'<li><span class="stock-name">{name}</span> <span class="stock-ticker">{ticker}</span></li>' for name, ticker in sorted(stocks, key=lambda x: x[0]))
            sub_html += f"""
            <div class="sub-category">
                <div class="sub-header">🔍 {sub_cat} ({len(stocks)} 檔)</div>
                <ul class="stock-list">
                    {stock_li}
                </ul>
            </div>
            """
            
        html_cards += f"""
        <div class="card">
            <div class="card-header" onclick="toggleCard({idx})">
                <span class="card-title">📁 {main_cat}</span>
                <span class="badge">{total_in_cat} 檔</span>
            </div>
            <div class="card-body" id="card-body-{idx}">
                {sub_html}
            </div>
        </div>
        """

    html_template = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>👑 全持股/觀測名單全分類產業地圖</title>
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: #151f32;
            --border-color: #233554;
            --text-color: #e2e8f0;
            --text-muted: #8892b0;
            --primary: #64ffda;
            --accent: #57cbff;
            --font: 'Outfit', 'Inter', -apple-system, sans-serif;
        }}
        
        body {{
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: var(--font);
            margin: 0;
            padding: 2rem;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        header {{
            text-align: center;
            margin-bottom: 3rem;
        }}
        
        h1 {{
            font-size: 2.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, var(--primary), var(--accent));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}
        
        .subtitle {{
            color: var(--text-muted);
            font-size: 1.1rem;
        }}
        
        .chart-section {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 2rem;
            margin-bottom: 3rem;
            box-shadow: 0 10px 30px -15px rgba(2, 12, 27, 0.7);
        }}
        
        .chart-title {{
            font-size: 1.4rem;
            font-weight: 700;
            margin-bottom: 1.5rem;
            color: var(--primary);
            border-left: 4px solid var(--primary);
            padding-left: 0.8rem;
        }}
        
        .chart-row {{
            display: flex;
            align-items: center;
            margin-bottom: 0.8rem;
        }}
        
        .chart-label {{
            width: 280px;
            font-weight: 600;
            font-size: 0.95rem;
        }}
        
        .chart-bar-container {{
            flex-grow: 1;
            background-color: #1d2d44;
            height: 16px;
            border-radius: 8px;
            overflow: hidden;
            margin: 0 1.5rem;
        }}
        
        .chart-bar {{
            background: linear-gradient(90deg, var(--primary), var(--accent));
            height: 100%;
            border-radius: 8px;
        }}
        
        .chart-value {{
            width: 80px;
            text-align: right;
            font-weight: 700;
            color: var(--primary);
        }}
        
        .grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
        }}
        
        @media (max-width: 1024px) {{
            .grid {{
                grid-template-columns: 1fr;
            }}
            .chart-row {{
                flex-direction: column;
                align-items: flex-start;
            }}
            .chart-label {{
                width: 100%;
                margin-bottom: 0.3rem;
            }}
            .chart-bar-container {{
                margin: 0.3rem 0;
                width: 100%;
            }}
        }}
        
        .card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 10px 30px -15px rgba(2, 12, 27, 0.5);
            transition: all 0.35s ease;
        }}
        
        .card:hover {{
            transform: translateY(-3px);
            border-color: var(--primary);
        }}
        
        .card-header {{
            background-color: rgba(2, 12, 27, 0.3);
            padding: 1.3rem 1.8rem;
            font-weight: 700;
            font-size: 1.25rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            user-select: none;
            border-bottom: 1px solid var(--border-color);
        }}
        
        .card-title {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        
        .badge {{
            background-color: rgba(100, 255, 218, 0.1);
            color: var(--primary);
            font-size: 0.85rem;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 700;
            border: 1px solid rgba(100, 255, 218, 0.2);
        }}
        
        .card-body {{
            padding: 1.8rem;
            display: none; /* Default closed to keep it clean on start */
        }}
        
        .sub-category {{
            margin-bottom: 1.5rem;
            background-color: rgba(2, 12, 27, 0.2);
            padding: 1.2rem;
            border-radius: 8px;
            border-left: 3px solid var(--accent);
        }}
        
        .sub-category:last-child {{
            margin-bottom: 0;
        }}
        
        .sub-header {{
            font-weight: 700;
            font-size: 1.05rem;
            margin-bottom: 0.8rem;
            color: var(--accent);
        }}
        
        .stock-list {{
            list-style: none;
            padding: 0;
            margin: 0;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.5rem;
        }}
        
        @media (max-width: 600px) {{
            .stock-list {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .stock-list li {{
            display: flex;
            justify-content: space-between;
            background-color: rgba(2, 12, 27, 0.1);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 0.9rem;
            border: 1px solid transparent;
            transition: all 0.2s;
        }}
        
        .stock-list li:hover {{
            background-color: rgba(2, 12, 27, 0.4);
            border-color: rgba(100, 255, 218, 0.3);
        }}
        
        .stock-name {{
            font-weight: 600;
        }}
        
        .stock-ticker {{
            color: var(--text-muted);
            font-family: monospace;
        }}
        
        .btn-toggle-all {{
            margin-bottom: 1.5rem;
            background: transparent;
            border: 1px solid var(--primary);
            color: var(--primary);
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.9rem;
            transition: all 0.3s;
        }}
        
        .btn-toggle-all:hover {{
            background-color: rgba(100, 255, 218, 0.1);
        }}
    </style>
    <script>
        function toggleCard(idx) {{
            const body = document.getElementById('card-body-' + idx);
            if (body.style.display === 'block') {{
                body.style.display = 'none';
            }} else {{
                body.style.display = 'block';
            }}
        }}
        
        let allOpen = false;
        function toggleAll() {{
            allOpen = !allOpen;
            const bodies = document.querySelectorAll('.card-body');
            bodies.forEach(body => {{
                body.style.display = allOpen ? 'block' : 'none';
            }});
            document.getElementById('btn-toggle').innerText = allOpen ? '⚡ 全部摺疊 (Collapse All)' : '⚡ 全部展開 (Expand All)';
        }}
    </script>
</head>
<body>
    <div class="container">
        <header>
            <h1>👑 全持股/觀測名單全產業地圖大師版</h1>
            <div class="subtitle">分析時間: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | 共分類 {len(details)} 檔標的</div>
        </header>
        
        <!-- Summary Chart Section -->
        <section class="chart-section">
            <div class="chart-title">📊 全球/台股板塊分佈統計</div>
            {chart_bars}
        </section>
        
        <button id="btn-toggle" class="btn-toggle-all" onclick="toggleAll()">⚡ 全部展開 (Expand All)</button>
        
        <!-- Detailed Groups Grid -->
        <section class="grid">
            {html_cards}
        </section>
    </div>
</body>
</html>
"""
    with open(REPORT_HTML, "w", encoding="utf-8") as f:
        f.write(html_template)
        
    print("=" * 60)
    print("🎉 Pipeline Completed Successfully!")
    print(f"- Master Markdown Report: {REPORT_MD}")
    print(f"- Master HTML Report: {REPORT_HTML}")
    print("=" * 60)

if __name__ == "__main__":
    run_pipeline()
