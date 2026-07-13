# 🏆 雙軸多週期產業板塊資金地圖 (Double-axis Sector Map)

這是一個專為台股交易者設計的**視覺化產業板塊資金地圖與監控看板**。它可以自動獲取台股 1970+ 檔上市櫃個股的最新收盤數據，計算 1 日、5 日、10 日的多週期產業平均漲跌幅，並透過一個極度精美的網頁互動看板呈現。

---

## 🌟 核心亮點功能

### 1. 📊 頂級 ECharts 互動式產業板塊樹狀圖 (Treemap)
* 採用市值（Market Cap）決定方塊大小，漲跌幅決定方塊顏色（翠綠/暗灰/亮紅）。
* **支援滾輪縮放與拖曳 (Zoom & Pan)**：可使用滑鼠滾輪或觸控板捏合手勢放大/縮小，並拖曳平移地圖。
* **支援層級下鑽 (Drill-down)**：單擊任何產業的標題，會平滑放大該產業區塊，展開底下所有個股細節。
* **麵包屑導航 (Breadcrumbs)**：下方附帶高對比麵包屑，可一鍵點擊退回上層。

### 2. ⚡ 智慧批次分析連動 (Bulk Analysis)
* 支援直接貼上 TradingView 或看盤軟體的選股清單（包含代號、中文名、單價、評級等雜亂數據）。
* **噪音字詞自動過濾**：自動排除單字母、浮點數、百分比，以及貨幣、產業、評級等欄位噪音。
* **Treemap 動態過濾連動**：批次分析後，整個 Treemap 會動態收縮，**僅顯示名單內個股的產業結構與漲跌幅**，且會**重新計算該清單專屬的產業平均漲幅**。清空後則立即還原。

### 3. 🎯 高保真（High-fidelity）台股產業分類體系
* 將全台股 1970+ 檔股票拆解為 20 個大產業、近 100 個精細的次產業。
* 經過嚴格校正，完美區分矽晶圓代工（僅限台積電、聯電、世界、力積電）與化合物半導體/砷化鎵（全新、穩懋、漢磊等），並新增獨立的【生技醫療 - 美容保養與醫美】板塊。

---

## ⚙️ 安裝與安裝依賴

本專案只需安裝三個核心 Python 套件：

```bash
pip install -r requirements.txt
```

---

## 🚀 如何使用

### 1. 執行更新並編譯看板
在專案資料夾下執行：
```bash
python track_daily_performance.py
```
這會自動：
1. 從證交所與 yfinance 下載台股最新行情。
2. 進行大數據產業分類與多週期漲跌計算。
3. 生成 `daily_sector_performance.html`（互動網頁看板）與 `daily_sector_performance.md`（文字報告）。

### 2. 💡 懶人一鍵啟動 (Windows)
您只需在 Windows 檔案總管中**按兩下執行 `run_tracker.bat`**，它會自動完成數據更新，並立即在您的預設瀏覽器中打開最新的資金地圖網頁！

---

## 📂 專案檔案結構說明

* `track_daily_performance.py`: 看板生成的主控程序（包含網頁範本與資料下載）。
* `classify_all_database.py`: 核心大數據分類與特徵比對引擎。
* `industry_cache.json`: 台股 1970+ 檔股票的基本面與產業簡介快取，避免重複下載。
* `run_tracker.bat`: 一鍵更新並開啟網頁看板的批次檔。
* `daily_sector_performance.html`: 編譯出來的動態資金地圖網頁（可直接用瀏覽器打開）。
* `app.py`: Streamlit 雲端網頁進入點。

---

## 🌐 雲端網頁部署 (Streamlit Cloud)

本專案已全面支援 Streamlit 雲端部署，讓您可以在瀏覽器上直接查看並手動點擊按鈕更新台股產業數據。

### 1. 本地預覽
在專案根目錄下執行：
```bash
streamlit run app.py
```

### 2. ⚠️ 上傳 GitHub 的完整檔案清單
要成功在 Streamlit Community Cloud 上執行，**僅上傳 `app.py` 和 `requirements.txt` 是不夠的**。請務必將以下檔案全部上傳到您的 GitHub 儲存庫：

* `app.py` (主程式網頁框架)
* `requirements.txt` (套件清單)
* `track_daily_performance.py` (下載行情與計算板塊資料的主程式)
* `classify_all_database.py` (台股個股產業分類定義檔)
* `stocks_list.txt` (要追蹤的個股代碼名單)
* `industry_cache.json` (基本面與產業資料快取檔 - ⚠️ **此檔案極為重要，可避免雲端下載過多股票資訊而導致運行超時！**)

