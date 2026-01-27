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

    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        if st.button("🔄 시트 데이터 새로고침"):
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

    tabs = st.tabs(["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리"])

    # --- 1. 재고 관리 ---
    with tabs[0]:
        with st.expander("➕ 새 장비 등록"):
            with st.form("add_form", clear_on_submit=True):
                col1, col2, col3 = st.columns([1,2,1])
                t, n, q = col1.text_input("타입"), col2.text_input("장비명"), col3.number_input("수량", 1)
                b = st.text_input("브랜드")
                if st.form_submit_button("등록"):
                    new_item = {'ID': str(uuid.uuid4()), '타입': t, '이름': n, '수량': q, '브랜드': b, '대여여부': '재고'}
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_item])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    st.rerun()
        edit_m = st.toggle("🔓 수정 모드")
        edited = st.data_editor(st.session_state.df, disabled=(not edit_m), hide_index=True, use_container_width=True)
        if edit_m and st.button("💾 모든 변경사항 저장"):
            save_data(edited, "Sheet1"); st.session_state.df = edited; st.success("저장 완료"); st.rerun()

    # --- 2. 외부 대여 (에러 방지 강화) ---
    with tabs[1]:
        st.subheader("📤 외부 업체 대여")
        # 수량이 0보다 큰 재고만 필터링
        stock = st.session_state.df[(st.session_state.df['대여여부'] == '재고') & (st.session_state.df['수량'].astype(int) > 0)]
        
        if not stock.empty:
            opts = stock.apply(lambda x: f"{x['이름']} ({x['브랜드']}) - 잔여: {x['수량']}개", axis=1)
            sel_key = st.selectbox("대여할 장비 선택", opts.index, format_func=lambda x: opts[x])
            
            with st.form("rent_form"):
                tgt = st.text_input("대여 업체명")
                max_qty = int(stock.loc[sel_key, '수량'])
                qty = st.number_input("수량", 1, max_qty)
                r_date = st.date_input("반납 예정일")
                
                # [중요] 모든 입력 폼에는 submit 버튼이 폼 안에 있어야 에러가 나지 않습니다.
                btn = st.form_submit_button("대여 처리 확정")
                
                if btn:
                    if not tgt:
                        st.error("업체명을 입력해주세요.")
                    else:
                        item = stock.loc[sel_key]
                        # 1. 기존 재고 수량 차감
                        st.session_state.df.at[sel_key, '수량'] -= qty
                        # 2. 대여 데이터 생성
                        new_r = item.copy()
                        new_r.update({
                            'ID': str(uuid.uuid4()), 
                            '수량': qty, 
                            '대여여부': '대여 중', 
                            '대여자': tgt, 
                            '대여일': datetime.now().strftime("%Y-%m-%d"), 
                            '반납예정일': str(r_date)
                        })
                        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_r])], ignore_index=True)
                        save_data(st.session_state.df, "Sheet1")
                        log_transaction("대여", item['이름'], qty, tgt, datetime.now().strftime("%Y-%m-%d"), str(r_date))
                        st.success("대여 처리가 완료되었습니다.")
                        st.rerun()
        else:
            st.warning("현재 대여 가능한 수량이 있는 재고가 없습니다.")

    # --- 나머지 탭 로직 (내역 관리 등) ---
    with tabs[5]:
        st.subheader("📜 활동 기록")
        log_view = load_data("Logs")
        if not log_view.empty:
            st.dataframe(log_view.iloc[::-1], use_container_width=True)

# 4. 실행부
def login_page():
    st.title("🔒 통합 장비 관리 시스템 로그인")
    with st.form("login_form"):
        u, p = st.text_input("아이디"), st.text_input("비밀번호", type="password")
        if st.form_submit_button("로그인"):
            if u == "admin" and p == "1234":
                st.session_state.logged_in, st.session_state.username, st.session_state.role = True, u, "admin"
                st.rerun()
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
