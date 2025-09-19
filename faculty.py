import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import plotly.express as px
from io import BytesIO

# Import the helper functions and panels
# You will need to ensure these files exist and contain the correct functions
from helpers.faculty_helper import get_grade_distribution_by_faculty
from student_progress_tracker import student_progress_tracker_panel
from subject_difficulty_heatmap import subject_difficulty_heatmap_panel
from intervention_candidates_list import intervention_candidates_list_panel
from grade_submission_status import grade_submission_status_panel
from custom_query_builder import custom_query_builder_panel
from helpers.utils import generate_excel


# ---------- HELPERS ----------




def highlight_failed(val):
    """Highlight failed grades in red, passed in green."""
    color = "red" if val == "Failed" else "green"
    return f"color: {color}; font-weight: bold;"


def get_subject_description(subject_code, db=None):
    """Return subject description from DB if available, otherwise placeholder."""
    if db is not None:
        doc = db["subjects"].find_one({"_id": subject_code}, {"Description": 1})
        if doc is not None:
            return doc.get("Description", f"Description for {subject_code}")
    return f"Description for {subject_code}"


def class_grade_distribution_report(db, teacher_name, subject_code=None):
    st.subheader("📊 Class Grade Distribution Report")

    # Get semester list
    try:
        semesters = list(db.semesters.find({}, {"_id": 1, "Semester": 1, "SchoolYear": 1}))
        # Sort semesters: First by SchoolYear descending, then by a custom semester order
        semester_order = {"First": 1, "Second": 2, "Summer": 3}
        semesters.sort(key=lambda s: (s.get("SchoolYear", 0), semester_order.get(s.get("Semester"), -1)), reverse=True)

        semester_options = {s["_id"]: f"{s['Semester']} - {s['SchoolYear']}" for s in semesters}
        semester_ids = [""] + list(semester_options.keys())

    except Exception as e:
        st.error(f"Error fetching semesters: {e}")
        return

    selected_semester_id = st.selectbox(
        "Select Semester and School Year",
        options=semester_ids,
        format_func=lambda x: semester_options.get(x, "Select..."),
    )

    if not selected_semester_id:
        st.info("Please select a semester to view the report.")
        return

    # Get data for the table
    df_dist = get_grade_distribution_by_faculty(db, teacher_name, selected_semester_id, subject_code=subject_code)

    if df_dist.empty:
        st.warning("No data found for the selected criteria.")
        return

    st.markdown("### Grade Distribution by Program")
    st.dataframe(df_dist, use_container_width=True)

    # ---------- DOWNLOAD REPORTS ----------
    st.markdown("### 💾 Download Report")

    excel_bytes = generate_excel(df_dist, "grade_distribution_report.xlsx")
    st.download_button(
        label="⬇️ Download as Excel",
        data=excel_bytes,
        file_name=f"GradeDistribution_{teacher_name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown("### Grade Distribution Histograms")

    # This part is for fetching raw grades for plotting
    pipeline = [
        {"$match": {"SemesterID": selected_semester_id, "Teachers": teacher_name}},
        {"$unwind": {"path": "$Teachers", "includeArrayIndex": "idx"}},
        {"$match": {"Teachers": teacher_name}},
        {"$unwind": {"path": "$Grades", "includeArrayIndex": "grade_idx"}},
        {"$match": {"$expr": {"$eq": ["$idx", "$grade_idx"]}}},
        {"$lookup": {"from": "students", "localField": "StudentID", "foreignField": "_id", "as": "student"}},
        {"$unwind": "$student"},
        {"$project": {"_id": 0, "Grade": "$Grades", "Course": "$student.Course"}}
    ]

    try:
        raw_grades_data = list(db.grades.aggregate(pipeline))
        if not raw_grades_data:
            st.warning("No grades found for plotting.")
            return
    except Exception as e:
        st.error(f"Error fetching grades for histogram: {e}")
        return

    df_grades = pd.DataFrame(raw_grades_data)

    # Get program names from curriculum
    courses = df_grades['Course'].unique()
    curriculum_map = {c['programCode']: c['programName'] for c in db.curriculum.find({"programCode": {"$in": list(courses)}})}
    df_grades['programName'] = df_grades['Course'].map(curriculum_map).fillna(df_grades['Course'])

    for program_name, group in df_grades.groupby('programName'):
        st.markdown(f"#### {program_name}")

        fig = px.histogram(
            group,
            x="Grade",
            title=f"Grade Distribution for {program_name}",
            nbins=20, # Adjust number of bins for better visualization
            template="plotly_dark"
        )
        fig.update_layout(
            xaxis_title="Grade",
            yaxis_title="Number of Students",
            bargap=0.1
        )
        st.plotly_chart(fig, use_container_width=True)


# ---------- ENTRY POINT ----------
def faculty(df, semesters_map, db, role, username):
    st.header("📘 Class Record")
    st.info("This report provides a detailed view of student performance in a specific subject.")
    if db is None:
        st.warning("⚠️ Database connection not available.")
        return

    # Build subjects_map from DB
    subjects_cursor = db["subjects"].find({}, {"_id": 1, "Description": 1, "Units": 1, "Teacher": 1})
    subjects_map = {doc["_id"]: doc for doc in subjects_cursor}

    selected_teacher_name = None
    if role == 'faculty':
        teacher_list = sorted({subj.get("Teacher") for subj in subjects_map.values() if subj.get("Teacher")})
        if not teacher_list:
            st.warning("⚠️ No teachers found in subjects mapping.")
            return
        selected_teacher_name = st.selectbox("Select Teacher", [""] + teacher_list, key="faculty_teacher")
    elif role == 'teacher':
        selected_teacher_name = username

    if not selected_teacher_name:
        st.info("Please select a teacher to continue.")
        return

    st.markdown("---")

    # Build DataFrame from subjects_map
    taught_subjects_df = pd.DataFrame(list(subjects_map.values()))
    taught_subjects_df["SubjectCode"] = list(subjects_map.keys())

    # Normalize teacher names (strip spaces, lowercase for comparison)
    taught_subjects_df["Teacher"] = (
        taught_subjects_df["Teacher"].astype(str).str.strip().str.lower()
    )
    selected_teacher_name_clean = str(selected_teacher_name).strip().lower()

    # Filter by normalized teacher name
    taught_subjects_df = taught_subjects_df[
        taught_subjects_df["Teacher"] == selected_teacher_name_clean
    ]

    if taught_subjects_df.empty:
        st.warning("You are not currently assigned to any subjects.")
        return

    st.markdown("### 📚 Your Subjects")
    selected_subject_code = st.selectbox(
        "Select a Subject",
        [""] + sorted(taught_subjects_df["SubjectCode"].unique()),
        key="faculty_subject"
    )

    if not selected_subject_code:
        return

    # (You can add logic here to display subject-specific info)
    st.success(f"You selected subject: {selected_subject_code}")

    # Render all the reports for the selected subject
    st.header("📊 Class Grade Distribution")
    class_grade_distribution_report(db, selected_teacher_name, subject_code=selected_subject_code)

    st.header("📈 Student Progress Tracker")
    student_progress_tracker_panel(db, teacher_name=selected_teacher_name, subject_code=selected_subject_code)

    st.header("🔥 Subject Difficulty Heatmap")
    subject_difficulty_heatmap_panel(db, teacher_name=selected_teacher_name, subject_code=selected_subject_code)

    st.header("🧑‍🏫 Intervention Candidates List")
    intervention_candidates_list_panel(db, teacher_name=selected_teacher_name, subject_code=selected_subject_code)

    st.header("📝 Grade Submission Status")
    grade_submission_status_panel(db, teacher_name=selected_teacher_name, subject_code=selected_subject_code)

    st.header("🔎 Custom Query Builder")
    custom_query_builder_panel(db, subject_code=selected_subject_code)