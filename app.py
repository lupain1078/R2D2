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

# 파일 저장 경로 설정 (Streamlit Cloud 환경 대응)
BASE_DIR = os.getcwd() # 현재 작업 디렉토리 기준
IMG_DIR = os.path.join(BASE_DIR, 'images')
TICKETS_DIR = os.path.join(BASE_DIR, 'tickets')

# 폴더 자동 생성
os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(TICKETS_DIR, exist_ok=True)

FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']

# ====================================================================
# 2. 데이터 처리 함수 (탭 이름 매칭 강화)
# ====================================================================

def load_data(sheet_name):
    """구글 시트에서 데이터를 읽어옴 (탭 이름 정확히 일치 확인)"""
    try:
        # ttl=0으로 설정하여 캐시 없이 실시간 데이터를 가져옵니다.
        df = conn.read(worksheet=sheet_name, ttl=0)
        return df.fillna("")
    except Exception as e:
        st.error(f"시트 '{sheet_name}' 로드 실패. 탭 이름을 확인하세요.")
        return pd.DataFrame()

def save_data(df, sheet_name):
    """구글 시트에 데이터를 저장함"""
    try:
        conn.update(worksheet=sheet_name, data=df)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"시트 '{sheet_name}' 저장 실패: {e}")

def hash_password(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

# --- 회원 관리 ---
def get_all_users():
    return load_data("Users") # 시트의 탭 이름인 'Users'와 일치해야 함

def login_user(username, password):
    df = get_all_users()
    if df.empty: return False, "사용자 데이터를 불러올 수 없습니다.", None
    
    hashed_pw = hash_password(password)
    # 아이디와 비밀번호 매칭 확인
    user_row = df[(df['username'].astype(str) == str(username)) & (df['password'].astype(str) == str(hashed_pw))]
    
    if user_row.empty: 
        return False, "아이디 또는 비밀번호가 일치하지 않습니다.", None
        
    user_data = user_row.iloc[0]
    
    # 승인 여부 확인 (구글 시트의 TRUE 값 대응)
    approved_val = str(user_data['approved']).upper()
    if approved_val != 'TRUE': 
        return False, "관리자 승인 대기 중입니다.", None
        
    return True, "로그인 성공", user_data['role']

# ====================================================================
# 3. UI 및 메인 로직 (생략된 부분은 기존과 동일하게 유지)
# ====================================================================

def login_page():
    st.title("🔒 통합 장비 관리 시스템")
    
    # 세션 초기화
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    tab1, tab2 = st.tabs(["로그인", "회원가입"])
    
    with tab1:
        with st.form("login_form"):
            uid = st.text_input("아이디")
            upw = st.text_input("비밀번호", type="password")
            submit = st.form_submit_button("로그인")
            
            if submit:
                if uid == "admin" and upw == "1234": # 비상용 로그인 (필요시 삭제)
                    st.session_state.logged_in = True
                    st.session_state.username = "admin"
                    st.session_state.role = "admin"
                    st.rerun()
                
                success, msg, role = login_user(uid, upw)
                if success:
                    st.session_state.logged_in = True
                    st.session_state.username = uid
                    st.session_state.role = role
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

# --- 메인 실행부 ---
if __name__ == '__main__':
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        
    if st.session_state.logged_in:
        # 여기에 main_app() 호출 로직 추가 (기존 코드의 main_app 함수 내용)
        st.write(f"반갑습니다, {st.session_state.username}님!") 
        # 실제 운영시는 main_app()을 실행하세요.
    else:
        login_page()
