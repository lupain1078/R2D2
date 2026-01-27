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
    # 수량 데이터가 문자열로 저장될 경우를 대비해 숫자로 변환 후 합산
    c1.metric("🚚 대여 중", pd.to_numeric(df[df['대여여부'] == '대여 중']['수량'], errors='coerce').sum() if not df.empty else 0)
    c2.metric("🎬 현장 출고", pd.to_numeric(df[df['대여여부'] == '현장 출고']['수량'], errors='coerce').sum() if not df.empty else 0)
    c3.metric("🛠️ 수리 중", pd.to_numeric(df[df['대여여부'] == '수리 중']['수량'], errors='coerce').sum() if not df.empty else 0)
    c4.metric("💔 파손", pd.to_numeric(df[df['대여여부'] == '파손']['수량'], errors='coerce').sum() if not df.empty else 0)

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
                    st.success("등록 완료"); st.rerun()
        
        edit_mode = st.toggle("🔓 수정 모드")
        edited = st.data_editor(st.session_state.df, disabled=(not edit_mode), hide_index=True, use_container_width=True)
        if edit_mode and st.button("💾 시트에 데이터 저장"):
            save_data(edited, "Sheet1"); st.session_state.df = edited; st.success("저장 완료"); st.rerun()

    # --- 2. 현장 출고 (데이터를 '현장 출고' 상태로 생성) ---
    with tabs[2]:
        st.subheader("🎬 현장 출고 처리")
        stock = st.session_state.df[(st.session_state.df['대여여부'] == '재고') & (st.session_state.df['수량'].astype(int) > 0)]
        if not stock.empty:
            opts = stock.apply(lambda x: f"{x['이름']} ({x['브랜드']}) - 잔여: {x['수량']}개", axis=1)
            sel_idx = st.selectbox("출고할 장비 선택", opts.index, format_func=lambda x: opts[x])
            with st.form("dispatch_form"):
                site = st.text_input("현장명")
                qty = st.number_input("수량", 1, int(stock.loc[sel_idx, '수량']))
                r_date = st.date_input("반납 예정일", key="dispatch_ret_date")
                if st.form_submit_button("현장 출고 확정"):
                    item = stock.loc[sel_idx]
                    st.session_state.df.at[sel_idx, '수량'] -= qty
                    new_d = item.copy()
                    new_d.update({'ID': str(uuid.uuid4()), '수량': qty, '대여여부': '현장 출고', '대여자': site, '대여일': datetime.now().strftime("%Y-%m-%d"), '반납예정일': str(r_date)})
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_d])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    log_transaction("현장출고", item['이름'], qty, site, datetime.now().strftime("%Y-%m-%d"), str(r_date))
                    st.success("현장 출고 처리가 완료되었습니다."); st.rerun()
        else: st.warning("출고 가능한 재고가 없습니다.")

    # --- 3. 반납 처리 (반납 목록 누락 문제 해결) ---
    with tabs[3]:
        st.subheader("📥 장비 반납")
        # [핵심수정] '대여 중' 뿐만 아니라 '현장 출고' 상태인 모든 장비를 불러옵니다.
        rented = st.session_state.df[st.session_state.df['대여여부'].isin(['대여 중', '현장 출고'])]
        
        if not rented.empty:
            r_opts = rented.apply(lambda x: f"[{x['대여여부']}] {x['이름']} - {x['대여자']} ({x['수량']}개)", axis=1)
            sel_ret = st.selectbox("반납할 장비 선택", r_opts.index, format_func=lambda x: r_opts[x])
            
            if st.button("반납 확정"):
                item = rented.loc[sel_ret]
                # 재고로 수량 합치기: 이름과 브랜드가 같은 '재고' 상태의 행을 찾음
                mask = (st.session_state.df['이름'] == item['이름']) & (st.session_state.df['브랜드'] == item['브랜드']) & (st.session_state.df['대여여부'] == '재고')
                
                if any(mask):
                    # 기존 재고 행이 있으면 수량만 더함
                    st.session_state.df.loc[mask, '수량'] = st.session_state.df.loc[mask, '수량'].astype(int) + int(item['수량'])
                    # 대여 중이었던 행은 삭제
                    st.session_state.df = st.session_state.df.drop(sel_ret).reset_index(drop=True)
                else:
                    # 기존 재고 행이 없으면 현재 행을 '재고' 상태로 변경
                    st.session_state.df.at[sel_ret, '대여여부'] = '재고'
                    st.session_state.df.at[sel_ret, '대여자'] = ''
                    st.session_state.df.at[sel_ret, '대여일'] = ''
                    st.session_state.df.at[sel_ret, '반납예정일'] = ''
                
                save_data(st.session_state.df, "Sheet1")
                log_transaction("반납", item['이름'], item['수량'], item['대여자'], datetime.now().strftime("%Y-%m-%d"))
                st.success(f"{item['이름']} 반납 처리가 완료되었습니다."); st.rerun()
        else:
            st.info("현재 대여 중이거나 현장 출고된 장비가 없습니다.")

# --- 로그인 및 실행부 (기존 코드 유지) ---
def login_page():
    st.title("🔒 로그인")
    with st.form("login_form"):
        u, p = st.text_input("아이디"), st.text_input("비밀번호", type="password")
        if st.form_submit_button("로그인"):
            if u == "admin" and p == "1234":
                st.session_state.logged_in, st.session_state.username, st.session_state.role = True, u, "admin"
                st.rerun()
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
