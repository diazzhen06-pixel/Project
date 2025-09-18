import pandas as pd
import streamlit as st
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the helper functions and panels
from reports.class_report import class_report
from reports.class_grade_distribution import class_grade_distribution_report
from reports.student_progress_tracker import student_progress_tracker_panel
from reports.subject_difficulty_heatmap import subject_difficulty_heatmap_panel
from reports.intervention_candidates_list import intervention_candidates_list_panel
from reports.grade_submission_status import grade_submission_status_panel
from reports.custom_query_builder import custom_query_builder_panel


# ---------- ENTRY POINT ----------
def faculty(df, semesters_map, db, role, username):
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

    # Dropdown for report selection
    report_options = [
        "📘 Class Report",
        "📊 Class Grade Distribution",
        "📈 Student Progress Tracker",
        "🔥 Subject Difficulty Heatmap",
        "🧑‍🏫 Intervention Candidates List",
        "📝 Grade Submission Status",
        "🔎 Custom Query Builder"
    ]

    selected_report = st.selectbox("Select a Report", report_options)

    # Render the selected report
    if selected_report == "📘 Class Report":
        class_report(selected_teacher_name, db)

    elif selected_report == "📊 Class Grade Distribution":
        class_grade_distribution_report(db, selected_teacher_name)

    elif selected_report == "📈 Student Progress Tracker":
        student_progress_tracker_panel(db, teacher_name=selected_teacher_name)

    elif selected_report == "🔥 Subject Difficulty Heatmap":
        subject_difficulty_heatmap_panel(db, teacher_name=selected_teacher_name)

    elif selected_report == "🧑‍🏫 Intervention Candidates List":
        intervention_candidates_list_panel(db, teacher_name=selected_teacher_name)

    elif selected_report == "📝 Grade Submission Status":
        grade_submission_status_panel(db, teacher_name=selected_teacher_name)

    elif selected_report == "🔎 Custom Query Builder":
        custom_query_builder_panel(db)