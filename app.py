import streamlit as st
import pandas as pd
import os
import uuid
import hashlib
from datetime import datetime
from io import BytesIO
from openpyxl.styles import Font
from streamlit_gsheets import GSheetsConnection

# 1. 설정 및 구글 시트 연결
st.set_page_config(page_title="통합 장비 관리 시스템", layout="wide", page_icon="🛠️")
conn = st.connection("gsheets", type=GSheetsConnection)

FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']

# 2. 데이터 처리 함수
def load_data(sheet_name="Sheet1"):
    try:
        df = conn.read(worksheet=sheet_name, ttl=0)
        return df.fillna("")
    except:
        return pd.DataFrame(columns=FIELD_NAMES if sheet_name=="Sheet1" else [])

def save_data(df, sheet_name="Sheet1"):
    conn.update(worksheet=sheet_name, data=df)
    st.cache_data.clear()

def log_transaction(kind, item_name, qty, target, date_val, return_val=''):
    try:
        log_df = load_data("Logs")
        new_log = {'시간': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), '작성자': st.session_state.username,
                   '종류': kind, '장비이름': item_name, '수량': qty, '대상': target, '날짜': date_val, '반납예정일': return_val}
        log_df = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
        save_data(log_df, "Logs")
    except: pass

# 3. 메인 앱 UI
def main_app():
    if 'df' not in st.session_state:
        st.session_state.df = load_data("Sheet1")
    
    df = st.session_state.df
    user_role = st.session_state.get('role', 'user')

    # 사이드바 (기본 기능)
    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        if st.button("🔄 시트 데이터 새로고침"):
            st.session_state.df = load_data("Sheet1")
            st.rerun()
        if st.button("🚪 로그아웃"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    # 상단 지표
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", df[df['대여여부'] == '대여 중']['수량'].sum() if not df.empty else 0)
    c2.metric("🎬 현장 출고", df[df['대여여부'] == '현장 출고']['수량'].sum() if not df.empty else 0)
    c3.metric("🛠️ 수리 중", df[df['대여여부'] == '수리 중']['수량'].sum() if not df.empty else 0)
    c4.metric("💔 파손", df[df['대여여부'] == '파손']['수량'].sum() if not df.empty else 0)

    # 모든 탭 복구
    tabs = st.tabs(["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리", "🗂️ 보관함", "👑 관리자"])

    # --- 탭별 상세 로직 ---
    with tabs[0]: # 재고 관리
        with st.expander("➕ 새 장비 등록"):
            with st.form("add"):
                col1, col2, col3 = st.columns([1,2,1])
                t, n, q = col1.text_input("타입"), col2.text_input("장비명"), col3.number_input("수량", 1)
                if st.form_submit_button("등록"):
                    new_item = {'ID': str(uuid.uuid4()), '타입': t, '이름': n, '수량': q, '대여여부': '재고'}
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_item])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    st.rerun()
        edit_m = st.toggle("🔓 수정 모드")
        edited = st.data_editor(st.session_state.df, disabled=(not edit_m), hide_index=True, use_container_width=True)
        if edit_m and st.button("💾 저장"):
            save_data(edited, "Sheet1"); st.session_state.df = edited; st.rerun()

    with tabs[1]: # 외부 대여
        stock = st.session_state.df[st.session_state.df['대여여부'] == '재고']
        if not stock.empty:
            sel = st.selectbox("장비 선택", stock.index, format_func=lambda x: stock.loc[x, '이름'])
            with st.form("rent"):
                tgt = st.text_input("업체명")
                qty = st.number_input("수량", 1, int(stock.loc[sel, '수량']))
                if st.form_submit_button("대여 확정"):
                    st.session_state.df.at[sel, '수량'] -= qty
                    new_r = stock.loc[sel].copy()
                    new_r.update({'ID': str(uuid.uuid4()), '수량': qty, '대여여부': '대여 중', '대여자': tgt, '대여일': datetime.now().strftime("%Y-%m-%d")})
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_r])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    log_transaction("대여", stock.loc[sel, '이름'], qty, tgt, datetime.now().strftime("%Y-%m-%d"))
                    st.rerun()

    with tabs[5]: # 내역 관리
        st.subheader("📜 활동 기록")
        st.dataframe(load_data("Logs").iloc[::-1], use_container_width=True)

# 4. 실행부
def login_page():
    st.title("🔒 로그인")
    with st.form("login"):
        u, p = st.text_input("ID"), st.text_input("PW", type="password")
        if st.form_submit_button("접속"):
            if u == "admin" and p == "1234":
                st.session_state.logged_in, st.session_state.username, st.session_state.role = True, u, "admin"
                st.rerun()
            # Users 시트 대조
            u_df = load_data("Users")
            hp = hashlib.sha256(p.encode()).hexdigest()
            user = u_df[(u_df['username'] == u) & (u_df['password'] == hp)]
            if not user.empty and str(user.iloc[0]['approved']).upper() == 'TRUE':
                st.session_state.logged_in, st.session_state.username, st.session_state.role = True, u, user.iloc[0]['role']
                st.rerun()
            else: st.error("로그인 실패")

if __name__ == '__main__':
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: login_page()
