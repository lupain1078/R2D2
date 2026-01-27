import streamlit as st
import pandas as pd
import os
import uuid
import hashlib
from datetime import datetime
from io import BytesIO
from streamlit_gsheets import GSheetsConnection

# 1. 페이지 기본 설정 및 구글 시트 연결
st.set_page_config(page_title="통합 장비 관리 시스템", layout="wide", page_icon="🛠️")
conn = st.connection("gsheets", type=GSheetsConnection)

# 장비 데이터 필드 정의
FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진', '삭제요청']

# 2. 데이터 처리 함수 (데이터 타입 및 공백 보정 강화)
def load_data(sheet_name="Sheet1"):
    try:
        df = conn.read(worksheet=sheet_name, ttl=0)
        df = df.fillna("")
        
        # [핵심] 모든 문자열의 공백을 제거하여 필터링 오류 방지
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        
        if sheet_name == "Sheet1":
            if not df.empty:
                # 삭제요청 열이 없으면 생성
                if '삭제요청' not in df.columns:
                    df['삭제요청'] = ""
                # 수량을 정수형으로 강제 변환
                df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0).astype(int)
            else:
                df = pd.DataFrame(columns=FIELD_NAMES)
        
        # [핵심] 회원 데이터의 승인 여부 타입 일치화
        if sheet_name == "Users":
            if not df.empty and 'approved' in df.columns:
                df['approved'] = df['approved'].astype(str).str.upper()
                
        return df
    except Exception as e:
        return pd.DataFrame()

def save_data(df, sheet_name="Sheet1"):
    # 저장 전 수량 정수화 확인
    if sheet_name == "Sheet1" and '수량' in df.columns:
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

def to_excel(df_list, sheet_names):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for df, name in zip(df_list, sheet_names):
            df.to_excel(writer, index=False, sheet_name=name)
    return output.getvalue()

# 3. 메인 앱 실행 함수
def main_app():
    if 'df' not in st.session_state:
        st.session_state.df = load_data("Sheet1")
    
    df = st.session_state.df
    is_admin = (st.session_state.username == "admin")

    # --- 사이드바 구역 ---
    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        
        # 데이터 관리 (회원 명단 제외 백업 기능)
        with st.expander("📂 데이터 관리", expanded=False):
            st.write("시스템 데이터를 엑셀로 백업합니다.")
            if st.button("📊 백업 파일 생성", use_container_width=True):
                with st.spinner("파일 생성 중..."):
                    logs_df = load_data("Logs")
                    excel_data = to_excel([st.session_state.df, logs_df], ["장비재고", "활동로그"])
                    st.download_button(
                        label="📥 엑셀 다운로드",
                        data=excel_data,
                        file_name=f"장비관리_백업_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
        st.write("---")
        if st.button("🚪 로그아웃", use_container_width=True):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    st.title("🛠️ 통합 장비 관리 시스템")

    # 상단 요약 지표 (정수 표시)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", int(df[df['대여여부'] == '대여 중']['수량'].sum()) if not df.empty else 0)
    c2.metric("🎬 현장 출고", int(df[df['대여여부'] == '현장 출고']['수량'].sum()) if not df.empty else 0)
    c3.metric("🛠️ 수리 중", int(df[df['대여여부'] == '수리 중']['수량'].sum()) if not df.empty else 0)
    c4.metric("💔 파손", int(df[df['대여여부'] == '파손']['수량'].sum()) if not df.empty else 0)

    # 탭 메뉴 정의
    tab_list = ["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리"]
    if is_admin:
        tab_list.append("👑 관리자 페이지")
    
    tabs = st.tabs(tab_list)

    # --- 탭 1: 재고 관리 ---
    with tabs[0]:
        with st.expander("➕ 새 장비 등록"):
            with st.form("add_form", clear_on_submit=True):
                col1, col2, col3 = st.columns([1,2,1])
                t_input = col1.text_input("타입")
                n_input = col2.text_input("장비명")
                q_input = col3.number_input("수량", 1, step=1)
                b_input = st.text_input("브랜드")
                if st.form_submit_button("등록"):
                    new_item = {
                        'ID': str(uuid.uuid4()), '타입': t_input, '이름': n_input, 
                        '수량': int(q_input), '브랜드': b_input, '대여여부': '재고', '삭제요청': ''
                    }
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_item])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    st.success("등록 완료")
                    st.rerun()
        
        edit_mode = st.toggle("🔓 수정 및 삭제 요청 모드")
        edited_df = st.data_editor(
            st.session_state.df, 
            disabled=(not edit_mode), 
            hide_index=True, 
            use_container_width=True,
            column_config={"ID": None} # ID 숨김
        )
        
        if edit_mode:
            if st.button("💾 모든 변경사항 저장"):
                save_data(edited_df, "Sheet1")
                st.session_state.df = edited_df
                st.success("저장 완료")
                st.rerun()
            st.write("---")
            target_del = st.selectbox("삭제 요청할 장비 선택", edited_df['이름'].unique() if not edited_df.empty else ["없음"])
            if st.button("🚩 삭제 요청 보내기") and not edited_df.empty:
                st.session_state.df.loc[st.session_state.df['이름'] == target_del, '삭제요청'] = 'Y'
                save_data(st.session_state.df, "Sheet1")
                st.warning(f"'{target_del}' 삭제 요청 완료")
                st.rerun()

    # --- 탭 2: 외부 대여 ---
    with tabs[1]:
        st.subheader("📤 외부 업체 대여 처리")
        stock_rent = st.session_state.df[(st.session_state.df['대여여부'] == '재고') & (st.session_state.df['수량'] > 0)]
        if not stock_rent.empty:
            opts_rent = stock_rent.apply(lambda x: f"{x['이름']} - 잔여: {int(x['수량'])}개", axis=1)
            sel_rent = st.selectbox("대여할 장비 선택", opts_rent.index, format_func=lambda x: opts_rent[x])
            with st.form("rent_form"):
                tgt_rent = st.text_input("대여 업체명")
                qty_rent = st.number_input("대여 수량", 1, int(stock_rent.loc[sel_rent, '수량']), step=1)
                r_date_rent = st.date_input("반납 예정일")
                if st.form_submit_button("대여 확정"):
                    item_rent = stock_rent.loc[sel_rent]
                    st.session_state.df.at[sel_rent, '수량'] -= int(qty_rent)
                    new_rent_row = item_rent.copy()
                    new_rent_row.update({
                        'ID': str(uuid.uuid4()), '수량': int(qty_rent), '대여여부': '대여 중', 
                        '대여자': tgt_rent, '대여일': datetime.now().strftime("%Y-%m-%d"), 
                        '반납예정일': str(r_date_rent)
                    })
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_rent_row])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    log_transaction("대여", item_rent['이름'], qty_rent, tgt_rent, datetime.now().strftime("%Y-%m-%d"), str(r_date_rent))
                    st.success("대여 처리 완료")
                    st.rerun()
        else: st.warning("대여 가능한 재고가 없습니다.")

    # --- 탭 3: 현장 출고 ---
    with tabs[2]:
        st.subheader("🎬 현장 출고 처리")
        stock_disp = st.session_state.df[(st.session_state.df['대여여부'] == '재고') & (st.session_state.df['수량'] > 0)]
        if not stock_disp.empty:
            opts_disp = stock_disp.apply(lambda x: f"{x['이름']} - 잔여: {int(x['수량'])}개", axis=1)
            sel_disp = st.selectbox("출고할 장비 선택", opts_disp.index, format_func=lambda x: opts_disp[x])
            with st.form("dispatch_form"):
                site_disp = st.text_input("현장명")
                qty_disp = st.number_input("출고 수량", 1, int(stock_disp.loc[sel_disp, '수량']), step=1)
                if st.form_submit_button("출고 확정"):
                    item_disp = stock_disp.loc[sel_disp]
                    st.session_state.df.at[sel_disp, '수량'] -= int(qty_disp)
                    new_disp_row = item_disp.copy()
                    new_disp_row.update({
                        'ID': str(uuid.uuid4()), '수량': int(qty_disp), '대여여부': '현장 출고', 
                        '대여자': site_disp, '대여일': datetime.now().strftime("%Y-%m-%d")
                    })
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_disp_row])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    log_transaction("현장출고", item_disp['이름'], qty_disp, site_disp, datetime.now().strftime("%Y-%m-%d"))
                    st.success("출고 처리 완료")
                    st.rerun()
        else: st.warning("출고 가능한 재고가 없습니다.")

    # --- 탭 4: 반납 처리 (목록 미노출 해결) ---
    with tabs[3]:
        st.subheader("📥 장비 반납 처리")
        # [해결] 공백 제거 후 필터링하여 목록이 나타나게 함
        rented_items = st.session_state.df[st.session_state.df['대여여부'].isin(['대여 중', '현장 출고'])]
        
        if not rented_items.empty:
            r_opts = rented_items.apply(lambda x: f"[{x['대여여부']}] {x['이름']} - {x['대여자']} ({int(x['수량'])}개)", axis=1)
            sel_ret = st.selectbox("반납 대상 선택", r_opts.index, format_func=lambda x: r_opts[x])
            
            if st.button("반납 확정"):
                item_ret = rented_items.loc[sel_ret]
                # 원래 재고 항목을 찾아 수량을 합침
                mask = (st.session_state.df['이름'] == item_ret['이름']) & (st.session_state.df['대여여부'] == '재고')
                if any(mask):
                    idx_stock = st.session_state.df[mask].index[0]
                    st.session_state.df.at[idx_stock, '수량'] = int(st.session_state.df.at[idx_stock, '수량']) + int(item_ret['수량'])
                    st.session_state.df = st.session_state.df.drop(sel_ret).reset_index(drop=True)
                else:
                    st.session_state.df.at[sel_ret, '대여여부'] = '재고'
                    st.session_state.df.at[sel_ret, '대여자'] = ''
                
                save_data(st.session_state.df, "Sheet1")
                log_transaction("반납", item_ret['이름'], item_ret['수량'], item_ret['대여자'], datetime.now().strftime("%Y-%m-%d"))
                st.success(f"'{item_ret['이름']}' 반납 완료")
                st.rerun()
        else:
            st.info("현재 대여 또는 출고 중인 장비가 없습니다.")

    # --- 탭 5: 수리/파손 ---
    with tabs[4]:
        st.subheader("🛠️ 수리 및 파손 관리")
        m_df = st.session_state.df[st.session_state.df['대여여부'].isin(['재고', '수리 중', '파손'])]
        if not m_df.empty:
            m_opts = m_df.apply(lambda x: f"[{x['대여여부']}] {x['이름']}", axis=1)
            sel_m = st.selectbox("상태를 변경할 항목 선택", m_opts.index, format_func=lambda x: m_opts[x])
            new_stat = st.selectbox("변경할 상태", ["재고", "수리 중", "파손"])
            if st.button("상태 변경 적용"):
                st.session_state.df.at[sel_m, '대여여부'] = new_stat
                save_data(st.session_state.df, "Sheet1")
                st.success("상태 변경 완료")
                st.rerun()
        else: st.info("대상 장비가 없습니다.")

    # --- 탭 6: 내역 관리 ---
    with tabs[5]:
        st.subheader("📜 활동 기록")
        st.dataframe(load_data("Logs").iloc[::-1], use_container_width=True)

    # --- 탭 7: 관리자 페이지 (강화) ---
    if is_admin:
        with tabs[6]:
            st.header("👑 관리자 페이지")
            
            # A. 장비 삭제 승인
            st.subheader("🗑️ 장비 삭제 요청 승인")
            if '삭제요청' in st.session_state.df.columns:
                del_req_df = st.session_state.df[st.session_state.df['삭제요청'] == 'Y']
                if not del_req_df.empty:
                    for idx, row in del_req_df.iterrows():
                        col_a, col_b, col_c = st.columns([3, 1, 1])
                        col_a.write(f"📂 **{row['이름']}** ({row['브랜드']}) | 수량: {row['수량']}")
                        if col_b.button("✅ 삭제 승인", key=f"d_ok_{idx}"):
                            st.session_state.df = st.session_state.df.drop(idx).reset_index(drop=True)
                            save_data(st.session_state.df, "Sheet1")
                            st.error("장비가 영구 삭제되었습니다.")
                            st.rerun()
                        if col_c.button("❌ 반려", key=f"d_no_{idx}"):
                            st.session_state.df.at[idx, '삭제요청'] = ""
                            save_data(st.session_state.df, "Sheet1")
                            st.info("삭제 요청을 반려했습니다.")
                            st.rerun()
                else: st.info("현재 대기 중인 장비 삭제 요청이 없습니다.")
            
            st.write("---")
            
            # [해결] B. 회원 가입 승인 대기 명단
            u_df = load_data("Users")
            st.subheader("👥 회원 가입 승인 대기")
            if not u_df.empty:
                # 시트의 FALSE 글자를 정확히 필터링
                pending_users = u_df[u_df['approved'].astype(str).str.upper() == 'FALSE']
                if not pending_users.empty:
                    for idx, row in pending_users.iterrows():
                        ca, cb, cc = st.columns([3, 1, 1])
                        birth_val = row.get('birth', '정보없음')
                        ca.write(f"👤 **성명: {row['username']}** | 생년월일: {birth_val}")
                        if cb.button("✅ 최종 가입 승인", key=f"u_ok_{idx}"):
                            u_df.at[idx, 'approved'] = 'TRUE'
                            save_data(u_df, "Users")
                            st.success(f"{row['username']}님 승인 완료")
                            st.rerun()
                        if cc.button("❌ 가입 거절", key=f"u_no_{idx}"):
                            u_df = u_df.drop(idx)
                            save_data(u_df, "Users")
                            st.warning("신청 정보가 삭제되었습니다.")
                            st.rerun()
                else: st.info("현재 대기 중인 가입 신청자가 없습니다.")

# 4. 로그인 및 회원가입 페이지
def login_page():
    st.title("🔒 통합 장비 관리 시스템")
    menu = st.radio("메뉴를 선택하세요", ["로그인", "회원가입"], horizontal=True)
    
    if menu == "로그인":
        with st.form("login_form"):
            u_name = st.text_input("성명 (ID)")
            u_pw = st.text_input("비밀번호 (PW)", type="password")
            if st.form_submit_button("로그인"):
                if u_name == "admin" and u_pw == "1234":
                    st.session_state.logged_in, st.session_state.username = True, u_name
                    st.rerun()
                
                users = load_data("Users")
                hashed_pw = hashlib.sha256(u_pw.encode()).hexdigest()
                if not users.empty:
                    # 필터링 시 데이터 타입을 문자열로 통일
                    user_match = users[(users['username'].astype(str) == str(u_name)) & 
                                       (users['password'].astype(str) == str(hashed_pw))]
                    if not user_match.empty:
                        if str(user_match.iloc[0]['approved']).upper() == 'TRUE':
                            st.session_state.logged_in, st.session_state.username = True, u_name
                            st.rerun()
                        else:
                            st.error("관리자의 가입 승인이 필요합니다.")
                    else:
                        st.error("성명 또는 비밀번호가 틀렸습니다.")
                else:
                    st.error("등록된 사용자가 없습니다. 먼저 회원가입을 해주세요.")
                        
    else: # 회원가입 신청
        st.subheader("📝 신규 가입 신청 양식")
        with st.form("signup_form"):
            new_name = st.text_input("성명 (실명 입력)")
            new_birth = st.date_input("생년월일", min_value=datetime(1950, 1, 1), max_value=datetime.now())
            new_pass = st.text_input("비밀번호 설정", type="password")
            st.caption("※ 신청 완료 후 관리자가 '👑 관리자 페이지'에서 승인하면 로그인이 가능합니다.")
            
            if st.form_submit_button("가입 신청 완료"):
                users_db = load_data("Users")
                if not users_db.empty and new_name in users_db['username'].values:
                    st.error("이미 등록된 성명입니다.")
                elif not new_name or not new_pass:
                    st.error("모든 항목을 입력해주세요.")
                else:
                    hashed_new_pw = hashlib.sha256(new_pass.encode()).hexdigest()
                    new_user_info = {
                        'username': new_name, 
                        'birth': str(new_birth),
                        'password': hashed_new_pw, 
                        'role': '사용자', 
                        'approved': 'FALSE', 
                        'created_at': datetime.now().strftime("%Y-%m-%d")
                    }
                    users_db = pd.concat([users_db, pd.DataFrame([new_user_info])], ignore_index=True)
                    save_data(users_db, "Users")
                    st.success("신청이 완료되었습니다! 관리자 승인을 기다려주세요.")

# 5. 앱 실행 제어부
if __name__ == '__main__':
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    if st.session_state.logged_in:
        main_app()
    else:
        login_page()
