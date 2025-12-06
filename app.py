import streamlit as st
import pandas as pd
import os
import uuid
import hashlib
from datetime import datetime
import shutil
from io import BytesIO

# ====================================================================
# 1. 설정 및 기본 경로
# ====================================================================

st.set_page_config(page_title="통합 장비 관리 시스템", layout="wide", page_icon="🛠️")

# Streamlit Cloud 환경 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = BASE_DIR
IMG_DIR = os.path.join(DATA_DIR, 'images') # 사진 저장 폴더

if not os.path.exists(IMG_DIR):
    os.makedirs(IMG_DIR)

FILE_NAME = os.path.join(DATA_DIR, 'equipment_data.csv')
LOG_FILE_NAME = os.path.join(DATA_DIR, 'transaction_log.csv')
USER_FILE_NAME = os.path.join(DATA_DIR, 'users.csv')
DEL_REQ_FILE_NAME = os.path.join(DATA_DIR, 'deletion_requests.csv') # 삭제 요청 파일
BACKUP_DIR = os.path.join(DATA_DIR, 'backup')

# [수정] 사진 컬럼 추가
FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']

# ====================================================================
# 2. 회원가입, 로그인, 관리자 기능 함수
# ====================================================================

def hash_password(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

def init_user_db():
    if not os.path.exists(USER_FILE_NAME):
        # [수정] 생년월일 컬럼 추가
        df = pd.DataFrame(columns=['username', 'password', 'role', 'approved', 'created_at', 'birthdate'])
        
        try: admin_pw = st.secrets["admin_password"]
        except: admin_pw = "1234"

        admin_user = {
            'username': 'admin',
            'password': hash_password(admin_pw),
            'role': 'admin',
            'approved': True,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'birthdate': '0000-00-00'
        }
        df = pd.concat([df, pd.DataFrame([admin_user])], ignore_index=True)
        df.to_csv(USER_FILE_NAME, index=False)

def register_user(username, password, birthdate):
    """회원가입 (생년월일 추가)"""
    init_user_db()
    df = pd.read_csv(USER_FILE_NAME)
    
    if username in df['username'].values:
        return False, "이미 존재하는 아이디입니다."
    
    new_user = {
        'username': username, 
        'password': hash_password(password),
        'role': 'user',          
        'approved': False,        
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'birthdate': str(birthdate)
    }
    df = pd.concat([df, pd.DataFrame([new_user])], ignore_index=True)
    df.to_csv(USER_FILE_NAME, index=False)
    return True, "가입 신청 완료. 관리자 승인 대기 중."

def login_user(username, password):
    init_user_db()
    try: df = pd.read_csv(USER_FILE_NAME)
    except: return False, "DB 오류", None

    hashed_pw = hash_password(password)
    user_row = df[(df['username'] == username) & (df['password'] == hashed_pw)]
    
    if user_row.empty: return False, "아이디/비번 불일치", None
    
    user_data = user_row.iloc[0]
    if not user_data['approved']: return False, "승인 대기 중입니다.", None
        
    return True, "로그인 성공", user_data['role']

def change_user_password(username, new_password):
    df = pd.read_csv(USER_FILE_NAME)
    df.loc[df['username'] == username, 'password'] = hash_password(new_password)
    df.to_csv(USER_FILE_NAME, index=False)
    return True

def get_all_users():
    init_user_db()
    return pd.read_csv(USER_FILE_NAME)

def update_user_status(username, action):
    df = pd.read_csv(USER_FILE_NAME)
    if action == "approve": df.loc[df['username'] == username, 'approved'] = True
    elif action == "delete": df = df[df['username'] != username]
    df.to_csv(USER_FILE_NAME, index=False)

# ====================================================================
# 3. 데이터 처리 함수 (엑셀, 백업, 로그, 삭제요청)
# ====================================================================

def perform_backup():
    if not os.path.exists(BACKUP_DIR): os.makedirs(BACKUP_DIR)
    if os.path.exists(FILE_NAME):
        today_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        try: shutil.copy(FILE_NAME, os.path.join(BACKUP_DIR, f"equipment_data_{today_str}.csv"))
        except: pass

def load_data():
    if not os.path.exists(FILE_NAME):
        df = pd.DataFrame(columns=FIELD_NAMES)
        df.to_csv(FILE_NAME, index=False)
        return df
    try:
        df = pd.read_csv(FILE_NAME)
        # 컬럼 누락 방지 (사진 등)
        for col in FIELD_NAMES:
            if col not in df.columns: df[col] = ""
        # ID 생성
        if 'ID' not in df.columns or df['ID'].isnull().any():
            df['ID'] = [str(uuid.uuid4()) for _ in range(len(df))]
        return df.fillna("")
    except:
        return pd.DataFrame(columns=FIELD_NAMES)

def save_data(df):
    df.to_csv(FILE_NAME, index=False)

def log_transaction(kind, item_name, qty, target, date_val, return_val=''):
    new_log = {
        '시간': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
        '작성자': st.session_state.username,
        '종류': kind, '장비이름': item_name, '수량': qty, 
        '대상': target, '날짜': date_val, '반납예정일': return_val
    }
    log_df = pd.DataFrame([new_log])
    if not os.path.exists(LOG_FILE_NAME): log_df.to_csv(LOG_FILE_NAME, index=False)
    else: log_df.to_csv(LOG_FILE_NAME, mode='a', header=False, index=False)

# [추가] 엑셀 출고증 생성 함수
def create_dispatch_ticket(item_name, brand, qty, target, date_out, date_ret, note, worker):
    df = pd.DataFrame([{
        "구분": "장비 출고증",
        "출고일자": date_out,
        "현장/업체명": target,
        "장비명": item_name,
        "브랜드": brand,
        "수량": qty,
        "반납예정일": date_ret,
        "비고": note,
        "담당자(출고)": worker,
        "발행일시": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='출고증')
    return output.getvalue()

# [추가] 삭제 요청 처리
def request_deletion(item_id, item_name, reason="사용자 요청"):
    req_df = pd.DataFrame(columns=['req_id', 'item_id', 'item_name', 'requester', 'reason', 'date'])
    if os.path.exists(DEL_REQ_FILE_NAME):
        req_df = pd.read_csv(DEL_REQ_FILE_NAME)
    
    new_req = {
        'req_id': str(uuid.uuid4()),
        'item_id': item_id,
        'item_name': item_name,
        'requester': st.session_state.username,
        'reason': reason,
        'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    req_df = pd.concat([req_df, pd.DataFrame([new_req])], ignore_index=True)
    req_df.to_csv(DEL_REQ_FILE_NAME, index=False)

# ====================================================================
# 4. 메인 어플리케이션 UI
# ====================================================================

def main_app():
    if 'df' not in st.session_state:
        perform_backup()
        st.session_state.df = load_data()

    df = st.session_state.df
    user_role = st.session_state.get('role', 'user')

    # --- 사이드바 ---
    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        st.caption(f"권한: {'👑 관리자' if user_role == 'admin' else '일반 사용자'}")
        
        st.divider()
        st.write("📂 데이터 관리")
        
        # [기능 6] 엑셀 불러오기/내보내기
        with st.expander("📥 데이터 불러오기/저장"):
            st.info("기존 엑셀 파일이 있으면 불러오세요. (주의: 기존 데이터는 덮어씌워집니다)")
            uploaded_file = st.file_uploader("엑셀 파일 업로드 (.xlsx)", type=['xlsx'])
            if uploaded_file is not None:
                if st.button("데이터 덮어쓰기 적용"):
                    try:
                        new_df = pd.read_excel(uploaded_file)
                        # 필수 컬럼 확인
                        for col in FIELD_NAMES:
                            if col not in new_df.columns: new_df[col] = ""
                        st.session_state.df = new_df
                        save_data(new_df)
                        st.success("데이터 로드 완료!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"오류 발생: {e}")

            if os.path.exists(FILE_NAME):
                with open(FILE_NAME, "rb") as f:
                    st.download_button("💾 현재 데이터 백업 (CSV)", f, "equipment_backup.csv", "text/csv")

        st.divider()
        with st.expander("🔒 비밀번호 변경"):
            with st.form("change_pw_form"):
                new_pw = st.text_input("새 비밀번호", type="password")
                if st.form_submit_button("변경"):
                    change_user_password(st.session_state.username, new_pw)
                    st.success("변경 완료")

    # --- 메인 헤더 ---
    col_h1, col_h2 = st.columns([8, 2])
    col_h1.title("🛠️ 통합 장비 관리 시스템")
    if col_h2.button("로그아웃", type="secondary"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

    # 현황판
    rented = df[df['대여여부'] == '대여 중']['수량'].sum() if not df.empty else 0
    dispatched = df[df['대여여부'] == '현장 출고']['수량'].sum() if not df.empty else 0
    repair = df[df['대여여부'] == '수리 중']['수량'].sum() if not df.empty else 0
    broken = df[df['대여여부'] == '파손']['수량'].sum() if not df.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", rented); c2.metric("🎬 현장 출고", dispatched)
    c3.metric("🛠️ 수리 중", repair); c4.metric("💔 파손", broken)

    st.divider()

    tabs = st.tabs(["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 로그 관리", "👑 관리자"])

    # ------------------ 탭 1: 재고 관리 (사진, 삭제요청) ------------------
    with tabs[0]:
        st.subheader("장비 관리")
        with st.expander("➕ 새 장비 등록 (사진 포함)"):
            with st.form("add_form", clear_on_submit=True):
                c1, c2, c3 = st.columns([1, 2, 1])
                new_type = c1.text_input("타입")
                new_name = c2.text_input("이름")
                new_count = c3.number_input("수량", min_value=1, value=1)
                
                c4, c5 = st.columns(2)
                new_brand = c4.text_input("브랜드")
                new_lender = c5.text_input("대여업체")
                
                new_note = st.text_input("특이사항")
                
                # [기능 7] 사진 업로드
                img_file = st.file_uploader("장비 사진 (선택)", type=['png', 'jpg', 'jpeg'])
                
                if st.form_submit_button("등록"):
                    if new_name:
                        img_path = ""
                        if img_file:
                            img_path = os.path.join("images", img_file.name)
                            # 실제 파일 저장
                            with open(os.path.join(DATA_DIR, img_path), "wb") as f:
                                f.write(img_file.getbuffer())
                        
                        new_row = {
                            'ID': str(uuid.uuid4()), '타입': new_type, '이름': new_name, '수량': new_count, 
                            '브랜드': new_brand, '특이사항': new_note, '대여업체': new_lender, 
                            '대여여부': '재고', '대여자': '', '대여일': '', '반납예정일': '', '출고비고': '',
                            '사진': img_path
                        }
                        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                        save_data(st.session_state.df)
                        st.success("등록 완료")
                        st.rerun()
                    else: st.error("이름 필수")

        # 재고 목록 표시
        search_q = st.text_input("🔍 재고 검색", placeholder="이름, 브랜드...")
        view_df = st.session_state.df.copy()
        if search_q: view_df = view_df[view_df.apply(lambda row: row.astype(str).str.contains(search_q, case=False).any(), axis=1)]
        
        # [기능 2] 대여중 색상 어둡게 변경 (가시성 확보)
        def highlight_rows(row):
            today = datetime.now().strftime("%Y-%m-%d")
            status = row['대여여부']
            r_date = row['반납예정일']
            
            style = []
            if r_date and r_date < today and status in ['대여 중', '현장 출고']: style = ['background-color: #ffcccc'] * len(row) # 연체 (빨강)
            elif status == '대여 중': style = ['background-color: #ffb74d'] * len(row) # [수정] 진한 주황색
            elif status == '현장 출고': style = ['background-color: #e3f2fd'] * len(row) # 파랑
            elif status == '파손': style = ['background-color: #cfd8dc; color: red'] * len(row)
            elif status == '수리 중': style = ['background-color: #ffccbc'] * len(row)
            else: style = [''] * len(row)
            return style

        st.dataframe(view_df.style.apply(highlight_rows, axis=1), use_container_width=True, hide_index=True)

        # [기능 10] 삭제 로직 (일반:요청, 관리자:즉시삭제)
        st.write("---")
        if not view_df.empty:
            del_opts = view_df.apply(lambda x: f"{x['이름']} ({x['브랜드']})", axis=1)
            to_delete_idx = st.selectbox("삭제 요청/처리할 장비 선택", options=del_opts.index, format_func=lambda x: del_opts[x])
            
            if st.button("선택 장비 삭제"):
                item_to_del = st.session_state.df.loc[to_delete_idx]
                
                if user_role == 'admin':
                    # 관리자는 즉시 삭제
                    st.session_state.df = st.session_state.df.drop(to_delete_idx).reset_index(drop=True)
                    save_data(st.session_state.df)
                    st.success("관리자 권한으로 삭제되었습니다.")
                    st.rerun()
                else:
                    # 일반 사용자는 요청만
                    request_deletion(item_to_del['ID'], item_to_del['이름'])
                    st.info("관리자에게 삭제 승인을 요청했습니다.")

    # ------------------ 탭 2: 외부 대여 (현황판 추가, 필수입력) ------------------
    with tabs[1]:
        st.subheader("📤 외부 대여")
        rent_search = st.text_input("🔍 장비 검색", key="rent_search")
        stock_df = st.session_state.df[st.session_state.df['대여여부'] == '재고']
        if rent_search: stock_df = stock_df[stock_df.apply(lambda row: row.astype(str).str.contains(rent_search, case=False).any(), axis=1)]
        
        if stock_df.empty: st.info("가능한 재고 없음")
        else:
            rent_opts = stock_df.apply(lambda x: f"{x['이름']} ({x['수량']}개)", axis=1)
            sel_idx = st.selectbox("대여할 장비", options=rent_opts.index, format_func=lambda x: rent_opts[x], key="rent_sel")
            
            if sel_idx is not None:
                item = st.session_state.df.loc[sel_idx]
                with st.form("rent_form"):
                    target = st.text_input("업체명")
                    c1, c2, c3 = st.columns(3)
                    qty = c1.number_input("수량", 1, int(item['수량']), 1)
                    d_out = c2.date_input("대여일", datetime.now())
                    d_ret = c3.date_input("반납예정일 (필수)", value=None) # [기능 1] 필수 표시
                    
                    if st.form_submit_button("대여 실행"):
                        if not target: st.error("업체명 입력 필요")
                        elif d_ret is None: st.error("⚠️ 반납 예정일은 필수입니다!") # [기능 1] 체크
                        else:
                            # 로직 실행
                            date_s = d_out.strftime("%Y-%m-%d"); ret_s = d_ret.strftime("%Y-%m-%d")
                            if qty < item['수량']:
                                st.session_state.df.at[sel_idx, '수량'] -= qty
                                new_row = item.copy(); new_row['ID'] = str(uuid.uuid4()); new_row['수량'] = qty; new_row['대여여부'] = '대여 중'; new_row['대여자'] = target; new_row['대여일'] = date_s; new_row['반납예정일'] = ret_s
                                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                            else:
                                st.session_state.df.at[sel_idx, '대여여부'] = '대여 중'; st.session_state.df.at[sel_idx, '대여자'] = target; st.session_state.df.at[sel_idx, '대여일'] = date_s; st.session_state.df.at[sel_idx, '반납예정일'] = ret_s
                            
                            log_transaction("외부대여", item['이름'], qty, target, date_s, ret_s)
                            save_data(st.session_state.df)
                            st.success("대여 완료")
                            st.rerun()

        # [기능 3] 현재 대여중 목록 표시
        st.write("---")
        st.write("#### 📋 현재 대여 중인 목록")
        cur_rent = st.session_state.df[st.session_state.df['대여여부'] == '대여 중']
        if not cur_rent.empty:
            st.dataframe(cur_rent[['이름', '브랜드', '수량', '대여자', '반납예정일']], use_container_width=True)
        else:
            st.info("현재 대여 중인 장비가 없습니다.")

    # ------------------ 탭 3: 현장 출고 (현황판, 필수입력, 출고증) ------------------
    with tabs[2]:
        st.subheader("🎬 현장 출고")
        disp_search = st.text_input("🔍 장비 검색", key="disp_search")
        stock_df = st.session_state.df[st.session_state.df['대여여부'] == '재고']
        if disp_search: stock_df = stock_df[stock_df.apply(lambda row: row.astype(str).str.contains(disp_search, case=False).any(), axis=1)]
        
        if stock_df.empty: st.info("재고 없음")
        else:
            disp_opts = stock_df.apply(lambda x: f"{x['이름']} ({x['수량']}개)", axis=1)
            sel_idx = st.selectbox("출고할 장비", options=disp_opts.index, format_func=lambda x: disp_opts[x], key="disp_sel")
            
            if sel_idx is not None:
                item = st.session_state.df.loc[sel_idx]
                with st.form("dispatch_form"):
                    target = st.text_input("현장명")
                    c1, c2, c3 = st.columns(3)
                    qty = c1.number_input("수량", 1, int(item['수량']), 1)
                    d_out = c2.date_input("출고일", datetime.now())
                    d_ret = c3.date_input("반납예정일 (필수)", value=None) # [기능 1]
                    note = st.text_input("비고")
                    
                    if st.form_submit_button("출고 실행"):
                        if not target: st.error("현장명 입력 필요")
                        elif d_ret is None: st.error("⚠️ 반납 예정일은 필수입니다!") # [기능 1]
                        else:
                            date_s = d_out.strftime("%Y-%m-%d"); ret_s = d_ret.strftime("%Y-%m-%d")
                            if qty < item['수량']:
                                st.session_state.df.at[sel_idx, '수량'] -= qty
                                new_row = item.copy(); new_row['ID'] = str(uuid.uuid4()); new_row['수량'] = qty; new_row['대여여부'] = '현장 출고'; new_row['대여자'] = target; new_row['대여일'] = date_s; new_row['반납예정일'] = ret_s; new_row['출고비고'] = note
                                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                            else:
                                st.session_state.df.at[sel_idx, '대여여부'] = '현장 출고'; st.session_state.df.at[sel_idx, '대여자'] = target; st.session_state.df.at[sel_idx, '대여일'] = date_s; st.session_state.df.at[sel_idx, '반납예정일'] = ret_s; st.session_state.df.at[sel_idx, '출고비고'] = note
                            
                            log_transaction("현장출고", item['이름'], qty, target, date_s, ret_s)
                            save_data(st.session_state.df)
                            
                            # [기능 5] 출고증 생성 (세션에 저장해서 버튼 활성화)
                            st.session_state.last_ticket = create_dispatch_ticket(item['이름'], item['브랜드'], qty, target, date_s, ret_s, note, st.session_state.username)
                            st.success("출고 완료! 아래에서 출고증을 다운로드하세요.")
                            st.rerun()

                # [기능 5] 출고증 다운로드 버튼
                if 'last_ticket' in st.session_state:
                    st.download_button("📄 방금 처리한 출고증 다운로드 (Excel)", st.session_state.last_ticket, "dispatch_ticket.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # [기능 4] 현장별 출고 현황
        st.write("---")
        st.write("#### 📋 현장별 출고 현황")
        cur_disp = st.session_state.df[st.session_state.df['대여여부'] == '현장 출고']
        if not cur_disp.empty:
            sites = cur_disp['대여자'].unique()
            selected_site = st.selectbox("현장 선택", ["전체보기"] + list(sites))
            if selected_site != "전체보기":
                cur_disp = cur_disp[cur_disp['대여자'] == selected_site]
            st.dataframe(cur_disp[['대여자', '이름', '수량', '반납예정일', '출고비고']], use_container_width=True)
        else:
            st.info("출고된 장비가 없습니다.")

    # ------------------ 탭 4: 반납 ------------------
    with tabs[3]:
        st.subheader("📥 반납")
        ret_search = st.text_input("🔍 반납 장비", key="ret_search")
        ret_df = st.session_state.df[st.session_state.df['대여여부'].isin(['대여 중', '현장 출고'])]
        if ret_search: ret_df = ret_df[ret_df.apply(lambda row: row.astype(str).str.contains(ret_search, case=False).any(), axis=1)]
        
        if ret_df.empty: st.info("반납할 것 없음")
        else:
            ret_opts = ret_df.apply(lambda x: f"[{x['대여여부']}] {x['이름']} - {x['대여자']}", axis=1)
            sel_idx = st.selectbox("선택", options=ret_opts.index, format_func=lambda x: ret_opts[x], key="ret_sel")
            
            if sel_idx is not None:
                item = st.session_state.df.loc[sel_idx]
                with st.form("in_form"):
                    qty = st.number_input("반납 수량", 1, int(item['수량']), int(item['수량']))
                    if st.form_submit_button("반납 실행"):
                        # 재고 합치기 로직
                        mask = ((st.session_state.df['이름'] == item['이름']) & (st.session_state.df['브랜드'] == item['브랜드']) & (st.session_state.df['대여여부'] == '재고'))
                        merge_idx = st.session_state.df[mask].index
                        
                        if qty < item['수량']: # 부분 반납
                            st.session_state.df.at[sel_idx, '수량'] -= qty
                            if not merge_idx.empty: st.session_state.df.at[merge_idx[0], '수량'] += qty
                            else:
                                new_row = item.copy(); new_row['ID'] = str(uuid.uuid4()); new_row['수량'] = qty; new_row['대여여부'] = '재고'; new_row['대여자'] = ''; new_row['대여일'] = ''; new_row['반납예정일'] = ''
                                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                        else: # 전체 반납
                            if not merge_idx.empty:
                                st.session_state.df.at[merge_idx[0], '수량'] += qty
                                st.session_state.df = st.session_state.df.drop(sel_idx).reset_index(drop=True)
                            else:
                                st.session_state.df.at[sel_idx, '대여여부'] = '재고'; st.session_state.df.at[sel_idx, '대여자'] = ''; st.session_state.df.at[sel_idx, '대여일'] = ''; st.session_state.df.at[sel_idx, '반납예정일'] = ''
                        
                        log_transaction("반납", item['이름'], qty, item['대여자'], datetime.now().strftime("%Y-%m-%d"))
                        save_data(st.session_state.df)
                        st.success("반납 완료")
                        st.rerun()

    # ------------------ 탭 5: 수리/파손 ------------------
    with tabs[4]:
        st.subheader("🛠️ 수리/파손")
        # (기존 로직 유지)
        maint_search = st.text_input("🔍 검색", key="maint_search")
        m_df = st.session_state.df[st.session_state.df['대여여부'].isin(['재고', '수리 중', '파손'])]
        if maint_search: m_df = m_df[m_df.apply(lambda row: row.astype(str).str.contains(maint_search, case=False).any(), axis=1)]
        
        if m_df.empty: st.info("없음")
        else:
            m_opts = m_df.apply(lambda x: f"[{x['대여여부']}] {x['이름']}", axis=1)
            sel_idx = st.selectbox("선택", options=m_opts.index, format_func=lambda x: m_opts[x], key="maint_sel")
            if sel_idx is not None:
                item = st.session_state.df.loc[sel_idx]
                with st.form("maint_form"):
                    target_st = st.selectbox("상태 변경", ["재고", "수리 중", "파손"])
                    qty = st.number_input("수량", 1, int(item['수량']), int(item['수량']))
                    if st.form_submit_button("변경"):
                        # (로직 간소화: 변경 처리)
                        st.session_state.df.at[sel_idx, '대여여부'] = target_st
                        if target_st == '재고': st.session_state.df.at[sel_idx, '대여자'] = ''
                        log_transaction(f"상태변경({target_st})", item['이름'], qty, target_st, datetime.now().strftime("%Y-%m-%d"))
                        save_data(st.session_state.df)
                        st.success("변경 완료")
                        st.rerun()

    # ------------------ 탭 6: 로그 관리 (관리자 삭제 기능) ------------------
    with tabs[5]:
        st.subheader("📜 기록 조회")
        if os.path.exists(LOG_FILE_NAME):
            log_df = pd.read_csv(LOG_FILE_NAME)
            log_df = log_df.iloc[::-1]
            
            # [기능 11] 관리자만 선택 삭제 가능
            if user_role == 'admin':
                st.warning("⚠️ 관리자 권한: 로그를 삭제할 수 있습니다.")
                # 체크박스 컬럼 추가
                log_df.insert(0, "선택", False)
                edited_df = st.data_editor(log_df, hide_index=True, use_container_width=True)
                
                if st.button("선택한 로그 영구 삭제"):
                    # 선택되지 않은 것만 남기기
                    remaining_df = edited_df[edited_df['선택'] == False].drop(columns=['선택'])
                    remaining_df = remaining_df.iloc[::-1] # 다시 저장 순서로
                    remaining_df.to_csv(LOG_FILE_NAME, index=False)
                    st.success("삭제 완료")
                    st.rerun()
            else:
                st.dataframe(log_df, use_container_width=True)
        else: st.info("기록 없음")

    # ------------------ 탭 7: 관리자 메뉴 (승인, 삭제요청 확인) ------------------
    if user_role == 'admin':
        with tabs[6]:
            st.subheader("👑 관리자 페이지")
            
            # 1. 회원 승인
            st.write("#### 👤 회원 가입 승인")
            all_users = get_all_users()
            pending = all_users[all_users['approved'] == False]
            if pending.empty: st.info("대기 중인 회원이 없습니다.")
            else:
                for idx, row in pending.iterrows():
                    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                    c1.write(f"**{row['username']}** (생일: {row['birthdate']})") # [기능 9] 생일 확인
                    if c3.button("승인", key=f"ok_{idx}"): update_user_status(row['username'], "approve"); st.rerun()
                    if c4.button("거절", key=f"no_{idx}"): update_user_status(row['username'], "delete"); st.rerun()
            
            st.divider()
            
            # 2. 장비 삭제 요청 승인 [기능 10]
            st.write("#### 🗑️ 장비 삭제 요청 목록")
            if os.path.exists(DEL_REQ_FILE_NAME):
                del_req_df = pd.read_csv(DEL_REQ_FILE_NAME)
                if del_req_df.empty: st.info("삭제 요청이 없습니다.")
                else:
                    for idx, row in del_req_df.iterrows():
                        with st.expander(f"요청: {row['item_name']} (요청자: {row['requester']})"):
                            st.write(f"사유: {row['reason']}")
                            col_a, col_b = st.columns(2)
                            if col_a.button("승인(삭제)", key=f"del_ok_{row['req_id']}"):
                                # 실제 데이터 삭제 로직
                                df_main = st.session_state.df
                                st.session_state.df = df_main[df_main['ID'] != row['item_id']]
                                save_data(st.session_state.df)
                                # 요청 목록에서 제거
                                del_req_df = del_req_df[del_req_df['req_id'] != row['req_id']]
                                del_req_df.to_csv(DEL_REQ_FILE_NAME, index=False)
                                st.success("삭제 승인 완료")
                                st.rerun()
                            
                            if col_b.button("반려(취소)", key=f"del_no_{row['req_id']}"):
                                del_req_df = del_req_df[del_req_df['req_id'] != row['req_id']]
                                del_req_df.to_csv(DEL_REQ_FILE_NAME, index=False)
                                st.warning("반려되었습니다.")
                                st.rerun()
            else: st.info("삭제 요청 파일이 없습니다.")

# ====================================================================
# 5. 로그인 페이지 (기능 8, 9 반영)
# ====================================================================

def login_page():
    st.title("🔒 통합 장비 관리 시스템")
    t1, t2 = st.tabs(["로그인", "회원가입"])
    
    with t1:
        with st.form("login"):
            id_in = st.text_input("아이디")
            pw_in = st.text_input("비밀번호", type="password")
            if st.form_submit_button("로그인"):
                succ, msg, role = login_user(id_in, pw_in)
                if succ:
                    st.session_state.logged_in = True
                    st.session_state.username = id_in
                    st.session_state.role = role
                    st.rerun()
                else: st.error(msg)
    
    with t2:
        st.info("💡 관리자 승인 후 로그인 가능합니다.")
        with st.form("signup"):
            # [기능 8] 아이디 안내 문구
            new_id = st.text_input("아이디 (본인 실명으로 기재해주세요)") 
            new_pw = st.text_input("비밀번호", type="password")
            # [기능 9] 생년월일 추가
            birth = st.date_input("생년월일", min_value=datetime(1960,1,1), max_value=datetime.now())
            
            if st.form_submit_button("가입신청"):
                if new_id and new_pw:
                    succ, msg = register_user(new_id, new_pw, birth)
                    if succ: st.success(msg)
                    else: st.error(msg)
                else: st.error("빈칸을 채워주세요.")

# ====================================================================
# 6. 실행
# ====================================================================

if __name__ == '__main__':
    init_user_db()
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    
    if st.session_state.logged_in: main_app()
    else: login_page()
