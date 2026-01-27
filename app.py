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
            # 모든 수량을 소수점 없는 정수로 변환
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

    # 탭 구성 (IndexError 해결을 위해 탭 정의를 명확히 함)
    tab_list = ["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리"]
    is_admin = (st.session_state.username == "admin")
    if is_admin:
        tab_list.append("👑 관리자 페이지")
    
    tabs = st.tabs(tab_list)

    # 1. 재고 관리
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

    # 2. 외부 대여
    with tabs[1]:
        st.subheader("📤 외부 업체 대여")
        stock = st.session_state.df[(st.session_state.df['대여여부'].str.strip() == '재고') & (st.session_state.df['수량'] > 0)]
        if not stock.empty:
            opts = stock.apply(lambda x: f"{x['이름']} - 잔여: {int(x['수량'])}개", axis=1)
            sel = st.selectbox("장비 선택", opts.index, format_func=lambda x: opts[x])
            with st.form("rent_form"):
                tgt, qty = st.text_input("대여 업체명"), st.number_input("수량", 1, int(stock.loc[sel, '수량']), step=1)
                r_date = st.date_input("반납 예정일")
                if st.form_submit_button("대여 확정"):
                    item = stock.loc[sel]
                    st.session_state.df.at[sel, '수량'] -= int(qty)
                    new_r = item.copy()
                    new_r.update({'ID': str(uuid.uuid4()), '수량': int(qty), '대여여부': '대여 중', '대여자': tgt, '대여일': datetime.now().strftime("%Y-%m-%d"), '반납예정일': str(r_date)})
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_r])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1"); log_transaction("외부대여", item['이름'], qty, tgt, datetime.now().strftime("%Y-%m-%d"), str(r_date))
                    st.success("대여 완료"); st.rerun()

    # 3. 현장 출고
    with tabs[2]:
        st.subheader("🎬 현장 출고")
        stock_disp = st.session_state.df[(st.session_state.df['대여여부'].str.strip() == '재고') & (st.session_state.df['수량'] > 0)]
        if not stock_disp.empty:
            opts_disp = stock_disp.apply(lambda x: f"{x['이름']} - 잔여: {int(x['수량'])}개", axis=1)
            sel_disp = st.selectbox("출고 선택", opts_disp.index, format_func=lambda x: opts_disp[x])
            with st.form("dispatch_form"):
                site, qty_disp = st.text_input("현장명"), st.number_input("출고 수량", 1, int(stock_disp.loc[sel_disp, '수량']), step=1)
                if st.form_submit_button("출고 확정"):
                    item = stock_disp.loc[sel_disp]
                    st.session_state.df.at[sel_disp, '수량'] -= int(qty_disp)
                    new_d = item.copy()
                    new_d.update({'ID': str(uuid.uuid4()), '수량': int(qty_disp), '대여여부': '현장 출고', '대여자': site, '대여일': datetime.now().strftime("%Y-%m-%d")})
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_d])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1"); log_transaction("현장출고", item['이름'], qty_disp, site, datetime.now().strftime("%Y-%m-%d"))
                    st.success("출고 완료"); st.rerun()

    # 4. 반납 처리 (강력한 필터링 적용)
    with tabs[3]:
        st.subheader("📥 장비 반납 처리")
        rented = st.session_state.df[st.session_state.df['대여여부'].str.strip().isin(['대여 중', '현장 출고'])]
        if not rented.empty:
            r_opts = rented.apply(lambda x: f"[{x['대여여부'].strip()}] {x['이름']} - {x['대여자']} ({int(x['수량'])}개)", axis=1)
            sel_ret = st.selectbox("반납 대상 선택", r_opts.index, format_func=lambda x: r_opts[x])
            if st.button("반납 확정"):
                item = rented.loc[sel_ret]
                mask = (st.session_state.df['이름'] == item['이름']) & (st.session_state.df['대여여부'].str.strip() == '재고')
                if any(mask):
                    idx = st.session_state.df[mask].index[0]
                    st.session_state.df.at[idx, '수량'] = int(st.session_state.df.at[idx, '수량']) + int(item['수량'])
                    st.session_state.df = st.session_state.df.drop(sel_ret).reset_index(drop=True)
                else:
                    st.session_state.df.at[sel_ret, '대여여부'] = '재고'; st.session_state.df.at[sel_ret, '대여자'] = ''
                save_data(st.session_state.df, "Sheet1"); log_transaction("반납", item['이름'], item['수량'], item['대여자'], datetime.now().strftime("%Y-%m-%d"))
                st.success("반납 완료"); st.rerun()
        else: st.info("대상 없음")

    # 5. 수리/파손
    with tabs[4]:
        st.subheader("🛠️ 수리 및 파손")
        m_df = st.session_state.df[st.session_state.df['대여여부'].str.strip().isin(['재고', '수리 중', '파손'])]
        if not m_df.empty:
            m_opts = m_df.apply(lambda x: f"[{x['대여여부'].strip()}] {x['이름']}", axis=1)
            sel_m = st.selectbox("항목 선택", m_opts.index, format_func=lambda x: m_opts[x])
            new_stat = st.selectbox("변경할 상태", ["재고", "수리 중", "파손"])
            if st.button("상태 변경 적용"):
                st.session_state.df.at[sel_m, '대여여부'] = new_stat
                save_data(st.session_state.df, "Sheet1"); st.success("변경 완료"); st.rerun()

    # 6. 내역 관리
    with tabs[5]:
        st.subheader("📜 활동 기록")
        st.dataframe(load_data("Logs").iloc[::-1], use_container_width=True)

    # 7. 관리자 페이지 (IndexError 방지 로직 적용)
    if is_admin:
        with tabs[6]:
            st.header("👑 관리자 페이지")
            u_df = load_data("Users")
            st.subheader("⏳ 승인 대기 회원")
            pending = u_df[u_df['approved'].astype(str).str.upper() == 'FALSE']
            if not pending.empty:
                for idx, row in pending.iterrows():
                    c1, c2, c3 = st.columns([3, 1, 1])
                    c1.write(f"🆔 **{row['username']}** | 가입일: {row.get('created_at', 'N/A')}")
                    if c2.button("✅ 승인", key=f"ok_{idx}"):
                        u_df.at[idx, 'approved'] = 'TRUE'; save_data(u_df, "Users"); st.rerun()
                    if c3.button("❌ 거절", key=f"no_{idx}"):
                        u_df = u_df.drop(idx); save_data(u_df, "Users"); st.rerun()
            else: st.info("대기 중인 회원이 없습니다.")

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
            user = u_df[(u_df['username'].astype(str) == str(u)) & (u_df['password'].astype(str) == str(hp))]
            if not user.empty:
                if str(user.iloc[0]['approved']).upper() == 'TRUE':
                    st.session_state.logged_in, st.session_state.username = True, u; st.rerun()
                else: st.error("승인 대기 중")
            else: st.error("정보 불일치")

if __name__ == '__main__':
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: login_page()
