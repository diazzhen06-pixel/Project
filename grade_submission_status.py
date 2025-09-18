import streamlit as st
import pandas as pd
from pymongo import MongoClient
from helpers.utils import generate_excel
from helpers.pdf_reporter import generate_grade_submission_status_pdf

def grade_submission_status_panel(db, teacher_name=None):
    """Displays the status of grade submissions by faculty."""
    st.header("📝 Grade Submission Status")
    st.info("This report tracks the status of grade submissions for each class taught by the selected faculty member for a given semester.")

    if teacher_name is None:
        st.warning("Please select a teacher from the main faculty page.")
        return

    # Semester selector
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

    # Fetch data for the selected teacher and semester
    pipeline = [
        {"$match": {"Teachers": teacher_name, "SemesterID": selected_semester_id}},
        {"$unwind": {"path": "$Teachers", "includeArrayIndex": "teacher_idx"}},
        {"$match": {"Teachers": teacher_name}},
        {"$project": {
            "SubjectCode": {"$arrayElemAt": ["$SubjectCodes", "$teacher_idx"]},
            "Grade": {"$arrayElemAt": ["$Grades", "$teacher_idx"]},
            "StudentID": 1
        }}
    ]

    try:
        submission_data = list(db.grades.aggregate(pipeline))
    except Exception as e:
        st.error(f"Error fetching submission data: {e}")
        return

    if not submission_data:
        st.warning("No classes found for the selected teacher and semester.")
        return

    df_submission = pd.DataFrame(submission_data)

    # Group by subject to calculate submission stats
    submission_summary = []
    for subject_code, group in df_submission.groupby('SubjectCode'):
        total_students = group['StudentID'].nunique()

        # A grade is considered "submitted" if it's not null/NaN and not an empty string.
        submitted_grades = group[pd.notna(group['Grade']) & (group['Grade'] != "")]['StudentID'].nunique()

        submission_rate = (submitted_grades / total_students) * 100 if total_students > 0 else 0

        submission_summary.append({
            "programCode": subject_code,
            "Submitted Grades": submitted_grades,
            "Total Students": total_students,
            "Submission Rate": submission_rate
        })

    if not submission_summary:
        st.warning("Could not compute submission statistics.")
        return

    df_summary = pd.DataFrame(submission_summary)

    # Add programName from subjects collection
    subject_codes = df_summary['programCode'].unique().tolist()
    subjects_info = {
        s['_id']: s['Description']
        for s in db.subjects.find({"_id": {"$in": subject_codes}}, {"_id": 1, "Description": 1})
    }
    df_summary['programName'] = df_summary['programCode'].map(subjects_info).fillna("N/A")

    # Reorder and format
    df_summary = df_summary[['programCode', 'programName', 'Submitted Grades', 'Total Students', 'Submission Rate']]
    df_summary['Submission Rate'] = df_summary['Submission Rate'].map('{:.2f}%'.format)

    st.dataframe(df_summary.reset_index(drop=True), use_container_width=True)

    # ---------- DOWNLOAD REPORTS ----------
    st.markdown("### 💾 Download Report")
    col_download_excel, col_download_pdf = st.columns(2)

    with col_download_excel:
        excel_bytes = generate_excel(df_summary, "grade_submission_status_report.xlsx")
        st.download_button(
            label="⬇️ Download as Excel",
            data=excel_bytes,
            file_name="grade_submission_status_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col_download_pdf:
        pdf_bytes = generate_grade_submission_status_pdf(
            data={
                "dataframe": df_summary,
            }
        )
        st.download_button(
            label="⬇️ Download as PDF",
            data=pdf_bytes,
            file_name="grade_submission_status_report.pdf",
            mime="application/pdf",
        )
