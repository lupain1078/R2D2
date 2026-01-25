import streamlit as st
import pandas as pd
import os
from datetime import datetime

# 1. 알투디투 전용 다크 테마 및 스타일 설정
st.set_page_config(page_title="R2D2 Inventory", layout="wide", page_icon="🤖")

st.markdown("""
    <style>
    /* 메인 배경 및 텍스트 색상 */
    .stApp {
        background-color: #050505;
        color: #e0e0e0;
    }
    /* 버튼 스타일: 알투디투 블루 */
    .stButton>button {
        background-color: #0070f3;
        color: white;
        border-radius: 6px;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: bold;
        transition: 0.3s;
    }
    .stButton>button:hover {
        background-color: #0051ad;
        border: 1px solid #00d4ff;
    }
    /* 헤더 포인트 */
    h1 {
        color: #00d4ff;
        font-family: 'Courier New', Courier, monospace;
        letter-spacing: -1px;
    }
    /* 카드형 컨테이너 */
    .metric-card {
        background-color: #111111;
        border: 1px solid #222222;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

# 2. 데이터 로드 및 초기 설정
FILE_NAME = 'r2d2_data.csv'

def load_data():
    if not os.path.exists(FILE_NAME):
        df = pd.DataFrame(columns=['이름', '카테고리', '수량', '상태', '현장명', '비고'])
        df.to_csv(FILE_NAME, index=False)
        return df
    return pd.read_csv(FILE_NAME).fillna("")

def save_data(df):
    df.to_csv(FILE_NAME, index=False)
    # 데이터 유실 방지를 위한 백업 생성
    backup_file = f"backup_{datetime.now().strftime('%Y%m%d')}.csv"
    df.to_csv(backup_file, index=False)

if 'df' not in st.session_state:
    st.session_state.df = load_data()

# 3. 사이드바 및 헤더
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/3/39/R2-D2_Droid.png", width=100) # R2D2 아이콘 예시
    st.title("R2D2 컨트롤 패널")
    menu = st.radio("이동", ["📊 대시보드", "📥 장비 등록", "🚚 출고/반납"])

st.title("🤖 R2D2 PRO AUDIO & LED")
st.caption("알투디투 장비 통합 관리 시스템 v2.0")

# 4. 기능별 페이지 구현
df = st.session_state.df

if menu == "📊 대시보드":
    c1, c2, c3 = st.columns(3)
    c1.metric("총 보유 장비", len(df))
    c2.metric("현장 출고 중", len(df[df['상태'] == '현장출고']))
    c3.metric("수리 필요", len(df[df['상태'] == '수리중']))
    
    st.write("### 📋 전체 장비 현황")
    st.dataframe(df, use_container_width=True)

elif menu == "📥 장비 등록":
    st.subheader("새로운 장비 추가")
    with st.form("add_item"):
        name = st.text_input("장비 이름 (예: 3.9mm LED)")
        cat = st.selectbox("카테고리", ["LED", "프로젝터", "스위처", "케이블", "기타"])
        qty = st.number_input("수량", min_value=1, value=1)
        note = st.text_area("특이사항")
        if st.form_submit_button("알투디투 자산으로 등록"):
            new_item = {'이름': name, '카테고리': cat, '수량': qty, '상태': '재고', '현장명': '-', '비고': note}
            st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_item])], ignore_index=True)
            save_data(st.session_state.df)
            st.success(f"{name} 등록 완료!")
            st.rerun()

elif menu == "🚚 출고/반납":
    st.subheader("장비 상태 변경")
    if not df.empty:
        selected_item = st.selectbox("장비 선택", df['이름'].tolist())
        col1, col2 = st.columns(2)
        new_status = col1.selectbox("상태 변경", ["재고", "현장출고", "수리중", "파손"])
        target_site = col2.text_input("현장/업체명", value="-")
        
        if st.button("상태 업데이트"):
            idx = df[df['이름'] == selected_item].index[0]
            st.session_state.df.at[idx, '상태'] = new_status
            st.session_state.df.at[idx, '현장명'] = target_site
            save_data(st.session_state.df)
            st.success(f"{selected_item} 상태가 {new_status}로 변경되었습니다.")
            st.rerun()
