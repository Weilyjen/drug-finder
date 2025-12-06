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
    url=f'https://coda.io/apis/v1/docs/{DOC_ID}/tables/{TABLE_ID
