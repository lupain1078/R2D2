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

# 2. 데이터 처리 함수 (정수화 및 공백 제거 강화)
def load_data(sheet_name="Sheet1"):
    try:
        df = conn.read(worksheet=sheet_name, ttl=0)
        df = df.fillna("")
        if not df.empty and '수량' in df.columns:
            df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0).astype(int)
        return df
    except:
        return pd.DataFrame(columns=FIELD_NAMES if sheet_name=="Sheet1" else [])

def save_data(df, sheet_name="Sheet1"):
    if '수량' in df.columns:
        df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0).astype(int)
    conn.update(worksheet=sheet_name, data=df)
    st.cache_data.clear()

def log_transaction(kind, item_name, qty, target, date_val, return_val=''):
    try:
        log_df = load_data("Logs")
        new_log = {'시간': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), '작성자': st.session_state.username,
                   '종류': kind, '장비이름': item_name, '수량': int(qty), '대상': target, '날짜': date_val, '반납예정일': return_val}
        log_df = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
        save_data(log_df, "Logs")
    except: pass

# 3. 메인 앱 UI
def main_app():
    if 'df' not in st.session_state:
        st.session_state.df = load_data("Sheet1")
    
    df = st.session_state.df
    user_role = st.session_state.get('role', 'user')

    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        if st.button("🔄 데이터 새로고침"):
            st.session_state.df = load_data("Sheet1")
            st.rerun()
        if st.button("🚪 로그아웃"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    st.title("🛠️ 통합 장비 관리 시스템")

    # 상단 요약 지표 (소수점 제거)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", int(df[df['대여여부'].str.strip() == '대여 중']['수량'].sum()) if not df.empty else 0)
    c2.metric("🎬 현장 출고", int(df[df['대여여부'].str.strip() == '현장 출고']['수량'].sum()) if not df.empty else 0)
    c3.metric("🛠️ 수리 중", int(df[df['대여여부'].str.strip() == '수리 중']['수량'].sum()) if not df.empty else 0)
    c4.metric("💔 파손", int(df[df['대여여부'].str.strip() == '파손']['수량'].sum()) if not df.empty else 0)

    tabs = st.tabs(["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리"])

    # --- 1. 재고 관리 ---
    with tabs[0]:
        with st.expander("➕ 새 장비 등록"):
            with st.form("add_form", clear_on_submit=True):
                col1, col2, col3 = st.columns([1,2,1])
                t, n, q = col1.text_input("타입"), col2.text_input("장비명"), col3.number_input("수량", 1, step=1)
                if st.form_submit_button("등록"):
                    new_item = {'ID': str(uuid.uuid4()), '타입': t, '이름': n, '수량': int(q), '대여여부': '재고'}
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_item])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    st.rerun()
        edit_m = st.toggle("🔓 수정 모드")
        edited = st.data_editor(st.session_state.df, disabled=(not edit_m), hide_index=True, use_container_width=True)
        if edit_m and st.button("💾 모든 변경사항 저장"):
            save_data(edited, "Sheet1"); st.session_state.df = edited; st.success("저장 완료"); st.rerun()

    # --- 2. 현장 출고 (수정된 로직) ---
    with tabs[2]:
        st.subheader("🎬 현장 출고 처리")
        # [수정] 수량이 0인 장비도 목록에는 뜨게 하되 대여 수량 선택만 제한
        stock = st.session_state.df[st.session_state.df['대여여부'].str.strip() == '재고']
        if not stock.empty:
            opts = stock.apply(lambda x: f"{x['이름']} ({x['브랜드']}) - 현재고: {int(x['수량'])}개", axis=1)
            sel_idx = st.selectbox("출고 장비 선택", opts.index, format_func=lambda x: opts[x], key="disp_sel")
            with st.form("dispatch_form"):
                site = st.text_input("현장명")
                max_q = int(stock.loc[sel_idx, '수량'])
                qty = st.number_input("출고 수량", 0, max_q if max_q > 0 else 0, step=1)
                r_date = st.date_input("반납 예정일", key="disp_date")
                if st.form_submit_button("현장 출고 확정"):
                    if qty < 1: st.error("출고할 수량이 없습니다."); st.stop()
                    item = stock.loc[sel_idx]
                    st.session_state.df.at[sel_idx, '수량'] -= int(qty)
                    new_d = item.copy()
                    new_d.update({'ID': str(uuid.uuid4()), '수량': int(qty), '대여여부': '현장 출고', '대여자': site, '대여일': datetime.now().strftime("%Y-%m-%d"), '반납예정일': str(r_date)})
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_d])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    log_transaction("현장출고", item['이름'], qty, site, datetime.now().strftime("%Y-%m-%d"), str(r_date))
                    st.success("현장 출고 완료"); st.rerun()
        else: st.warning("출고 가능한 '재고' 상태의 장비가 없습니다.")

    # --- 3. 수리/파손 (수정된 로직) ---
    with tabs[4]:
        st.subheader("🛠️ 수리 및 파손 관리")
        # [수정] 재고뿐만 아니라 이미 수리/파손 중인 항목도 모두 불러옴
        m_df = st.session_state.df[st.session_state.df['대여여부'].str.strip().isin(['재고', '수리 중', '파손'])]
        if not m_df.empty:
            m_opts = m_df.apply(lambda x: f"[{x['대여여부']}] {x['이름']} ({int(x['수량'])}개)", axis=1)
            sel_m = st.selectbox("상태 변경 장비 선택", m_opts.index, format_func=lambda x: m_opts[x])
            with st.form("maint_form"):
                new_stat = st.selectbox("변경할 상태", ["재고", "수리 중", "파손"])
                if st.form_submit_button("상태 변경 적용"):
                    st.session_state.df.at[sel_m, '대여여부'] = new_stat
                    save_data(st.session_state.df, "Sheet1")
                    log_transaction(f"상태변경({new_stat})", st.session_state.df.loc[sel_m, '이름'], 0, new_stat, datetime.now().strftime("%Y-%m-%d"))
                    st.success("변경 완료"); st.rerun()
        else: st.info("상태를 변경할 장비가 없습니다.")

# --- 로그인 및 실행 로직 동일 ---
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
            user = u_df[(u_df['username'].astype(str) == str(u)) & (u_df['password'].astype(str) == str(hp))]
            if not user.empty and str(user.iloc[0]['approved']).upper() == 'TRUE':
                st.session_state.logged_in, st.session_state.username, st.session_state.role = True, u, user.iloc[0]['role']
                st.rerun()
            else: st.error("로그인 실패")

if __name__ == '__main__':
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: login_page()
