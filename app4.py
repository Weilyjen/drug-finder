import streamlit as st
import pandas as pd
import requests
import time
import smtplib
from email.mime.text import MIMEText
import random

# ==========================================
# 1. 設定區 (Secrets)
# ==========================================
try:
    CODA_API_KEY = st.secrets["CODA_API_KEY"]
    DOC_ID = st.secrets["DOC_ID"]
    MAIL_ACCOUNT = st.secrets["MAIL_ACCOUNT"]
    MAIL_PASSWORD = st.secrets["MAIL_PASSWORD"]
except:
    st.error("設定檔讀取失敗！請檢查 .streamlit/secrets.toml 或雲端 Secrets 設定。")
    st.stop()

# 表格 ID
TABLE_ID_DRUGS = 'DB_Drugs'
TABLE_ID_REQUESTS = 'DB_Requests'
TABLE_ID_CITIES = 'DB_Cities'
TABLE_ID_INBOX = 'DB_Supply_Inbox'
TABLE_ID_INVENTORY = 'DB_Inventory'
TABLE_ID_FEEDBACK = 'DB_Feedback'

headers = {'Authorization': f'Bearer {CODA_API_KEY}'}

# ==========================================
# 2. 核心函式 (定義區)
# ==========================================

@st.cache_data(ttl=60)
def load_drugs_data():
    """讀取藥品清單 (用於下拉選單)"""
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
            })
        return pd.DataFrame(rows)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_cities_data():
    """讀取縣市清單 (回傳由北到南排序好的列表)"""
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_CITIES}/rows?useColumnNames=true'
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        items = data['items']
        # 依照 Coda 裡的 index 排序 (由北到南)
        items.sort(key=lambda x: x['index'])
        return [item['name'] for item in items]
    except:
        return []

@st.cache_data(ttl=10)
def load_requests_raw():
    """讀取許願池原始資料 (用於 Tab 3 排行榜)"""
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_REQUESTS}/rows?useColumnNames=true&limit=1000'
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        rows = []
        for item in data['items']:
            vals = item['values']
            rows.append({
                "想要藥品": vals.get("想要藥品", ""), 
                "所在縣市": vals.get("所在縣市", ""),
            })
        return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"讀取許願池失敗: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=30)
def load_inventory_data():
    """讀取庫存資料 (用於 Tab 4 找藥)"""
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_INVENTORY}/rows?useColumnNames=true'
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        rows = []
        for item in data['items']:
            vals = item['values']
            # [重點修正] 優先抓取 '縣市1' (新截圖中的欄位)，若無則抓 '縣市'
            city_val = vals.get("縣市1", vals.get("縣市", ""))
            
            rows.append({
                "診所名稱": vals.get("診所", ""), 
                "機構代碼": vals.get("機構代碼", ""), 
                "藥品名稱": vals.get("藥品", ""),
                "縣市": city_val,  
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
    """發送驗證信"""
    subject = "【藥品特搜網】身分驗證碼"
    body = f"您的驗證碼為：{code}\n\n請在網頁上輸入此代碼以完成操作。\n感謝您的使用！"
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = MAIL_ACCOUNT
    msg['To'] = to_email
    try:
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
    """寫入許願"""
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_REQUESTS}/rows'
    payload = {"rows": [{"cells": [{"column": "許願者Email", "value": email}, {"column": "所在縣市", "value": region}, {"column": "想要藥品", "value": drug_name}]}]}
    try: requests.post(url, headers=headers, json=payload).raise_for_status(); return True
    except: return False

def submit_supply(code, name, region, drug_name, conditions, email):
    """寫入診所回報"""
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_INBOX}/rows'
    payload = {"rows": [{"cells": [{"column": "機構代碼", "value": code}, {"column": "診所名稱", "value": name}, {"column": "所在縣市", "value": region}, {"column": "提供藥品", "value": drug_name}, {"column": "給付條件", "value": conditions}, {"column": "聯絡Email", "value": email}]}]}
    try: requests.post(url, headers=headers, json=payload).raise_for_status(); return True
    except: return False

def submit_feedback(code, drug, email, feedback_type, comment):
    """寫入民眾回饋"""
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_FEEDBACK}/rows'
    payload = {"rows": [{"cells": [{"column": "機構代碼", "value": code}, {"column": "藥品名稱", "value": drug}, {"column": "回饋類型", "value": feedback_type}, {"column": "民眾Email", "value": email}, {"column": "備註", "value": comment}]}]}
    try: requests.post(url, headers=headers, json=payload).raise_for_status(); return True
    except Exception as e: st.error(f"回饋失敗: {e}"); return False

# ==========================================
# 3. App 介面 (執行區)
# ==========================================

st.set_page_config(page_title="全台缺藥特搜網", page_icon="💊")
st.title("💊 全台缺藥特搜網")

df_drugs = load_drugs_data()
cities_list = load_cities_data()
df_inventory = load_inventory_data()

if df_drugs.empty:
    st.error("無法連接資料庫")
    st.stop()

tab1, tab2, tab3, tab4 = st.tabs(["📢 民眾許願", "🏥 診所回報供貨", "📊 熱度排行榜", "🔍 找哪裡有藥"])

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
                st.cache_data.clear()

# --- Tab 2: 診所回報 ---
with tab2:
    st.markdown("#### 我是醫事機構，我有藥！")
    st.info("💡 初次填寫需驗證 Email。")

    if "is_verified" not in st.session_state: st.session_state.is_verified = False
    if "verify_code" not in st.session_state: st.session_state.verify_code = None
    if "email_input" not in st.session_state: st.session_state.email_input = ""

    if not st.session_state.is_verified:
        with st.container(border=True):
            st.subheader("🔐 身分驗證")
            email_input = st.text_input("診所 Email")
            c1, c2 = st.columns([1, 2])
            with c1:
                if st.button("寄送驗證碼"):
                    if email_input:
                        code = str(random.randint(100000, 999999))
                        st.session_state.verify_code = code
                        st.session_state.email_input = email_input
                        with st.spinner("寄信中..."):
                            if send_verification_email(email_input, code): st.success("已寄出")
            with c2:
                user_code = st.text_input("輸入驗證碼", max_chars=6)
                if st.button("確認"):
                    if user_code == st.session_state.verify_code:
                        st.session_state.is_verified = True
                        st.rerun()
                    else: st.error("錯誤")
    else:
        st.success(f"已驗證：{st.session_state.email_input}")
        with st.container(border=True):
            st.subheader("📋 填寫供貨資訊")
            col1, col2 = st.columns(2)
            with col1:
                c_code = st.text_input("機構代碼", max_chars=10)
                c_name = st.text_input("診所名稱")
            with col2:
                c_email = st.text_input("Email", value=st.session_state.email_input, disabled=True)
                c_region = st.selectbox("縣市", cities_list, key="c_city_v")
            c_drug = st.selectbox("藥品", df_drugs["藥品名稱"].tolist(), key="c_drug_v")
            c_conditions = st.multiselect("給付條件", ["健保", "自費", "國健署專案"])
            if st.button("📤 提交", type="primary"):
                if submit_supply(c_code, c_name, c_region, c_drug, c_conditions, c_email):
                    st.success("提交成功，待審核。")

# --- Tab 3: 排行榜 ---
with tab3:
    st.markdown("### 🔥 缺藥熱度排行榜 (即時統計)")
    if st.button("🔄 刷新數據"):
        st.cache_data.clear(); st.rerun()
    
    df_raw_requests = load_requests_raw()
    
    if not df_raw_requests.empty:
        df_detailed = df_raw_requests.groupby(["想要藥品", "所在縣市"]).size().reset_index(name="人次")
        df_detailed = df_detailed.sort_values(by="人次", ascending=False)
        
        df_chart = df_raw_requests.groupby("想要藥品").size().reset_index(name="總人次")
        df_chart = df_chart.sort_values(by="總人次", ascending=False).head(10)
        
        st.caption("全台總熱度 Top 10")
        st.bar_chart(df_chart.set_index("想要藥品")["總人次"])
        st.markdown("#### 📋 詳細數據")
        st.dataframe(df_detailed, column_config={"想要藥品":"藥品名稱","所在縣市":"區域","人次":st.column_config.NumberColumn("許願人次", format="%d")}, hide_index=True, width='stretch')
    else:
        st.info("尚無許願資料")

# --- Tab 4: 找藥 (改版：直接顯示庫存列表 + 排序) ---
with tab4:
    st.markdown("### 🔍 藥品供貨清單")
    
    col_s1, col_s2 = st.columns(2)
    # 增加 "全部" 選項，方便使用者瀏覽
    with col_s1: search_drug = st.selectbox("藥品篩選", ["全部"] + df_drugs["藥品名稱"].tolist(), key="sd")
    with col_s2: search_city = st.selectbox("縣市篩選", ["全台灣"] + cities_list, key="sc")

    if not df_inventory.empty:
        # 1. 先做基本過濾：必須有貨 + 必須上架
        res = df_inventory[(df_inventory["庫存狀態"]=="有貨") & (df_inventory["是否上架"]==True)].copy()

        # 2. 套用使用者篩選
        if search_drug != "全部":
            res = res[res["藥品名稱"] == search_drug]
        if search_city != "全台灣":
            res = res[res["縣市"] == search_city]

        # 3. [關鍵邏輯] 排序：先藥品，再縣市 (依照 DB_Cities 由北到南順序)
        # 建立縣市排序的類別 (Categorical)
        res['縣市'] = pd.Categorical(res['縣市'], categories=cities_list, ordered=True)
        # 執行排序
        res = res.sort_values(by=["藥品名稱", "縣市"])

        # 4. 顯示結果
        if res.empty:
            st.warning(f"目前條件下尚無庫存資料。")
        else:
            st.success(f"共找到 {len(res)} 筆供貨資訊")
            
            # 使用迴圈顯示卡片 (保留了您需要的回饋功能)
            for idx, row in res.iterrows():
                cid = f"{row['診所名稱']}_{idx}"
                with st.container(border=True):
                    # 標題顯示：藥品 - 診所
                    st.markdown(f"#### 💊 {row['藥品名稱']}  |  🏥 {row['診所名稱']}")
                    
                    # 內容：縣市 + 給付條件
                    conds = row['給付條件']
                    cond_str = "  |  ".join([f"`{c}`" for c in conds]) if isinstance(conds, list) else f"`{conds}`"
                    
                    st.markdown(f"📍 **{row['縣市']}**")
                    st.markdown(f"🏷️ 給付條件：{cond_str}")
                    
                    if row['備註']: st.info(f"備註: {row['備註']}")
                    
                    # 認證與回報功能 (維持不變)
                    with st.expander("💬 認證 / 回報"):
                        v_key, c_key, e_key = f"vs_{cid}", f"vc_{cid}", f"ve_{cid}"
                        if v_key not in st.session_state: st.session_state[v_key] = False
                        
                        if not st.session_state[v_key]:
                            umail = st.text_input("Email", key=f"em_{cid}")
                            b1, b2 = st.columns([1,2])
                            with b1:
                                if st.button("寄碼", key=f"bs_{cid}"):
                                    code = str(random.randint(100000,999999))
                                    st.session_state[c_key], st.session_state[e_key] = code, umail
                                    send_verification_email(umail, code)
                                    st.toast("已寄出")
                            with b2:
                                ucode = st.text_input("驗證碼", max_chars=6, key=f"cd_{cid}")
                                if st.button("驗證", key=f"bv_{cid}"):
                                    if ucode == st.session_state.get(c_key):
                                        st.session_state[v_key] = True
                                        st.rerun()
                        else:
                            st.success("已驗證")
                            fb_type = st.radio("類型", ["✅ 認證有貨", "⚠️ 資訊不實"], key=f"ft_{cid}")
                            cmmt = st.text_area("說明", key=f"cm_{cid}")
                            if st.button("送出", key=f"sub_{cid}"):
                                t_code = row.get('機構代碼', row['診所名稱'])
                                if submit_feedback(t_code, row['藥品名稱'], st.session_state[e_key], fb_type, cmmt):
                                    st.success("感謝回報")
    else:
        st.info("資料庫讀取中...")
