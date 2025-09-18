import streamlit as st
import pandas as pd
from pymongo import MongoClient
from helpers.utils import generate_excel

def get_grade_submission_data(db, teacher_name, semester_id):
    """Fetches and processes grade submission data using an aggregation pipeline."""
    pipeline = [
        {"$match": {"Teachers": teacher_name, "SemesterID": semester_id}},
        {"$unwind": {"path": "$Teachers", "includeArrayIndex": "teacher_idx"}},
        {"$match": {"Teachers": teacher_name}},
        {"$project": {
            "SubjectCode": {"$arrayElemAt": ["$SubjectCodes", "$teacher_idx"]},
            "Grade": {"$arrayElemAt": ["$Grades", "$teacher_idx"]},
            "StudentID": 1
        }},
        {"$group": {
            "_id": "$SubjectCode",
            "TotalStudents": {"$sum": 1},
            "SubmittedGrades": {"$sum": {"$cond": [{"$ne": ["$Grade", ""]}, 1, 0]}}
        }},
        {"$lookup": {
            "from": "subjects",
            "localField": "_id",
            "foreignField": "_id",
            "as": "subject_info"
        }},
        {"$unwind": "$subject_info"},
        {"$project": {
            "programCode": "$_id",
            "programName": "$subject_info.Description",
            "Submitted Grades": "$SubmittedGrades",
            "Total Students": "$TotalStudents",
            "Submission Rate": {
                "$multiply": [
                    {"$divide": ["$SubmittedGrades", "$TotalStudents"]},
                    100
                ]
            }
        }}
    ]

    try:
        data = list(db.grades.aggregate(pipeline))
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error fetching submission data: {e}")
        return pd.DataFrame()

def display_submission_status(df):
    """Displays the grade submission status."""
    df['Submission Rate'] = df['Submission Rate'].map('{:.2f}%'.format)
    st.dataframe(df.reset_index(drop=True), use_container_width=True)

    st.markdown("### 💾 Download Report")
    excel_bytes = generate_excel(df, "grade_submission_status_report.xlsx")
    st.download_button(
        label="⬇️ Download as Excel",
        data=excel_bytes,
        file_name="grade_submission_status_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

def grade_submission_status_panel(db, teacher_name=None):
    """Main function to display the grade submission status report."""
    st.header("📝 Grade Submission Status")
    st.info("This report tracks the status of grade submissions for each class taught by the selected faculty member for a given semester.")

    if teacher_name is None:
        st.warning("Please select a teacher from the main faculty page.")
        return

    try:
        semesters = list(db.semesters.find({}, {"_id": 1, "Semester": 1, "SchoolYear": 1}))
        semester_order = {"First": 1, "Second": 2, "Summer": 3}
        semesters.sort(key=lambda s: (s.get("SchoolYear", 0), semester_order.get(s.get("Semester"), -1)), reverse=True)
        semester_options = {s["_id"]: f"{s['Semester']} - {s['SchoolYear']}" for s in semesters}
        selected_semester_id = st.selectbox(
            "Select Semester",
            options=[""] + list(semester_options.keys()),
            format_func=lambda x: semester_options.get(x, "Select..."),
            key="submission_status_semester"
        )
    except Exception as e:
        st.error(f"Error fetching semesters: {e}")
        return

    if not selected_semester_id:
        st.info("Please select a semester to view the submission status.")
        return

    df_summary = get_grade_submission_data(db, teacher_name, selected_semester_id)

    if df_summary.empty:
        st.warning("No classes found for the selected teacher and semester.")
        return

    display_submission_status(df_summary)
