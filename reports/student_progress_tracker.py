import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from helpers.utils import generate_excel

# ----------------- LOAD ENV -----------------
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

# ----------------- CONNECT TO MONGODB -----------------
@st.cache_resource
def get_client():
    return MongoClient(MONGO_URI)

def get_trend(grades, high_performance_threshold=90, trend_threshold=5):
    """Calculates the trend based on a list of grades."""
    if not grades or len(grades) < 2:
        return "N/A"

    if all(g >= high_performance_threshold for g in grades if pd.notna(g)):
        return "Stable High"

    if (grades[-1] - grades[0]) > trend_threshold:
        return "Improving"

    if (grades[0] - grades[-1]) > trend_threshold:
        return "Needs Attention"

    return "Stable"

def get_student_progress_data(db, teacher_name=None, subject=None, course=None, year_level=None):
    """Fetches and processes student progress data."""
    pipeline = []
    match_filter = {}

    if teacher_name:
        match_filter["Teachers"] = teacher_name
    if subject:
        match_filter["SubjectCodes"] = subject

    if match_filter:
        pipeline.append({"$match": match_filter})

    pipeline.extend([
        {"$lookup": {"from": "students", "localField": "StudentID", "foreignField": "_id", "as": "student_info"}},
        {"$unwind": "$student_info"},
        {"$lookup": {"from": "semesters", "localField": "SemesterID", "foreignField": "_id", "as": "semester_info"}},
        {"$unwind": "$semester_info"},
    ])

    student_match = {}
    if course:
        student_match["student_info.Course"] = course
    if year_level:
        student_match["student_info.YearLevel"] = year_level

    if student_match:
        pipeline.append({"$match": student_match})

    pipeline.append({"$project": {
        "StudentID": 1,
        "Name": "$student_info.Name",
        "Semester": "$semester_info.Semester",
        "AvgGrade": {"$avg": "$Grades"}
    }})

    df = pd.DataFrame(list(db.grades.aggregate(pipeline)))
    if df.empty:
        return pd.DataFrame()

    pivot_df = df.pivot_table(index=['StudentID', 'Name'], columns='Semester', values='AvgGrade').reset_index()
    rename_map = {'1st Sem': 'FirstSem', 'First': 'FirstSem', '2nd Sem': 'SecondSem', 'Second': 'SecondSem'}
    pivot_df.rename(columns={k: v for k, v in rename_map.items() if k in pivot_df.columns}, inplace=True)

    sem_cols = ['FirstSem', 'SecondSem', 'Summer']
    for col in sem_cols:
        if col not in pivot_df.columns:
            pivot_df[col] = None

    trends = [get_trend([row[col] for col in sem_cols if pd.notna(row[col])]) for _, row in pivot_df.iterrows()]
    pivot_df['Overall Trend'] = trends

    return pivot_df.rename(columns={'StudentID': 'Student ID'})

def display_filters(db):
    """Displays filters for the registrar view."""
    st.header("Student Progress Tracker")
    col1, col2, col3 = st.columns(3)
    with col1:
        subject_list = [""] + sorted(db["subjects"].distinct("_id"))
        selected_subject = st.selectbox("Filter by Subject", subject_list, key="spt_subject")
    with col2:
        course_list = [""] + sorted(db["students"].distinct("Course"))
        selected_course = st.selectbox("Filter by Course", course_list, key="spt_course")
    with col3:
        year_level_list = [""] + sorted(db["students"].distinct("YearLevel"))
        selected_year_level = st.selectbox("Filter by Year Level", year_level_list, key="spt_year")
    return selected_subject, selected_course, selected_year_level

def display_progress_chart(df):
    """Displays the performance chart for a selected student."""
    st.subheader("Performance Chart")
    if not df.empty:
        student_options = df['Name'].tolist()
        selected_student_name = st.selectbox("Select Student to Visualize", options=student_options, key="spt_student_viz")

        if selected_student_name:
            student_data = df[df['Name'] == selected_student_name].iloc[0]
            chart_data = {
                'Semester': ['FirstSem', 'SecondSem', 'Summer'],
                'Grade': [student_data.get('FirstSem'), student_data.get('SecondSem'), student_data.get('Summer')]
            }
            chart_df = pd.DataFrame(chart_data).dropna()

            if not chart_df.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=chart_df['Semester'], y=chart_df['Grade'], mode='lines+markers', name=selected_student_name))
                fig.update_layout(title=f"Performance for {selected_student_name}", xaxis_title="Semester", yaxis_title="Average Grade")
                st.plotly_chart(fig)
            else:
                st.warning(f"No grade data available for {selected_student_name} to plot.")
    else:
        st.warning("No data available to display chart.")

def student_progress_tracker_panel(db, teacher_name=None):
    """Main function to display the student progress tracker."""
    selected_subject, selected_course, selected_year_level = (None, None, None)
    if teacher_name is None:
        selected_subject, selected_course, selected_year_level = display_filters(db)

    df = get_student_progress_data(db, teacher_name, selected_subject, selected_course, selected_year_level)

    if df.empty:
        st.warning("No data found for the selected filters.")
        return

    st.dataframe(df[['Student ID', 'Name', 'FirstSem', 'SecondSem', 'Summer', 'Overall Trend']].fillna('N/A'))

    st.markdown("### 💾 Download Report")
    excel_bytes = generate_excel(df, "student_progress_report.xlsx")
    st.download_button(
        label="⬇️ Download as Excel",
        data=excel_bytes,
        file_name="student_progress_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    display_progress_chart(df)
