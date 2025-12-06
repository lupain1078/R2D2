import streamlit as st
import pandas as pd
import os
import uuid
import hashlib
from datetime import datetime
import shutil

# ====================================================================
# 1. 설정 및 기본 경로
# ====================================================================

st.set_page_config(page_title="통합 장비 관리 시스템", layout="wide", page_icon="🛠️")

# Streamlit Cloud 환경에 맞는 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = BASE_DIR

FILE_NAME = os.path.join(DATA_DIR, 'equipment_data.csv')
LOG_FILE_NAME = os.path.join(DATA_DIR, 'transaction_log.csv')
USER_FILE_NAME = os.path.join(DATA_DIR, 'users.csv')
BACKUP_DIR = os.path.join(DATA_DIR, 'backup')

FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고']

# ====================================================================
# 2. 회원가입, 로그인, 관리자 기능 함수
# ====================================================================

def hash_password(password):
    """비밀번호 암호화"""
    return hashlib.sha256(str(password).encode()).hexdigest()

def init_user_db():
    """유저 파일이 없으면 생성하고 기본 관리자 계정 생성"""
    if not os.path.exists(USER_FILE_NAME):
        df = pd.DataFrame(columns=['username', 'password', 'role', 'approved', 'created_at'])
        
        # [보안 수정] 비밀번호를 Streamlit Secrets에서 가져오거나 기본값 사용
        try:
            admin_pw = st.secrets["admin_password"]
        except:
            admin_pw = "1234" # secrets 설정 안했을 때 기본 비번

        admin_user = {
            'username': 'admin',
            'password': hash_password(admin_pw),
            'role': 'admin',
            'approved': True,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        df = pd.concat([df, pd.DataFrame([admin_user])], ignore_index=True)
        df.to_csv(USER_FILE_NAME, index=False)

def register_user(username, password):
    """회원가입"""
    init_user_db()
    df = pd.read_csv(USER_FILE_NAME)
    
    if username in df['username'].values:
        return False, "이미 존재하는 아이디입니다."
    
    new_user = {
        'username': username, 
        'password': hash_password(password),
        'role': 'user',          
        'approved': False,        
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    df = pd.concat([df, pd.DataFrame([new_user])], ignore_index=True)
    df.to_csv(USER_FILE_NAME, index=False)
    return True, "가입 신청 완료. 관리자 승인 대기 중."

def login_user(username, password):
    """로그인 처리"""
    init_user_db()
    try:
        df = pd.read_csv(USER_FILE_NAME)
    except pd.errors.EmptyDataError:
        return False, "데이터베이스 오류. 관리자에게 문의하세요.", None

    hashed_pw = hash_password(password)
    user_row = df[(df['username'] == username) & (df['password'] == hashed_pw)]
    
    if user_row.empty: return False, "아이디 또는 비밀번호 불일치", None
    
    user_data = user_row.iloc[0]
    if not user_data['approved']: return False, "승인 대기 중입니다.", None
        
    return True, "로그인 성공", user_data['role']

def change_user_password(username, new_password):
    """비밀번호 변경"""
    df = pd.read_csv(USER_FILE_NAME)
    new_hash = hash_password(new_password)
    df.loc[df['username'] == username, 'password'] = new_hash
    df.to_csv(USER_FILE_NAME, index=False)
    return True

def get_all_users():
    """모든 유저 정보"""
    init_user_db()
    return pd.read_csv(USER_FILE_NAME)

def update_user_status(username, action):
    """유저 승인/삭제"""
    df = pd.read_csv(USER_FILE_NAME)
    if action == "approve":
        df.loc[df['username'] == username, 'approved'] = True
    elif action == "delete":
        df = df[df['username'] != username]
    df.to_csv(USER_FILE_NAME, index=False)

# ====================================================================
# 3. 데이터 처리 함수
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
        # ID가 없는 구버전 데이터 호환성 체크
        if 'ID' not in df.columns: 
            df['ID'] = [str(uuid.uuid4()) for _ in range(len(df))]
        return df.fillna("")
    except:
        return pd.DataFrame(columns=FIELD_NAMES)

def save_data(df):
    df.to_csv(FILE_NAME, index=False)

def log_transaction(kind, item_name, qty, target, date_val, return_val=''):
    new_log = {
        '시간': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
        '종류': kind, 
        '장비이름': item_name, 
        '수량': qty, 
        '대상(현장/업체)': target, 
        '날짜': date_val, 
        '반납예정일': return_val
    }
    log_df = pd.DataFrame([new_log])
    if not os.path.exists(LOG_FILE_NAME): log_df.to_csv(LOG_FILE_NAME, index=False)
    else: log_df.to_csv(LOG_FILE_NAME, mode='a', header=False, index=False)

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
        
        # [데이터 보호 기능]
        st.warning("⚠️ 서버 재배포 시 데이터가 초기화될 수 있습니다. 중요한 데이터는 자주 백업하세요.")
        if os.path.exists(FILE_NAME):
            with open(FILE_NAME, "rb") as f:
                st.download_button("💾 전체 데이터 백업(다운로드)", f, file_name="equipment_backup.csv", mime="text/csv")

        st.divider()

        with st.expander("🔒 비밀번호 변경"):
            with st.form("change_pw_form"):
                cur_pw = st.text_input("현재 비밀번호", type="password")
                new_pw = st.text_input("새 비밀번호", type="password")
                new_pw_chk = st.text_input("새 비밀번호 확인", type="password")
                
                if st.form_submit_button("변경하기"):
                    df_users = pd.read_csv(USER_FILE_NAME)
                    stored_pw = df_users.loc[df_users['username'] == st.session_state.username, 'password'].values[0]
                    
                    if hash_password(cur_pw) != stored_pw:
                        st.error("현재 비밀번호가 틀렸습니다.")
                    elif new_pw != new_pw_chk:
                        st.error("새 비밀번호가 일치하지 않습니다.")
                    elif not new_pw:
                        st.error("비밀번호를 입력해주세요.")
                    else:
                        change_user_password(st.session_state.username, new_pw)
                        st.success("변경 완료! 다시 로그인해주세요.")

    # --- 메인 헤더 ---
    col_h1, col_h2 = st.columns([8, 2])
    col_h1.title("🛠️ 통합 장비 관리 시스템")
    
    with col_h2:
        if st.button("로그아웃", key="logout_btn", type="secondary"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # 현황판
    rented = df[df['대여여부'] == '대여 중']['수량'].sum() if not df.empty else 0
    dispatched = df[df['대여여부'] == '현장 출고']['수량'].sum() if not df.empty else 0
    repair = df[df['대여여부'] == '수리 중']['수량'].sum() if not df.empty else 0
    broken = df[df['대여여부'] == '파손']['수량'].sum() if not df.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", rented)
    c2.metric("🎬 현장 출고", dispatched)
    c3.metric("🛠️ 수리 중", repair)
    c4.metric("💔 파손", broken)

    st.divider()

    tabs_list = ["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 기록"]
    if user_role == 'admin': tabs_list.append("👑 관리자 메뉴")
    tabs = st.tabs(tabs_list)

    # ------------------ 탭 1: 재고 관리 ------------------
    with tabs[0]:
        st.subheader("장비 관리")
        with st.expander("➕ 새 장비 등록"):
            with st.form("add_form", clear_on_submit=True):
                c1, c2, c3 = st.columns([1, 2, 1])
                new_type = c1.text_input("타입")
                new_name = c2.text_input("이름")
                new_count = c3.number_input("수량", min_value=1, value=1)
                
                c4, c5, c6 = st.columns(3)
                new_brand = c4.text_input("브랜드")
                new_lender = c5.text_input("대여업체")
                new_note = c6.text_input("특이사항")
                
                if st.form_submit_button("등록"):
                    if new_name:
                        new_row = {
                            'ID': str(uuid.uuid4()), '타입': new_type, '이름': new_name, '수량': new_count, 
                            '브랜드': new_brand, '특이사항': new_note, '대여업체': new_lender, 
                            '대여여부': '재고', '대여자': '', '대여일': '', '반납예정일': '', '출고비고': ''
                        }
                        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                        save_data(st.session_state.df)
                        st.success("등록 완료")
                        st.rerun()
                    else: st.error("이름 필수")

        search_q = st.text_input("🔍 재고 검색", placeholder="이름, 브랜드...")
        view_df = st.session_state.df.copy()
        if search_q: view_df = view_df[view_df.apply(lambda row: row.astype(str).str.contains(search_q, case=False).any(), axis=1)]
        
        display_df = view_df.drop(columns=['ID'])
        def highlight_rows(row):
            today = datetime.now().strftime("%Y-%m-%d")
            status = row['대여여부']
            r_date = row['반납예정일']
            
            # 스타일 지정
            style = []
            if r_date and r_date < today and status in ['대여 중', '현장 출고']: style = ['background-color: #ffcccc'] * len(row) # 연체
            elif status == '대여 중': style = ['background-color: #fff2cc'] * len(row)
            elif status == '현장 출고': style = ['background-color: #e3f2fd'] * len(row)
            elif status == '파손': style = ['background-color: #cfd8dc; color: red'] * len(row)
            elif status == '수리 중': style = ['background-color: #ffccbc'] * len(row)
            else: style = [''] * len(row)
            return style

        st.dataframe(display_df.style.apply(highlight_rows, axis=1), use_container_width=True, hide_index=True)

        st.write("---")
        if not view_df.empty:
            del_opts = view_df.apply(lambda x: f"{x['이름']} ({x['브랜드']}) - {x['수량']}개 [{x['대여여부']}]", axis=1)
            to_delete_idx = st.selectbox("🗑️ 삭제할 장비 선택", options=del_opts.index, format_func=lambda x: del_opts[x])
            if st.button("선택 장비 영구 삭제", type="primary"):
                st.session_state.df = st.session_state.df.drop(to_delete_idx).reset_index(drop=True)
                save_data(st.session_state.df)
                st.success("삭제되었습니다.")
                st.rerun()

    # ------------------ 탭 2: 외부 대여 ------------------
    with tabs[1]:
        st.subheader("📤 외부 대여 처리")
        rent_search = st.text_input("🔍 대여할 장비 검색", key="rent_search")
        stock_df = st.session_state.df[st.session_state.df['대여여부'] == '재고']
        if rent_search: stock_df = stock_df[stock_df.apply(lambda row: row.astype(str).str.contains(rent_search, case=False).any(), axis=1)]
        
        if stock_df.empty: st.info("대여 가능한 재고가 없습니다.")
        else:
            rent_opts = stock_df.apply(lambda x: f"{x['이름']} ({x['브랜드']}) | 재고: {x['수량']}개", axis=1)
            sel_idx = st.selectbox("장비 선택", options=rent_opts.index, format_func=lambda x: rent_opts[x], key="rent_sel")
            if sel_idx is not None:
                item = st.session_state.df.loc[sel_idx]
                with st.form("rent_form"):
                    target = st.text_input("빌리는 업체명")
                    c1, c2, c3 = st.columns(3)
                    qty = c1.number_input("수량", min_value=1, max_value=int(item['수량']), value=1)
                    d_out = c2.date_input("대여일", datetime.now())
                    d_ret = c3.date_input("반납예정일", value=None)
                    
                    if st.form_submit_button("대여 실행"):
                        if not target: st.error("업체명을 입력하세요.")
                        else:
                            date_s = d_out.strftime("%Y-%m-%d")
                            ret_s = d_ret.strftime("%Y-%m-%d") if d_ret else ""
                            
                            # 로직: 수량 분리
                            if qty < item['수량']:
                                st.session_state.df.at[sel_idx, '수량'] -= qty
                                new_row = item.copy()
                                new_row['ID'] = str(uuid.uuid4())
                                new_row['수량'] = qty
                                new_row['대여여부'] = '대여 중'
                                new_row['대여자'] = target
                                new_row['대여일'] = date_s
                                new_row['반납예정일'] = ret_s
                                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                            else:
                                st.session_state.df.at[sel_idx, '대여여부'] = '대여 중'
                                st.session_state.df.at[sel_idx, '대여자'] = target
                                st.session_state.df.at[sel_idx, '대여일'] = date_s
                                st.session_state.df.at[sel_idx, '반납예정일'] = ret_s
                            
                            log_transaction("외부대여", item['이름'], qty, target, date_s, ret_s)
                            save_data(st.session_state.df)
                            st.success("대여 처리 완료")
                            st.rerun()

    # ------------------ 탭 3: 현장 출고 ------------------
    with tabs[2]:
        st.subheader("🎬 현장 출고 처리")
        disp_search = st.text_input("🔍 출고할 장비 검색", key="disp_search")
        stock_df = st.session_state.df[st.session_state.df['대여여부'] == '재고']
        if disp_search: stock_df = stock_df[stock_df.apply(lambda row: row.astype(str).str.contains(disp_search, case=False).any(), axis=1)]
        
        if stock_df.empty: st.info("출고 가능한 재고가 없습니다.")
        else:
            disp_opts = stock_df.apply(lambda x: f"{x['이름']} ({x['브랜드']}) | 재고: {x['수량']}개", axis=1)
            sel_idx = st.selectbox("장비 선택", options=disp_opts.index, format_func=lambda x: disp_opts[x], key="disp_sel")
            if sel_idx is not None:
                item = st.session_state.df.loc[sel_idx]
                with st.form("dispatch_form"):
                    target = st.text_input("현장명")
                    c1, c2, c3 = st.columns(3)
                    qty = c1.number_input("수량", min_value=1, max_value=int(item['수량']), value=1)
                    d_out = c2.date_input("출고일", datetime.now())
                    d_ret = c3.date_input("반납예정일", value=None)
                    note = st.text_input("출고 비고")
                    
                    if st.form_submit_button("출고 실행"):
                        if not target: st.error("현장명을 입력하세요.")
                        else:
                            date_s = d_out.strftime("%Y-%m-%d")
                            ret_s = d_ret.strftime("%Y-%m-%d") if d_ret else ""
                            
                            if qty < item['수량']:
                                st.session_state.df.at[sel_idx, '수량'] -= qty
                                new_row = item.copy()
                                new_row['ID'] = str(uuid.uuid4())
                                new_row['수량'] = qty
                                new_row['대여여부'] = '현장 출고'
                                new_row['대여자'] = target
                                new_row['대여일'] = date_s
                                new_row['반납예정일'] = ret_s
                                new_row['출고비고'] = note
                                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                            else:
                                st.session_state.df.at[sel_idx, '대여여부'] = '현장 출고'
                                st.session_state.df.at[sel_idx, '대여자'] = target
                                st.session_state.df.at[sel_idx, '대여일'] = date_s
                                st.session_state.df.at[sel_idx, '반납예정일'] = ret_s
                                st.session_state.df.at[sel_idx, '출고비고'] = note
                            
                            log_transaction("현장출고", item['이름'], qty, target, date_s, ret_s)
                            save_data(st.session_state.df)
                            st.success("출고 처리 완료")
                            st.rerun()

    # ------------------ 탭 4: 반납 ------------------
    with tabs[3]:
        st.subheader("📥 반납 처리")
        ret_search = st.text_input("🔍 반납할 장비 검색", key="ret_search")
        ret_df = st.session_state.df[st.session_state.df['대여여부'].isin(['대여 중', '현장 출고'])]
        if ret_search: ret_df = ret_df[ret_df.apply(lambda row: row.astype(str).str.contains(ret_search, case=False).any(), axis=1)]
        
        if ret_df.empty: st.info("반납할 내역이 없습니다.")
        else:
            ret_opts = ret_df.apply(lambda x: f"[{x['대여여부']}] {x['이름']} - {x['대여자']} ({x['수량']}개)", axis=1)
            sel_idx = st.selectbox("반납할 장비 선택", options=ret_opts.index, format_func=lambda x: ret_opts[x], key="ret_sel")
            if sel_idx is not None:
                item = st.session_state.df.loc[sel_idx]
                with st.form("in_form"):
                    qty = st.number_input("반납 수량", min_value=1, max_value=int(item['수량']), value=int(item['수량']))
                    if st.form_submit_button("반납 실행"):
                        # 동일 조건의 재고 찾기 (합치기 위함)
                        mask = ((st.session_state.df['이름'] == item['이름']) & 
                                (st.session_state.df['브랜드'] == item['브랜드']) & 
                                (st.session_state.df['대여업체'] == item['대여업체']) & 
                                (st.session_state.df['특이사항'] == item['특이사항']) & 
                                (st.session_state.df['대여여부'] == '재고'))
                        merge_idx = st.session_state.df[mask].index
                        
                        if qty < item['수량']: # 부분 반납
                            st.session_state.df.at[sel_idx, '수량'] -= qty
                            if not merge_idx.empty:
                                st.session_state.df.at[merge_idx[0], '수량'] += qty
                            else:
                                new_row = item.copy()
                                new_row['ID'] = str(uuid.uuid4())
                                new_row['수량'] = qty
                                new_row['대여여부'] = '재고'
                                new_row['대여자'] = ''
                                new_row['대여일'] = ''
                                new_row['반납예정일'] = ''
                                new_row['출고비고'] = ''
                                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                        else: # 전체 반납
                            if not merge_idx.empty:
                                st.session_state.df.at[merge_idx[0], '수량'] += qty
                                st.session_state.df = st.session_state.df.drop(sel_idx).reset_index(drop=True)
                            else:
                                st.session_state.df.at[sel_idx, '대여여부'] = '재고'
                                st.session_state.df.at[sel_idx, '대여자'] = ''
                                st.session_state.df.at[sel_idx, '대여일'] = ''
                                st.session_state.df.at[sel_idx, '반납예정일'] = ''
                                st.session_state.df.at[sel_idx, '출고비고'] = ''
                        
                        log_transaction("반납", item['이름'], qty, item['대여자'], datetime.now().strftime("%Y-%m-%d"))
                        save_data(st.session_state.df)
                        st.success("반납 완료")
                        st.rerun()

    # ------------------ 탭 5: 수리/파손 ------------------
    with tabs[4]:
        st.subheader("🛠️ 수리 및 파손 관리")
        maint_search = st.text_input("🔍 장비 검색", key="maint_search")
        m_df = st.session_state.df[st.session_state.df['대여여부'].isin(['재고', '수리 중', '파손'])]
        if maint_search: m_df = m_df[m_df.apply(lambda row: row.astype(str).str.contains(maint_search, case=False).any(), axis=1)]
        
        if m_df.empty: st.info("처리 가능한 장비가 없습니다.")
        else:
            m_opts = m_df.apply(lambda x: f"[{x['대여여부']}] {x['이름']} ({x['수량']}개)", axis=1)
            sel_idx = st.selectbox("장비 선택", options=m_opts.index, format_func=lambda x: m_opts[x], key="maint_sel")
            if sel_idx is not None:
                item = st.session_state.df.loc[sel_idx]
                with st.form("maint_form"):
                    target_st = st.selectbox("변경할 상태", ["재고", "수리 중", "파손"])
                    qty = st.number_input("변경 수량", min_value=1, max_value=int(item['수량']), value=int(item['수량']))
                    
                    if st.form_submit_button("상태 변경"):
                        if item['대여여부'] == target_st: st.warning("이미 해당 상태입니다.")
                        else:
                            # 동일 상태의 항목이 있는지 찾기 (합치기용)
                            merge_idx = pd.Index([])
                            if target_st == '재고':
                                mask = ((st.session_state.df['이름'] == item['이름']) & (st.session_state.df['브랜드'] == item['브랜드']) & 
                                        (st.session_state.df['대여업체'] == item['대여업체']) & (st.session_state.df['특이사항'] == item['특이사항']) & 
                                        (st.session_state.df['대여여부'] == '재고'))
                                merge_idx = st.session_state.df[mask].index
                            
                            if qty < item['수량']: # 부분 변경
                                st.session_state.df.at[sel_idx, '수량'] -= qty
                                if not merge_idx.empty:
                                    st.session_state.df.at[merge_idx[0], '수량'] += qty
                                else:
                                    new_row = item.copy()
                                    new_row['ID'] = str(uuid.uuid4())
                                    new_row['수량'] = qty
                                    new_row['대여여부'] = target_st
                                    new_row['대여자'] = target_st if target_st != '재고' else ''
                                    new_row['대여일'] = ''
                                    new_row['반납예정일'] = ''
                                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                            else: # 전체 변경
                                if not merge_idx.empty:
                                    st.session_state.df.at[merge_idx[0], '수량'] += qty
                                    st.session_state.df = st.session_state.df.drop(sel_idx).reset_index(drop=True)
                                else:
                                    st.session_state.df.at[sel_idx, '대여여부'] = target_st
                                    st.session_state.df.at[sel_idx, '대여자'] = target_st if target_st != '재고' else ''
                                    st.session_state.df.at[sel_idx, '대여일'] = ''
                                    st.session_state.df.at[sel_idx, '반납예정일'] = ''
                            
                            log_transaction(f"상태변경({target_st})", item['이름'], qty, target_st, datetime.now().strftime("%Y-%m-%d"))
                            save_data(st.session_state.df)
                            st.success(f"{target_st} 변경 완료")
                            st.rerun()

    # ------------------ 탭 6: 로그 ------------------
    with tabs[5]:
        st.subheader("📜 기록 조회")
        if os.path.exists(LOG_FILE_NAME):
            log_df = pd.read_csv(LOG_FILE_NAME)
            log_df = log_df.iloc[::-1] # 최신순 정렬
            st.dataframe(log_df, use_container_width=True, hide_index=True)
            
            # 로그 다운로드 버튼
            csv_d = log_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("CSV 다운로드", csv_d, "transaction_logs.csv", "text/csv")
        else: st.info("기록이 없습니다.")

    # ------------------ 탭 7: 관리자 메뉴 ------------------
    if user_role == 'admin':
        with tabs[6]:
            st.subheader("👑 관리자 회원 관리")
            all_users = get_all_users()
            
            st.write("#### ⏳ 승인 대기 목록")
            pending_users = all_users[all_users['approved'] == False]
            if pending_users.empty: st.info("대기 중인 회원이 없습니다.")
            else:
                for idx, row in pending_users.iterrows():
                    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                    c1.write(f"**{row['username']}**")
                    c2.write(f"{row['created_at']}")
                    if c3.button("승인", key=f"app_{idx}"):
                        update_user_status(row['username'], "approve")
                        st.success("승인 완료")
                        st.rerun()
                    if c4.button("거절", key=f"rej_{idx}"):
                        update_user_status(row['username'], "delete")
                        st.warning("삭제 완료")
                        st.rerun()
            
            st.divider()
            st.write("#### 👥 전체 회원 목록")
            approved_users = all_users[all_users['approved'] == True]
            for idx, row in approved_users.iterrows():
                if row['role'] == 'admin': continue
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.write(f"👤 {row['username']}")
                c2.write(f"{row['created_at']}")
                if c3.button("추방", key=f"del_{idx}"):
                    update_user_status(row['username'], "delete")
                    st.rerun()

# ====================================================================
# 5. 로그인 페이지
# ====================================================================

def login_page():
    st.title("🔒 통합 장비 관리 시스템")
    
    # 탭 디자인 개선
    tab1, tab2 = st.tabs(["로그인", "회원가입 요청"])
    
    with tab1:
        with st.form("login_form"):
            username = st.text_input("아이디")
            password = st.text_input("비밀번호", type="password")
            
            if st.form_submit_button("로그인"):
                success, msg, role = login_user(username, password)
                if success:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.role = role
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    
    with tab2:
        st.info("💡 가입 신청 후 관리자의 승인을 받아야 로그인할 수 있습니다.")
        with st.form("signup_form"):
            new_user = st.text_input("사용할 아이디")
            new_pw = st.text_input("사용할 비밀번호", type="password")
            new_pw_chk = st.text_input("비밀번호 확인", type="password")
            
            if st.form_submit_button("가입 신청"):
                if new_pw != new_pw_chk: st.error("비밀번호가 일치하지 않습니다.")
                elif not new_user or not new_pw: st.error("아이디와 비밀번호를 모두 입력해주세요.")
                else:
                    success, msg = register_user(new_user, new_pw)
                    if success: st.success(msg)
                    else: st.error(msg)

# ====================================================================
# 6. 실행
# ====================================================================

if __name__ == '__main__':
    # 초기 DB 세팅
    init_user_db()
    
    # 세션 상태 초기화
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    
    # 로그인 여부에 따른 화면 전환
    if st.session_state.logged_in:
        main_app()
    else:
        login_page()
