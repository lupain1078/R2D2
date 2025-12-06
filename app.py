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

# 구글 시트 인증 (에러 방지 강화)
def get_google_sheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        # Secrets에서 데이터 가져오기 (문자열 또는 딕셔너리 모두 처리)
        secrets_val = st.secrets["google_credentials"]
        
        if isinstance(secrets_val, str):
            # 문자열이면 JSON으로 변환 (따옴표 문제 자동 수정 시도)
            try:
                creds_json = json.loads(secrets_val)
            except json.JSONDecodeError:
                # 작은따옴표를 큰따옴표로 바꿔서 재시도 (흔한 실수 방지)
                creds_json = json.loads(secrets_val.replace("'", '"'))
        else:
            # 이미 딕셔너리(TOML 파싱됨)라면 그대로 사용
            creds_json = secrets_val

        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"⚠️ 구글 연결 실패: Secrets 설정을 확인하세요.\n에러 내용: {e}")
        return None

# 시트 이름 설정
SPREADSHEET_NAME = "장비관리시스템"

# 데이터 로드
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
        # 컬럼 보정 (없는 컬럼 추가 및 문자열 변환)
        for col in columns:
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].astype(str).replace('nan', '')
            
        return df
    except Exception as e:
        st.error(f"데이터 로드 오류 ({worksheet_name}): {e}")
        return pd.DataFrame(columns=columns)

# 데이터 저장
def save_data_to_sheet(worksheet_name, df):
    client = get_google_sheet_client()
    if not client: return
    
    try:
        sh = client.open(SPREADSHEET_NAME)
        ws = sh.worksheet(worksheet_name)
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
    except Exception as e:
        st.error(f"데이터 저장 실패: {e}")

# 컬럼 정의
COLS_EQUIP = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진']
COLS_LOG = ['시간', '작성자', '종류', '장비이름', '수량', '대상', '날짜', '반납예정일']
COLS_USER = ['username', 'password', 'role', 'approved', 'created_at', 'birthdate']
COLS_TICKET = ['ticket_id', 'site_names', 'writer', 'created_at'] 

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
        '종류': kind, '장비이름': item_name, '수량': str(qty), 
        '대상': target, '날짜': date_val, '반납예정일': return_val
    }
    client = get_google_sheet_client()
    if client:
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
            
            ws.column_dimensions['A'].width = 25; ws.column_dimensions['B'].width = 15; ws.column_dimensions['C'].width = 10
            ws.column_dimensions['D'].width = 15; ws.column_dimensions['E'].width = 15; ws.column_dimensions['F'].width = 30
    return output.getvalue()

def save_ticket_history(site_names_str):
    client = get_google_sheet_client()
    if client:
        sh = client.open(SPREADSHEET_NAME)
        try: ws = sh.worksheet("출고증")
        except: ws = sh.add_worksheet("출고증", 1000, 10); ws.append_row(COLS_TICKET)
        
        new_record = [
            str(uuid.uuid4()), site_names_str, st.session_state.username,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]
        ws.append_row(new_record)

# ====================================================================
# 3. 메인 앱 로직
# ====================================================================

def main_app():
    if 'df_equip' not in st.session_state:
        st.session_state.df_equip = load_data_from_sheet("재고", COLS_EQUIP)
    
    # 사이드바
    df = st.session_state.df_equip
    user_role = st.session_state.role

    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        st.caption(f"권한: {'👑 관리자' if user_role == 'admin' else '직원'}") # 권한명 수정
        
        st.divider()
        if st.button("🔄 데이터 새로고침"):
            st.session_state.df_equip = load_data_from_sheet("재고", COLS_EQUIP)
            st.success("동기화 완료")

        st.divider()
        csv = df.drop(columns=['ID'], errors='ignore').to_csv(index=False).encode('utf-8-sig')
        st.download_button("💾 장비 목록 백업", csv, "equipment_backup.csv", "text/csv") # 버튼명 수정

    # 메인 헤더
    col_h1, col_h2 = st.columns([8, 2])
    col_h1.title("🛠️ 통합 장비 관리 시스템 (Google)")
    if col_h2.button("로그아웃", type="secondary"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

    # 현황판 (숫자 변환 후 계산)
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
                    new_row = {'ID': str(uuid.uuid4()), '타입': n_type, '이름': n_name, '수량': n_qty, '브랜드': n_brand, '특이사항': n_note, '대여업체': n_lend, '대여여부': '재고', '대여자': '', '대여일': '', '반납예정일': '', '출고비고': '', '사진': ''}
                    st.session_state.df_equip = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    save_data_to_sheet("재고", st.session_state.df_equip)
                    st.success("등록 완료"); st.rerun()

        st.write("---")
        c_s, c_t = st.columns([4, 1])
        with c_s: search_q = st.text_input("🔍 검색", placeholder="이름, 브랜드...")
        with c_t: st.write(""); edit_mode = st.toggle("🔓 수정 모드")

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

        disabled = ["ID", "대여여부", "대여자", "대여일", "반납예정일", "출고비고", "사진"]
        if not edit_mode: disabled += ["타입", "이름", "수량", "브랜드", "특이사항", "대여업체"]

        edited = st.data_editor(view_df.style.apply(highlight, axis=1), column_config={"ID": None, "사진": None}, disabled=disabled, hide_index=True, use_container_width=True)

        if edit_mode and st.button("💾 수정 사항 구글 시트에 저장"):
            for i, row in edited.data.iterrows():
                st.session_state.df_equip.loc[st.session_state.df_equip['ID'] == row['ID'], :] = row
            save_data_to_sheet("재고", st.session_state.df_equip)
            st.success("저장 완료"); st.rerun()

        st.write("---")
        if not view_df.empty:
            del_opts = view_df.apply(lambda x: f"{x['이름']} ({x['브랜드']})", axis=1)
            del_idx = st.selectbox("🗑️ 삭제할 장비 선택", options=del_opts.index, format_func=lambda x: del_opts[x])
            if st.button("삭제 요청"): # 버튼명 수정
                if user_role == 'admin':
                    st.session_state.df_equip = st.session_state.df_equip.drop(del_idx).reset_index(drop=True)
                    save_data_to_sheet("재고", st.session_state.df_equip)
                    st.success("삭제 완료"); st.rerun()
                else:
                    log_transaction("삭제요청", st.session_state.df_equip.loc[del_idx, '이름'], 0, "관리자", "")
                    st.info("관리자에게 삭제를 요청했습니다.")

    # 2. 외부 대여
    with tabs[1]:
        st.subheader("📤 외부 대여")
        search_r = st.text_input("🔍 검색", key="s_r")
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
        search_d = st.text_input("🔍 검색", key="s_d")
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
                    st.success("기록 완료")

    # 4. 반납
    with tabs[3]:
        st.subheader("📥 반납")
        method = st.radio("방식", ["개별 반납", "🏢 현장 전체 반납"], horizontal=True)
        cur_all = st.session_state.df_equip[st.session_state.df_equip['대여여부'].isin(['대여 중', '현장 출고'])]
        
        if method == "개별 반납":
            if cur_all.empty: st.info("반납 대상 없음")
            else:
                opts = cur_all.apply(lambda x: f"[{x['대여여부']}] {x['이름']} - {x['대여자']}", axis=1)
                sel = st.selectbox("선택", opts.index, format_func=lambda x: opts[x])
                if st.button("반납 실행"):
                    # 재고 합치기 로직
                    row = st.session_state.df_equip.loc[sel]
                    mask = ((st.session_state.df_equip['이름'] == row['이름']) & (st.session_state.df_equip['대여여부'] == '재고'))
                    m_idx = st.session_state.df_equip[mask].index
                    
                    if not m_idx.empty:
                        st.session_state.df_equip.at[m_idx[0], '수량'] += row['수량']
                        st.session_state.df_equip = st.session_state.df_equip.drop(sel)
                    else:
                        st.session_state.df_equip.at[sel, '대여여부'] = '재고'
                        st.session_state.df_equip.at[sel, '대여자'] = ''
                    
                    st.session_state.df_equip = st.session_state.df_equip.reset_index(drop=True)
                    save_data_to_sheet("재고", st.session_state.df_equip)
                    log_transaction("반납", row['이름'], row['수량'], row['대여자'], datetime.now().strftime("%Y-%m-%d"))
                    st.success("완료"); st.rerun()
        else:
            if cur_all.empty: st.info("없음")
            else:
                tgt_site = st.selectbox("현장 선택", list(cur_all['대여자'].unique()))
                if tgt_site and st.button("🚨 전체 반납"):
                    items = cur_all[cur_all['대여자'] == tgt_site]
                    for idx, row in items.iterrows():
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

    # 5. 수리/파손
    with tabs[4]:
        st.subheader("🛠️ 수리/파손")
        m_s = st.text_input("🔍 검색", key="m_s")
        m_df = st.session_state.df_equip[st.session_state.df_equip['대여여부'].isin(['재고', '수리 중', '파손'])]
        if m_s: m_df = m_df[m_df.apply(lambda r: r.astype(str).str.contains(m_s, case=False).any(), axis=1)]
        
        if not m_df.empty:
            opts = m_df.apply(lambda x: f"[{x['대여여부']}] {x['이름']}", axis=1)
            sel = st.selectbox("선택", opts.index, format_func=lambda x: opts[x])
            if sel is not None:
                item = st.session_state.df_equip.loc[sel]
                with st.form("maint"):
                    stat = st.selectbox("상태", ["재고", "수리 중", "파손"])
                    qty = st.number_input("수량", 1, int(item['수량']), int(item['수량']))
                    if st.form_submit_button("변경"):
                        st.session_state.df_equip.at[sel, '대여여부'] = stat
                        if stat == '재고': st.session_state.df_equip.at[sel, '대여자'] = ''
                        save_data_to_sheet("재고", st.session_state.df_equip)
                        log_transaction(f"상태변경({stat})", item['이름'], qty, stat, "")
                        st.success("완료"); st.rerun()

    # 6. 내역 관리 (사이즈 조정)
    with tabs[5]:
        st.subheader("📜 내역")
        df_log = load_data_from_sheet("로그", COLS_LOG)
        
        if user_role == 'admin':
            st.warning("관리자 삭제 모드")
            if '선택' not in df_log.columns: df_log.insert(0, '선택', False)
            # [수정] 체크박스 사이즈 조정
            edited_log = st.data_editor(
                df_log.iloc[::-1],
                column_config={"선택": st.column_config.CheckboxColumn("삭제", width="small")},
                hide_index=True, use_container_width=True
            )
            if st.button("선택 삭제"):
                # 구글 시트에서 행을 찾아 지워야 하는데 복잡하므로,
                # 전체 데이터를 다시 덮어쓰는 방식으로 간소화
                keep_df = edited_log[~edited_log['선택']].drop(columns=['선택'])
                save_data_to_sheet("로그", keep_df)
                st.success("삭제 완료"); st.rerun()
        else:
            st.dataframe(df_log.iloc[::-1], use_container_width=True)

    # 7. 출고증 기록
    with tabs[6]:
        st.subheader("🗂️ 출고증 발급 기록")
        df_tick = load_data_from_sheet("출고증", COLS_TICKET)
        if user_role == 'admin':
            if '선택' not in df_tick.columns: df_tick.insert(0, '선택', False)
            edited_tick = st.data_editor(
                df_tick.iloc[::-1],
                column_config={"선택": st.column_config.CheckboxColumn("삭제", width="small")},
                hide_index=True, use_container_width=True
            )
            if st.button("기록 삭제"):
                keep_df = edited_tick[~edited_tick['선택']].drop(columns=['선택'])
                save_data_to_sheet("출고증", keep_df)
                st.success("삭제 완료"); st.rerun()
        else:
            st.dataframe(df_tick.iloc[::-1], use_container_width=True)

    # 8. 관리자 (직원 관리)
    if user_role == 'admin':
        with tabs[7]:
            st.subheader("👑 전체 직원 관리") # 타이틀 수정
            df_users = load_data_from_sheet("직원", COLS_USER)
            
            edited_users = st.data_editor(
                df_users,
                column_config={
                    "approved": st.column_config.CheckboxColumn("승인 여부", width="small"),
                    "password": None # 비번 숨김
                },
                hide_index=True, use_container_width=True
            )
            if st.button("변경사항 저장 (승인/정보수정)"):
                save_data_to_sheet("직원", edited_users)
                st.success("저장 완료"); st.rerun()

# ====================================================================
# 로그인 페이지
# ====================================================================
def login_page():
    st.title("🔒 통합 장비 관리 시스템")
    
    df_users = load_data_from_sheet("직원", COLS_USER)
    if df_users.empty:
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
