import streamlit as st
import pandas as pd
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# ----------------- LOAD ENV -----------------
load_dotenv()
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASS = os.getenv("MONGO_PASS")

# ----------------- CONNECT TO MONGODB -----------------
@st.cache_resource
def get_client():
    uri = f"mongodb+srv://{MONGO_USER}:{MONGO_PASS}@cluster0.l7fdbmf.mongodb.net"
    return MongoClient(uri)

def get_difficulty_level(fail_rate, dropout_rate):
    """Determines the difficulty level based on fail and dropout rates."""
    total_rate = fail_rate + dropout_rate
    if total_rate > 20:
        return "High"
    elif total_rate > 10:
        return "Medium"
    else:
        return "Low"

def subject_difficulty_heatmap_panel(db, teacher_name=None):
    if teacher_name is None:
        st.header("Subject Difficulty Heatmap")

    # Fetch data
    grades_col = db["grades"]
    subjects_col = db["subjects"]

    query = {}
    if teacher_name:
        query = {"Teachers": teacher_name}

    all_grades = list(grades_col.find(query))
    all_subjects = list(subjects_col.find({}))

    if not all_grades or not all_subjects:
        st.warning("No grades or subjects data found.")
        return

    df_grades = pd.DataFrame(all_grades)
    df_subjects = pd.DataFrame(all_subjects).rename(columns={'_id': 'SubjectCode', 'Description': 'programName'})

    # Process data
    subject_data = {}
    for _, row in df_grades.iterrows():
        subjects = row.get('SubjectCodes', [])
        grades = row.get('Grades', [])
        teachers = row.get('Teachers', [])

        for i, subject_code in enumerate(subjects):
            # If in teacher view, only process subjects for that teacher
            if teacher_name and (i >= len(teachers) or teachers[i] != teacher_name):
                continue

            if subject_code not in subject_data:
                subject_data[subject_code] = {'enrolled': 0, 'failed': 0, 'dropped': 0}

            subject_data[subject_code]['enrolled'] += 1
            grade = grades[i] if i < len(grades) else None

            if isinstance(grade, (int, float)) and grade < 75:
                subject_data[subject_code]['failed'] += 1
            elif str(grade).upper() in ['DRP', 'W']:
                subject_data[subject_code]['dropped'] += 1

    # Calculate rates and difficulty
    subject_stats = []
    for code, data in subject_data.items():
        enrolled = data['enrolled']
        fail_rate = (data['failed'] / enrolled) * 100 if enrolled > 0 else 0
        dropout_rate = (data['dropped'] / enrolled) * 100 if enrolled > 0 else 0

        subject_info = df_subjects[df_subjects['SubjectCode'] == code]
        program_name = subject_info['programName'].iloc[0] if not subject_info.empty else "N/A"

        subject_stats.append({
            'programCode': code,
            'programName': program_name,
            'Fail Rate(%)': fail_rate,
            'Dropout Rate(%)': dropout_rate,
            'Difficulty Level': get_difficulty_level(fail_rate, dropout_rate)
        })

    if not subject_stats:
        st.warning("Could not compute subject statistics for the selected teacher.")
        return

    display_df = pd.DataFrame(subject_stats)

    # Styling for heatmap effect
    def style_rates(val):
        color = 'rgba(255, 0, 0, {})'.format(val / 100.0) # Red scale based on percentage
        return f'background-color: {color}'

    def color_difficulty(val):
        color = 'lightgreen'
        if val == 'High':
            color = 'salmon'
        elif val == 'Medium':
            color = 'khaki'
        return f'background-color: {color}'

    styled_df = display_df.style \
        .applymap(style_rates, subset=['Fail Rate(%)', 'Dropout Rate(%)']) \
        .applymap(color_difficulty, subset=['Difficulty Level']) \
        .format({'Fail Rate(%)': '{:.2f}%', 'Dropout Rate(%)': '{:.2f}%'})

    if teacher_name is None:
        st.subheader("Subjects Analysis")
    st.dataframe(styled_df)
