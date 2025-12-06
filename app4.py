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
        return pd.DataFrame([{'藥品名稱':i['values'].get('藥品名稱',''), '分類':i['values'].get('藥品分類','')} for i in data['items']])
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
    payload = {
        "rows": [
            {
                "cells": [
                    {"column": "許願者Email", "value": str(email)},
                    {"column": "所在縣市", "value": str(region)},      # 這裡送出 "基隆市"，Coda 會自動連到 DB_Cities
                    {"column": "建議藥名", "value": str(new_drug_name)}, # 這是純文字
                    {"column": "狀態", "value": "待處理"}             # 預設狀態
                ]
            }
        ]
    }
    
    try:
        requests.post(url, headers=headers, json=payload).raise_for_status()
        return True
    except Exception as e:
        print(f"寫入 Wishlist 失敗: {e}")
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
# Tab 4: 找藥
# ==========================================
elif selected_tab == "🔍 找哪裡有藥":
    st.markdown("### 🔍 藥品供貨清單")
    
    c1, c2 = st.columns(2)
    s_drug = c1.selectbox("藥品", ["全部"]+df_drugs["藥品名稱"].tolist())
    s_city = c2.selectbox("縣市", ["全台灣"]+cities_list)

    if not df_inventory.empty:
        res = df_inventory[(df_inventory["庫存狀態"]=="有貨") & (df_inventory["是否上架"]==True)].copy()
        if s_drug != "全部": res = res[res["藥品名稱"]==s_drug]
        if s_city != "全台灣": res = res[res["縣市"]==s_city]
        
        res['縣市'] = pd.Categorical(res['縣市'], categories=cities_list, ordered=True)
        res = res.sort_values(by=["藥品名稱", "縣市"])

        if res.empty:
            st.warning("尚無資料")
        else:
            st.success(f"找到 {len(res)} 筆")
            
            if 'active_feedback_id' not in st.session_state:
                st.session_state.active_feedback_id = None

            for idx, row in res.iterrows():
                cid = f"{row['診所名稱']}_{idx}"
                clinic_code = row.get('機構代碼', row['診所名稱'])
                drug_name = row['藥品名稱']
                
                with st.container(border=True):
                    st.markdown(f"#### 💊 {drug_name}  |  🏥 {row['診所名稱']}")
                    conds = row['給付條件']
                    st.markdown(f"📍 **{row['縣市']}** | 🏷️ {' '.join([f'`{c}`' for c in (conds if isinstance(conds, list) else [conds])])}")
                    if row['備註']: st.info(f"備註: {row['備註']}")

                    if not df_feedback.empty:
                        revs = df_feedback[(df_feedback['機構代碼']==clinic_code) & (df_feedback['藥品名稱']==drug_name)]
                        if not revs.empty:
                            ok = len(revs[revs['回饋類型'].str.contains("認證")])
                            bad = len(revs[revs['回饋類型'].str.contains("不實")])
                            st.markdown(f"✅ **{ok}**　⚠️ **{bad}**")
                            with st.expander(f"查看 {len(revs)} 則留言"):
                                for _, r in revs.iterrows():
                                    # [修正] 這裡改成 r['時間']，對應 DataFrame 的欄位名稱
                                    st.text(f"{r['時間'][:10]} {('✅' if '認證' in r['回饋類型'] else '⚠️')} : {r['備註']}")

                    if st.session_state.active_feedback_id != cid:
                        if st.button("💬 我要回報/認證", key=f"btn_open_{cid}"):
                            st.session_state.active_feedback_id = cid
                            st.rerun()
                    
                    if st.session_state.active_feedback_id == cid:
                        st.markdown("---")
                        st.markdown("##### 📝 填寫回報")
                        
                        with st.container():
                            v_key = f"verified_{cid}"
                            if v_key not in st.session_state: st.session_state[v_key] = False
                            
                            if not st.session_state[v_key]:
                                col_f1, col_f2 = st.columns([1,1])
                                umail = col_f1.text_input("您的 Email", key=f"mail_{cid}")
                                if col_f1.button("寄驗證碼", key=f"send_{cid}"):
                                    code = str(random.randint(100000,999999))
                                    st.session_state[f"code_{cid}"] = code
                                    send_verification_email(umail, code)
                                    st.toast("已寄出")
                                
                                ucode = col_f2.text_input("驗證碼", max_chars=6, key=f"code_in_{cid}")
                                if col_f2.button("驗證身分", key=f"verify_{cid}"):
                                    if ucode == st.session_state.get(f"code_{cid}"):
                                        st.session_state[v_key] = True
                                        st.rerun()
                                    else:
                                        st.error("驗證碼錯誤")
                                # 修改後的程式碼建議
                                # ---------------------------------------------------------
                                else:
                                    # 1. 宣告一個 Form (表單)，這能確保資料送出前不會因為 Rerun 而消失
                                    with st.form(key=f"feedback_form_{cid}"):
                                        
                                        fb_type = st.radio("回報類型", ["✅ 認證有貨", "⚠️ 資訊不實"], key=f"type_{cid}")
                                        cmmt = st.text_area("詳細說明", key=f"cmmt_{cid}")
                                        
                                        col_b1, col_b2 = st.columns([1, 4])
                                        
                                        # 2. 關鍵修改：將普通 button 改為 form_submit_button
                                        # 注意：在 form 裡面，這兩個按鈕按下去都會觸發 "Submit" 行為
                                        submitted = col_b1.form_submit_button("📤 送出", type="primary")
                                        cancelled = col_b2.form_submit_button("取消")
                                
                                    # 3. 處理邏輯移到 Form 區塊外面
                                    if submitted:
                                        # 加入 print 以確認後端有收到訊號
                                        print(f"[{cid}] 送出按鈕被觸發，準備寫入...") 
                                        
                                        # 呼叫您的寫入函式
                                        if submit_feedback(clinic_code, drug_name, st.session_state.get(f"mail_{cid}"), fb_type, cmmt):
                                            st.success("回報成功！")
                                            st.session_state.active_feedback_id = None 
                                            # load_feedback_data.clear() # 如果這是快取清除，請確保語法正確
                                            time.sleep(1)
                                            st.rerun()
                                            
                                    if cancelled:
                                        st.session_state.active_feedback_id = None
                                        st.rerun()
        
    else:
        st.info("資料庫讀取中...")





