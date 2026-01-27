import streamlit as st
import pandas as pd
import os
import uuid
import hashlib
from datetime import datetime
from io import BytesIO
from streamlit_gsheets import GSheetsConnection

# 1. 설정 및 구글 시트 연결
st.set_page_config(page_title="통합 장비 관리 시스템", layout="wide", page_icon="🛠️")
conn = st.connection("gsheets", type=GSheetsConnection)

# 필드 정의
FIELD_NAMES = ['ID', '타입', '이름', '수량', '브랜드', '특이사항', '대여업체', '대여여부', '대여자', '대여일', '반납예정일', '출고비고', '사진', '삭제요청']

# 2. 데이터 처리 함수 (공백 제거 및 타입 변환 강화)
def load_data(sheet_name="Sheet1"):
    try:
        df = conn.read(worksheet=sheet_name, ttl=0)
        df = df.fillna("")
        
        # [공통] 모든 문자열 데이터의 앞뒤 공백 제거
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        
        if sheet_name == "Sheet1":
            if not df.empty:
                if '삭제요청' not in df.columns: df['삭제요청'] = ""
                # 수량 정수화 (.0 제거)
                df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0).astype(int)
            else:
                df = pd.DataFrame(columns=FIELD_NAMES)
        
        return df
    except:
        return pd.DataFrame()

def save_data(df, sheet_name="Sheet1"):
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

# 3. 메인 앱 UI
def main_app():
    if 'df' not in st.session_state:
        st.session_state.df = load_data("Sheet1")
    
    df = st.session_state.df
    is_admin = (st.session_state.username == "admin")

    with st.sidebar:
        st.header(f"👤 {st.session_state.username}님")
        with st.expander("📂 데이터 관리", expanded=False):
            if st.button("📊 백업 파일 생성", use_container_width=True):
                with st.spinner("파일 생성 중..."):
                    logs_df = load_data("Logs")
                    excel_data = to_excel([st.session_state.df, logs_df], ["장비재고", "활동로그"])
                    st.download_button(label="📥 엑셀 다운로드", data=excel_data, 
                                       file_name=f"백업_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       use_container_width=True)
        st.write("---")
        if st.button("🚪 로그아웃", use_container_width=True):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    st.title("🛠️ 통합 장비 관리 시스템")

    # 상단 요약 지표
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 대여 중", int(df[df['대여여부'] == '대여 중']['수량'].sum()) if not df.empty else 0)
    c2.metric("🎬 현장 출고", int(df[df['대여여부'] == '현장 출고']['수량'].sum()) if not df.empty else 0)
    c3.metric("🛠️ 수리 중", int(df[df['대여여부'] == '수리 중']['수량'].sum()) if not df.empty else 0)
    c4.metric("💔 파손", int(df[df['대여여부'] == '파손']['수량'].sum()) if not df.empty else 0)

    tab_list = ["📋 재고 관리", "📤 외부 대여", "🎬 현장 출고", "📥 반납", "🛠️ 수리/파손", "📜 내역 관리"]
    if is_admin: tab_list.append("👑 관리자 페이지")
    tabs = st.tabs(tab_list)

    # --- 1. 재고 관리 ---
    with tabs[0]:
        with st.expander("➕ 새 장비 등록"):
            with st.form("add_form", clear_on_submit=True):
                col1, col2, col3 = st.columns([1,2,1])
                t, n, q = col1.text_input("타입"), col2.text_input("장비명"), col3.number_input("수량", 1, step=1)
                b = st.text_input("브랜드")
                if st.form_submit_button("등록"):
                    new_item = {'ID': str(uuid.uuid4()), '타입': t, '이름': n, '수량': int(q), '브랜드': b, '대여여부': '재고', '삭제요청': ''}
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_item])], ignore_index=True)
                    save_data(st.session_state.df, "Sheet1"); st.rerun()
        
        edit_m = st.toggle("🔓 수정 및 삭제 요청 모드")
        edited = st.data_editor(st.session_state.df, disabled=(not edit_m), hide_index=True, use_container_width=True, column_config={"ID": None})
        if edit_m and st.button("💾 모든 변경사항 저장"):
            save_data(edited, "Sheet1"); st.session_state.df = edited; st.success("저장 완료"); st.rerun()

    # (외부대여, 현장출고 원본 유지)
    with tabs[1]: st.subheader("📤 외부 업체 대여")
    with tabs[2]: st.subheader("🎬 현장 출고")

    # --- 🟢 4. 반납 처리 (공백 해결 버전) ---
    with tabs[3]:
        st.subheader("📥 장비 반납 처리")
        # [해결] 앞뒤 공백 제거된 상태에서 필터링
        rented = st.session_state.df[st.session_state.df['대여여부'].isin(['대여 중', '현장 출고'])]
        if not rented.empty:
            r_opts = rented.apply(lambda x: f"[{x['대여여부']}] {x['이름']} - {x['대여자']} ({int(x['수량'])}개)", axis=1)
            sel_ret = st.selectbox("반납 대상 선택", r_opts.index, format_func=lambda x: r_opts[x])
            if st.button("반납 확정"):
                item = rented.loc[sel_ret]
                mask = (st.session_state.df['이름'] == item['이름']) & (st.session_state.df['대여여부'] == '재고')
                if any(mask):
                    idx = st.session_state.df[mask].index[0]
                    st.session_state.df.at[idx, '수량'] += int(item['수량'])
                    st.session_state.df = st.session_state.df.drop(sel_ret).reset_index(drop=True)
                else:
                    st.session_state.df.at[sel_ret, '대여여부'] = '재고'; st.session_state.df.at[sel_ret, '대여자'] = ''
                save_data(st.session_state.df, "Sheet1"); log_transaction("반납", item['이름'], item['수량'], item['대여자'], datetime.now().strftime("%Y-%m-%d")); st.rerun()
        else: st.info("반납할 장비가 없습니다.")

    # (수리, 내역 원본 유지)
    with tabs[4]: st.subheader("🛠️ 수리 및 파손")
    with tabs[5]: st.subheader("📜 활동 기록"); st.dataframe(load_data("Logs").iloc[::-1], use_container_width=True)

    # --- 👑 7. 관리자 페이지 (회원 승인 해결 버전) ---
    if is_admin:
        with tabs[6]:
            st.header("👑 관리자 페이지")
            # 장비 삭제 승인
            st.subheader("🗑️ 장비 삭제 요청 승인")
            del_req = st.session_state.df[st.session_state.df['삭제요청'] == 'Y']
            if not del_req.empty:
                for idx, row in del_req.iterrows():
                    ca, cb, cc = st.columns([3, 1, 1])
                    ca.write(f"📂 **{row['이름']}** | 수량: {row['수량']}")
                    if cb.button("✅ 승인", key=f"d_ok_{idx}"):
                        st.session_state.df = st.session_state.df.drop(idx).reset_index(drop=True)
                        save_data(st.session_state.df, "Sheet1"); st.rerun()
                    if cc.button("❌ 반려", key=f"d_no_{idx}"):
                        st.session_state.df.at[idx, '삭제요청'] = ""; save_data(st.session_state.df, "Sheet1"); st.rerun()
            
            st.write("---")
            # [해결] 회원 가입 승인 대기 명단 추출
            u_df = load_data("Users")
            st.subheader("👥 회원 가입 승인 대기")
            if not u_df.empty:
                # approved 컬럼의 값을 대문자 문자열로 변환하여 'FALSE'인 것만 추출
                pending = u_df[u_df['approved'].astype(str).str.upper() == 'FALSE']
                if not pending.empty:
                    for idx, row in pending.iterrows():
                        c1, c2, c3 = st.columns([3, 1, 1])
                        birth = row.get('birth', '정보없음')
                        c1.write(f"👤 **{row['username']}** | 생년월일: {birth}")
                        if c2.button("✅ 가입 승인", key=f"u_ok_{idx}"):
                            u_df.at[idx, 'approved'] = 'TRUE'
                            save_data(u_df, "Users")
                            st.success(f"{row['username']}님 승인 완료")
                            st.rerun()
                        if c3.button("❌ 거절/삭제", key=f"u_no_{idx}"):
                            u_df = u_df.drop(idx)
                            save_data(u_df, "Users")
                            st.rerun()
                else: st.info("현재 대기 중인 회원이 없습니다.")

# 4. 로그인 및 회원가입 페이지
def login_page():
    st.title("🔒 통합 장비 관리 시스템")
    choice = st.radio("서비스를 선택하세요", ["로그인", "회원가입"], horizontal=True)
    
    if choice == "로그인":
        with st.form("login_form"):
            u, p = st.text_input("성명 (ID)"), st.text_input("비밀번호 (PW)", type="password")
            if st.form_submit_button("로그인"):
                if u == "admin" and p == "1234":
                    st.session_state.logged_in, st.session_state.username = True, u; st.rerun()
                
                u_df = load_data("Users")
                hp = hashlib.sha256(p.encode()).hexdigest()
                if not u_df.empty:
                    # 필터링 시 공백 제거 및 문자열 일치 확인
                    user = u_df[(u_df['username'].astype(str) == str(u)) & (u_df['password'].astype(str) == str(hp))]
                    if not user.empty:
                        if str(user.iloc[0]['approved']).upper() == 'TRUE':
                            st.session_state.logged_in, st.session_state.username = True, u; st.rerun()
                        else: st.error("관리자의 가입 승인이 완료되지 않았습니다.")
                    else: st.error("정보 불일치")
                        
    else: # 회원가입
        st.subheader("📝 신규 회원가입 신청")
        with st.form("signup_form"):
            new_u = st.text_input("성명 (한글/실명)")
            new_birth = st.date_input("생년월일", min_value=datetime(1950, 1, 1))
            new_p = st.text_input("비밀번호 (PW)", type="password")
            if st.form_submit_button("가입 신청하기"):
                u_df = load_data("Users")
                hp = hashlib.sha256(new_p.encode()).hexdigest()
                new_user = {'username': new_u, 'birth': str(new_birth), 'password': hp, 'role': '사용자', 'approved': 'FALSE', 'created_at': datetime.now().strftime("%Y-%m-%d")}
                u_df = pd.concat([u_df, pd.DataFrame([new_user])], ignore_index=True)
                save_data(u_df, "Users")
                st.success("신청 완료! 관리자 승인 후 이용 가능합니다.")

if __name__ == '__main__':
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: main_app()
    else: login_page()
