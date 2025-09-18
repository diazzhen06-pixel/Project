import streamlit as st
import pandas as pd
from pymongo import MongoClient
from helpers.utils import generate_excel

def custom_query_builder_panel(db):
    """A panel for building custom queries on student grades."""
    st.header("🔎 Custom Query Builder")
    st.info(
        "This tool allows you to build custom queries to filter student data. "
        "For example, you can find all students who scored below 75 in a specific subject."
    )

    # --- UI Components ---
    col1, col2, col3 = st.columns(3)
    with col1:
        program_code = st.text_input("Program Code (e.g., IT103)")
    with col2:
        operator = st.selectbox("Operator", ["<", ">", "<=", ">=", "="])
    with col3:
        grade = st.number_input("Grade", min_value=0, max_value=100, value=75)

    if st.button("Run Query"):
        if not program_code:
            st.warning("Please enter a Program Code.")
        else:
            run_query(db, program_code, operator, grade)

def run_query(db, program_code, operator, grade):
    """Runs the query and displays the results."""
    operator_map = {
        "<": "$lt",
        ">": "$gt",
        "<=": "$lte",
        ">=": "$gte",
        "=": "$eq",
    }
    mongo_operator = operator_map[operator]

    pipeline = [
        {"$unwind": {"path": "$SubjectCodes", "includeArrayIndex": "subject_idx"}},
        {"$unwind": {"path": "$Grades", "includeArrayIndex": "grade_idx"}},
        {"$match": {
            "$expr": {"$eq": ["$subject_idx", "$grade_idx"]},
            "SubjectCodes": program_code,
            "Grades": {mongo_operator: grade}
        }},
        {"$lookup": {
            "from": "students",
            "localField": "StudentID",
            "foreignField": "_id",
            "as": "student_info"
        }},
        {"$unwind": "$student_info"},
        {"$lookup": {
            "from": "subjects",
            "localField": "SubjectCodes",
            "foreignField": "_id",
            "as": "subject_info"
        }},
        {"$unwind": "$subject_info"},
        {"$project": {
            "_id": 0,
            "StudentID": "$StudentID",
            "StudentName": "$student_info.Name",
            "programCode": "$SubjectCodes",
            "programName": "$subject_info.Description",
            "Grade": "$Grades"
        }}
    ]

    try:
        results = list(db.grades.aggregate(pipeline))
        if not results:
            st.warning("No records found for the given criteria.")
            return

        df = pd.DataFrame(results)
        df = df.rename(columns={
            "StudentID": "Student ID",
            "StudentName": "Student Name",
            "programCode": "Program Code",
            "programName": "Program Name",
        })
        st.dataframe(df, use_container_width=True)

        st.markdown("### 💾 Download Report")
        excel_bytes = generate_excel(df, "custom_query_report.xlsx")
        st.download_button(
            label="⬇️ Download as Excel",
            data=excel_bytes,
            file_name="custom_query_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        st.error(f"An error occurred while running the query: {e}")
