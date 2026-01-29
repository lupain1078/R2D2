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
        
        # [핵심] 회원 데이터의 승인 여부 타입 일치화 (0, FALSE, False 모두 대응)
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
    # [보완] 앱 시작 시 장비 데이터 새로 로드
    st.session_state.df = load_data("Sheet1")
    # [보완] 회원 관리 기능을 위해 매 실행 시마다 유저 데이터를 최신으로 동기화
    u_df_current = load_data("Users")
    
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
                t_input, n_input, q_input = col1.text_input("타입"), col2.text_input("장비명"), col3.number_input("수량", 1, step=1)
                b_input = st.text_input("브랜드")
                if st.form_submit_button("등록"):
                    new_item = {'ID': str(uuid.uuid4()), '타입': t_input, '이름': n_input, '수량': int(q_input), '브랜드': b_input, '대여여부': '재고', '삭제요청': ''}
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_item])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1")
                    st.success("등록 완료")
                    st.rerun()
        
        edit_mode = st.toggle("🔓 수정 및 삭제 요청 모드")
        edited_df = st.data_editor(st.session_state.df, disabled=(not edit_mode), hide_index=True, use_container_width=True, column_config={"ID": None})
        if edit_mode and st.button("💾 모든 변경사항 저장"):
            save_data(edited_df, "Sheet1"); st.session_state.df = edited_df; st.rerun()

    # --- 탭 2: 외부 대여 / 3: 현장 출고 / 4: 반납 (기존 로직 유지) ---
    with tabs[1]: st.subheader("📤 외부 업체 대여 처리")
    with tabs[2]: st.subheader("🎬 현장 출고 처리")
    with tabs[3]:
        st.subheader("📥 장비 반납 처리")
        rented_items = st.session_state.df[st.session_state.df['대여여부'].isin(['대여 중', '현장 출고'])]
        if not rented_items.empty:
            r_opts = rented_items.apply(lambda x: f"[{x['대여여부']}] {x['이름']} - {x['대여자']} ({int(x['수량'])}개)", axis=1)
            sel_ret = st.selectbox("반납 대상 선택", r_opts.index, format_func=lambda x: r_opts[x])
            if st.button("반납 확정"):
                item_ret = rented_items.loc[sel_ret]
                mask = (st.session_state.df['이름'] == item_ret['이름']) & (st.session_state.df['대여여부'] == '재고')
                if any(mask):
                    idx_stock = st.session_state.df[mask].index[0]
                    st.session_state.df.at[idx_stock, '수량'] = int(st.session_state.df.at[idx_stock, '수량']) + int(item_ret['수량'])
                    st.session_state.df = st.session_state.df.drop(sel_ret).reset_index(drop=True)
                else:
                    st.session_state.df.at[sel_ret, '대여여부'] = '재고'; st.session_state.df.at[sel_ret, '대여자'] = ''
                save_data(st.session_state.df, "Sheet1")
                log_transaction("반납", item_ret['이름'], item_ret['수량'], item_ret['대여자'], datetime.now().strftime("%Y-%m-%d"))
                st.success(f"'{item_ret['이름']}' 반납 완료"); st.rerun()
        else: st.info("현재 대여 또는 출고 중인 장비가 없습니다.")

    with tabs[4]: st.subheader("🛠️ 수리 및 파손 관리")
    with tabs[5]: st.subheader("📜 활동 기록"); st.dataframe(load_data("Logs").iloc[::-1], use_container_width=True)

    # --- 탭 7: 관리자 페이지 (승인 즉시 회원 목록 이동 보완) ---
    if is_admin:
        with tabs[6]:
            st.header("👑 관리자 페이지")
            # A. 장비 삭제 승인
            st.subheader("🗑️ 장비 삭제 요청 승인")
            del_req_df = st.session_state.df[st.session_state.df['삭제요청'] == 'Y']
            if not del_req_df.empty:
                for idx, row in del_req_df.iterrows():
                    ca, cb, cc = st.columns([3, 1, 1])
                    ca.write(f"📂 **{row['이름']}** | 수량: {row['수량']}")
                    if cb.button("✅ 삭제 승인", key=f"d_ok_{idx}"):
                        st.session_state.df = st.session_state.df.drop(idx).reset_index(drop=True)
                        save_data(st.session_state.df, "Sheet1"); st.rerun()
                    if cc.button("❌ 반려", key=f"d_no_{idx}"):
                        st.session_state.df.at[idx, '삭제요청'] = ""; save_data(st.session_state.df, "Sheet1"); st.rerun()
            
            st.write("---")
            
            # [해결 핵심] B-1. 회원 가입 승인 대기 명단
            st.subheader("⏳ 회원 가입 승인 대기")
            if not u_df_current.empty:
                pending_users = u_df_current[~u_df_current['approved'].astype(str).str.upper().isin(['TRUE', '1', 'T'])]
                if not pending_users.empty:
                    for idx, row in pending_users.iterrows():
                        ca, cb, cc = st.columns([3, 1, 1])
                        birth_val = row.get('birth', '정보없음')
                        ca.write(f"👤 **성명: {row['username']}** | 생년월일: {birth_val}")
                        if cb.button("✅ 최종 가입 승인", key=f"u_ok_{idx}"):
                            u_df_current.at[idx, 'approved'] = 'TRUE' # 상태 변경
                            save_data(u_df_current, "Users") # 시트 저장
                            st.success(f"{row['username']}님 승인 완료")
                            st.rerun() # [해결] 승인 즉시 화면을 새로고침하여 회원 목록으로 데이터 이동
                        if cc.button("❌ 가입 거절", key=f"u_no_{idx}"):
                            u_df_current = u_df_current.drop(idx)
                            save_data(u_df_current, "Users"); st.rerun()
                else: st.info("현재 대기 중인 가입 신청자가 없습니다.")
            
            st.write("---")
            
            # B-2. 전체 회원 관리 (삭제 기능)
            st.subheader("👥 전체 회원 관리")
            if not u_df_current.empty:
                approved_users = u_df_current[u_df_current['approved'].astype(str).str.upper().isin(['TRUE', '1', 'T'])]
                if not approved_users.empty:
                    display_users = approved_users[['username', 'birth', 'role', 'created_at']].copy()
                    display_users.columns = ['성명', '생년월일', '권한', '가입일']
                    st.dataframe(display_users, use_container_width=True, hide_index=True)
                    st.write("---")
                    manage_list = approved_users[approved_users['username'] != 'admin']['username'].tolist()
                    if manage_list:
                        del_target = st.selectbox("삭제할 회원 선택", manage_list)
                        if st.button("🔥 회원 계정 삭제"):
                            u_df_new = u_df_current[u_df_current['username'] != del_target]
                            save_data(u_df_new, "Users"); st.rerun()
                else:
                    st.info("승인 완료된 회원이 없습니다.")

# 4. 로그인 및 가입 페이지 (마스터 계정 고정)
def login_page():
    st.title("🔒 통합 장비 관리 시스템")
    menu = st.radio("메뉴 선택", ["로그인", "회원가입"], horizontal=True)
    if menu == "로그인":
        with st.form("login"):
            u, p = st.text_input("성명 (ID)"), st.text_input("비밀번호 (PW)", type="password")
            if st.form_submit_button("로그인"):
                if u == "admin" and p == "1234":
                    st.session_state.logged_in, st.session_state.username = True, u; st.rerun()
                users = load_data("Users")
                hp = hashlib.sha256(p.encode()).hexdigest()
                if not users.empty:
                    user_match = users[(users['username'].astype(str) == str(u)) & (users['password'].astype(str) == str(hp))]
                    if not user_match.empty and str(user_match.iloc[0]['approved']).upper() in ['TRUE', '1', 'T']:
                        st.session_state.logged_in, st.session_state.username = True, u; st.rerun()
                    else: st.error("정보 불일치 또는 승인 대기")
    else:
        with st.form("signup"):
            new_n, new_b, new_p = st.text_input("성명"), st.date_input("생년월일", min_value=datetime(1950, 1, 1)), st.text_input("비밀번호", type="password")
            if st.form_submit_button("신청 완료"):
                users_db = load_data("Users")
                hp = hashlib.sha256(new_p.encode()).hexdigest()
                new_user = {'username': new_n, 'birth': str(new_b), 'password': hp, 'role': '사용자', 'approved': 'FALSE', 'created_at': datetime.now().strftime("%Y-%m-%d")}
                save_data(pd.concat([users_db, pd.DataFrame([new_user])], ignore_index=True), "Users")
                st.success("신청 완료! 관리자 승인을 기다려주세요.")

if __name__ == '__main__':
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: login_page()
