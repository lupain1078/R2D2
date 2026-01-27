import streamlit as st
import pandas as pd
import os
import uuid
import hashlib
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# 1. 설정 및 구글 시트 연결
st.set_page_config(page_title="통합 장비 관리 시스템", layout="wide", page_icon="🛠️")
conn = st.connection("gsheets", type=GSheetsConnection)

FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']

# 2. 데이터 처리 함수 (정수화 및 공백 제거 필수 적용)
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
        new_log = {
            '시간': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            '작성자': st.session_state.get('username', 'system'),
            '종류': kind, '장비이름': item_name, '수량': int(qty), 
            '대상': target, '날짜': date_val, '반납예정일': return_val
        }
        log_df = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
        save_data(log_df, "Logs")
    except: pass

# 3. 메인 앱 UI
def main_app():
    if 'df' not in st.session_state:
        st.session_state.df = load_data("Sheet1")
    
    df = st.session_state.df

    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        if st.button("🔄 데이터 새로고침"):
            st.session_state.df = load_data("Sheet1")
            st.rerun()
        if st.button("🚪 로그아웃"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    st.title("🛠️ 통합 장비 관리 시스템")

    # 상단 요약 지표 (정수 표시)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", int(df[df['대여여부'].str.strip() == '대여 중']['수량'].sum()) if not df.empty else 0)
    c2.metric("🎬 현장 출고", int(df[df['대여여부'].str.strip() == '현장 출고']['수량'].sum()) if not df.empty else 0)
    c3.metric("🛠️ 수리 중", int(df[df['대여여부'].str.strip() == '수리 중']['수량'].sum()) if not df.empty else 0)
    c4.metric("💔 파손", int(df[df['대여여부'].str.strip() == '파손']['수량'].sum()) if not df.empty else 0)

    # 탭 메뉴 구성 (관리자 전용 탭 추가)
    tab_list = ["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리"]
    if st.session_state.username == "admin":
        tab_list.append("👑 관리자 페이지")
    
    tabs = st.tabs(tab_list)

    # --- 기존 탭 로직 (0~5번) ---
    with tabs[0]: # 재고 관리
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

    # (중략: 대여, 출고, 반납, 수리 탭 로직은 보내주신 코드와 동일하게 유지)
    with tabs[1]: st.subheader("📤 외부 업체 대여") # 생략 가능 (원본 로직 유지)
    with tabs[2]: st.subheader("🎬 현장 출고") # 생략 가능 (원본 로직 유지)
    with tabs[3]: st.subheader("📥 장비 반납 처리") # 생략 가능 (원본 로직 유지)
    with tabs[4]: st.subheader("🛠️ 수리 및 파손") # 생략 가능 (원본 로직 유지)
    with tabs[5]: 
        st.subheader("📜 활동 기록")
        st.dataframe(load_data("Logs").iloc[::-1], use_container_width=True)

    # --- 👑 6번 탭: 관리자 전용 페이지 (신규 추가) ---
    if st.session_state.username == "admin":
        with tabs[6]:
            st.header("👑 관리자 페이지")
            u_df = load_data("Users")
            
            # 승인 대기 명단 추출
            st.subheader("⏳ 승인 대기")
            pending = u_df[u_df['approved'].astype(str).str.upper() == 'FALSE']
            
            if not pending.empty:
                for idx, row in pending.iterrows():
                    c1, c2, c3 = st.columns([3, 1, 1])
                    c1.write(f"🆔 **{row['username']}** | 권한: {row['role']}")
                    if c2.button("✅ 승인", key=f"ok_{idx}"):
                        u_df.at[idx, 'approved'] = 'TRUE'
                        save_data(u_df, "Users")
                        st.success(f"{row['username']} 승인됨"); st.rerun()
                    if c3.button("❌ 거절", key=f"no_{idx}"):
                        u_df = u_df.drop(idx)
                        save_data(u_df, "Users")
                        st.warning("거절됨"); st.rerun()
            else:
                st.info("대기 중인 회원이 없습니다.")

            st.write("---")
            st.subheader("👥 전체 회원 목록")
            st.dataframe(u_df, use_container_width=True, hide_index=True)

# 4. 로그인 및 실행부
def login_page():
    st.title("🔒 통합 장비 관리 시스템 로그인")
    with st.form("login"):
        u, p = st.text_input("ID"), st.text_input("PW", type="password")
        if st.form_submit_button("로그인"):
            if u == "admin" and p == "1234":
                st.session_state.logged_in, st.session_state.username = True, u
                st.rerun()
            u_df = load_data("Users")
            hp = hashlib.sha256(p.encode()).hexdigest()
            # [수정] 아이디/비번 매칭 및 승인 여부 동시 확인
            user = u_df[(u_df['username'].astype(str) == str(u)) & (u_df['password'].astype(str) == str(hp))]
            if not user.empty:
                if str(user.iloc[0]['approved']).upper() == 'TRUE':
                    st.session_state.logged_in, st.session_state.username = True, u
                    st.rerun()
                else: st.error("관리자 승인이 필요한 계정입니다.")
            else: st.error("로그인 정보가 틀렸습니다.")

if __name__ == '__main__':
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: login_page()
