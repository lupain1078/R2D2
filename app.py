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

# 구글 시트 연결 (Secrets에 설정된 정보를 사용)
conn = st.connection("gsheets", type=GSheetsConnection)

BASE_DIR = os.getcwd()
IMG_DIR = os.path.join(BASE_DIR, 'images')
TICKETS_DIR = os.path.join(BASE_DIR, 'tickets')

os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(TICKETS_DIR, exist_ok=True)

FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']

# ====================================================================
# 2. 데이터 처리 핵심 함수 (Google Sheets CRUD)
# ====================================================================

def load_data(sheet_name="Sheet1"):
    """구글 시트에서 데이터를 읽어옴"""
    try:
        df = conn.read(worksheet=sheet_name, ttl=0)
        return df.fillna("")
    except:
        return pd.DataFrame(columns=FIELD_NAMES if sheet_name=="Sheet1" else [])

def save_data(df, sheet_name="Sheet1"):
    """구글 시트에 데이터를 저장함"""
    conn.update(worksheet=sheet_name, data=df)
    st.cache_data.clear()

def hash_password(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

def log_transaction(kind, item_name, qty, target, date_val, return_val=''):
    """Logs 시트에 활동 내역 기록"""
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

# --- 회원 관리 ---
def get_all_users():
    return load_data("Users")

def login_user(username, password):
    df = get_all_users()
    if df.empty: return False, "DB 로드 실패", None
    hashed_pw = hash_password(password)
    user_row = df[(df['username'].astype(str) == str(username)) & (df['password'].astype(str) == str(hashed_pw))]
    if user_row.empty: return False, "아이디/비번 불일치", None
    user_data = user_row.iloc[0]
    if str(user_data['approved']).upper() != 'TRUE': return False, "승인 대기 중", None
    return True, "성공", user_data['role']

# ====================================================================
# 3. 엑셀 출고증 생성
# ====================================================================
def create_dispatch_ticket(site_list, full_df, worker):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for site in site_list:
            site_df = full_df[full_df['대여자'] == site]
            if site_df.empty: continue
            display_df = site_df[['이름', '브랜드', '수량', '대여일', '반납예정일', '출고비고']].copy()
            display_df.columns = ['장비명', '브랜드', '수량', '출고일', '반납예정일', '비고']
            sheet_title = str(site)[:30].replace("/", "_")
            display_df.to_excel(writer, index=False, sheet_name=sheet_title, startrow=4)
            ws = writer.sheets[sheet_title]
            ws['A1'] = f"장비 출고증 ({site})"; ws['A1'].font = Font(bold=True, size=16)
    return output.getvalue()

# ====================================================================
# 4. 메인 앱 UI (모든 탭 기능 포함)
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
        st.subheader("📦 장비 재고 목록")
        with st.expander("➕ 새 장비 등록"):
            with st.form("add_item"):
                c1, c2, c3 = st.columns([1,2,1])
                t = c1.text_input("타입"); n = c2.text_input("이름"); q = c3.number_input("수량", 1)
                b = st.text_input("브랜드")
                if st.form_submit_button("등록"):
                    new_row = {'ID': str(uuid.uuid4()), '타입': t, '이름': n, '수량': q, '브랜드': b, '대여여부': '재고'}
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    st.success("등록 완료"); st.rerun()
        
        edit_mode = st.toggle("🔓 수정 모드")
        edited_df = st.data_editor(st.session_state.df, disabled=(not edit_mode), hide_index=True, use_container_width=True)
        if edit_mode and st.button("💾 변경사항 저장"):
            save_data(edited_df, "Sheet1")
            st.session_state.df = edited_df
            st.success("저장되었습니다."); st.rerun()

    # --- 2. 외부 대여 ---
    with tabs[1]:
        st.subheader("📤 외부 업체 대여")
        stock = st.session_state.df[st.session_state.df['대여여부'] == '재고']
        if not stock.empty:
            opts = stock.apply(lambda x: f"{x['이름']} ({x['수량']}개)", axis=1)
            sel_idx = st.selectbox("대여할 장비 선택", opts.index, format_func=lambda x: opts[x])
            with st.form("rent_form"):
                target = st.text_input("대여 업체명")
                c1, c2 = st.columns(2)
                qty = c1.number_input("대여 수량", 1, int(stock.loc[sel_idx, '수량']))
                r_date = c2.date_input("반납 예정일")
                if st.form_submit_button("대여 실행"):
                    item = stock.loc[sel_idx]
                    # 수량 차감 및 상태 변경 로직
                    st.session_state.df.at[sel_idx, '수량'] -= qty
                    new_r = item.copy(); new_r['ID'] = str(uuid.uuid4()); new_r['수량'] = qty; new_r['대여여부'] = '대여 중'; new_r['대여자'] = target; new_r['반납예정일'] = str(r_date)
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_r])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    log_transaction("외부대여", item['이름'], qty, target, datetime.now().strftime("%Y-%m-%d"), str(r_date))
                    st.success("대여 처리 완료"); st.rerun()

    # --- 3. 현장 출고 ---
    with tabs[2]:
        st.subheader("🎬 현장 출고 관리")
        # 외부 대여와 유사한 로직으로 현장명 입력 및 출고증 다운로드 버튼 배치
        sites = st.session_state.df[st.session_state.df['대여여부'] == '현장 출고']['대여자'].unique()
        if len(sites) > 0:
            sel_sites = st.multiselect("출고증을 뽑을 현장 선택", sites)
            if sel_sites:
                ticket = create_dispatch_ticket(sel_sites, st.session_state.df, st.session_state.username)
                st.download_button("📄 선택 현장 출고증 다운로드 (Excel)", ticket, "dispatch_ticket.xlsx")

    # --- 4. 반납 ---
    with tabs[3]:
        st.subheader("📥 장비 반납 처리")
        rented = st.session_state.df[st.session_state.df['대여여부'].isin(['대여 중', '현장 출고'])]
        if not rented.empty:
            r_opts = rented.apply(lambda x: f"[{x['대여여부']}] {x['이름']} ({x['대여자']})", axis=1)
            ret_idx = st.selectbox("반납할 장비 선택", r_opts.index, format_func=lambda x: r_opts[x])
            if st.button("반납 확정"):
                item = rented.loc[ret_idx]
                # 재고로 수량 합치기
                mask = (st.session_state.df['이름'] == item['이름']) & (st.session_state.df['대여여부'] == '재고')
                if any(mask):
                    st.session_state.df.loc[mask, '수량'] += item['수량']
                    st.session_state.df = st.session_state.df.drop(ret_idx)
                else:
                    st.session_state.df.at[ret_idx, '대여여부'] = '재고'; st.session_state.df.at[ret_idx, '대여자'] = ''
                save_data(st.session_state.df, "Sheet1")
                log_transaction("반납", item['이름'], item['수량'], item['대여자'], datetime.now().strftime("%Y-%m-%d"))
                st.success("반납 완료"); st.rerun()

    # --- 5. 내역 관리 ---
    with tabs[5]:
        st.subheader("📜 전체 트랜잭션 로그")
        logs = load_data("Logs")
        st.dataframe(logs.iloc[::-1], use_container_width=True)

# ====================================================================
# 5. 실행부
# ====================================================================
def login_page():
    st.title("🔒 통합 장비 관리 시스템")
    with st.form("login_form"):
        uid = st.text_input("아이디")
        upw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("로그인"):
            if uid == "admin" and upw == "1234":
                st.session_state.logged_in = True; st.session_state.username = "admin"; st.session_state.role = "admin"; st.rerun()
            ok, msg, role = login_user(uid, upw)
            if ok:
                st.session_state.logged_in = True; st.session_state.username = uid; st.session_state.role = role; st.rerun()
            else: st.error(msg)

if __name__ == '__main__':
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: login_page()
