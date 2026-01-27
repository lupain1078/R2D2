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

# 연결 시도 중 에러가 나면 화면에 표시되도록 설정
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"구글 시트 연결 설정 오류: {e}")
    st.stop()

FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']

# 2. 데이터 처리 함수 (모든 수량 정수화)
def load_data(sheet_name="Sheet1"):
    try:
        df = conn.read(worksheet=sheet_name, ttl=0)
        df = df.fillna("")
        if not df.empty and '수량' in df.columns:
            df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0).astype(int)
        return df
    except Exception as e:
        st.error(f"'{sheet_name}' 탭을 읽어오지 못했습니다: {e}")
        return pd.DataFrame(columns=FIELD_NAMES if sheet_name=="Sheet1" else [])

def save_data(df, sheet_name="Sheet1"):
    if '수량' in df.columns:
        df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0).astype(int)
    conn.update(worksheet=sheet_name, data=df)
    st.cache_data.clear()

# 3. 메인 앱 화면 (상세 로직 생략 - 이전과 동일)
def main_app():
    if 'df' not in st.session_state:
        st.session_state.df = load_data("Sheet1")
    
    df = st.session_state.df
    # ... (중략: 이전 로직 사용) ...
    st.title("🛠️ 통합 장비 관리 시스템")
    st.write(f"접속 중인 아이디: {st.session_state.username}")
    # 여기에 탭 로직들을 넣으세요

# 4. 로그인 화면
def login_page():
    st.title("🔒 통합 장비 관리 시스템")
    # [수정] 폼 외부에 에러 메시지가 뜰 수 있도록 구성
    with st.form("login_form"):
        u = st.text_input("아이디")
        p = st.text_input("비밀번호", type="password")
        if st.form_submit_button("로그인"):
            if u == "admin" and p == "1234":
                st.session_state.logged_in, st.session_state.username, st.session_state.role = True, u, "admin"
                st.rerun()
            try:
                u_df = load_data("Users")
                hp = hashlib.sha256(p.encode()).hexdigest()
                user = u_df[(u_df['username'].astype(str) == str(u)) & (u_df['password'].astype(str) == str(hp))]
                if not user.empty and str(user.iloc[0]['approved']).upper() == 'TRUE':
                    st.session_state.logged_in, st.session_state.username, st.session_state.role = True, u, user.iloc[0]['role']
                    st.rerun()
                else: st.error("로그인 실패 또는 승인 대기 중")
            except:
                st.error("사용자 정보를 불러올 수 없습니다. 구글 시트의 'Users' 탭을 확인하세요.")

if __name__ == '__main__':
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    if st.session_state.logged_in:
        main_app()
    else:
        login_page()
