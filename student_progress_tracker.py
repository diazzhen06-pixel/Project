import streamlit as st
import pandas as pd
import plotly.graph_objects as go
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

def get_trend(grades):
    """Calculates the trend based on a list of grades."""
    if not grades or len(grades) < 2:
        return "N/A"

    # Check for high stable performance
    if all(g >= 3.5 for g in grades if pd.notna(g)):
        return "Stable High"

    # Check for improvement
    if grades[-1] > grades[0]:
        return "Improving"

    # Check for decline
    if grades[-1] < grades[0]:
        return "Needs Attention"

    return "Stable"

def student_progress_tracker_panel(db, teacher_name=None):
    if teacher_name is None:
        st.header("Student Progress Tracker")
        # Filters for registrar view
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
    else:
        selected_subject = None
        selected_course = None
        selected_year_level = None


    # Data loading
    grades_col = db["grades"]
    pipeline = [
        {"$lookup": {"from": "students", "localField": "StudentID", "foreignField": "_id", "as": "student_info"}},
        {"$unwind": "$student_info"},
        {"$lookup": {"from": "semesters", "localField": "SemesterID", "foreignField": "_id", "as": "semester_info"}},
        {"$unwind": "$semester_info"},
        {"$project": {
            "StudentID": 1,
            "Name": "$student_info.Name",
            "Course": "$student_info.Course",
            "YearLevel": "$student_info.YearLevel",
            "Semester": "$semester_info.Semester",
            "SchoolYear": "$semester_info.SchoolYear",
            "Grades": 1,
            "SubjectCodes": 1,
            "Teachers": 1,
        }}
    ]

    if teacher_name:
        pipeline.insert(0, {"$match": {"Teachers": teacher_name}})

    df = pd.DataFrame(list(grades_col.aggregate(pipeline)))

    if df.empty:
        st.warning("No data found.")
        return

    # Apply filters if not in teacher view
    if teacher_name is None:
        if selected_subject:
            df = df[df['SubjectCodes'].apply(lambda x: selected_subject in x if isinstance(x, list) else False)]
        if selected_course:
            df = df[df['Course'] == selected_course]
        if selected_year_level:
            df = df[df['YearLevel'] == selected_year_level]

    if df.empty:
        st.warning("No students found for the selected filters.")
        return

    # Calculate average grade per student per semester
    df['AvgGrade'] = df['Grades'].apply(lambda x: pd.to_numeric(x, errors='coerce').mean())

    # Pivot table to get semesters as columns
    pivot_df = df.pivot_table(index=['StudentID', 'Name'], columns='Semester', values='AvgGrade').reset_index()

    # Define semester columns
    sem_cols = ['1st Sem', '2nd Sem', 'Summer']
    for col in sem_cols:
        if col not in pivot_df.columns:
            pivot_df[col] = None

    # Calculate Overall Trend
    trends = []
    for _, row in pivot_df.iterrows():
        grades = [row[col] for col in sem_cols if pd.notna(row[col])]
        trends.append(get_trend(grades))
    pivot_df['Overall Trend'] = trends

    # Rename columns for display
    pivot_df.rename(columns={'1st Sem': 'FirstSem', '2nd Sem': 'SecondSem', 'StudentID': 'Student ID'}, inplace=True)

    # Display table
    st.dataframe(pivot_df[['Student ID', 'Name', 'FirstSem', 'SecondSem', 'Summer', 'Overall Trend']].fillna('N/A'))

    # Chart
    st.subheader("Performance Chart")

    if not pivot_df.empty:
        # Let user select a student from the filtered list
        student_options = pivot_df['Name'].tolist()
        selected_student_name = st.selectbox("Select Student to Visualize", options=student_options, key="spt_student_viz")

        if selected_student_name:
            student_data = pivot_df[pivot_df['Name'] == selected_student_name].iloc[0]

            # Prepare data for chart
            chart_data = {
                'Semester': ['FirstSem', 'SecondSem', 'Summer'],
                'Grade': [student_data['FirstSem'], student_data['SecondSem'], student_data['Summer']]
            }
            chart_df = pd.DataFrame(chart_data).dropna()

            if not chart_df.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=chart_df['Semester'],
                    y=chart_df['Grade'],
                    mode='lines+markers',
                    name=selected_student_name
                ))
                fig.update_layout(
                    title=f"Performance for {selected_student_name}",
                    xaxis_title="Semester",
                    yaxis_title="Average Grade"
                )
                st.plotly_chart(fig)
            else:
                st.warning(f"No grade data available for {selected_student_name} to plot.")
    else:
        st.warning("No data available to display chart.")
