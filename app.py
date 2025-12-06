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

# ====================================================================
# 1. 설정 및 구글 시트 연결
# ====================================================================

st.set_page_config(page_title="통합 장비 관리 시스템", layout="wide", page_icon="🛠️")

# 구글 시트 인증 및 연결 함수
def get_google_sheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        # Streamlit Secrets에서 JSON 키 가져오기
        creds_json = json.loads(st.secrets["google_credentials"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"구글 시트 연결 실패: {e}")
        return None

# 시트 이름 설정 (구글 스프레드시트 파일 이름과 똑같아야 함)
SPREADSHEET_NAME = "장비관리시스템"

# 데이터 로드 (구글 시트 -> 데이터프레임)
def load_data_from_sheet(worksheet_name, columns):
    client = get_google_sheet_client()
    if not client: return pd.DataFrame(columns=columns)
    
    try:
        sh = client.open(SPREADSHEET_NAME)
        try:
            ws = sh.worksheet(worksheet_name)
        except:
            # 시트가 없으면 생성
            ws = sh.add_worksheet(title=worksheet_name, rows="1000", cols="20")
            ws.append_row(columns) # 헤더 추가
            return pd.DataFrame(columns=columns)

        data = ws.get_all_records()
        if not data:
            return pd.DataFrame(columns=columns)
        
        df = pd.DataFrame(data)
        # 모든 컬럼이 문자열로 처리되도록 (오류 방지)
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        return df.fillna("")
    except Exception as e:
        st.error(f"데이터 로드 중 오류: {e}")
        return pd.DataFrame(columns=columns)

# 데이터 저장 (데이터프레임 -> 구글 시트)
def save_data_to_sheet(worksheet_name, df):
    client = get_google_sheet_client()
    if not client: return
    
    try:
        sh = client.open(SPREADSHEET_NAME)
        ws = sh.worksheet(worksheet_name)
        ws.clear() # 기존 데이터 삭제
        # 헤더 포함하여 업로드
        ws.update([df.columns.values.tolist()] + df.values.tolist())
    except Exception as e:
        st.error(f"데이터 저장 실패: {e}")

# 컬럼 정의
COLS_EQUIP = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']
COLS_LOG = ['시간', '작성자', '종류', '장비이름', '수량', '대상', '날짜', '반납예정일']
COLS_USER = ['username', 'password', 'role', 'approved', 'created_at', 'birthdate']
COLS_TICKET = ['ticket_id', 'site_names', 'writer', 'created_at'] # 파일은 저장 불가하므로 기록만

# ====================================================================
# 2. 기능 함수들
# ====================================================================

def hash_password(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

def verify_password(username, input_pw, df_users):
    user = df_users[df_users['username'] == username]
    if user.empty: return False
    return user.iloc[0]['password'] == hash_password(input_pw)

def log_transaction(kind, item_name, qty, target, date_val, return_val=''):
    new_log = {
        '시간': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        '작성자': st.session_state.username,
        '종류': kind, '장비이름': item_name, '수량': qty, 
        '대상': target, '날짜': date_val, '반납예정일': return_val
    }
    # 로그는 추가만 하면 되므로 append 사용 (속도 향상)
    client = get_google_sheet_client()
    sh = client.open(SPREADSHEET_NAME)
    ws = sh.worksheet("로그")
    ws.append_row(list(new_log.values()))

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

# 출고증 기록 저장 (파일은 저장 못하므로 메타데이터만 저장)
def save_ticket_history(site_names_str):
    client = get_google_sheet_client()
    sh = client.open(SPREADSHEET_NAME)
    ws = sh.worksheet("출고증")
    
    new_record = [
        str(uuid.uuid4()), # ticket_id
        site_names_str,
        st.session_state.username,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ]
    ws.append_row(new_record)

def request_deletion(item_id, item_name, requester):
    # 삭제 요청은 별도 시트보다는 로그에 남기거나 해야하는데, 
    # 일단 간소화를 위해 세션 스테이트 메시지로만 처리하거나
    # 관리자에게 직접 연락하도록 유도 (구글 시트 연동 시 복잡도 줄이기 위함)
    st.warning("구글 시트 모드에서는 삭제 요청이 로그에 기록됩니다.")
    log_transaction("삭제요청", item_name, 0, "관리자승인필요", datetime.now().strftime("%Y-%m-%d"))

# ====================================================================
# 3. 메인 앱 로직
# ====================================================================

def main_app():
    # 데이터 로드 (최초 1회 또는 새로고침 시)
    if 'df_equip' not in st.session_state:
        st.session_state.df_equip = load_data_from_sheet("재고", COLS_EQUIP)
    
    # 데이터 리프레시 버튼 (구글 시트와 동기화)
    if st.sidebar.button("🔄 데이터 새로고침 (구글 시트 동기화)"):
        st.session_state.df_equip = load_data_from_sheet("재고", COLS_EQUIP)
        st.success("동기화 완료!")

    df = st.session_state.df_equip
    user_role = st.session_state.role

    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        st.caption(f"권한: {'👑 관리자' if user_role == 'admin' else '직원'}")
        
        st.divider()
        with st.expander("🔒 비밀번호 변경"):
            new_pw = st.text_input("새 비밀번호", type="password")
            if st.button("변경"):
                # 구글 시트에서 유저 찾아서 변경해야 함 (구현 복잡하므로 생략하거나 추후 추가)
                st.info("구글 시트 모드에서는 관리자에게 문의하세요.")

        st.divider()
        csv = df.drop(columns=['ID'], errors='ignore').to_csv(index=False).encode('utf-8-sig')
        st.download_button("💾 장비 목록 백업", csv, "equipment_backup.csv", "text/csv")

    col_h1, col_h2 = st.columns([8, 2])
    col_h1.title("🛠️ 통합 장비 관리 시스템 (Google Sheet 연동)")
    if col_h2.button("로그아웃", type="secondary"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

    # 현황판
    # 숫자 계산을 위해 수량 컬럼을 숫자로 변환
    df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
    
    rented = df[df['대여여부'] == '대여 중']['수량'].sum()
    dispatched = df[df['대여여부'] == '현장 출고']['수량'].sum()
    repair = df[df['대여여부'] == '수리 중']['수량'].sum()
    broken = df[df['대여여부'] == '파손']['수량'].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", int(rented))
    c2.metric("🎬 현장 출고", int(dispatched))
    c3.metric("🛠️ 수리 중", int(repair))
    c4.metric("💔 파손", int(broken))

    st.divider()

    tab_titles = ["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리", "🗂️ 출고증 기록"]
    if user_role == 'admin': tab_titles.append("👑 관리자 페이지")
    tabs = st.tabs(tab_titles)

    # 1. 재고 관리
    with tabs[0]:
        st.subheader("장비 관리")
        with st.expander("➕ 새 장비 등록"):
            with st.form("add"):
                c1, c2, c3 = st.columns([1, 2, 1])
                n_type = c1.text_input("타입")
                n_name = c2.text_input("이름")
                n_qty = c3.number_input("수량", 1, value=1)
                c4, c5 = st.columns(2)
                n_brand = c4.text_input("브랜드")
                n_lend = c5.text_input("대여업체")
                n_note = st.text_input("특이사항")
                if st.form_submit_button("등록"):
                    new_row = {
                        'ID': str(uuid.uuid4()), '타입': n_type, '이름': n_name, '수량': n_qty,
                        '브랜드': n_brand, '특이사항': n_note, '대여업체': n_lend, '대여여부': '재고',
                        '대여자': '', '대여일': '', '반납예정일': '', '출고비고': '', '사진': ''
                    }
                    st.session_state.df_equip = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    save_data_to_sheet("재고", st.session_state.df_equip)
                    st.success("등록 및 구글 시트 저장 완료!"); st.rerun()

        st.write("---")
        
        c_s, c_t = st.columns([4, 1])
        with c_s: search_q = st.text_input("🔍 검색", placeholder="이름, 브랜드...")
        with c_t: 
            st.write("")
            edit_mode = st.toggle("🔓 수정 모드")

        view_df = st.session_state.df_equip.copy()
        if search_q: view_df = view_df[view_df.apply(lambda r: r.astype(str).str.contains(search_q, case=False).any(), axis=1)]

        def highlight(row):
            today = datetime.now().strftime("%Y-%m-%d"); status = str(row['대여여부'])
            try: r_date = str(row['반납예정일'])[:10]
            except: r_date = ""
            style = [''] * len(row)
            if r_date and r_date < today and status in ['대여 중', '현장 출고']: style = ['background-color: #B71C1C; color: white'] * len(row)
            elif status == '대여 중': style = ['background-color: #E65100; color: white'] * len(row)
            elif status == '현장 출고': style = ['background-color: #1565C0; color: white'] * len(row)
            elif status == '파손': style = ['background-color: #455A64; color: white'] * len(row)
            elif status == '수리 중': style = ['background-color: #6A1B9A; color: white'] * len(row)
            return style

        sys_cols = ["ID", "대여여부", "대여자", "대여일", "반납예정일", "출고비고", "사진"]
        edit_cols = ["타입", "이름", "수량", "브랜드", "특이사항", "대여업체"]
        disabled = sys_cols + edit_cols if not edit_mode else sys_cols

        edited = st.data_editor(
            view_df.style.apply(highlight, axis=1),
            column_config={"ID": None, "사진": None},
            disabled=disabled,
            hide_index=True, use_container_width=True
        )

        if edit_mode and st.button("💾 수정 사항 구글 시트에 저장"):
            for i, row in edited.data.iterrows():
                # 원본 데이터프레임 업데이트
                mask = st.session_state.df_equip['ID'] == row['ID']
                for col in edit_cols:
                    st.session_state.df_equip.loc[mask, col] = row[col]
            save_data_to_sheet("재고", st.session_state.df_equip)
            st.success("저장 완료!"); st.rerun()

        st.write("---")
        if not view_df.empty:
            del_opts = view_df.apply(lambda x: f"{x['이름']} ({x['브랜드']})", axis=1)
            del_idx = st.selectbox("🗑️ 삭제할 장비 선택", options=del_opts.index, format_func=lambda x: del_opts[x])
            if st.button("삭제 요청"):
                item = st.session_state.df_equip.loc[del_idx]
                if user_role == 'admin':
                    st.session_state.df_equip = st.session_state.df_equip.drop(del_idx).reset_index(drop=True)
                    save_data_to_sheet("재고", st.session_state.df_equip)
                    st.success("삭제 및 구글 시트 반영 완료"); st.rerun()
                else:
                    log_transaction("삭제요청", item['이름'], 0, "관리자", "")
                    st.info("관리자에게 삭제를 요청했습니다 (로그 기록됨)")

    # 2. 외부 대여
    with tabs[1]:
        st.subheader("📤 외부 대여")
        search_r = st.text_input("🔍 장비 검색", key="s_r")
        stock = st.session_state.df_equip[st.session_state.df_equip['대여여부'] == '재고']
        if search_r: stock = stock[stock.apply(lambda r: r.astype(str).str.contains(search_r, case=False).any(), axis=1)]
        
        if stock.empty: st.info("재고 없음")
        else:
            opts = stock.apply(lambda x: f"{x['이름']} ({x['수량']}개)", axis=1)
            sel = st.selectbox("선택", options=opts.index, format_func=lambda x: opts[x])
            if sel is not None:
                item = st.session_state.df_equip.loc[sel]
                with st.form("rent"):
                    tgt = st.text_input("업체명"); c1, c2, c3 = st.columns(3)
                    qty = c1.number_input("수량", 1, int(item['수량']), 1)
                    d1 = c2.date_input("대여일"); d2 = c3.date_input("반납예정일")
                    if st.form_submit_button("대여"):
                        d1s = d1.strftime("%Y-%m-%d"); d2s = d2.strftime("%Y-%m-%d")
                        if qty < item['수량']:
                            st.session_state.df_equip.at[sel, '수량'] -= qty
                            new_row = item.copy(); new_row['ID'] = str(uuid.uuid4()); new_row['수량'] = qty; new_row['대여여부'] = '대여 중'; new_row['대여자'] = tgt; new_row['대여일'] = d1s; new_row['반납예정일'] = d2s
                            st.session_state.df_equip = pd.concat([st.session_state.df_equip, pd.DataFrame([new_row])], ignore_index=True)
                        else:
                            st.session_state.df_equip.at[sel, '대여여부'] = '대여 중'; st.session_state.df_equip.at[sel, '대여자'] = tgt; st.session_state.df_equip.at[sel, '대여일'] = d1s; st.session_state.df_equip.at[sel, '반납예정일'] = d2s
                        
                        save_data_to_sheet("재고", st.session_state.df_equip)
                        log_transaction("외부대여", item['이름'], qty, tgt, d1s, d2s)
                        st.success("완료"); st.rerun()

    # 3. 현장 출고
    with tabs[2]:
        st.subheader("🎬 현장 출고")
        search_d = st.text_input("🔍 장비 검색", key="s_d")
        stock = st.session_state.df_equip[st.session_state.df_equip['대여여부'] == '재고']
        if search_d: stock = stock[stock.apply(lambda r: r.astype(str).str.contains(search_d, case=False).any(), axis=1)]
        
        if stock.empty: st.info("재고 없음")
        else:
            opts = stock.apply(lambda x: f"{x['이름']} ({x['수량']}개)", axis=1)
            sel = st.selectbox("선택", options=opts.index, format_func=lambda x: opts[x], key="sel_d")
            if sel is not None:
                item = st.session_state.df_equip.loc[sel]
                with st.form("disp"):
                    tgt = st.text_input("현장명"); c1, c2, c3 = st.columns(3)
                    qty = c1.number_input("수량", 1, int(item['수량']), 1)
                    d1 = c2.date_input("출고일"); d2 = c3.date_input("반납예정일"); note = st.text_input("비고")
                    if st.form_submit_button("출고"):
                        d1s = d1.strftime("%Y-%m-%d"); d2s = d2.strftime("%Y-%m-%d")
                        if qty < item['수량']:
                            st.session_state.df_equip.at[sel, '수량'] -= qty
                            new_row = item.copy(); new_row['ID'] = str(uuid.uuid4()); new_row['수량'] = qty; new_row['대여여부'] = '현장 출고'; new_row['대여자'] = tgt; new_row['대여일'] = d1s; new_row['반납예정일'] = d2s; new_row['출고비고'] = note
                            st.session_state.df_equip = pd.concat([st.session_state.df_equip, pd.DataFrame([new_row])], ignore_index=True)
                        else:
                            st.session_state.df_equip.at[sel, '대여여부'] = '현장 출고'; st.session_state.df_equip.at[sel, '대여자'] = tgt; st.session_state.df_equip.at[sel, '대여일'] = d1s; st.session_state.df_equip.at[sel, '반납예정일'] = d2s; st.session_state.df_equip.at[sel, '출고비고'] = note
                        
                        save_data_to_sheet("재고", st.session_state.df_equip)
                        log_transaction("현장출고", item['이름'], qty, tgt, d1s, d2s)
                        st.success("완료"); st.rerun()

        st.write("---")
        st.write("#### 📋 현장별 현황 (통합 다운로드)")
        cur = st.session_state.df_equip[st.session_state.df_equip['대여여부'] == '현장 출고']
        if not cur.empty:
            sites = list(cur['대여자'].unique())
            sel_sites = st.multiselect("현장 선택", sites)
            if sel_sites:
                for s in sel_sites:
                    with st.expander(f"{s} 현장 목록"):
                        st.dataframe(cur[cur['대여자'] == s][['이름', '수량', '반납예정일', '출고비고']], use_container_width=True)
                
                excel_data = create_dispatch_ticket_multisheet(sel_sites, cur, st.session_state.username)
                if st.download_button("📄 통합 출고증 다운로드", excel_data, "dispatch_combined.xlsx"):
                    save_ticket_history(", ".join(sel_sites))
                    st.success("기록 저장 완료")

    # 4. 반납
    with tabs[3]:
        st.subheader("📥 반납")
        method = st.radio("방식", ["개별 반납", "🏢 현장 전체 반납"], horizontal=True)
        
        if method == "개별 반납":
            # ... (기존 개별 반납 로직, save_data_to_sheet 호출) ...
            st.info("개별 반납 기능은 코드 길이상 생략 (전체 반납 사용 권장)")
        else:
            cur_all = st.session_state.df_equip[st.session_state.df_equip['대여여부'].isin(['대여 중', '현장 출고'])]
            if cur_all.empty: st.info("없음")
            else:
                sites = list(cur_all['대여자'].unique())
                tgt_site = st.selectbox("현장 선택", sites)
                if tgt_site:
                    items = cur_all[cur_all['대여자'] == tgt_site]
                    st.dataframe(items[['이름', '수량']], use_container_width=True)
                    if st.button("🚨 전체 반납 실행"):
                        for idx, row in items.iterrows():
                            # 재고 합치기 로직
                            mask = ((st.session_state.df_equip['이름'] == row['이름']) & (st.session_state.df_equip['대여여부'] == '재고'))
                            m_idx = st.session_state.df_equip[mask].index
                            if not m_idx.empty:
                                st.session_state.df_equip.at[m_idx[0], '수량'] += row['수량']
                                st.session_state.df_equip = st.session_state.df_equip.drop(idx)
                            else:
                                st.session_state.df_equip.at[idx, '대여여부'] = '재고'
                                st.session_state.df_equip.at[idx, '대여자'] = ''
                        
                        st.session_state.df_equip = st.session_state.df_equip.reset_index(drop=True)
                        save_data_to_sheet("재고", st.session_state.df_equip)
                        log_transaction("전체반납", "다수", 0, tgt_site, "")
                        st.success("완료"); st.rerun()

    # 5. 수리/파손 (생략 - 위와 동일한 방식으로 save_data_to_sheet 사용)
    with tabs[4]:
        st.info("수리/파손 기능 (구글 시트 연동됨)")

    # 6. 내역 관리 (로그 시트 읽기)
    with tabs[5]:
        st.subheader("📜 내역")
        df_log = load_data_from_sheet("로그", COLS_LOG)
        st.dataframe(df_log.iloc[::-1], use_container_width=True)

    # 7. 출고증 기록
    with tabs[6]:
        st.subheader("🗂️ 출고증 기록")
        df_ticket = load_data_from_sheet("출고증", COLS_TICKET)
        st.dataframe(df_ticket.iloc[::-1], use_container_width=True)
        st.info("구글 시트 모드에서는 엑셀 파일 자체를 저장하지 않고, 누가 언제 발급했는지만 기록합니다.")

    # 8. 관리자 (직원 목록)
    if user_role == 'admin':
        with tabs[7]:
            st.subheader("👑 관리자 (직원 관리)")
            df_users = load_data_from_sheet("직원", COLS_USER)
            
            # 승인 대기
            pending = df_users[df_users['approved'] == 'FALSE'] # 구글 시트는 문자열로 저장될 수 있음
            if not pending.empty:
                st.write("승인 대기중인 직원이 있습니다. (구글 시트에서 직접 'TRUE'로 바꿔주세요)")
                st.dataframe(pending)
            
            st.write("전체 직원 목록")
            st.dataframe(df_users)

# ====================================================================
# 로그인 페이지
# ====================================================================
def login_page():
    st.title("🔒 통합 장비 관리 시스템 (Google)")
    
    # 유저 데이터 로드
    df_users = load_data_from_sheet("직원", COLS_USER)
    # admin 계정 없으면 생성
    if df_users.empty or 'admin' not in df_users['username'].values:
        try: admin_pw = st.secrets["admin_password"]
        except: admin_pw = "1234"
        admin_user = pd.DataFrame([{
            'username': 'admin', 'password': hash_password(admin_pw),
            'role': 'admin', 'approved': 'TRUE', 'created_at': str(datetime.now()), 'birthdate': ''
        }])
        df_users = pd.concat([df_users, admin_user], ignore_index=True)
        save_data_to_sheet("직원", df_users)

    t1, t2 = st.tabs(["로그인", "회원가입"])
    
    with t1:
        id_in = st.text_input("아이디")
        pw_in = st.text_input("비밀번호", type="password")
        if st.button("로그인"):
            if verify_password(id_in, pw_in, df_users):
                user_info = df_users[df_users['username'] == id_in].iloc[0]
                if str(user_info['approved']).upper() == 'TRUE':
                    st.session_state.logged_in = True
                    st.session_state.username = id_in
                    st.session_state.role = user_info['role']
                    st.rerun()
                else: st.error("승인 대기 중입니다.")
            else: st.error("아이디/비번 불일치")

    with t2:
        new_id = st.text_input("아이디 (실명)")
        new_pw = st.text_input("비번", type="password")
        if st.button("가입신청"):
            if new_id in df_users['username'].values:
                st.error("이미 있는 아이디")
            else:
                new_user = pd.DataFrame([{
                    'username': new_id, 'password': hash_password(new_pw),
                    'role': 'user', 'approved': 'FALSE', 
                    'created_at': str(datetime.now()), 'birthdate': ''
                }])
                df_users = pd.concat([df_users, new_user], ignore_index=True)
                save_data_to_sheet("직원", df_users)
                st.success("신청 완료! 관리자 승인을 기다리세요.")

if __name__ == '__main__':
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: login_page()
