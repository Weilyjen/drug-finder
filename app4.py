import streamlit as st
import pandas as pd
import requests
import time
import smtplib
from email.mime.text import MIMEText
import random

# ==========================================
# 1. 設定區
# ==========================================
try:
    CODA_API_KEY = st.secrets["CODA_API_KEY"]
    DOC_ID = st.secrets["DOC_ID"]
    MAIL_ACCOUNT = st.secrets["MAIL_ACCOUNT"]
    MAIL_PASSWORD = st.secrets["MAIL_PASSWORD"]
except:
    st.error("設定檔讀取失敗！")
    st.stop()

TABLE_ID_DRUGS = 'DB_Drugs'
TABLE_ID_REQUESTS = 'DB_Requests'
TABLE_ID_CITIES = 'DB_Cities'
TABLE_ID_INBOX = 'DB_Supply_Inbox'
TABLE_ID_INVENTORY = 'DB_Inventory'
TABLE_ID_FEEDBACK = 'DB_Feedback'
TABLE_ID_WISHLIST = 'DB_Wishlist'

headers = {'Authorization': f'Bearer {CODA_API_KEY}'}

# ==========================================
# 2. 核心函式
# ==========================================

@st.cache_data(ttl=60)
def load_drugs_data():
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_DRUGS}/rows?useColumnNames=true'
    try:
        r = requests.get(url, headers=headers); r.raise_for_status(); data = r.json()
        return pd.DataFrame([{'藥品名稱':i['values'].get('藥品名稱',''), '分類':i['values'].get('藥品分類','未分類')} for i in data['items']])
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_cities_data():
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_CITIES}/rows?useColumnNames=true'
    try:
        r = requests.get(url, headers=headers); r.raise_for_status(); data = r.json(); items = data['items']; items.sort(key=lambda x: x['index'])
        return [i['name'] for i in items]
    except: return []

@st.cache_data(ttl=10)
def load_requests_raw():
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_REQUESTS}/rows?useColumnNames=true&limit=1000'
    try:
        r = requests.get(url, headers=headers); r.raise_for_status(); data = r.json()
        return pd.DataFrame([{'想要藥品':i['values'].get('想要藥品',''), '所在縣市':i['values'].get('所在縣市','')} for i in data['items']])
    except: return pd.DataFrame()

@st.cache_data(ttl=10)
def load_wishlist_data():
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_WISHLIST}/rows?useColumnNames=true&limit=100'
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        # 抓取我們需要的欄位：建議藥名、狀態
        return pd.DataFrame([
            {
                '建議藥名': i['values'].get('建議藥名', ''),
                '狀態': i['values'].get('狀態', ''),
                '許願者Email': i['values'].get('許願者Email', '')
            } 
            for i in data['items']
        ])
    except:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def load_inventory_data():
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_INVENTORY}/rows?useColumnNames=true'
    try:
        r = requests.get(url, headers=headers); r.raise_for_status(); data = r.json()
        return pd.DataFrame([{'診所名稱':i['values'].get('診所',''), '機構代碼':i['values'].get('機構代碼',''), '藥品名稱':i['values'].get('藥品',''), '縣市':i['values'].get('縣市1', i['values'].get('縣市','')), '庫存狀態':i['values'].get('庫存狀態',''), '給付條件':i['values'].get('給付條件',''), '是否上架':i['values'].get('是否上架',False), '備註':i['values'].get('備註','')} for i in data['items']])
    except: return pd.DataFrame()

@st.cache_data(ttl=5) 
def load_feedback_data():
    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_FEEDBACK}/rows?useColumnNames=true&limit=500'
    try:
        r = requests.get(url, headers=headers); r.raise_for_status(); data = r.json()
        # [修正點] 這裡定義的 key 是 '時間'
        return pd.DataFrame([{'機構代碼':i['values'].get('機構代碼',''), '藥品名稱':i['values'].get('藥品名稱',''), '回饋類型':i['values'].get('回饋類型',''), '備註':i['values'].get('備註',''), '時間':i['values'].get('回報時間','')} for i in data['items']])
    except: return pd.DataFrame()

def send_verification_email(to_email, code):
    msg = MIMEText(f"驗證碼：{code}"); msg['Subject']="【藥品特搜網】驗證碼"; msg['From']=MAIL_ACCOUNT; msg['To']=to_email
    try:
        s = smtplib.SMTP('smtp.gmail.com', 587); s.starttls(); s.login(MAIL_ACCOUNT, MAIL_PASSWORD); s.sendmail(MAIL_ACCOUNT, to_email, msg.as_string()); s.quit(); return True
    except: return False

def submit_wish(email, region, drug):
    url=f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_REQUESTS}/rows'
    payload={"rows":[{"cells":[{"column":"許願者Email","value":email},{"column":"所在縣市","value":region},{"column":"想要藥品","value":drug}]}]}
    try: requests.post(url, headers=headers, json=payload).raise_for_status(); return True
    except: return False

def submit_raw_wish(email, region, new_drug_name):
    """
    寫入 DB_Wishlist (除錯模式：會顯示詳細錯誤)
    """
    # 1. 檢查變數是否定義
    if 'TABLE_ID_WISHLIST' not in globals():
        st.error("❌ 程式碼缺少變數設定！請在最上方加入： TABLE_ID_WISHLIST = 'DB_Wishlist'")
        return False

    url = f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_WISHLIST}/rows'
    
    payload = {
        "rows": [
            {
                "cells": [
                    {"column": "許願者Email", "value": str(email)},
                    {"column": "所在縣市", "value": str(region)},
                    {"column": "建議藥名", "value": str(new_drug_name)},
                    {"column": "狀態", "value": "待處理"} 
                ]
            }
        ]
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload)
        r.raise_for_status() # 如果失敗，會跳到 except
        return True
        
    except Exception as e:
        st.error(f"❌ 寫入失敗！原因：{e}")
        # 如果有 Coda 的回傳訊息，也印出來 (通常會告訴你哪個欄位錯了)
        if 'r' in locals():
            st.code(r.text, language='json')
        return False

def submit_supply(code, name, region, drug, conds, email):
    url=f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_INBOX}/rows'
    payload={"rows":[{"cells":[{"column":"機構代碼","value":code},{"column":"診所名稱","value":name},{"column":"所在縣市","value":region},{"column":"提供藥品","value":drug},{"column":"給付條件","value":conds},{"column":"聯絡Email","value":email}]}]}
    try: requests.post(url, headers=headers, json=payload).raise_for_status(); return True
    except: return False

def submit_feedback(code, drug, email, type, comment):
    url=f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID_FEEDBACK}/rows'
    payload={"rows":[{"cells":[{"column":"機構代碼","value":code},{"column":"藥品名稱","value":drug},{"column":"回饋類型","value":type},{"column":"民眾Email","value":email},{"column":"備註","value":comment}]}]}
    try: requests.post(url, headers=headers, json=payload).raise_for_status(); return True
    except: return False

# ==========================================
# 3. App 介面
# ==========================================

st.set_page_config(page_title="全台缺藥特搜網", page_icon="💊")
st.title("💊 全台缺藥特搜網")

if 'current_tab' not in st.session_state:
    st.session_state.current_tab = "🔍 找哪裡有藥"

selected_tab = st.radio(
    "", 
    ["🔍 找哪裡有藥", "📢 民眾許願", "🏥 診所回報供貨", "📊 熱度排行榜"], 
    horizontal=True,
    label_visibility="collapsed",
    key="nav_radio",
    index=["🔍 找哪裡有藥", "📢 民眾許願", "🏥 診所回報供貨", "📊 熱度排行榜"].index(st.session_state.current_tab)
)

if selected_tab != st.session_state.current_tab:
    st.session_state.current_tab = selected_tab

df_drugs = load_drugs_data()
cities_list = load_cities_data()
df_inventory = load_inventory_data()
df_feedback = load_feedback_data()

if df_drugs.empty: st.stop()

# ==========================================
# Tab 1: 民眾許願 (最終版：支援 Relation 與 Wishlist 分流)
# ==========================================
if selected_tab == "📢 民眾許願":
    st.markdown("### 🎋 許願池 & 缺藥排行")

    # 讀取現有計票
    df_req = load_requests_raw()
    
    # 統計排行榜
    if not df_req.empty and "想要藥品" in df_req.columns:
        rank_df = df_req["想要藥品"].value_counts().reset_index()
        rank_df.columns = ["想要藥品", "人次"]
    else:
        rank_df = pd.DataFrame(columns=["想要藥品", "人次"])

    # --- 新增許願 / 推薦新藥區塊 ---
    with st.expander("➕ 找不到不在榜上的藥？點此發起新許願", expanded=False):
        with st.form("wish_form"):
            st.write("填寫新藥品需求：")
            u_email = st.text_input("Email (選填)", placeholder="name@example.com")
            
            # 縣市選擇 (對應 DB_Cities Relation)
            if cities_list:
                u_region = st.selectbox("您的縣市", cities_list)
            else:
                u_region = st.text_input("您的縣市")
            
            st.markdown("---")
            st.caption("請選擇藥品，若清單中沒有，請選「其他」並手動輸入")
            
            # 藥品選單
            drug_options = ["❓ 其他 (自行輸入)"] + df_drugs["藥品名稱"].tolist()
            u_drug_select = st.selectbox("選擇藥品", drug_options)
            u_drug_manual = st.text_input("輸入新藥名", placeholder="若上方選擇「其他」，請在此輸入藥名")
            
            # 送出按鈕
            if st.form_submit_button("🚀 送出新許願", type="primary"):
                # 處理 Email
                final_email = u_email if u_email else "anonymous@wish"
                
                # === 分流邏輯 ===
                # 1. 民眾手動輸入新藥 -> 寫入 DB_Wishlist (待審核)
                if u_drug_select == "❓ 其他 (自行輸入)":
                    final_drug = u_drug_manual.strip()
                    if not final_drug:
                        st.error("❌ 請輸入藥品名稱！")
                    else:
                        if submit_raw_wish(final_email, u_region, final_drug):
                            st.success(f"收到！「{final_drug}」已列入待審核清單，管理員審核後將開放票選。")
                            time.sleep(2)
                            st.rerun()

                # 2. 民眾選擇現有藥品 -> 寫入 DB_Requests (直接計票)
                else:
                    final_drug = u_drug_select
                    if submit_wish(final_email, u_region, final_drug):
                        st.success(f"已記錄您的需求：{final_drug}")
                        load_requests_raw.clear()
                        time.sleep(1)
                        st.rerun()

    st.divider()

    st.divider()
    df_wish = load_wishlist_data()
    
    # 過濾出狀態是 "待處理" 的資料
    if not df_wish.empty and "狀態" in df_wish.columns:
        pending_drugs = df_wish[df_wish["狀態"] == "待處理"]
        
        if not pending_drugs.empty:
            st.info(f"🆕 目前有 {len(pending_drugs)} 款新藥正在審核中，即將加入票選：")
            
            # 用類似標籤的方式顯示藥名
            # 這裡把藥名串接起來顯示，例如：欣剋疹帶狀疱疹疫苗、某某藥...
            drug_names = pending_drugs["建議藥名"].unique().tolist()
            st.write("、".join([f"**{d}**" for d in drug_names]))

    st.divider()
    
    # 讀取 Wishlist 資料
    df_wish = load_wishlist_data()
    
    # 確保資料表有 "狀態" 欄位
    if not df_wish.empty and "狀態" in df_wish.columns:
        
        # === 區塊 A: 🎉 賀！審核通過 (剛加入 DB_Drugs 的新藥) ===
        # 邏輯：找出狀態是 "已加入" 的藥品
        approved_drugs = df_wish[df_wish["狀態"] == "已加入"]
        
        if not approved_drugs.empty:
            st.success(f"🎉 賀！共有 {len(approved_drugs)} 款新藥通過審核，已加入票選名單！")
            st.markdown("👇 **點擊按鈕，搶先投下第一票：**")
            
            # 顯示這些新藥，並加上 +1 按鈕
            # 為了版面整齊，我們用 columns 排列，一行放 2~3 個
            cols = st.columns(2) 
            for i, (idx, row) in enumerate(approved_drugs.iterrows()):
                drug_name = row["建議藥名"]
                
                # 輪流使用 column (左 -> 右 -> 左...)
                with cols[i % 2]:
                    with st.container(border=True):
                        st.markdown(f"**💊 {drug_name}**")
                        # 這裡的 key 加上 "approved" 以示區別
                        if st.button(f"🙋‍♂️ 投我一票", key=f"vote_new_{idx}"):
                            # 直接幫忙送出選票到 DB_Requests
                            default_city = "全台灣" if "全台灣" in cities_list else (cities_list[0] if cities_list else "全台灣")
                            
                            if submit_wish("new_arrival@vote", default_city, drug_name):
                                st.balloons() # 慶祝一下
                                st.toast(f"已為 {drug_name} 開張第一票！")
                                load_requests_raw.clear() # 清除計票快取
                                time.sleep(1)
                                st.rerun()

        # === 區塊 B: ⏳ 審核中 (原本的邏輯) ===
        pending_drugs = df_wish[df_wish["狀態"] == "待處理"]
        if not pending_drugs.empty:
            st.info(f"🆕 尚有 {len(pending_drugs)} 款新藥正在審核中...")
            # 簡單列出藥名即可
            drug_names = pending_drugs["建議藥名"].unique().tolist()
            st.caption("、".join([f"{d}" for d in drug_names]))

    st.divider()
    
    
    # --- 熱門許願榜 ---
    st.subheader("🔥 大家都在找這些藥 (點擊 +1 幫忙集氣)")

    if rank_df.empty:
        st.info("目前還沒有人許願，搶頭香嗎？👆")
    else:
        for idx, row in rank_df.head(15).iterrows():
            drug_name = row["想要藥品"]
            count = row["人次"]
            
            c_text, c_btn = st.columns([4, 1])
            with c_text:
                st.markdown(f"**💊 {drug_name}**")
                st.progress(min(count / 50.0, 1.0))
                st.caption(f"目前集氣：{count} 人次")
            
            with c_btn:
                # 點擊 +1，預設帶入 "全台灣" (或您可改為預設某個縣市)
                # 若 DB_Requests 的縣市也是 Relation，這裡寫入文字 "全台灣" 也必須在 DB_Cities 裡有對應資料
                # 建議：若 DB_Cities 裡有 "全台灣" 這個選項最好，若沒有，請改帶入 cities_list[0] 或其他有效縣市
                if st.button(f"🙋‍♂️ +1", key=f"plus1_{idx}_{drug_name}"):
                    # 注意：這裡的縣市建議使用一個通用值
                    default_city = "全台灣" if "全台灣" in cities_list else cities_list[0]
                    
                    if submit_wish("plus1@vote", default_city, drug_name):
                        st.toast(f"已為 {drug_name} +1！")
                        load_requests_raw.clear()
                        time.sleep(0.5)
                        st.rerun()
            st.divider()

# ==========================================
# Tab 2: 診所回報
# ==========================================
elif selected_tab == "🏥 診所回報供貨":
    st.markdown("#### 我是醫事機構，我有藥！")
    
    if "is_verified" not in st.session_state: st.session_state.is_verified = False
    if "verify_code" not in st.session_state: st.session_state.verify_code = None
    if "email_input" not in st.session_state: st.session_state.email_input = ""

    if not st.session_state.is_verified:
        with st.container(border=True):
            st.subheader("🔐 身分驗證")
            email_input = st.text_input("診所 Email")
            c1, c2 = st.columns([1,2])
            with c1:
                if st.button("寄送驗證碼"):
                    if email_input:
                        code = str(random.randint(100000,999999))
                        st.session_state.verify_code = code; st.session_state.email_input = email_input
                        send_verification_email(email_input, code)
                        st.toast("已寄出")
            with c2:
                user_code = st.text_input("驗證碼", max_chars=6)
                if st.button("驗證"):
                    if user_code == st.session_state.verify_code:
                        st.session_state.is_verified = True
                        st.rerun()
                    else: st.error("錯誤")
    else:
        st.success(f"已驗證：{st.session_state.email_input}")
        with st.container(border=True):
            st.subheader("📋 供貨資訊")
            c_code = st.text_input("機構代碼", max_chars=10)
            c_name = st.text_input("診所名稱")
            c_email = st.text_input("Email", value=st.session_state.email_input, disabled=True)
            c_region = st.selectbox("縣市", cities_list)
            c_drug = st.selectbox("藥品", df_drugs["藥品名稱"].tolist())
            c_conds = st.multiselect("條件", ["健保", "自費", "國健署專案"])
            if st.button("📤 提交", type="primary"):
                if submit_supply(c_code, c_name, c_region, c_drug, c_conds, c_email):
                    st.success("提交成功！")

# ==========================================
# Tab 3: 排行榜
# ==========================================
elif selected_tab == "📊 熱度排行榜":
    st.markdown("### 🔥 缺藥熱度")
    if st.button("🔄 刷新"): st.cache_data.clear(); st.rerun()
    df_raw = load_requests_raw()
    if not df_raw.empty:
        df_chart = df_raw.groupby("想要藥品").size().reset_index(name="人次").sort_values("人次", ascending=False).head(10)
        st.bar_chart(df_chart.set_index("想要藥品")["人次"])
        st.dataframe(df_raw.groupby(["想要藥品","所在縣市"]).size().reset_index(name="人次").sort_values("人次", ascending=False), hide_index=True, width='stretch')

# ==========================================
# Tab 4: 找藥 (修改版：含分類篩選、搜尋與導引)
# ==========================================
elif selected_tab == "🔍 找哪裡有藥":
    st.markdown("### 🔍 藥品供貨清單")
    
    # --- 1. 篩選區塊 (分類 & 關鍵字) ---
    with st.container(border=True):
        col_filter1, col_filter2 = st.columns(2)
        
        # [A] 藥品分類篩選
        # 取得所有不重複的分類，並加上 "全部"
        unique_cats = ["全部"] + sorted(df_drugs["分類"].astype(str).unique().tolist())
        sel_cat = col_filter1.selectbox("📂 1. 先選分類 (選填)", unique_cats)
        
        # [B] 關鍵字搜尋
        search_keyword = col_filter2.text_input("🔎 2. 或輸入關鍵字搜尋", placeholder="例如：易利氣")

    # --- 2. 執行過濾邏輯 ---
    filtered_drugs_df = df_drugs.copy()

    # 邏輯 A: 如果有選分類
    if sel_cat != "全部":
        filtered_drugs_df = filtered_drugs_df[filtered_drugs_df["分類"] == sel_cat]

    # 邏輯 B: 如果有輸入關鍵字
    if search_keyword:
        filtered_drugs_df = filtered_drugs_df[
            filtered_drugs_df["藥品名稱"].str.contains(search_keyword, case=False)
        ]

    # --- 3. 處理搜尋結果 (導引邏輯) ---
    
    # 狀況一：搜尋後完全沒有藥品 -> 導引去許願
    if filtered_drugs_df.empty:
        st.warning(f"🤔 找不到名稱包含「{search_keyword}」且分類為「{sel_cat}」的藥品...")
        
        col_help1, col_help2 = st.columns([2, 1])
        with col_help1:
            st.markdown("👉 **資料庫還沒收錄這個藥嗎？**")
        with col_help2:
            if st.button("🙋‍♂️ 前往許願池新增", type="primary"):
                # 切換 Tab 到許願
                st.session_state.current_tab = "📢 民眾許願"
                # (選用) 可以把關鍵字存起來，帶到許願頁面的輸入框 (需配合 Tab 1 修改)
                # st.session_state.prefill_drug = search_keyword 
                st.rerun()
                
    # 狀況二：有找到藥品 -> 顯示正常的搜尋介面
    else:
        # 準備藥品選單 (只顯示過濾後的藥品)
        drug_options = ["全部"] + filtered_drugs_df["藥品名稱"].tolist()
        
        st.divider()
        col_sel1, col_sel2 = st.columns(2)
        
        # [C] 最終藥品選擇 (連動過濾後的清單)
        s_drug = col_sel1.selectbox("💊 3. 選擇藥品", drug_options)
        
        # [D] 縣市選擇
        s_city = col_sel2.selectbox("📍 4. 選擇縣市", ["全台灣"] + cities_list)

        # --- 4. 查詢庫存邏輯 (原本的程式碼) ---
        if not df_inventory.empty:
            # 這裡要注意：如果不選藥品(全部)，就是列出該分類下所有藥的庫存
            res = df_inventory[
                (df_inventory["庫存狀態"] == "有貨") & 
                (df_inventory["是否上架"] == True)
            ].copy()
            
            # 過濾藥品：如果是選 "全部"，則範圍限定在 filtered_drugs_df (分類過濾後的名單) 裡面的藥
            if s_drug == "全部":
                valid_drugs = filtered_drugs_df["藥品名稱"].tolist()
                res = res[res["藥品名稱"].isin(valid_drugs)]
            else:
                res = res[res["藥品名稱"] == s_drug]

            # 過濾縣市
            if s_city != "全台灣":
                res = res[res["縣市"] == s_city]
            
            # 排序與顯示
            res['縣市'] = pd.Categorical(res['縣市'], categories=cities_list, ordered=True)
            res = res.sort_values(by=["藥品名稱", "縣市"])

            if res.empty:
                st.info("目前條件下尚無診所回報供貨。")
                # 這裡也可以加一個按鈕導引去許願
                if st.button("沒貨？幫我集氣 (+1)", key="btn_empty_wish"):
                    st.session_state.current_tab = "📢 民眾許願"
                    st.rerun()
            else:
                st.success(f"找到 {len(res)} 筆供貨資訊")
                
                # 初始化 session state
                if 'active_feedback_id' not in st.session_state:
                    st.session_state.active_feedback_id = None

                # 顯示列表 (迴圈部分維持不變)
                for idx, row in res.iterrows():
                    cid = f"{row['診所名稱']}_{idx}"
                    clinic_code = row.get('機構代碼', row['診所名稱'])
                    drug_name = row['藥品名稱']
                    
                    with st.container(border=True):
                        st.markdown(f"#### 💊 {drug_name} | 🏥 {row['診所名稱']}")
                        conds = row['給付條件']
                        cond_str = ' '.join([f'`{c}`' for c in (conds if isinstance(conds, list) else [conds])])
                        st.markdown(f"📍 **{row['縣市']}** | 🏷️ {cond_str}")
                        if row['備註']: st.info(f"備註: {row['備註']}")

                        # 載入回饋留言邏輯 (維持不變)
                        if not df_feedback.empty:
                            revs = df_feedback[(df_feedback['機構代碼']==clinic_code) & (df_feedback['藥品名稱']==drug_name)]
                            if not revs.empty:
                                ok = len(revs[revs['回饋類型'].str.contains("認證")])
                                bad = len(revs[revs['回饋類型'].str.contains("不實")])
                                st.markdown(f"✅ **{ok}**　⚠️ **{bad}**")
                                with st.expander(f"查看 {len(revs)} 則留言"):
                                    for _, r in revs.iterrows():
                                        st.text(f"{str(r['時間'])[:10]} {('✅' if '認證' in str(r['回饋類型']) else '⚠️')} : {r['備註']}")

                        # 回報按鈕邏輯 (維持不變)
                        if st.session_state.active_feedback_id != cid:
                            if st.button("💬 我要回報/認證", key=f"btn_open_{cid}"):
                                st.session_state.active_feedback_id = cid
                                st.rerun()
                        
                        # 回報表單顯示 (維持不變，請確保這裡的縮排與之前修正的一致)
                        if st.session_state.active_feedback_id == cid:
                            st.markdown("---")
                            # ... (請貼上之前修正好的 回報表單 程式碼) ...
                            # 為了節省篇幅，請保留您之前修正好的 verified 邏輯與 form 邏輯
                            
                            # (以下為簡略示意外殼，請使用您目前運作正常的版本)
                            v_key = f"verified_{cid}"
                            if v_key not in st.session_state: st.session_state[v_key] = False
                            
                            if not st.session_state[v_key]:
                                # ... 驗證碼邏輯 ...
                                st.warning("請先驗證 Email (請貼回原有程式碼)")
                                # 這裡請貼回您原本的身分驗證區塊代碼
                            else:
                                with st.form(key=f"feedback_form_{cid}"):
                                    fb_type = st.radio("回報類型", ["✅ 認證有貨", "⚠️ 資訊不實"], key=f"type_{cid}")
                                    cmmt = st.text_area("詳細說明", key=f"cmmt_{cid}")
                                    col_b1, col_b2 = st.columns([1, 4])
                                    submitted = col_b1.form_submit_button("📤 送出", type="primary")
                                    cancelled = col_b2.form_submit_button("取消")
                                
                                if submitted:
                                    # ... submit_feedback 邏輯 ...
                                    st.success("回報成功")
                                    st.session_state.active_feedback_id = None
                                    st.rerun()
                                if cancelled:
                                    st.session_state.active_feedback_id = None
                                    st.rerun()
        else:
             st.info("資料庫讀取中，請稍候...")
