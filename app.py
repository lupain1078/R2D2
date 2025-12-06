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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = BASE_DIR
IMG_DIR = os.path.join(DATA_DIR, 'images')

if not os.path.exists(IMG_DIR):
    os.makedirs(IMG_DIR)

FILE_NAME = os.path.join(DATA_DIR, 'equipment_data.csv')
LOG_FILE_NAME = os.path.join(DATA_DIR, 'transaction_log.csv')
USER_FILE_NAME = os.path.join(DATA_DIR, 'users.csv')
DEL_REQ_FILE_NAME = os.path.join(DATA_DIR, 'deletion_requests.csv')
BACKUP_DIR = os.path.join(DATA_DIR, 'backup')

FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']

# ====================================================================
# 2. 회원 및 데이터 처리 함수
# ====================================================================

def hash_password(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

def init_user_db():
    if not os.path.exists(USER_FILE_NAME):
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
    else:
        try:
            df = pd.read_csv(USER_FILE_NAME)
            if 'birthdate' not in df.columns:
                df['birthdate'] = '0000-00-00'
                df.to_csv(USER_FILE_NAME, index=False)
        except: pass

def register_user(username, password, birthdate):
    init_user_db()
    df = pd.read_csv(USER_FILE_NAME)
    if username in df['username'].values: return False, "이미 존재하는 아이디입니다."
    
    new_user = {
        'username': username, 'password': hash_password(password), 'role': 'user',          
        'approved': False, 'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'birthdate': str(birthdate)
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

def verify_password(username, input_password):
    df = pd.read_csv(USER_FILE_NAME)
    stored_pw = df.loc[df['username'] == username, 'password'].values[0]
    return stored_pw == hash_password(input_password)

def get_all_users():
    init_user_db()
    return pd.read_csv(USER_FILE_NAME)

def update_user_status(username, action):
    df = pd.read_csv(USER_FILE_NAME)
    if action == "approve": df.loc[df['username'] == username, 'approved'] = True
    elif action == "delete": df = df[df['username'] != username]
    df.to_csv(USER_FILE_NAME, index=False)

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

# [수정] 출고증 생성 함수 업그레이드 (현장별 묶음 출력 + 상단 담당자 1회 표기)
def create_dispatch_ticket_grouped(site_name, items_df, worker):
    output = BytesIO()
    
    # 데이터프레임 정리 (필요한 컬럼만)
    display_df = items_df[['이름', '브랜드', '수량', '대여일', '반납예정일', '출고비고']].copy()
    display_df.columns = ['장비명', '브랜드', '수량', '출고일', '반납예정일', '비고']
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # 데이터를 5번째 줄부터 작성 (상단에 정보를 넣기 위해)
        display_df.to_excel(writer, index=False, sheet_name='출고증', startrow=4)
        
        # 워크시트 가져오기
        ws = writer.sheets['출고증']
        
        # 상단 정보 작성 (Row 1~4)
        ws['A1'] = "장비 출고증"
        ws['A1'].font = pd.io.formats.excel.ExcelCell.style_converter({'font': {'bold': True, 'size': 16}})['font']
        
        # 현장명, 담당자, 출력일자 (한번만 표시)
        ws['A2'] = f"현장명: {site_name}"
        ws['A3'] = f"출고 담당자: {worker}"
        ws['D3'] = f"출력일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        # 열 너비 조정 (대략적으로)
        ws.column_dimensions['A'].width = 25 # 장비명
        ws.column_dimensions['B'].width = 15 # 브랜드
        ws.column_dimensions['C'].width = 10 # 수량
        ws.column_dimensions['D'].width = 15 # 출고일
        ws.column_dimensions['E'].width = 15 # 반납예정일
        ws.column_dimensions['F'].width = 30 # 비고

    return output.getvalue()

def request_deletion(item_id, item_name, reason="사용자 요청"):
    req_df = pd.DataFrame(columns=['req_id', 'item_id', 'item_name', 'requester', 'reason', 'date'])
    if os.path.exists(DEL_REQ_FILE_NAME): req_df = pd.read_csv(DEL_REQ_FILE_NAME)
    new_req = {
        'req_id': str(uuid.uuid4()), 'item_id': item_id, 'item_name': item_name,
        'requester': st.session_state.username, 'reason': reason, 'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        with st.expander("🔒 비밀번호 변경"):
            with st.form("change_pw_form"):
                cur_pw = st.text_input("현재 비밀번호", type="password")
                new_pw = st.text_input("새 비밀번호", type="password")
                new_pw_chk = st.text_input("새 비밀번호 확인", type="password")
                
                if st.form_submit_button("변경하기"):
                    if not verify_password(st.session_state.username, cur_pw):
                        st.error("현재 비밀번호가 일치하지 않습니다.")
                    elif new_pw != new_pw_chk:
                        st.error("새 비밀번호가 서로 다릅니다.")
                    elif not new_pw:
                        st.error("비밀번호를 입력해주세요.")
                    else:
                        change_user_password(st.session_state.username, new_pw)
                        st.success("변경 완료! 다시 로그인해주세요.")

        st.divider()
        with st.expander("📥 데이터 관리"):
            uploaded_file = st.file_uploader("파일 불러오기 (Excel/CSV)", type=['xlsx', 'csv'])
            if uploaded_file and st.button("데이터 덮어쓰기 적용"):
                try:
                    if uploaded_file.name.endswith('.csv'):
                        new_df = pd.read_csv(uploaded_file)
                    else:
                        new_df = pd.read_excel(uploaded_file)
                    
                    new_df = new_df.fillna("") 
                    for col in FIELD_NAMES:
                        if col not in new_df.columns: new_df[col] = ""
                    st.session_state.df = new_df
                    save_data(new_df)
                    st.success("데이터 로드 완료!"); st.rerun()
                except Exception as e: st.error(f"오류: {e}")
            
            if not st.session_state.df.empty:
                clean_df = st.session_state.df.drop(columns=['ID'], errors='ignore')
                csv_data = clean_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("💾 장비 목록 백업 (ID 제외)", csv_data, "equipment_list.csv", "text/csv")

    # --- 메인 화면 ---
    col_h1, col_h2 = st.columns([8, 2])
    col_h1.title("🛠️ 통합 장비 관리 시스템")
    if col_h2.button("로그아웃", type="secondary"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

    # 현황판
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", df[df['대여여부'] == '대여 중']['수량'].sum() if not df.empty else 0)
    c2.metric("🎬 현장 출고", df[df['대여여부'] == '현장 출고']['수량'].sum() if not df.empty else 0)
    c3.metric("🛠️ 수리 중", df[df['대여여부'] == '수리 중']['수량'].sum() if not df.empty else 0)
    c4.metric("💔 파손", df[df['대여여부'] == '파손']['수량'].sum() if not df.empty else 0)

    st.divider()

    tab_titles = ["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리"]
    if user_role == 'admin': tab_titles.append("👑 관리자 페이지")
    tabs = st.tabs(tab_titles)

    # 1. 재고 관리
    with tabs[0]:
        st.subheader("장비 관리")
        with st.expander("➕ 새 장비 등록"):
            with st.form("add_form", clear_on_submit=True):
                c1, c2, c3 = st.columns([1, 2, 1])
                new_type = c1.text_input("타입"); new_name = c2.text_input("이름"); new_count = c3.number_input("수량", 1, value=1)
                c4, c5 = st.columns(2)
                new_brand = c4.text_input("브랜드"); new_lender = c5.text_input("대여업체")
                new_note = st.text_input("특이사항")
                img_file = st.file_uploader("장비 사진", type=['png', 'jpg'])
                if st.form_submit_button("등록"):
                    if new_name:
                        img_path = ""
                        if img_file:
                            img_path = os.path.join("images", img_file.name)
                            with open(os.path.join(DATA_DIR, img_path), "wb") as f: f.write(img_file.getbuffer())
                        new_row = {'ID': str(uuid.uuid4()), '타입': new_type, '이름': new_name, '수량': new_count, '브랜드': new_brand, '특이사항': new_note, '대여업체': new_lender, '대여여부': '재고', '대여자': '', '대여일': '', '반납예정일': '', '출고비고': '', '사진': img_path}
                        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                        save_data(st.session_state.df); st.success("등록 완료"); st.rerun()
                    else: st.error("이름 필수")

        search_q = st.text_input("🔍 재고 검색", placeholder="이름, 브랜드...")
        view_df = st.session_state.df.copy()
        if search_q: view_df = view_df[view_df.apply(lambda row: row.astype(str).str.contains(search_q, case=False).any(), axis=1)]
        
        def highlight_rows(row):
            today = datetime.now().strftime("%Y-%m-%d"); status = row['대여여부']
            r_date = str(row['반납예정일']).strip()
            if r_date and r_date != 'nan' and r_date < today and status in ['대여 중', '현장 출고']: return ['background-color: #ffcccc'] * len(row)
            elif status == '대여 중': return ['background-color: #ffb74d'] * len(row)
            elif status == '현장 출고': return ['background-color: #e3f2fd'] * len(row)
            elif status == '파손': return ['background-color: #cfd8dc; color: red'] * len(row)
            elif status == '수리 중': return ['background-color: #ffccbc'] * len(row)
            return [''] * len(row)

        display_df = view_df.drop(columns=['ID'], errors='ignore')
        st.dataframe(display_df.style.apply(highlight_rows, axis=1), use_container_width=True, hide_index=True)

        if not view_df.empty:
            del_opts = view_df.apply(lambda x: f"{x['이름']} ({x['브랜드']})", axis=1)
            to_delete_idx = st.selectbox("삭제 요청/처리 선택", options=del_opts.index, format_func=lambda x: del_opts[x])
            if st.button("삭제 실행"):
                item_to_del = st.session_state.df.loc[to_delete_idx]
                if user_role == 'admin':
                    st.session_state.df = st.session_state.df.drop(to_delete_idx).reset_index(drop=True)
                    save_data(st.session_state.df); st.success("관리자 권한 삭제 완료"); st.rerun()
                else:
                    request_deletion(item_to_del['ID'], item_to_del['이름'])
                    st.info("관리자에게 삭제 승인을 요청했습니다.")

    # 2. 외부 대여
    with tabs[1]:
        st.subheader("📤 외부 대여")
        rent_search = st.text_input("🔍 검색", key="rent_s")
        stock = st.session_state.df[st.session_state.df['대여여부'] == '재고']
        if rent_search: stock = stock[stock.apply(lambda row: row.astype(str).str.contains(rent_search, case=False).any(), axis=1)]
        
        if stock.empty: st.info("재고 없음")
        else:
            rent_opts = stock.apply(lambda x: f"{x['이름']} ({x['수량']}개)", axis=1)
            sel = st.selectbox("선택", options=rent_opts.index, format_func=lambda x: rent_opts[x], key="rent_sel")
            if sel is not None:
                item = st.session_state.df.loc[sel]
                with st.form("rent"):
                    tgt = st.text_input("업체명"); c1, c2, c3 = st.columns(3)
                    q = c1.number_input("수량", 1, int(item['수량']), 1); d1 = c2.date_input("대여일"); d2 = c3.date_input("반납예정일(필수)", value=None)
                    if st.form_submit_button("대여"):
                        if not tgt: st.error("업체명 필수")
                        elif d2 is None: st.error("반납일 필수")
                        else:
                            d1s = d1.strftime("%Y-%m-%d"); d2s = d2.strftime("%Y-%m-%d")
                            if q < item['수량']:
                                st.session_state.df.at[sel, '수량'] -= q
                                new_r = item.copy(); new_r['ID'] = str(uuid.uuid4()); new_r['수량'] = q; new_r['대여여부'] = '대여 중'; new_r['대여자'] = tgt; new_r['대여일'] = d1s; new_r['반납예정일'] = d2s
                                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_r])], ignore_index=True)
                            else:
                                st.session_state.df.at[sel, '대여여부'] = '대여 중'; st.session_state.df.at[sel, '대여자'] = tgt; st.session_state.df.at[sel, '대여일'] = d1s; st.session_state.df.at[sel, '반납예정일'] = d2s
                            log_transaction("외부대여", item['이름'], q, tgt, d1s, d2s); save_data(st.session_state.df); st.success("완료"); st.rerun()
        st.write("---")
        st.write("#### 📋 현재 대여 중 목록"); cur_rent = st.session_state.df[st.session_state.df['대여여부'] == '대여 중']
        if not cur_rent.empty: st.dataframe(cur_rent[['이름', '대여자', '수량', '반납예정일']], use_container_width=True)

    # 3. 현장 출고
    with tabs[2]:
        st.subheader("🎬 현장 출고")
        disp_search = st.text_input("🔍 검색", key="disp_s")
        stock = st.session_state.df[st.session_state.df['대여여부'] == '재고']
        if disp_search: stock = stock[stock.apply(lambda row: row.astype(str).str.contains(disp_search, case=False).any(), axis=1)]
        
        if stock.empty: st.info("재고 없음")
        else:
            disp_opts = stock.apply(lambda x: f"{x['이름']} ({x['수량']}개)", axis=1)
            sel = st.selectbox("선택", options=disp_opts.index, format_func=lambda x: disp_opts[x], key="disp_sel")
            if sel is not None:
                item = st.session_state.df.loc[sel]
                with st.form("disp"):
                    # [수정] 현장명 입력 안내 명확화
                    tgt = st.text_input("현장명"); c1, c2, c3 = st.columns(3)
                    q = c1.number_input("수량", 1, int(item['수량']), 1); d1 = c2.date_input("출고일"); d2 = c3.date_input("반납예정일(필수)", value=None); note = st.text_input("비고")
                    if st.form_submit_button("출고"):
                        if not tgt: st.error("현장명 필수")
                        elif d2 is None: st.error("반납일 필수")
                        else:
                            d1s = d1.strftime("%Y-%m-%d"); d2s = d2.strftime("%Y-%m-%d")
                            if q < item['수량']:
                                st.session_state.df.at[sel, '수량'] -= q
                                new_r = item.copy(); new_r['ID'] = str(uuid.uuid4()); new_r['수량'] = q; new_r['대여여부'] = '현장 출고'; new_r['대여자'] = tgt; new_r['대여일'] = d1s; new_r['반납예정일'] = d2s; new_r['출고비고'] = note
                                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_r])], ignore_index=True)
                            else:
                                st.session_state.df.at[sel, '대여여부'] = '현장 출고'; st.session_state.df.at[sel, '대여자'] = tgt; st.session_state.df.at[sel, '대여일'] = d1s; st.session_state.df.at[sel, '반납예정일'] = d2s; st.session_state.df.at[sel, '출고비고'] = note
                            log_transaction("현장출고", item['이름'], q, tgt, d1s, d2s); save_data(st.session_state.df)
                            st.success("출고 완료"); st.rerun()

        st.write("---")
        st.write("#### 📋 현장별 현황 (출고증 통합 다운로드)")
        
        # [수정] 현장별 필터 및 통합 다운로드 기능
        cur_disp = st.session_state.df[st.session_state.df['대여여부'] == '현장 출고']
        if not cur_disp.empty:
            sites = ["선택하세요"] + list(cur_disp['대여자'].unique())
            s_site = st.selectbox("현장 선택 (출고증을 뽑으려면 선택하세요)", sites)
            
            if s_site != "선택하세요":
                site_data = cur_disp[cur_disp['대여자'] == s_site]
                # 컬럼명도 UI에 맞게 '현장명'으로 표시
                display_table = site_data[['대여자', '이름', '수량', '반납예정일', '출고비고']].rename(columns={'대여자': '현장명'})
                st.dataframe(display_table, use_container_width=True)
                
                # [수정] 통합 출고증 다운로드 버튼
                ticket_data = create_dispatch_ticket_grouped(s_site, site_data, st.session_state.username)
                st.download_button(
                    label=f"📄 [{s_site}] 전체 출고증 다운로드",
                    data=ticket_data,
                    file_name=f"dispatch_ticket_{s_site}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.info("출고된 장비가 없습니다.")

    # 4. 반납
    with tabs[3]:
        st.subheader("📥 반납")
        ret_s = st.text_input("🔍 검색", key="ret_s")
        ret_df = st.session_state.df[st.session_state.df['대여여부'].isin(['대여 중', '현장 출고'])]
        if ret_s: ret_df = ret_df[ret_df.apply(lambda row: row.astype(str).str.contains(ret_s, case=False).any(), axis=1)]
        if ret_df.empty: st.info("대상 없음")
        else:
            # 여기도 '현장명'으로 표시되도록 수정
            opts = ret_df.apply(lambda x: f"[{x['대여여부']}] {x['이름']} - {x['대여자']}", axis=1)
            sel = st.selectbox("선택", options=opts.index, format_func=lambda x: opts[x], key="ret_sel")
            if sel is not None:
                item = st.session_state.df.loc[sel]
                with st.form("ret"):
                    q = st.number_input("수량", 1, int(item['수량']), int(item['수량']))
                    if st.form_submit_button("반납"):
                        mask = ((st.session_state.df['이름'] == item['이름']) & (st.session_state.df['브랜드'] == item['브랜드']) & (st.session_state.df['대여여부'] == '재고'))
                        m_idx = st.session_state.df[mask].index
                        if q < item['수량']:
                            st.session_state.df.at[sel, '수량'] -= q
                            if not m_idx.empty: st.session_state.df.at[m_idx[0], '수량'] += q
                            else:
                                new_r = item.copy(); new_r['ID'] = str(uuid.uuid4()); new_r['수량'] = q; new_r['대여여부'] = '재고'; new_r['대여자'] = ''
                                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_r])], ignore_index=True)
                        else:
                            if not m_idx.empty:
                                st.session_state.df.at[m_idx[0], '수량'] += q
                                st.session_state.df = st.session_state.df.drop(sel).reset_index(drop=True)
                            else:
                                st.session_state.df.at[sel, '대여여부'] = '재고'; st.session_state.df.at[sel, '대여자'] = ''
                        log_transaction("반납", item['이름'], q, item['대여자'], datetime.now().strftime("%Y-%m-%d")); save_data(st.session_state.df); st.success("완료"); st.rerun()

    # 5. 수리/파손
    with tabs[4]:
        st.subheader("🛠️ 수리/파손")
        m_s = st.text_input("🔍 검색", key="maint_s")
        m_df = st.session_state.df[st.session_state.df['대여여부'].isin(['재고', '수리 중', '파손'])]
        if m_s: m_df = m_df[m_df.apply(lambda row: row.astype(str).str.contains(m_s, case=False).any(), axis=1)]
        if m_df.empty: st.info("없음")
        else:
            opts = m_df.apply(lambda x: f"[{x['대여여부']}] {x['이름']}", axis=1)
            sel = st.selectbox("선택", options=opts.index, format_func=lambda x: opts[x], key="maint_sel")
            if sel is not None:
                item = st.session_state.df.loc[sel]
                with st.form("maint"):
                    stat = st.selectbox("변경 상태", ["재고", "수리 중", "파손"])
                    q = st.number_input("수량", 1, int(item['수량']), int(item['수량']))
                    if st.form_submit_button("변경"):
                        st.session_state.df.at[sel, '대여여부'] = stat
                        if stat == '재고': st.session_state.df.at[sel, '대여자'] = ''
                        log_transaction(f"상태변경({stat})", item['이름'], q, stat, datetime.now().strftime("%Y-%m-%d")); save_data(st.session_state.df); st.success("완료"); st.rerun()

    # 6. 내역 관리
    with tabs[5]:
        st.subheader("📜 내역 관리")
        if os.path.exists(LOG_FILE_NAME):
            log_df = pd.read_csv(LOG_FILE_NAME)
            log_df = log_df.iloc[::-1] # 최신순
            
            if user_role == 'admin':
                st.warning("⚠️ 관리자 권한: 내역 삭제 가능")
                if '선택' not in log_df.columns: log_df.insert(0, "선택", False)
                if st.checkbox("✅ 전체 선택"): log_df['선택'] = True
                
                edited_df = st.data_editor(log_df, hide_index=True, use_container_width=True)
                if st.button("선택한 내역 영구 삭제"):
                    remaining_df = edited_df[edited_df['선택'] == False].drop(columns=['선택'])
                    remaining_df.to_csv(LOG_FILE_NAME, index=False)
                    st.success("삭제 완료"); st.rerun()
            else:
                st.dataframe(log_df, use_container_width=True)
            csv_d = log_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("내역 다운로드 (CSV)", csv_d, "history.csv", "text/csv")
        else: st.info("기록 없음")

    # 7. 관리자 페이지
    if user_role == 'admin':
        with tabs[6]:
            st.subheader("👑 관리자 페이지")
            
            st.write("#### 👥 전체 회원 관리 (탈퇴)")
            users = get_all_users()
            approved_users = users[users['approved'] == True]
            
            if approved_users.empty:
                st.info("승인된 회원이 없습니다.")
            else:
                for idx, row in approved_users.iterrows():
                    if row['role'] == 'admin': continue
                    
                    c1, c2, c3 = st.columns([3, 2, 1])
                    c1.write(f"👤 **{row['username']}** (생일: {row['birthdate']})")
                    c2.caption(f"가입일: {row['created_at']}")
                    if c3.button("추방(탈퇴)", key=f"kick_{idx}"):
                        update_user_status(row['username'], "delete")
                        st.warning(f"{row['username']} 님을 탈퇴시켰습니다.")
                        st.rerun()

            st.divider()

            st.write("#### ⏳ 승인 대기")
            pending = users[users['approved'] == False]
            if pending.empty: st.info("대기 없음")
            else:
                for idx, row in pending.iterrows():
                    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                    c1.write(f"**{row['username']}** (생일: {row['birthdate']})")
                    if c3.button("승인", key=f"ok_{idx}"): update_user_status(row['username'], "approve"); st.rerun()
                    if c4.button("거절", key=f"no_{idx}"): update_user_status(row['username'], "delete"); st.rerun()
            
            st.divider()
            st.write("#### 🗑️ 삭제 요청 목록")
            if os.path.exists(DEL_REQ_FILE_NAME):
                reqs = pd.read_csv(DEL_REQ_FILE_NAME)
                if reqs.empty: st.info("요청 없음")
                else:
                    for idx, row in reqs.iterrows():
                        with st.expander(f"{row['item_name']} - {row['requester']}"):
                            st.write(f"사유: {row['reason']}")
                            c1, c2 = st.columns(2)
                            if c1.button("승인(삭제)", key=f"del_ok_{row['req_id']}"):
                                st.session_state.df = st.session_state.df[st.session_state.df['ID'] != row['item_id']]
                                save_data(st.session_state.df)
                                reqs = reqs[reqs['req_id'] != row['req_id']]; reqs.to_csv(DEL_REQ_FILE_NAME, index=False)
                                st.success("삭제됨"); st.rerun()
                            if c2.button("반려", key=f"del_no_{row['req_id']}"):
                                reqs = reqs[reqs['req_id'] != row['req_id']]; reqs.to_csv(DEL_REQ_FILE_NAME, index=False)
                                st.warning("반려됨"); st.rerun()

def login_page():
    st.title("🔒 통합 장비 관리 시스템")
    t1, t2 = st.tabs(["로그인", "회원가입"])
    with t1:
        with st.form("login"):
            id_in = st.text_input("아이디"); pw_in = st.text_input("비밀번호", type="password")
            if st.form_submit_button("로그인"):
                succ, msg, role = login_user(id_in, pw_in)
                if succ:
                    st.session_state.logged_in = True; st.session_state.username = id_in; st.session_state.role = role; st.rerun()
                else: st.error(msg)
    with t2:
        st.info("관리자 승인 필요")
        with st.form("signup"):
            new_id = st.text_input("아이디 (실명 권장)"); new_pw = st.text_input("비밀번호", type="password")
            birth = st.date_input("생년월일", min_value=datetime(1960,1,1), max_value=datetime.now())
            if st.form_submit_button("신청"):
                if new_id and new_pw:
                    succ, msg = register_user(new_id, new_pw, birth)
                    if succ: st.success(msg)
                    else: st.error(msg)
                else: st.error("입력 필수")

if __name__ == '__main__':
    init_user_db()
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: login_page()
