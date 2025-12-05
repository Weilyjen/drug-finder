import streamlit as st
import pandas as pd
import requests
import time
import smtplib
from email.mime.text import MIMEText
import random

# ==========================================
# 1. 設定區 (改用 Secrets 讀取，更安全)
# ==========================================
# 這裡不再直接寫死 Key，而是叫 Python 去「保險箱」拿

try:
    CODA_API_KEY = st.secrets["CODA_API_KEY"]
    DOC_ID = st.secrets["DOC_ID"]
    # 讀取郵件設定
    MAIL_ACCOUNT = st.secrets["MAIL_ACCOUNT"]
    MAIL_PASSWORD = st.secrets["MAIL_PASSWORD"]

except:
    st.error("設定檔讀取失敗！請檢查 .streamlit/secrets.toml")
    st.stop()
    

# 表格 ID (請確認 Coda 裡的名稱一致)
TABLE_ID_DRUGS = 'DB_Drugs'
TABLE_ID_REQUESTS = 'DB_Requests'
TABLE_ID_CITIES = 'DB_Cities'
TABLE_ID_INBOX = 'DB_Supply_Inbox'
TABLE_ID_INVENTORY = 'DB_Inventory'

headers = {'Authorization': f'Bearer {CODA_API_KEY}'}

# ==========================================
# 2. 核心函式
# ==========================================

@st.cache_data(ttl=60)
def load_drugs_data():
    """讀取藥品清單"""
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_DRUGS}/rows?useColumnNames=true'
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        rows = []
        for item in data['items']:
            vals = item['values']
            rows.append({
                "藥品名稱": vals.get("藥品名稱", "未知"), 
                "分類": vals.get("藥品分類", ""),
                "許願人數": vals.get("許願人數", 0),
                "供貨診所數": vals.get("供貨診所數", 0)
            })
        return pd.DataFrame(rows)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_cities_data():
    """讀取縣市清單"""
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_CITIES}/rows?useColumnNames=true'
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        items = data['items']
        items.sort(key=lambda x: x['index'])
        return [item['name'] for item in items]
    except:
        return []

@st.cache_data(ttl=30) # 庫存變動快，縮短快取時間
def load_inventory_data():
    """讀取庫存資料 (包含新的 '縣市' 欄位)"""
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_INVENTORY}/rows?useColumnNames=true'
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        rows = []
        for item in data['items']:
            vals = item['values']
            rows.append({
                "診所名稱": vals.get("診所", ""), # 這裡抓到的是 Display Name
                "藥品名稱": vals.get("藥品", ""),
                "縣市": vals.get("縣市", ""), # <--- 這是剛剛在 Coda 新增的欄位！
                "庫存狀態": vals.get("庫存狀態", ""),
                "給付條件": vals.get("給付條件", ""),
                "是否上架": vals.get("是否上架", False),
                "備註": vals.get("備註", "") 
            })
        return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"讀取庫存失敗: {e}")
        return pd.DataFrame()

def send_verification_email(to_email, code):
    """發送驗證碼郵件"""
    subject = "【藥品特搜網】診所身分驗證碼"
    body = f"親愛的醫事人員您好：\n\n您的驗證碼為：{code}\n\n請在網頁上輸入此代碼以完成藥品庫存回報。\n感謝您的貢獻！"
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = MAIL_ACCOUNT
    msg['To'] = to_email

    try:
        # 連接 Gmail SMTP Server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(MAIL_ACCOUNT, MAIL_PASSWORD)
        server.sendmail(MAIL_ACCOUNT, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"寄信失敗: {e}")
        return False

def submit_wish(email, region, drug_name):
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_REQUESTS}/rows'
    payload = {"rows": [{"cells": [
        {"column": "許願者Email", "value": email},
        {"column": "所在縣市", "value": region},
        {"column": "想要藥品", "value": drug_name},
    ]}]}
    try:
        requests.post(url, headers=headers, json=payload).raise_for_status()
        return True
    except: return False

def submit_supply(code, name, region, drug_name, conditions, email):
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_INBOX}/rows'
    payload = {"rows": [{"cells": [
        {"column": "機構代碼", "value": code},
        {"column": "診所名稱", "value": name},
        {"column": "所在縣市", "value": region},
        {"column": "提供藥品", "value": drug_name},
        {"column": "給付條件", "value": conditions},
        {"column": "聯絡Email", "value": email},
    ]}]}
    try:
        requests.post(url, headers=headers, json=payload).raise_for_status()
        return True
    except: return False

# ==========================================
# 3. App 介面
# ==========================================

st.set_page_config(page_title="全台缺藥特搜網", page_icon="💊")
st.title("💊 全台缺藥特搜網")

df_drugs = load_drugs_data()
cities_list = load_cities_data()
df_inventory = load_inventory_data()

if df_drugs.empty:
    st.error("無法連接資料庫")
    st.stop()

tab1, tab2, tab3, tab4 = st.tabs(["📢 民眾許願", "🏥 診所供貨", "📊 排行榜", "🔍 找哪裡有藥"])

# --- Tab 1: 民眾許願 ---
with tab1:
    st.markdown("#### 找不到藥嗎？請填寫需求")
    with st.form("wish_form"):
        u_email = st.text_input("您的 Email", placeholder="name@example.com")
        u_region = st.selectbox("所在縣市", cities_list) if cities_list else st.text_input("縣市")
        u_drug = st.selectbox("想找什麼藥？", df_drugs["藥品名稱"].tolist())
        if st.form_submit_button("🚀 送出許願"):
            if submit_wish(u_email, u_region, u_drug):
                st.success(f"已記錄！")
                with st.spinner("更新排行榜..."):
                    time.sleep(2)
                    st.cache_data.clear()

# ==========================================
# [重點修改] Tab 2: 診所回報 (加入驗證邏輯)
# ==========================================
with tab2:
    st.markdown("#### 我是醫事機構，我有藥！")
    st.info("💡 為確保資訊正確，初次填寫需驗證 Email。")

    # 使用 session_state 來記住使用者的驗證狀態
    # 這樣網頁重新整理時，才不會忘記他已經驗證過了
    if "is_verified" not in st.session_state:
        st.session_state.is_verified = False
    if "verify_code" not in st.session_state:
        st.session_state.verify_code = None
    if "email_input" not in st.session_state:
        st.session_state.email_input = ""

    # === 第一階段：驗證 Email ===
    if not st.session_state.is_verified:
        with st.container(border=True):
            st.subheader("🔐 步驟 1：身分驗證")
            email_input = st.text_input("請輸入診所公務信箱", placeholder="clinic@example.com")
            
            col_v1, col_v2 = st.columns([1, 2])
            
            # 發送按鈕
            with col_v1:
                if st.button("寄送驗證碼"):
                    if not email_input:
                        st.error("請輸入 Email")
                    else:
                        # 產生 6 位數亂碼
                        code = str(random.randint(100000, 999999))
                        st.session_state.verify_code = code
                        st.session_state.email_input = email_input # 鎖定這個 Email
                        
                        with st.spinner("寄信中..."):
                            if send_verification_email(email_input, code):
                                st.success("✅ 驗證碼已寄出，請檢查信箱！")
                            else:
                                st.error("❌ 寄信失敗，請確認 Email 格式或稍後再試。")
            
            # 輸入驗證碼
            with col_v2:
                user_code = st.text_input("輸入 6 位數驗證碼", max_chars=6)
                if st.button("確認驗證"):
                    if user_code == st.session_state.verify_code and user_code is not None:
                        st.session_state.is_verified = True
                        st.success("🎉 驗證成功！請填寫供貨資訊。")
                        st.rerun() # 重新整理畫面，進入第二階段
                    else:
                        st.error("驗證碼錯誤，請重新輸入。")

    # === 第二階段：填寫資料 (只有驗證通過才會顯示) ===
    else:
        st.success(f"✅ 已驗證身分：{st.session_state.email_input}")
        
        # 這裡不使用 st.form，因為 form 裡面不能再有互動按鈕，我們直接用一般 input
        with st.container(border=True):
            st.subheader("📋 步驟 2：填寫供貨資訊")
            
            col1, col2 = st.columns(2)
            with col1:
                c_code = st.text_input("機構代碼 (必填)", max_chars=10)
                c_name = st.text_input("診所名稱 (必填)")
            with col2:
                # 自動帶入剛剛驗證過的 Email，並設為唯讀 (disabled)
                c_email = st.text_input("聯絡 Email", value=st.session_state.email_input, disabled=True)
                c_region = st.selectbox("診所所在縣市", cities_list, key="c_city_verified")
                
            st.markdown("---")
            c_drug = st.selectbox("目前有貨的藥品", df_drugs["藥品名稱"].tolist(), key="c_drug_verified")
            
            c_conditions = st.multiselect(
                "給付條件 (可多選)",
                ["健保", "自費", "國健署專案"]
            )
            
            if st.button("📤 提交供貨資訊", type="primary"):
                if not c_code or not c_name:
                    st.error("請填寫機構代碼與名稱！")
                else:
                    with st.spinner("正在提交審核..."):
                        if submit_supply(c_code, c_name, c_region, c_drug, c_conditions, c_email):
                            st.success("✅ 提交成功！感謝您為台灣醫療貢獻心力。")
                            st.balloons()
                            # 提交後可以選擇是否重置驗證狀態，這裡我們先保留，方便他繼續填下一筆藥


# --- Tab 3: 排行榜 ---
with tab3:
    st.markdown("### 🔥 缺藥熱度排行榜")
    if st.button("🔄 刷新"):
        st.cache_data.clear()
        st.rerun()
    df_sorted = df_drugs.sort_values(by="許願人數", ascending=False).head(10)
    st.bar_chart(df_sorted.set_index("藥品名稱")["許願人數"])
    st.dataframe(df_sorted[["藥品名稱", "分類", "許願人數", "供貨診所數"]], hide_index=True, width='stretch')

# --- Tab 4: 找藥 (完整邏輯) ---
with tab4:
    st.markdown("### 🔍 查詢哪裡有藥")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        search_drug = st.selectbox("請選擇藥品", df_drugs["藥品名稱"].tolist(), key="search_drug")
    with col_s2:
        search_city = st.selectbox("請選擇縣市", ["全台灣"] + cities_list, key="search_city")

    if not df_inventory.empty:
        # 1. 篩選藥品
        result = df_inventory[df_inventory["藥品名稱"] == search_drug]
        
        # 2. 篩選是否有上架
        result = result[result["是否上架"] == True]
        
        # 3. 篩選是否有貨
        result = result[result["庫存狀態"] != "缺貨"]
        
        # 4. 篩選縣市 (關鍵修正)
        if search_city != "全台灣":
            result = result[result["縣市"] == search_city]
        
        if result.empty:
            st.warning(f"目前 **{search_city}** 尚未有診所回報 **{search_drug}** 的庫存。")
        else:
            st.success(f"找到 {len(result)} 間診所有貨！")
            
            for index, row in result.iterrows():
                with st.container(border=True):
                    # 標題區：診所名稱
                    st.markdown(f"#### 🏥 {row['診所名稱']}")
                    
                    # 標籤區：給付條件
                    conditions = row['給付條件']
                    # 處理 Coda 可能回傳 string 或 list 的狀況
                    if isinstance(conditions, list):
                        tags = "  |  ".join([f"`{c}`" for c in conditions])
                        st.markdown(tags)
                    else:
                        st.markdown(f"`{conditions}`")
                        
                    st.text(f"📍 地點：{row['縣市']}")
                    
                    if row['備註']:
                        st.info(f"💡 備註：{row['備註']}")
    else:
        st.info("資料庫讀取中或尚無資料...")