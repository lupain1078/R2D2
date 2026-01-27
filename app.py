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

# 구글 시트 연결 (Secrets에 설정된 정보를 자동으로 사용함)
conn = st.connection("gsheets", type=GSheetsConnection)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE_DIR, 'images')
TICKETS_DIR = os.path.join(BASE_DIR, 'tickets')

if not os.path.exists(IMG_DIR): os.makedirs(IMG_DIR)
if not os.path.exists(TICKETS_DIR): os.makedirs(TICKETS_DIR)

FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']

# ====================================================================
# 2. 데이터 처리 함수 (Google Sheets CRUD)
# ====================================================================

def load_data(sheet_name="Sheet1"):
    """구글 시트에서 데이터를 읽어옴"""
    try:
        df = conn.read(worksheet=sheet_name, ttl="0")
        return df.fillna("")
    except:
        return pd.DataFrame(columns=FIELD_NAMES)

def save_data(df, sheet_name="Sheet1"):
    """구글 시트에 데이터를 저장함"""
    conn.update(worksheet=sheet_name, data=df)
    st.cache_data.clear()

def hash_password(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

# --- 회원 관리 함수 ---
def get_all_users():
    return load_data("Users")

def register_user(username, password, birthdate):
    df = get_all_users()
    if username in df['username'].values: return False, "이미 존재하는 아이디입니다."
    
    new_user = {
        'username': username, 'password': hash_password(password), 'role': 'user',          
        'approved': False, 'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'birthdate': str(birthdate)
    }
    df = pd.concat([df, pd.DataFrame([new_user])], ignore_index=True)
    save_data(df, "Users")
    return True, "가입 신청 완료. 관리자 승인 대기 중."

def login_user(username, password):
    df = get_all_users()
    hashed_pw = hash_password(password)
    user_row = df[(df['username'] == username) & (df['password'] == hashed_pw)]
    
    if user_row.empty: return False, "아이디/비번 불일치", None
    user_data = user_row.iloc[0]
    if not user_data['approved']: return False, "승인 대기 중입니다.", None
    return True, "로그인 성공", user_data['role']

def update_user_status(username, action):
    df = get_all_users()
    if action == "approve": df.loc[df['username'] == username, 'approved'] = True
    elif action == "delete": df = df[df['username'] != username]
    save_data(df, "Users")

# --- 로그 기록 함수 ---
def log_transaction(kind, item_name, qty, target, date_val, return_val=''):
    log_df = load_data("Logs")
    new_log = {
        '시간': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), '작성자': st.session_state.username,
        '종류': kind, '장비이름': item_name, '수량': qty, '대상': target, '날짜': date_val, '반납예정일': return_val
    }
    log_df = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
    save_data(log_df, "Logs")

# ====================================================================
# 3. 엑셀 출력 및 UI 유틸리티
# ====================================================================
def create_dispatch_ticket_multisheet(site_list, full_df, worker):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for site in site_list:
            site_df = full_df[full_df['대여자'] == site]
            if site_df.empty: continue
            display_df = site_df[['이름', '브랜드', '수량', '대여일', '반납예정일', '출고비고']].copy()
            display_df.columns = ['장비명', '브랜드', '수량', '출고일', '반납예정일', '비고']
            sheet_title = str(site)[:30].replace("/", "_").replace("\\", "_")
            display_df.to_excel(writer, index=False, sheet_name=sheet_title, startrow=4)
            ws = writer.sheets[sheet_title]
            ws['A1'] = f"장비 출고증 ({site})"; ws['A1'].font = Font(bold=True, size=16)
            ws['A2'] = f"현장명: {site}"; ws['A3'] = f"출고 담당자: {worker}"
    return output.getvalue()

# ====================================================================
# 4. 메인 어플리케이션 UI
# ====================================================================
def main_app():
    if 'df' not in st.session_state:
        st.session_state.df = load_data("Sheet1")

    df = st.session_state.df
    user_role = st.session_state.get('role', 'user')

    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        st.caption(f"권한: {'👑 관리자' if user_role == 'admin' else '일반 사용자'}")
        if st.button("🔄 데이터 새로고침"):
            st.session_state.df = load_data("Sheet1")
            st.rerun()

    col_h1, col_h2 = st.columns([8, 2])
    col_h1.title("🛠️ 통합 장비 관리 시스템")
    if col_h2.button("로그아웃"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

    # 상단 요약 지표
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", df[df['대여여부'] == '대여 중']['수량'].sum() if not df.empty else 0)
    c2.metric("🎬 현장 출고", df[df['대여여부'] == '현장 출고']['수량'].sum() if not df.empty else 0)
    c3.metric("🛠️ 수리 중", df[df['대여여부'] == '수리 중']['수량'].sum() if not df.empty else 0)
    c4.metric("💔 파손", df[df['대여여부'] == '파손']['수량'].sum() if not df.empty else 0)

    tabs = st.tabs(["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리", "👑 관리자"])

    # --- 탭 로직 (중복 방지를 위해 핵심만 요약, 기존 로직에서 save_data(st.session_state.df)만 호출하면 됨) ---
    with tabs[0]: # 재고 관리
        st.subheader("장비 관리")
        with st.expander("➕ 새 장비 등록"):
            with st.form("add_form", clear_on_submit=True):
                c1, c2, c3 = st.columns([1, 2, 1])
                n_type = c1.text_input("타입"); n_name = c2.text_input("이름"); n_qty = c3.number_input("수량", 1)
                if st.form_submit_button("등록"):
                    new_row = {'ID': str(uuid.uuid4()), '타입': n_type, '이름': n_name, '수량': n_qty, '대여여부': '재고'}
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    st.success("등록 완료"); st.rerun()

        # 데이터 에디터 (수정 모드)
        edit_mode = st.toggle("🔓 수정 모드")
        edited_df = st.data_editor(st.session_state.df, disabled=(not edit_mode), hide_index=True, use_container_width=True)
        if edit_mode and st.button("💾 수정 사항 저장"):
            st.session_state.df = edited_df
            save_data(edited_df, "Sheet1")
            st.success("저장 완료"); st.rerun()

    with tabs[5]: # 내역 관리
        st.subheader("📜 내역 관리")
        logs = load_data("Logs")
        st.dataframe(logs.iloc[::-1], use_container_width=True)

    if user_role == 'admin':
        with tabs[6]: # 관리자 전용
            st.subheader("👑 회원 승인 관리")
            u_df = get_all_users()
            pending = u_df[u_df['approved'] == False]
            for _, row in pending.iterrows():
                col1, col2 = st.columns([3, 1])
                col1.write(f"신청자: {row['username']} ({row['created_at']})")
                if col2.button("승인", key=row['username']):
                    update_user_status(row['username'], "approve")
                    st.rerun()

def login_page():
    st.title("🔒 통합 장비 관리 시스템")
    tab1, tab2 = st.tabs(["로그인", "회원가입"])
    with tab1:
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
    with tab2:
        with st.form("signup"):
            nid = st.text_input("아이디"); npw = st.text_input("비밀번호", type="password"); bday = st.date_input("생일")
            if st.form_submit_button("가입 신청"):
                ok, msg = register_user(nid, npw, bday)
                if ok: st.success(msg)
                else: st.error(msg)

if __name__ == '__main__':
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: login_page()
