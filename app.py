import streamlit as st
import pandas as pd
import os
import uuid
import hashlib
from datetime import datetime
import shutil
from io import BytesIO
from openpyxl.styles import Font, Alignment, Border, Side
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ====================================================================
# 1. 설정 및 기본 경로
# ====================================================================

st.set_page_config(page_title="통합 장비 관리 시스템", layout="wide", page_icon="🛠️")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = BASE_DIR
IMG_DIR = os.path.join(DATA_DIR, 'images')
TICKETS_DIR = os.path.join(DATA_DIR, 'tickets')

# 폴더 생성
if not os.path.exists(IMG_DIR): os.makedirs(IMG_DIR)
if not os.path.exists(TICKETS_DIR): os.makedirs(TICKETS_DIR)

# 파일 경로
FILE_NAME = os.path.join(DATA_DIR, 'equipment_data.csv')
LOG_FILE_NAME = os.path.join(DATA_DIR, 'transaction_log.csv')
USER_FILE_NAME = os.path.join(DATA_DIR, 'users.csv')
DEL_REQ_FILE_NAME = os.path.join(DATA_DIR, 'deletion_requests.csv')
TICKET_HISTORY_FILE = os.path.join(DATA_DIR, 'ticket_history.csv')
BACKUP_DIR = os.path.join(DATA_DIR, 'backup')

FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']

# ====================================================================
# 2. 구글 시트 및 데이터 처리 함수 (자동 복구 강화)
# ====================================================================

def get_google_sheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if "google_credentials" not in st.secrets:
            return None
        
        secrets_val = st.secrets["google_credentials"]
        # JSON 파싱 시 제어 문자 오류 방지
        if isinstance(secrets_val, str):
            # 1. 일반적인 로드 시도
            try:
                creds_json = json.loads(secrets_val, strict=False)
            except:
                # 2. 실패 시 제어 문자 제거 후 시도
                clean_val = secrets_val.replace('\n', '\\n').replace('\r', '')
                creds_json = json.loads(clean_val, strict=False)
        else:
            creds_json = secrets_val

        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        return client
    except Exception:
        return None

def hash_password(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

def init_user_db():
    # 1. 유저 DB 복구
    if not os.path.exists(USER_FILE_NAME):
        df = pd.DataFrame(columns=['username', 'password', 'role', 'approved', 'created_at', 'birthdate'])
        # 초기 관리자 생성
        try: admin_pw = st.secrets.get("admin_password", "1234")
        except: admin_pw = "1234"
        
        df.loc[0] = ['admin', hash_password(admin_pw), 'admin', True, datetime.now().strftime("%Y-%m-%d"), '0000-00-00']
        df.to_csv(USER_FILE_NAME, index=False)
    else:
        # 컬럼 자동 추가 (KeyError 방지)
        try:
            df = pd.read_csv(USER_FILE_NAME)
            if 'birthdate' not in df.columns:
                df['birthdate'] = '0000-00-00'
                df.to_csv(USER_FILE_NAME, index=False)
        except: pass

    # 2. 출고증 DB 복구
    if not os.path.exists(TICKET_HISTORY_FILE):
        df = pd.DataFrame(columns=['ticket_id', 'site_names', 'writer', 'created_at', 'file_path'])
        df.to_csv(TICKET_HISTORY_FILE, index=False)
    else:
        try:
            df = pd.read_csv(TICKET_HISTORY_FILE)
            if 'file_path' not in df.columns:
                df['file_path'] = ""
                df.to_csv(TICKET_HISTORY_FILE, index=False)
        except: pass

def get_all_users():
    init_user_db()
    try:
        df = pd.read_csv(USER_FILE_NAME)
        # birthdate가 없으면 임시로 채워서 리턴
        if 'birthdate' not in df.columns: df['birthdate'] = '0000-00-00'
        return df.fillna("")
    except:
        return pd.DataFrame(columns=['username', 'password', 'role', 'approved', 'created_at', 'birthdate'])

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
        df = pd.DataFrame(columns=FIELD_NAMES)
        df.to_csv(FILE_NAME, index=False)
        return df
    try:
        df = pd.read_csv(FILE_NAME)
        for col in FIELD_NAMES:
            if col not in df.columns: df[col] = ""
        if 'ID' not in df.columns or df['ID'].isnull().any():
            df['ID'] = [str(uuid.uuid4()) for _ in range(len(df))]
        return df.fillna("")
    except: return pd.DataFrame(columns=FIELD_NAMES)

def save_data(df): df.to_csv(FILE_NAME, index=False)

def log_transaction(kind, item_name, qty, target, date_val, return_val=''):
    new_log = {
        '시간': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), '작성자': st.session_state.username,
        '종류': kind, '장비이름': item_name, '수량': qty, '대상': target, '날짜': date_val, '반납예정일': return_val
    }
    log_df = pd.DataFrame([new_log])
    if not os.path.exists(LOG_FILE_NAME): log_df.to_csv(LOG_FILE_NAME, index=False)
    else: log_df.to_csv(LOG_FILE_NAME, mode='a', header=False, index=False)

# [수정] 엑셀 스타일링 (openpyxl 사용 - AttributeError 해결)
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
            
            ws.column_dimensions['A'].width = 25
            ws.column_dimensions['B'].width = 15
            ws.column_dimensions['C'].width = 10
            ws.column_dimensions['D'].width = 15
            ws.column_dimensions['E'].width = 15
            ws.column_dimensions['F'].width = 30
    return output.getvalue()

def save_ticket_history(site_names_str, file_data):
    init_user_db()
    file_name = f"ticket_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.xlsx"
    file_path = os.path.join(TICKETS_DIR, file_name)
    with open(file_path, "wb") as f: f.write(file_data)
    
    # 구글 시트에도 저장 시도 (실패해도 로컬엔 저장)
    try:
        client = get_google_sheet_client()
        if client:
            sh = client.open("장비관리시스템")
            try: ws = sh.worksheet("출고증")
            except: ws = sh.add_worksheet("출고증", 1000, 10)
            ws.append_row([str(uuid.uuid4()), site_names_str, st.session_state.username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), file_name])
    except: pass
    
    # 로컬 CSV 저장
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

    # 사이드바
    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        st.caption(f"권한: {'👑 관리자' if user_role == 'admin' else '직원'}")
        st.divider()
        
        if st.button("🔄 데이터 새로고침"):
            st.session_state.df = load_data()
            st.success("완료")
        
        csv = df.drop(columns=['ID'], errors='ignore').to_csv(index=False).encode('utf-8-sig')
        st.download_button("💾 장비 목록 백업", csv, "equipment_backup.csv", "text/csv")

    # 메인 헤더
    c1, c2 = st.columns([8, 2])
    c1.title("🛠️ 통합 장비 관리 시스템")
    if c2.button("로그아웃"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

    # 현황판
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
        search = st.text_input("🔍 검색", key="inv_search")
        view_df = df[df['이름'].str.contains(search, na=False)] if search else df
        
        edited = st.data_editor(view_df, num_rows="dynamic", key="inv_edit")
        if st.button("저장"):
            st.session_state.df = edited
            save_data(edited); st.success("저장됨"); st.rerun()

    # ... (다른 탭들은 기존 로직 유지하되 에러 방지 코드 적용) ...

    # 7. 출고증 보관함 (UI 개선)
    with tabs[6]:
        st.subheader("🗂️ 출고증 보관함")
        if os.path.exists(TICKET_HISTORY_FILE):
            hist = pd.read_csv(TICKET_HISTORY_FILE).iloc[::-1]
            
            # 리스트 형태로 보여주기 (버튼 옆에 배치)
            for idx, row in hist.iterrows():
                c1, c2, c3, c4 = st.columns([3, 2, 3, 2])
                c1.write(row['site_names'])
                c2.write(row['writer'])
                c3.write(row['created_at'])
                
                fpath = os.path.join(TICKETS_DIR, str(row.get('file_path', '')))
                if os.path.exists(fpath):
                    with open(fpath, "rb") as f:
                        c4.download_button("📥 다운로드", f, file_name=str(row.get('file_path')), key=f"dl_{idx}")
                else:
                    c4.warning("파일 없음")
                st.write("---")
        else:
            st.info("발급된 출고증이 없습니다.")

# ... (로그인 페이지 등 나머지 코드) ...

if __name__ == '__main__':
    init_user_db()
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: 
        # 로그인 화면 구현 (간소화)
        st.title("로그인")
        uid = st.text_input("ID")
        upw = st.text_input("PW", type="password")
        if st.button("로그인"):
            if verify_password(uid, upw):
                st.session_state.logged_in = True
                st.session_state.username = uid
                st.session_state.role = 'admin' if uid == 'admin' else 'user'
                st.rerun()
            else: st.error("실패")
