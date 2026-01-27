import streamlit as st
import pandas as pd
import os
import uuid
import hashlib
from datetime import datetime
from io import BytesIO
from openpyxl.styles import Font
from streamlit_gsheets import GSheetsConnection

# ====================================================================
# 1. 설정 및 구글 시트 연결
# ====================================================================
st.set_page_config(page_title="통합 장비 관리 시스템", layout="wide", page_icon="🛠️")

conn = st.connection("gsheets", type=GSheetsConnection)

BASE_DIR = os.getcwd()
os.makedirs(os.path.join(BASE_DIR, 'images'), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'tickets'), exist_ok=True)

FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']

# ====================================================================
# 2. 데이터 처리 함수
# ====================================================================

def load_data(sheet_name="Sheet1"):
    try:
        df = conn.read(worksheet=sheet_name, ttl=0)
        if df.empty:
            return pd.DataFrame(columns=FIELD_NAMES if sheet_name=="Sheet1" else [])
        return df.fillna("")
    except:
        return pd.DataFrame(columns=FIELD_NAMES if sheet_name=="Sheet1" else [])

def save_data(df, sheet_name="Sheet1"):
    conn.update(worksheet=sheet_name, data=df)
    st.cache_data.clear()

def log_transaction(kind, item_name, qty, target, date_val, return_val=''):
    try:
        log_df = load_data("Logs")
        new_log = {
            '시간': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            '작성자': st.session_state.username,
            '종류': kind, '장비이름': item_name, '수량': qty, 
            '대상': target, '날짜': date_val, '반납예정일': return_val
        }
        log_df = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
        save_data(log_df, "Logs")
    except: pass

def hash_password(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

# ====================================================================
# 3. 메인 앱 UI
# ====================================================================
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

    # 상단 요약 지표
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", df[df['대여여부'] == '대여 중']['수량'].sum() if not df.empty else 0)
    c2.metric("🎬 현장 출고", df[df['대여여부'] == '현장 출고']['수량'].sum() if not df.empty else 0)
    c3.metric("🛠️ 수리 중", df[df['대여여부'] == '수리 중']['수량'].sum() if not df.empty else 0)
    c4.metric("💔 파손", df[df['대여여부'] == '파손']['수량'].sum() if not df.empty else 0)

    tabs = st.tabs(["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "📜 내역 관리"])

    # 1. 재고 관리 (장비 등록이 선행되어야 함)
    with tabs[0]:
        st.subheader("📦 장비 등록 및 수정")
        with st.expander("➕ 새 장비 등록"):
            with st.form("add_item_form", clear_on_submit=True):
                c1, c2, c3 = st.columns([1,2,1])
                t = c1.text_input("타입")
                n = c2.text_input("장비 이름")
                q = c3.number_input("초기 수량", 1)
                b = st.text_input("브랜드")
                if st.form_submit_button("장비 등록"):
                    new_row = {'ID': str(uuid.uuid4()), '타입': t, '이름': n, '수량': q, '브랜드': b, '대여여부': '재고'}
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    st.success(f"{n} 등록 완료"); st.rerun()
        
        edit_mode = st.toggle("🔓 데이터 수정 모드")
        edited_df = st.data_editor(st.session_state.df, disabled=(not edit_mode), hide_index=True, use_container_width=True)
        if edit_mode and st.button("💾 모든 변경사항 시트에 저장"):
            save_data(edited_df, "Sheet1")
            st.session_state.df = edited_df
            st.success("구글 시트 동기화 완료"); st.rerun()

    # 2. 외부 대여 (재고가 있을 때만 활성화)
    with tabs[1]:
        st.subheader("📤 외부 대여 처리")
        stock = st.session_state.df[st.session_state.df['대여여부'] == '재고']
        if stock.empty:
            st.warning("현재 대여 가능한 재고가 없습니다. [재고 관리]에서 장비를 먼저 등록하세요.")
        else:
            opts = stock.apply(lambda x: f"{x['이름']} ({x['브랜드']}) - 잔여: {x['수량']}개", axis=1)
            sel_idx = st.selectbox("대여할 장비 선택", opts.index, format_func=lambda x: opts[x])
            
            with st.form("rent_process_form"):
                target = st.text_input("대여 업체명")
                c1, c2 = st.columns(2)
                max_q = int(stock.loc[sel_idx, '수량'])
                qty = c1.number_input("대여 수량", 1, max_q if max_q > 0 else 1)
                r_date = c2.date_input("반납 예정일")
                if st.form_submit_button("대여 확정"):
                    if not target:
                        st.error("업체명을 입력해주세요.")
                    else:
                        item = stock.loc[sel_idx]
                        st.session_state.df.at[sel_idx, '수량'] -= qty
                        new_r = item.copy()
                        new_r['ID'] = str(uuid.uuid4()); new_r['수량'] = qty; new_r['대여여부'] = '대여 중'
                        new_r['대여자'] = target; new_r['반납예정일'] = str(r_date); new_r['대여일'] = datetime.now().strftime("%Y-%m-%d")
                        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_r])], ignore_index=True)
                        save_data(st.session_state.df, "Sheet1")
                        log_transaction("외부대여", item['이름'], qty, target, datetime.now().strftime("%Y-%m-%d"), str(r_date))
                        st.success("대여 처리 완료"); st.rerun()

    # 3. 내역 관리
    with tabs[4]:
        st.subheader("📜 활동 기록")
        logs = load_data("Logs")
        if not logs.empty:
            st.dataframe(logs.iloc[::-1], use_container_width=True)
        else:
            st.info("아직 기록된 활동이 없습니다.")

# ====================================================================
# 4. 로그인 및 실행부
# ====================================================================
def login_page():
    st.title("🔒 통합 장비 관리 시스템")
    with st.form("login_form"):
        uid = st.text_input("아이디")
        upw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("로그인"):
            if uid == "admin" and upw == "1234":
                st.session_state.logged_in = True; st.session_state.username = "admin"; st.session_state.role = "admin"; st.rerun()
            df_u = conn.read(worksheet="Users", ttl=0)
            hashed_pw = hash_password(upw)
            user_row = df_u[(df_u['username'].astype(str) == str(uid)) & (df_u['password'].astype(str) == str(hashed_pw))]
            if not user_row.empty and str(user_row.iloc[0]['approved']).upper() == 'TRUE':
                st.session_state.logged_in = True; st.session_state.username = uid; st.session_state.role = user_row.iloc[0]['role']; st.rerun()
            else: st.error("로그인 실패 또는 승인 대기 중")

if __name__ == '__main__':
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: login_page()
