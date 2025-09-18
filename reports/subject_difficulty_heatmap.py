import streamlit as st
import pandas as pd
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from helpers.utils import generate_excel
from helpers.data_helper import get_programs

# ----------------- LOAD ENV -----------------
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

# ----------------- CONSTANTS -----------------
HIGH_DIFFICULTY_THRESHOLD = 20
MEDIUM_DIFFICULTY_THRESHOLD = 10

# ----------------- CONNECT TO MONGODB -----------------
@st.cache_resource
def get_client():
    return MongoClient(MONGO_URI)

def get_difficulty_level(fail_rate, dropout_rate):
    """Determines the difficulty level based on fail and dropout rates."""
    total_rate = fail_rate + dropout_rate
    if total_rate > HIGH_DIFFICULTY_THRESHOLD:
        return "High"
    elif total_rate > MEDIUM_DIFFICULTY_THRESHOLD:
        return "Medium"
    else:
        return "Low"

def get_subject_difficulty_data(db, teacher_name=None, program_code=None, program_name=None):
    """Fetches and processes subject difficulty data using an aggregation pipeline."""
    pipeline = []
    if teacher_name:
        pipeline.append({"$match": {"Teachers": teacher_name}})

    pipeline.extend([
        {"$lookup": {
            "from": "students",
            "localField": "StudentID",
            "foreignField": "_id",
            "as": "student_info"
        }},
        {"$unwind": "$student_info"},
    ])

    if program_code:
        programs_df = get_programs(db)
        p_name = programs_df[programs_df['programCode'] == program_code]['programName'].iloc[0]
        pipeline.append({"$match": {"$or": [
            {"student_info.Course": program_code},
            {"student_info.Course": p_name}
        ]}})
    elif program_name:
        pipeline.append({"$match": {"student_info.Course": program_name}})

    pipeline.extend([
        {"$unwind": "$SubjectCodes"},
        {"$unwind": "$Grades"},
        {"$group": {
            "_id": "$SubjectCodes",
            "enrolled": {"$sum": 1},
            "failed": {"$sum": {"$cond": [{"$lt": ["$Grades", 75]}, 1, 0]}},
            "dropped": {"$sum": {"$cond": [{"$in": ["$Grades", ["DRP", "W"]]}, 1, 0]}}
        }},
        {"$lookup": {
            "from": "subjects",
            "localField": "_id",
            "foreignField": "_id",
            "as": "subject_info"
        }},
        {"$unwind": "$subject_info"},
        {"$project": {
            "Subject Code": "$_id",
            "Subject Name": "$subject_info.Description",
            "enrolled": "$enrolled",
            "failed": "$failed",
            "dropped": "$dropped"
        }}
    ])

    data = list(db.grades.aggregate(pipeline))
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df["Fail Rate(%)"] = (df["failed"] / df["enrolled"]) * 100
    df["Dropout Rate(%)"] = (df["dropped"] / df["enrolled"]) * 100
    df["Difficulty Level"] = df.apply(lambda row: get_difficulty_level(row["Fail Rate(%)"], row["Dropout Rate(%)"]), axis=1)

    return df

def style_heatmap(df):
    """Applies styling to the DataFrame for a heatmap effect."""
    def style_rates(val):
        color = 'rgba(255, 0, 0, {})'.format(val / 100.0)
        return f'background-color: {color}'

    def color_difficulty(val):
        color_map = {'High': 'salmon', 'Medium': 'khaki', 'Low': 'lightgreen'}
        return f'background-color: {color_map.get(val, "white")}'

    return df.style \
        .applymap(style_rates, subset=['Fail Rate(%)', 'Dropout Rate(%)']) \
        .applymap(color_difficulty, subset=['Difficulty Level']) \
        .format({'Fail Rate(%)': '{:.2f}%', 'Dropout Rate(%)': '{:.2f}%'})

def subject_difficulty_heatmap_panel(db, teacher_name=None):
    """Main function to display the subject difficulty heatmap."""
    if teacher_name is None:
        st.header("Subject Difficulty Heatmap")

    programs_df = get_programs(db)
    program_codes = [""] + sorted(programs_df["programCode"].unique())
    program_names = [""] + sorted(programs_df["programName"].unique())

    col1, col2 = st.columns(2)
    with col1:
        selected_program_code = st.selectbox("Filter by Program Code", program_codes, key="sdh_program_code")
    with col2:
        if selected_program_code:
            program_name_options = [""] + sorted(programs_df[programs_df["programCode"] == selected_program_code]["programName"].unique())
        else:
            program_name_options = program_names
        selected_program_name = st.selectbox("Filter by Program Name", program_name_options, key="sdh_program_name")

    df = get_subject_difficulty_data(db, teacher_name, selected_program_code, selected_program_name)

    if df.empty:
        st.warning("No data found to generate the heatmap.")
        return

    styled_df = style_heatmap(df)

    if teacher_name is None:
        st.subheader("Subjects Analysis")
    st.dataframe(styled_df)

    st.markdown("### 💾 Download Report")
    excel_bytes = generate_excel(df, "subject_difficulty_report.xlsx")
    st.download_button(
        label="⬇️ Download as Excel",
        data=excel_bytes,
        file_name="subject_difficulty_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
