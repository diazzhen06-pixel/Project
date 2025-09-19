import os
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
import streamlit as st
import plotly.graph_objects as go
from student import student_panel
from faculty import faculty
from newfaculty import new_faculty_panel
from login import login

# ----------------- LOAD ENV -----------------
load_dotenv()
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASS = os.getenv("MONGO_PASS")

if not MONGO_USER or not MONGO_PASS:
    st.error("❌ Missing MongoDB credentials in .env file")
    st.stop()

# ----------------- CONNECT TO MONGODB -----------------
@st.cache_resource
def get_client():
    uri = f"mongodb+srv://{MONGO_USER}:{MONGO_PASS}@cluster0.l7fdbmf.mongodb.net"
    return MongoClient(uri)

client = get_client()
db = client["mit261"]

# ----------------- SESSION STATE -----------------
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    login(db)
    st.stop()

# ----------------- LOAD DATA -----------------
@st.cache_data
def load_data():
    grades_col = db["grades"]
    pipeline = [
        {"$lookup": {"from": "students", "localField": "StudentID", "foreignField": "_id", "as": "student_info"}},
        {"$unwind": {"path": "$student_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {"from": "semesters", "localField": "SemesterID", "foreignField": "_id", "as": "semester_info"}},
        {"$unwind": {"path": "$semester_info", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 0,
            "StudentID": 1,
            "SemesterID": 1,
            "SubjectCodes": 1,
            "Grades": 1,
            "Teachers": 1,
            "SchoolYear": 1,
            "SemesterSchoolYear": "$semester_info.SchoolYear",
            "Name": "$student_info.Name",
            "Course": "$student_info.Course",
            "YearLevel": "$student_info.YearLevel",
        }},
    ]

    cursor = grades_col.aggregate(pipeline)
    df = pd.DataFrame(list(cursor))

    # Ensure necessary fields exist
    for col in ["SchoolYear", "Grades"]:
        if col not in df.columns:
            df[col] = None

    if "SemesterSchoolYear" in df.columns:
        df["SchoolYear"] = df["SchoolYear"].fillna(df["SemesterSchoolYear"])

    semesters_map = (
        df[["SemesterID", "SemesterSchoolYear"]]
        .dropna()
        .drop_duplicates()
        .set_index("SemesterID")["SemesterSchoolYear"]
        .to_dict()
    )
    return df, semesters_map

df_merged, semesters_map = load_data()

# ----------------- STREAMLIT UI -----------------
st.set_page_config(page_title="Student Grades Dashboard", layout="wide")
st.title("MIT Faculty Portal")

# Logout Button
if st.sidebar.button("Logout"):
    st.session_state['logged_in'] = False
    st.rerun()

# Navigation bar
role = st.session_state.get('role')
nav_options = []
if role == 'registrar':
    nav_options = ["Registrar"]
elif role == 'faculty':
    nav_options = ["Faculty", "Faculty Tasks"]
elif role == 'teacher':
    nav_options = ["Faculty"]
elif role == 'student':
    nav_options = ["Student"]

selected_nav = st.sidebar.radio("Navigation", nav_options) if nav_options else None

# ----------------- REGISTRAR SECTION -----------------
if selected_nav == "Registrar" and role == "registrar":
    st.header(" Registrar Dashboard")

    # Dropdowns
    semester_list = sorted(df_merged["SemesterID"].dropna().unique())
    subject_set = set()
    df_merged["SubjectCodes"].dropna().apply(lambda x: subject_set.update(x if isinstance(x, list) else []))
    subject_list = sorted(subject_set)

    selected_semester = st.selectbox("Select Semester", [""] + list(semester_list))
    selected_subject = st.selectbox("Select Subject Code", [""] + subject_list)

    # ----------------- DISPLAY -----------------
    if selected_semester and selected_subject:
        filtered = df_merged[
            (df_merged["SemesterID"] == selected_semester) &
            (df_merged["SubjectCodes"].apply(lambda codes: selected_subject in codes if isinstance(codes, list) else False))
        ]

        if filtered.empty:
            st.warning("❌ No records found for the selected semester and subject.")
        else:
            # Stats
            total_students_sem = filtered["StudentID"].nunique()
            school_year_str = str(semesters_map.get(selected_semester, "N/A"))

            # Teachers
            teachers = []
            for _, row in filtered.iterrows():
                if isinstance(row["SubjectCodes"], list) and isinstance(row["Teachers"], list):
                    for idx, code in enumerate(row["SubjectCodes"]):
                        if code == selected_subject and idx < len(row["Teachers"]):
                            teachers.append(row["Teachers"][idx])
            teachers_str = ", ".join(sorted(set(teachers))) if teachers else "N/A"

            # Extract grade per subject
            def get_grade(r):
                if isinstance(r["SubjectCodes"], list) and isinstance(r["Grades"], list):
                    for idx, code in enumerate(r["SubjectCodes"]):
                        if code == selected_subject and idx < len(r["Grades"]):
                            return r["Grades"][idx]
                return None

            filtered = filtered.copy()
            filtered["Grade"] = filtered.apply(get_grade, axis=1)

            # GPA
            gpa = filtered["Grade"].dropna()
            gpa_value = round(gpa.mean(), 2) if not gpa.empty else None
            above_count = (gpa > gpa_value).sum() if gpa_value is not None else None
            below_count = (gpa < gpa_value).sum() if gpa_value is not None else None

            # Subject description
            subject_doc = db["subjects"].find_one({"_id": selected_subject}, {"Description": 1})
            subject_description = subject_doc.get("Description", "N/A") if subject_doc else "N/A"

            # Total enrolled across all semesters
            total_enrolled = df_merged["StudentID"].loc[
                df_merged["SubjectCodes"].apply(lambda codes: selected_subject in codes if isinstance(codes, list) else False)
            ].nunique()

            # Header
            st.markdown(f"### Subject: {selected_subject} - {subject_description}")
            st.text(f"Teacher(s): {teachers_str}")

            # Metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="Semester", value=selected_semester)
                st.metric(label="Total Enrolled (All Semesters)", value=total_enrolled)
                st.metric(label="General Percentile Average (GPA)", value=f"{gpa_value:.2f}" if gpa_value is not None else "N/A")
            with col2:
                st.metric(label="School Year", value=school_year_str)
                st.metric(label="Total Students (This Semester)", value=total_students_sem)
                st.metric(label="Students Above GPA", value=above_count if above_count is not None else "N/A")

            with col3:
                st.metric(label="Subject Code", value=selected_subject)
                st.metric(label="Students Below GPA", value=below_count if below_count is not None else "N/A")


            # Student list
            display_df = filtered[["StudentID", "Name", "Course", "YearLevel", "Grade"]].copy()
            display_df.rename(columns={"Name": "FullName", "YearLevel": "Year Level"}, inplace=True)
            display_df["Grade"] = display_df["Grade"].apply(lambda x: int(x) if isinstance(x, (int, float)) and x == int(x) else x)
            display_df = display_df.sort_values("FullName").reset_index(drop=True)
            display_df.index += 1
            st.dataframe(display_df, use_container_width=True)

            # ----------------- SIMPLE LINE GRAPH -----------------
            student_ids = display_df["StudentID"].astype(str).tolist()
            student_names = display_df["FullName"].tolist()
            grades = display_df["Grade"].tolist()

            fig = go.Figure()

            # Line graph of grades
            fig.add_trace(
                go.Scatter(
                    x=student_ids,
                    y=grades,
                    mode="lines+markers",
                    name="Grades",
                    line=dict(color="blue", width=2),
                    marker=dict(size=6, color="blue"),
                    hovertemplate="StudentID: %{x}<br>Name: %{customdata}<br>Grade: %{y}<extra></extra>",
                    customdata=student_names
                )
            )

            # GPA line
            if gpa_value is not None:
                fig.add_trace(
                    go.Scatter(
                        x=student_ids,
                        y=[gpa_value] * len(student_ids),
                        mode="lines",
                        name="Average GPA",
                        line=dict(color="yellow", width=2, dash="dash"),
                        hovertemplate="Average GPA: %{y}<extra></extra>",
                    )
                )

            fig.update_layout(
                title=f"📈 Grades Line Chart - {selected_subject} ({selected_semester})",
                xaxis_title="Student ID",
                yaxis_title="Grade",
                template="plotly_dark",
                height=500,
            )

            st.plotly_chart(fig, use_container_width=True)

# ----------------- FACULTY SECTION -----------------
elif selected_nav == "Faculty" and (role == "faculty" or role == "teacher"):
    faculty(df_merged, semesters_map, db, role=st.session_state['role'], username=st.session_state['username'])

# ----------------- FACULTY TASKS SECTION -----------------
elif selected_nav == "Faculty Tasks" and role == "faculty":
    new_faculty_panel(db)

# ----------------- STUDENT SECTION -----------------
elif selected_nav == "Student" and role == "student":
    student_panel()
elif selected_nav:
    st.warning("You do not have access to this page.")