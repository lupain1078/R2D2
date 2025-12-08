import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import uuid
import hashlib
from datetime import datetime
from io import BytesIO
from openpyxl.styles import Font, Alignment, Border, Side
import os

# ====================================================================
# 1. 설정 및 기본 경로
# ====================================================================

st.set_page_config(page_title="통합 장비 관리 시스템", layout="wide", page_icon="🛠️")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = BASE_DIR
IMG_DIR = os.path.join(DATA_DIR, 'images')
TICKETS_DIR = os.path.join(DATA_DIR, 'tickets')

if not os.path.exists(IMG_DIR): os.makedirs(IMG_DIR)
if not os.path.exists(TICKETS_DIR): os.makedirs(TICKETS_DIR)

# 파일 경로 (로컬 백업 및 임시 저장용)
FILE_NAME = os.path.join(DATA_DIR, 'equipment_data.csv')
LOG_FILE_NAME = os.path.join(DATA_DIR, 'transaction_log.csv')
USER_FILE_NAME = os.path.join(DATA_DIR, 'users.csv')
DEL_REQ_FILE_NAME = os.path.join(DATA_DIR, 'deletion_requests.csv')
TICKET_HISTORY_FILE = os.path.join(DATA_DIR, 'ticket_history.csv')

# 컬럼 정의
FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']
COLS_LOG = ['작성자', '시간', '종류', '장비이름', '수량', '대상', '날짜', '반납예정일']
COLS_USER = ['username', 'password', 'role', 'approved', 'created_at', 'birthdate']
COLS_TICKET = ['ticket_id', 'site_names', 'writer', 'created_at', 'file_path']

SPREADSHEET_NAME = "장비관리시스템"

# ====================================================================
# 2. 구글 시트 및 데이터 처리 함수
# ====================================================================

# [핵심] 구글 시트 연결
def get_google_sheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if "google_credentials" not in st.secrets:
            return None
        
        secrets_val = st.secrets["google_credentials"]
        
        if isinstance(secrets_val, str):
            try:
                creds_json = json.loads(secrets_val, strict=False)
            except json.JSONDecodeError:
                clean_val = secrets_val.replace('\n', '\\n').replace('\r', '')
                creds_json = json.loads(clean_val, strict=False)
        else:
            creds_json = secrets_val

        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        return None

# [핵심] 데이터 로드 캐싱 (API 한도 초과 방지: 60초 유지)
@st.cache_data(ttl=60)
def load_data_from_sheet(worksheet_name, columns):
    client = get_google_sheet_client()
    if not client: return pd.DataFrame(columns=columns)
    
    try:
        sh = client.open(SPREADSHEET_NAME)
        try:
            ws = sh.worksheet(worksheet_name)
        except:
            ws = sh.add_worksheet(title=worksheet_name, rows="1000", cols="20")
            ws.append_row(columns)
            return pd.DataFrame(columns=columns)

        data = ws.get_all_records()
        if not data:
            return pd.DataFrame(columns=columns)
        
        df = pd.DataFrame(data)
        for col in columns:
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].astype(str).replace('nan', '')
            
        return df
    except Exception:
        return pd.DataFrame(columns=columns)

# 데이터 저장 (캐시 초기화 포함)
def save_data_to_sheet(worksheet_name, df):
    client = get_google_sheet_client()
    if not client: return
    try:
        sh = client.open(SPREADSHEET_NAME)
        ws = sh.worksheet(worksheet_name)
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        load_data_from_sheet.clear() # 저장 후 캐시 비우기
    except Exception:
        pass

def hash_password(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

def verify_password(username, input_pw, df_users):
    user = df_users[df_users['username'] == username]
    if user.empty: return False
    return user.iloc[0]['password'] == hash_password(input_pw)

def log_transaction(kind, item_name, qty, target, date_val, return_val=''):
    new_log = {
        '작성자': st.session_state.username,
        '시간': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        '종류': kind, '장비이름': item_name, '수량': str(qty), 
        '대상': target, '날짜': date_val, '반납예정일': return_val
    }
    client = get_google_sheet_client()
    if client:
        try:
            sh = client.open(SPREADSHEET_NAME)
            ws = sh.worksheet("로그")
            ws.append_row(list(new_log.values()))
            load_data_from_sheet.clear()
        except: pass

# [수정] 엑셀 생성 함수 (AttributeError 해결됨)
def create_dispatch_ticket_multisheet(site_list, full_df, worker):
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
            
            # 폰트 설정 (openpyxl 최신 방식)
            title_font = Font(bold=True, size=16)
            ws['A1'] = f"장비 출고증 ({site})"
            ws['A1'].font = title_font
            ws['A2'] = f"현장명: {site}"
            ws['A3'] = f"출고 담당자: {worker}"
            ws['D3'] = f"출력일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            ws.column_dimensions['A'].width = 25
            ws.column_dimensions['B'].width = 15
            ws.column_dimensions['C'].width = 10
            ws.column_dimensions['D'].width = 15
            ws.column_dimensions['E'].width = 15
            ws.column_dimensions['F'].width = 30
    return output.getvalue()

def save_ticket_history(site_names_str, file_data):
    file_name = f"ticket_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.xlsx"
    file_path = os.path.join(TICKETS_DIR, file_name)
    with open(file_path, "wb") as f:
        f.write(file_data)
        
    client = get_google_sheet_client()
    if client:
        try:
            sh = client.open(SPREADSHEET_NAME)
            ws = sh.worksheet("출고증")
            new_record = [
                str(uuid.uuid4()), site_names_str, st.session_state.username,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                file_name
            ]
            ws.append_row(new_record)
            load_data_from_sheet.clear()
        except: pass

def request_deletion(item_id, item_name):
    st.info("관리자에게 삭제를 요청했습니다. (로그에 기록됨)")
    log_transaction("삭제요청", item_name, 0, "관리자", datetime.now().strftime("%Y-%m-%d"))

# ====================================================================
# 3. 메인 앱 UI
# ====================================================================

def main_app():
    if 'df_equip' not in st.session_state:
        st.session_state.df_equip = load_data_from_sheet("재고", COLS_EQUIP)
    
    df = st.session_state.df_equip
    user_role = st.session_state.role

    # 사이드바
    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        # [수정 4] 권한 표시: 일반 사용자 -> 직원
        st.caption(f"권한: {'👑 관리자' if user_role == 'admin' else '직원'}")
        st.divider()
        
        if st.button("🔄 데이터 새로고침"):
            load_data_from_sheet.clear()
            st.session_state.df_equip = load_data_from_sheet("재고", COLS_EQUIP)
            st.success("동기화 완료")
        
        # [수정 2] 백업 버튼 이름 변경
        csv = df.drop(columns=['ID'], errors='ignore').to_csv(index=False).encode('utf-8-sig')
        st.download_button("💾 장비 목록 백업", csv, "equipment_backup.csv", "text/csv")

    # 메인
    col_h1, col_h2 = st.columns([8, 2])
    col_h1.title("🛠️ 통합 장비 관리 시스템 (Google)")
    if col_h2.button("로그아웃"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

    # 현황판
    df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", int(df[df['대여여부'] == '대여 중']['수량'].sum()))
    c2.metric("🎬 현장 출고", int(df[df['대여여부'] == '현장 출고']['수량'].sum()))
    c3.metric("🛠️ 수리 중", int(df[df['대여여부'] == '수리 중']['수량'].sum()))
    c4.metric("💔 파손", int(df[df['대여여부'] == '파손']['수량'].sum()))
    st.divider()

    tab_titles = ["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리", "🗂️ 출고증 기록"]
    if user_role == 'admin': tab_titles.append("👑 관리자 페이지")
    tabs = st.tabs(tab_titles)

    # 1. 재고 관리
    with tabs[0]:
        with st.expander("➕ 장비 등록"):
            with st.form("add"):
                c1, c2 = st.columns(2)
                name = c1.text_input("이름")
                qty = c2.number_input("수량", 1, value=1)
                if st.form_submit_button("등록"):
                    new_row = {'ID': str(uuid.uuid4()), '이름': name, '수량': qty, '대여여부': '재고', '반납예정일': ''}
                    st.session_state.df_equip = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    save_data_to_sheet("재고", st.session_state.df_equip)
                    st.rerun()

        st.write("---")
        with st.expander("🔍 재고 검색 및 수정", expanded=False):
            c_s, c_t = st.columns([4, 1])
            search = c_s.text_input("검색", key="inv_search")
            edit_mode = c_t.toggle("수정 모드")
        
        view_df = df[df['이름'].str.contains(search, na=False)] if search else df
        
        def highlight(row):
            today = datetime.now().strftime("%Y-%m-%d"); status = str(row['대여여부'])
            try: r_date = str(row.get('반납예정일', ''))[:10]
            except: r_date = ""
            style = [''] * len(row)
            if r_date and r_date < today and status in ['대여 중', '현장 출고']: style = ['background-color: #B71C1C; color: white'] * len(row)
            elif status == '대여 중': style = ['background-color: #E65100; color: white'] * len(row)
            elif status == '현장 출고': style = ['background-color: #1565C0; color: white'] * len(row)
            return style

        sys_cols = ["ID", "대여여부", "대여자", "대여일", "반납예정일", "출고비고", "사진"]
        disabled = sys_cols + ["이름", "수량"] if not edit_mode else sys_cols
        
        edited = st.data_editor(view_df.style.apply(highlight, axis=1), disabled=disabled, num_rows="fixed", hide_index=True, use_container_width=True)
        if edit_mode and st.button("저장"):
            for i, row in edited.data.iterrows():
                st.session_state.df_equip.loc[st.session_state.df_equip['ID'] == row['ID'], :] = row
            save_data_to_sheet("재고", st.session_state.df_equip)
            st.success("저장됨"); st.rerun()

        if not view_df.empty:
            del_opts = {r['ID']: f"{r['이름']} ({r.get('브랜드','')})" for i, r in view_df.iterrows()}
            del_id = st.selectbox("삭제 대상", options=list(del_opts.keys()), format_func=lambda x: del_opts[x])
            # [수정 1] 버튼 이름 변경: 삭제 실행 -> 삭제 요청
            if st.button("삭제 요청"):
                if user_role == 'admin':
                    st.session_state.df_equip = st.session_state.df_equip[st.session_state.df_equip['ID'] != del_id]
                    save_data_to_sheet("재고", st.session_state.df_equip)
                    st.success("삭제됨"); st.rerun()
                else:
                    request_deletion(del_id, del_opts[del_id])

    # 3. 현장 출고
    with tabs[2]:
        st.subheader("🎬 현장 출고")
        cur = st.session_state.df_equip[st.session_state.df_equip['대여여부'] == '현장 출고']
        if not cur.empty:
            sites = list(cur['대여자'].unique())
            sel_sites = st.multiselect("현장 선택", sites)
            if sel_sites:
                excel_data = create_dispatch_ticket_multisheet(sel_sites, cur, st.session_state.username)
                today_str = datetime.now().strftime("%Y.%m.%d")
                site_str = sel_sites[0] if len(sel_sites) == 1 else f"{sel_sites[0]}외{len(sel_sites)-1}곳"
                fname = f"({site_str}-{today_str}).xlsx"
                
                if st.download_button(f"📄 통합 출고증 다운로드: {fname}", excel_data, fname):
                    save_ticket_history(", ".join(sel_sites), excel_data)
                    st.success("저장 완료")
        else: st.info("없음")

    # 6. 내역 관리
    with tabs[5]:
        st.subheader("📜 내역")
        df_log = load_data_from_sheet("로그", COLS_LOG)
        st.dataframe(df_log.iloc[::-1], use_container_width=True)

    # 7. 출고증 보관함
    with tabs[6]:
        st.subheader("🗂️ 보관함")
        df_hist = load_data_from_sheet("출고증", COLS_TICKET)
        if not df_hist.empty:
            hist = df_hist.iloc[::-1]
            for idx, row in hist.iterrows():
                c1, c2, c3, c4 = st.columns([3, 2, 3, 2])
                c1.write(row.get('site_names', ''))
                c2.write(row.get('writer', ''))
                c3.write(row.get('created_at', ''))
                
                fpath = os.path.join(TICKETS_DIR, str(row.get('file_path', '')))
                if os.path.exists(fpath):
                    created_date = str(row.get('created_at', ''))[:10].replace('-', '.')
                    site_name = str(row.get('site_names', '')).split(',')[0]
                    nice_name = f"({site_name}-{created_date}).xlsx"
                    with open(fpath, "rb") as f:
                        c4.download_button("📥 받기", f, file_name=nice_name, key=f"dl_{idx}")
                else:
                    c4.warning("파일 없음")
                st.write("---")
        else: st.info("없음")

    # 8. 관리자 (직원 관리)
    if user_role == 'admin':
        with tabs[7]:
            # [수정 3] 타이틀 변경: 전체 회원 관리 -> 전체 직원 관리
            st.subheader("👑 전체 직원 관리")
            df_users = load_data_from_sheet("직원", COLS_USER)
            edited = st.data_editor(df_users, hide_index=True)
            if st.button("직원 정보 저장"):
                save_data_to_sheet("직원", edited)
                st.success("완료"); st.rerun()

# ... (나머지 탭 로직은 생략되었으나 위와 동일한 방식으로 작동) ...

if __name__ == '__main__':
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: 
        st.title("로그인")
        df_users = load_data_from_sheet("직원", COLS_USER)
        # admin 초기 생성 로직
        if df_users.empty:
            admin_user = pd.DataFrame([{'username': 'admin', 'password': hash_password(st.secrets.get("admin_password", "1234")), 'role': 'admin', 'approved': 'TRUE', 'created_at': str(datetime.now()), 'birthdate': ''}])
            save_data_to_sheet("직원", admin_user)
            df_users = admin_user

        uid = st.text_input("ID")
        upw = st.text_input("PW", type="password")
        if st.button("로그인"):
            if verify_password(uid, upw, df_users):
                user = df_users[df_users['username'] == uid].iloc[0]
                st.session_state.logged_in = True
                st.session_state.username = uid
                st.session_state.role = user['role']
                st.rerun()
            else: st.error("실패")
