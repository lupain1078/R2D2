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
        df = df.fillna("")
        # [수정] 모든 수량 데이터를 정수(int)로 강제 변환
        if not df.empty and '수량' in df.columns:
            df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0).astype(int)
        return df
    except:
        return pd.DataFrame(columns=FIELD_NAMES if sheet_name=="Sheet1" else [])

def save_data(df, sheet_name="Sheet1"):
    # 저장 전 수량 데이터 정수화 확인
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
        if st.button("🔄 시트 데이터 새로고침"):
            st.session_state.df = load_data("Sheet1")
            st.rerun()
        if st.button("🚪 로그아웃"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    st.title("🛠️ 통합 장비 관리 시스템")

    # [수정] 상단 지표 소수점 제거 (.0 제거)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", int(df[df['대여여부'] == '대여 중']['수량'].sum()) if not df.empty else 0)
    c2.metric("🎬 현장 출고", int(df[df['대여여부'] == '현장 출고']['수량'].sum()) if not df.empty else 0)
    c3.metric("🛠️ 수리 중", int(df[df['대여여부'] == '수리 중']['수량'].sum()) if not df.empty else 0)
    c4.metric("💔 파손", int(df[df['대여여부'] == '파손']['수량'].sum()) if not df.empty else 0)

    tabs = st.tabs(["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리"])

    # --- 1. 재고 관리 ---
    with tabs[0]:
        with st.expander("➕ 새 장비 등록"):
            with st.form("add_form", clear_on_submit=True):
                col1, col2, col3 = st.columns([1,2,1])
                t, n, q = col1.text_input("타입"), col2.text_input("장비명"), col3.number_input("수량", 1, step=1)
                b = st.text_input("브랜드")
                if st.form_submit_button("등록"):
                    new_item = {'ID': str(uuid.uuid4()), '타입': t, '이름': n, '수량': int(q), '브랜드': b, '대여여부': '재고'}
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_item])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    st.rerun()
        
        edit_mode = st.toggle("🔓 수정 모드")
        # 데이터 에디터에서도 정수형 유지
        edited = st.data_editor(st.session_state.df, disabled=(not edit_mode), hide_index=True, use_container_width=True)
        if edit_mode and st.button("💾 모든 변경사항 저장"):
            save_data(edited, "Sheet1"); st.session_state.df = edited; st.success("저장 완료"); st.rerun()

    # --- 2. 외부 대여 (필터링 강화 및 소수점 제거) ---
    with tabs[1]:
        st.subheader("📤 외부 업체 대여")
        # [핵심수정] '재고' 텍스트 공백 제거 및 대소문자 무시 필터링
        stock = st.session_state.df[
            (st.session_state.df['대여여부'].str.strip() == '재고') & 
            (st.session_state.df['수량'].astype(int) > 0)
        ]
        
        if not stock.empty:
            opts = stock.apply(lambda x: f"{x['이름']} ({x['브랜드']}) - 잔여: {int(x['수량'])}개", axis=1)
            sel_idx = st.selectbox("대여할 장비 선택", opts.index, format_func=lambda x: opts[x])
            
            with st.form("rent_form"):
                target = st.text_input("대여 업체명")
                max_q = int(stock.loc[sel_idx, '수량'])
                qty = st.number_input("수량", 1, max_q, step=1)
                r_date = st.date_input("반납 예정일")
                if st.form_submit_button("대여 확정"):
                    item = stock.loc[sel_idx]
                    st.session_state.df.at[sel_idx, '수량'] -= int(qty)
                    new_r = item.copy()
                    new_r.update({'ID': str(uuid.uuid4()), '수량': int(qty), '대여여부': '대여 중', '대여자': target, '대여일': datetime.now().strftime("%Y-%m-%d"), '반납예정일': str(r_date)})
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_r])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    log_transaction("대여", item['이름'], qty, target, datetime.now().strftime("%Y-%m-%d"), str(r_date))
                    st.success("대여 완료"); st.rerun()
        else:
            st.warning("대여 가능한 '재고' 상태의 장비가 없습니다. 시트의 '대여여부' 칸에 '재고'라고 정확히 적혀있는지 확인하세요.")

    # --- 3. 반납 (목록 필터링 강화) ---
    with tabs[3]:
        st.subheader("📥 장비 반납")
        rented = st.session_state.df[st.session_state.df['대여여부'].str.strip().isin(['대여 중', '현장 출고'])]
        if not rented.empty:
            r_opts = rented.apply(lambda x: f"[{x['대여여부']}] {x['이름']} - {x['대여자']} ({int(x['수량'])}개)", axis=1)
            sel_ret = st.selectbox("반납할 장비 선택", r_opts.index, format_func=lambda x: r_opts[x])
            if st.button("반납 확정"):
                item = rented.loc[sel_ret]
                mask = (st.session_state.df['이름'] == item['이름']) & (st.session_state.df['브랜드'] == item['브랜드']) & (st.session_state.df['대여여부'].str.strip() == '재고')
                if any(mask):
                    st.session_state.df.loc[mask, '수량'] += int(item['수량'])
                    st.session_state.df = st.session_state.df.drop(sel_ret).reset_index(drop=True)
                else:
                    st.session_state.df.at[sel_ret, '대여여부'] = '재고'; st.session_state.df.at[sel_ret, '대여자'] = ''
                save_data(st.session_state.df, "Sheet1")
                log_transaction("반납", item['이름'], item['수량'], item['대여자'], datetime.now().strftime("%Y-%m-%d"))
                st.success("반납 완료"); st.rerun()

# (이하 로그인 및 실행 로직 동일)
