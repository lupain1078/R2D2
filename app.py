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

FILE_NAME = os.path.join(DATA_DIR, 'equipment_data.csv')
LOG_FILE_NAME = os.path.join(DATA_DIR, 'transaction_log.csv')
USER_FILE_NAME = os.path.join(DATA_DIR, 'users.csv')
DEL_REQ_FILE_NAME = os.path.join(DATA_DIR, 'deletion_requests.csv')
TICKET_HISTORY_FILE = os.path.join(DATA_DIR, 'ticket_history.csv')
BACKUP_DIR = os.path.join(DATA_DIR, 'backup')

# [수정] 내역 관리 컬럼 순서 변경 (작성자 맨 앞으로)
FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']
COLS_LOG = ['작성자', '시간', '종류', '장비이름', '수량', '대상', '날짜', '반납예정일'] 
COLS_USER = ['username', 'password', 'role', 'approved', 'created_at', 'birthdate']
COLS_TICKET = ['ticket_id', 'site_names', 'writer', 'created_at', 'file_path']

# ====================================================================
# 2. 구글 시트 및 데이터 처리 함수
# ====================================================================

def get_google_sheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if "google_credentials" not in st.secrets: return None
        secrets_val = st.secrets["google_credentials"]
        if isinstance(secrets_val, str):
            try: creds_json = json.loads(secrets_val, strict=False)
            except: clean_val = secrets_val.replace('\n', '\\n').replace('\r', ''); creds_json = json.loads(clean_val, strict=False)
        else: creds_json = secrets_val
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        return client
    except: return None

def hash_password(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

def init_user_db():
    if not os.path.exists(USER_FILE_NAME):
        df = pd.DataFrame(columns=['username', 'password', 'role', 'approved', 'created_at', 'birthdate'])
        try: admin_pw = st.secrets.get("admin_password", "1234")
        except: admin_pw = "1234"
        df.loc[0] = ['admin', hash_password(admin_pw), 'admin', True, datetime.now().strftime("%Y-%m-%d"), '0000-00-00']
        df.to_csv(USER_FILE_NAME, index=False)
    else:
        try:
            df = pd.read_csv(USER_FILE_NAME)
            if 'birthdate' not in df.columns: df['birthdate'] = '0000-00-00'; df.to_csv(USER_FILE_NAME, index=False)
        except: pass

    if not os.path.exists(TICKET_HISTORY_FILE):
        df = pd.DataFrame(columns=['ticket_id', 'site_names', 'writer', 'created_at', 'file_path'])
        df.to_csv(TICKET_HISTORY_FILE, index=False)
    else:
        try:
            df = pd.read_csv(TICKET_HISTORY_FILE)
            if 'file_path' not in df.columns: df['file_path'] = ""; df.to_csv(TICKET_HISTORY_FILE, index=False)
        except: pass

def get_all_users():
    init_user_db()
    try:
        df = pd.read_csv(USER_FILE_NAME)
        if 'birthdate' not in df.columns: df['birthdate'] = '0000-00-00'
        return df.fillna("")
    except: return pd.DataFrame(columns=['username', 'password', 'role', 'approved', 'created_at', 'birthdate'])

def update_user_status(username, action):
    df = pd.read_csv(USER_FILE_NAME)
    if action == "approve": df.loc[df['username'] == username, 'approved'] = True
    elif action == "delete": df = df[df['username'] != username]
    df.to_csv(USER_FILE_NAME, index=False)

def verify_password(username, input_pw):
    df = get_all_users()
    user = df[df['username'] == username]
    if user.empty: return False
    return user.iloc[0]['password'] == hash_password(input_pw)

def load_data():
    if not os.path.exists(FILE_NAME):
        df = pd.DataFrame(columns=FIELD_NAMES); df.to_csv(FILE_NAME, index=False); return df
    try:
        df = pd.read_csv(FILE_NAME)
        for col in FIELD_NAMES:
            if col not in df.columns: df[col] = ""
        if 'ID' not in df.columns or df['ID'].isnull().any(): df['ID'] = [str(uuid.uuid4()) for _ in range(len(df))]
        return df.fillna("")
    except: return pd.DataFrame(columns=FIELD_NAMES)

def save_data(df): df.to_csv(FILE_NAME, index=False)

# [수정] 로그 저장 시 컬럼 순서 반영 (작성자 먼저)
def log_transaction(kind, item_name, qty, target, date_val, return_val=''):
    new_log = {
        '작성자': st.session_state.username, # 작성자를 맨 앞으로
        '시간': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        '종류': kind, '장비이름': item_name, '수량': qty, '대상': target, '날짜': date_val, '반납예정일': return_val
    }
    log_df = pd.DataFrame([new_log])
    # 로컬 CSV 저장 (헤더 순서가 바뀌었을 수 있으므로 기존 파일이 있다면 확인 필요하지만, 여기선 append 모드라 유의)
    if not os.path.exists(LOG_FILE_NAME): 
        log_df.to_csv(LOG_FILE_NAME, index=False, columns=COLS_LOG)
    else: 
        # 기존 파일과 컬럼 순서 맞추기 위해 읽어서 저장 (안전)
        try:
            old_df = pd.read_csv(LOG_FILE_NAME)
            # 만약 기존 파일 컬럼 순서가 다르면 재정렬
            if list(old_df.columns) != COLS_LOG:
                # 없는 컬럼 추가 등 처리 후 재저장
                for c in COLS_LOG: 
                    if c not in old_df.columns: old_df[c] = ""
                old_df = old_df[COLS_LOG] # 순서 강제
            
            # 새 로그와 합치기
            log_df = log_df[COLS_LOG] # 순서 보장
            combined_df = pd.concat([old_df, log_df], ignore_index=True)
            combined_df.to_csv(LOG_FILE_NAME, index=False)
        except:
            log_df.to_csv(LOG_FILE_NAME, mode='a', header=False, index=False)

    # 구글 시트 저장 (옵션)
    try:
        client = get_google_sheet_client()
        if client:
            sh = client.open("장비관리시스템")
            try: ws = sh.worksheet("로그")
            except: ws = sh.add_worksheet("로그", 1000, 10); ws.append_row(COLS_LOG)
            # 구글 시트도 순서 맞춰서
            row_data = [new_log.get(c, "") for c in COLS_LOG]
            ws.append_row(row_data)
    except: pass

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
            
            title_font = Font(bold=True, size=16)
            ws['A1'] = f"장비 출고증 ({site})"
            ws['A1'].font = title_font
            ws['A2'] = f"현장명: {site}"
            ws['A3'] = f"출고 담당자: {worker}"
            ws['D3'] = f"출력일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            ws.column_dimensions['A'].width = 25; ws.column_dimensions['B'].width = 15
            ws.column_dimensions['C'].width = 10; ws.column_dimensions['D'].width = 15
            ws.column_dimensions['E'].width = 15; ws.column_dimensions['F'].width = 30
    return output.getvalue()

def save_ticket_history(site_names_str, file_data):
    init_user_db()
    file_name = f"ticket_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.xlsx"
    file_path = os.path.join(TICKETS_DIR, file_name)
    with open(file_path, "wb") as f: f.write(file_data)
    
    try:
        client = get_google_sheet_client()
        if client:
            sh = client.open("장비관리시스템")
            try: ws = sh.worksheet("출고증")
            except: ws = sh.add_worksheet("출고증", 1000, 10); ws.append_row(COLS_TICKET)
            ws.append_row([str(uuid.uuid4()), site_names_str, st.session_state.username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), file_name])
    except: pass
    
    if not os.path.exists(TICKET_HISTORY_FILE):
        df = pd.DataFrame(columns=['ticket_id', 'site_names', 'writer', 'created_at', 'file_path'])
    else: df = pd.read_csv(TICKET_HISTORY_FILE)
    
    new_row = {'ticket_id': str(uuid.uuid4()), 'site_names': site_names_str, 'writer': st.session_state.username, 
               'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'file_path': file_name}
    pd.concat([df, pd.DataFrame([new_row])], ignore_index=True).to_csv(TICKET_HISTORY_FILE, index=False)

def request_deletion(item_id, item_name):
    req_df = pd.DataFrame(columns=['req_id', 'item_id', 'item_name', 'requester', 'reason', 'date'])
    if os.path.exists(DEL_REQ_FILE_NAME): req_df = pd.read_csv(DEL_REQ_FILE_NAME)
    new_req = {'req_id': str(uuid.uuid4()), 'item_id': item_id, 'item_name': item_name, 'requester': st.session_state.username, 'reason': "사용자 요청", 'date': datetime.now().strftime("%Y-%m-%d")}
    pd.concat([req_df, pd.DataFrame([new_req])], ignore_index=True).to_csv(DEL_REQ_FILE_NAME, index=False)

# ====================================================================
# 3. 메인 앱 UI
# ====================================================================

def main_app():
    if 'df' not in st.session_state: st.session_state.df = load_data()
    df = st.session_state.df
    user_role = st.session_state.get('role', 'user')

    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        st.caption(f"권한: {'👑 관리자' if user_role == 'admin' else '직원'}")
        st.divider()
        if st.button("🔄 데이터 새로고침"): st.session_state.df = load_data(); st.success("완료")
        csv = df.drop(columns=['ID'], errors='ignore').to_csv(index=False).encode('utf-8-sig')
        st.download_button("💾 장비 목록 백업", csv, "equipment_backup.csv", "text/csv")

    c1, c2 = st.columns([8, 2])
    c1.title("🛠️ 통합 장비 관리 시스템")
    if c2.button("로그아웃"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

    cols = st.columns(4)
    cols[0].metric("🚚 대여 중", len(df[df['대여여부'] == '대여 중']))
    cols[1].metric("🎬 현장 출고", len(df[df['대여여부'] == '현장 출고']))
    cols[2].metric("🛠️ 수리 중", len(df[df['대여여부'] == '수리 중']))
    cols[3].metric("💔 파손", len(df[df['대여여부'] == '파손']))
    st.divider()

    tabs = st.tabs(["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리", "🗂️ 출고증 보관함", "👑 관리자 페이지" if user_role == 'admin' else ""])

    # 1. 재고 관리
    with tabs[0]:
        with st.expander("➕ 장비 등록"):
            with st.form("add"):
                c1, c2 = st.columns(2)
                name = c1.text_input("이름")
                qty = c2.number_input("수량", 1, value=1)
                if st.form_submit_button("등록"):
                    new_row = {'ID': str(uuid.uuid4()), '이름': name, '수량': qty, '대여여부': '재고', '반납예정일': ''}
                    st.session_state.df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    save_data(st.session_state.df); st.rerun()

        st.write("---")
        with st.expander("🔍 재고 검색 및 수정", expanded=False):
            c_s, c_t = st.columns([4, 1])
            search = c_s.text_input("검색", key="inv_search")
            edit_mode = c_t.toggle("수정 모드")
        
        view_df = df[df['이름'].str.contains(search, na=False)] if search else df
        
        # 색상 로직
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
                st.session_state.df.loc[st.session_state.df['ID'] == row['ID'], :] = row
            save_data(st.session_state.df); st.success("저장됨"); st.rerun()

        st.write("---")
        if not view_df.empty:
            del_opts = {r['ID']: f"{r['이름']} ({r.get('브랜드','')})" for i, r in view_df.iterrows()}
            del_id = st.selectbox("삭제 대상 선택", options=list(del_opts.keys()), format_func=lambda x: del_opts[x])
            if st.button("삭제 요청"):
                if user_role == 'admin':
                    st.session_state.df = st.session_state.df[st.session_state.df['ID'] != del_id]
                    save_data(st.session_state.df); st.success("삭제됨"); st.rerun()
                else:
                    request_deletion(del_id, del_opts[del_id]); st.info("요청됨")

    # 3. 현장 출고 (파일명 변경)
    with tabs[2]:
        st.subheader("🎬 현장 출고")
        # ... (검색 등 생략, 기존과 동일) ...
        cur = st.session_state.df[st.session_state.df['대여여부'] == '현장 출고']
        if not cur.empty:
            sites = list(cur['대여자'].unique())
            sel_sites = st.multiselect("현장 선택", sites)
            if sel_sites:
                for s in sel_sites:
                    with st.expander(f"{s} 목록"):
                        st.dataframe(cur[cur['대여자'] == s][['이름', '수량']], use_container_width=True)
                
                # [수정] 파일명 포맷 변경: (현장명-yyyy.mm.dd).xlsx
                today_str = datetime.now().strftime("%Y.%m.%d")
                if len(sel_sites) == 1: site_str = sel_sites[0]
                else: site_str = f"{sel_sites[0]}외{len(sel_sites)-1}곳"
                fname = f"({site_str}-{today_str}).xlsx"
                
                excel_data = create_dispatch_ticket_multisheet(sel_sites, cur, st.session_state.username)
                if st.download_button(f"📄 통합 출고증 다운로드: {fname}", excel_data, fname):
                    save_ticket_history(", ".join(sel_sites), excel_data)
                    st.success("저장 완료")

    # 6. 내역 관리 (컬럼 변경 확인)
    with tabs[5]:
        st.subheader("📜 내역")
        if os.path.exists(LOG_FILE_NAME):
            log_df = pd.read_csv(LOG_FILE_NAME)
            # COLS_LOG 순서대로 표시 (작성자, 시간, 종류...)
            st.dataframe(log_df[COLS_LOG].iloc[::-1], use_container_width=True)

    # 7. 출고증 보관함 (재다운로드 파일명 변경)
    with tabs[6]:
        st.subheader("🗂️ 보관함")
        if os.path.exists(TICKET_HISTORY_FILE):
            hist = pd.read_csv(TICKET_HISTORY_FILE).iloc[::-1]
            # ... (관리자 삭제 로직 생략) ...
            
            st.write("#### 📄 목록")
            for idx, row in hist.iterrows():
                c1, c2, c3, c4 = st.columns([3, 2, 3, 2])
                c1.write(row['site_names'])
                c2.write(row['writer'])
                c3.write(row['created_at'])
                
                fpath = os.path.join(TICKETS_DIR, str(row.get('file_path', '')))
                if os.path.exists(fpath):
                    # [수정] 재다운로드 시에도 보기 좋은 파일명으로 제공
                    created_date = str(row['created_at'])[:10].replace('-', '.') # YYYY.MM.DD
                    site_name = row['site_names'].split(',')[0] # 첫 번째 현장만 따옴 (간소화)
                    if ',' in row['site_names']: site_name += "외"
                    nice_name = f"({site_name}-{created_date}).xlsx"
                    
                    with open(fpath, "rb") as f:
                        c4.download_button("📥 받기", f, file_name=nice_name, key=f"dl_{idx}")
                else: c4.error("파일 없음")
                st.write("---")

    # 8. 관리자 (타이틀 변경)
    if user_role == 'admin':
        with tabs[7]:
            st.subheader("👑 전체 직원 관리") # 타이틀 수정됨
            # ... (기존 로직 동일) ...

# ... (나머지 탭 및 로그인 로직은 기존 유지) ...

if __name__ == '__main__':
    init_user_db()
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: 
        st.title("로그인")
        uid = st.text_input("ID")
        upw = st.text_input("PW", type="password")
        if st.button("로그인"):
            if verify_password(uid, upw):
                st.session_state.logged_in = True
                st.session_state.username = uid
                st.session_state.role = 'admin' if uid == 'admin' else 'user'
                st.rerun()
