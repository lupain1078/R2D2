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

# 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

BASE_DIR = os.getcwd()
IMG_DIR = os.path.join(BASE_DIR, 'images')
TICKETS_DIR = os.path.join(BASE_DIR, 'tickets')

os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(TICKETS_DIR, exist_ok=True)

FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']

# ====================================================================
# 2. 데이터 처리 함수
# ====================================================================

def load_data(sheet_name="Sheet1"):
    try:
        df = conn.read(worksheet=sheet_name, ttl=0)
        return df.fillna("")
    except:
        return pd.DataFrame(columns=FIELD_NAMES)

def save_data(df, sheet_name="Sheet1"):
    conn.update(worksheet=sheet_name, data=df)
    st.cache_data.clear()

def hash_password(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

def get_all_users():
    return load_data("Users")

def login_user(username, password):
    df = get_all_users()
    if df.empty: return False, "데이터 오류", None
    hashed_pw = hash_password(password)
    user_row = df[(df['username'].astype(str) == str(username)) & (df['password'].astype(str) == str(hashed_pw))]
    if user_row.empty: return False, "아이디/비번 불일치", None
    user_data = user_row.iloc[0]
    if str(user_data['approved']).upper() != 'TRUE': return False, "승인 대기 중", None
    return True, "성공", user_data['role']

# ====================================================================
# 3. 메인 앱 화면 (main_app) - 여기서 모든 기능을 호출합니다.
# ====================================================================
def main_app():
    if 'df' not in st.session_state:
        st.session_state.df = load_data("Sheet1")

    df = st.session_state.df
    user_role = st.session_state.get('role', 'user')

    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        st.caption(f"권한: {user_role}")
        if st.button("🔄 데이터 새로고침"):
            st.session_state.df = load_data("Sheet1")
            st.rerun()
        if st.button("로그아웃"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    st.title("🛠️ 통합 장비 관리 시스템")

    # 상단 요약 지표
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", df[df['대여여부'] == '대여 중']['수량'].sum() if not df.empty else 0)
    c2.metric("🎬 현장 출고", df[df['대여여부'] == '현장 출고']['수량'].sum() if not df.empty else 0)
    c3.metric("🛠️ 수리 중", df[df['대여여부'] == '수리 중']['수량'].sum() if not df.empty else 0)
    c4.metric("💔 파손", df[df['대여여부'] == '파손']['수량'].sum() if not df.empty else 0)

    tabs = st.tabs(["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리", "👑 관리자"])

    with tabs[0]: # 재고 관리
        st.subheader("📦 장비 재고 목록")
        with st.expander("➕ 새 장비 등록"):
            with st.form("add_item"):
                c1, c2, c3 = st.columns([1,2,1])
                t = c1.text_input("타입"); n = c2.text_input("이름"); q = c3.number_input("수량", 1)
                if st.form_submit_button("등록"):
                    new_row = {'ID': str(uuid.uuid4()), '타입': t, '이름': n, '수량': q, '대여여부': '재고'}
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    st.success("등록 완료"); st.rerun()
        
        edit_mode = st.toggle("🔓 수정 모드")
        edited_df = st.data_editor(st.session_state.df, disabled=(not edit_mode), hide_index=True, use_container_width=True)
        if edit_mode and st.button("💾 변경사항 저장"):
            save_data(edited_df, "Sheet1")
            st.session_state.df = edited_df
            st.success("저장되었습니다."); st.rerun()

    # 나머지 탭 로직들도 여기에 추가 가능합니다.

# ====================================================================
# 4. 로그인 / 회원가입 화면
# ====================================================================
def login_page():
    st.title("🔒 통합 장비 관리 시스템")
    t1, t2 = st.tabs(["로그인", "회원가입"])
    with t1:
        with st.form("login"):
            uid = st.text_input("아이디"); upw = st.text_input("비밀번호", type="password")
            if st.form_submit_button("로그인"):
                ok, msg, role = login_user(uid, upw)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.username = uid
                    st.session_state.role = role
                    st.rerun()
                else: st.error(msg)
    with t2:
        st.info("회원가입 신청 후 관리자 승인이 필요합니다.")

# ====================================================================
# 5. 실행부 (엔트리 포인트)
# ====================================================================
if __name__ == '__main__':
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    if st.session_state.logged_in:
        main_app() # 로그인 성공 시 메인 화면 호출
    else:
        login_page() # 미로그인 시 로그인 페이지 호출
