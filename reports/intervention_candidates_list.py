import streamlit as st
import pandas as pd
from pymongo import MongoClient
from helpers.utils import generate_excel

# ----------------- CONSTANTS -----------------
AT_RISK_THRESHOLD = 60

def get_risk_flag(grade):
    """Determine the risk flag based on the grade."""
    if pd.isna(grade) or grade == "":
        return "Missing Grade"
    try:
        if float(grade) < AT_RISK_THRESHOLD:
            return f"At Risk (<{AT_RISK_THRESHOLD})"
    except (ValueError, TypeError):
        return "Invalid Grade Format"
    return None

def get_intervention_candidates_data(db, teacher_name, semester_id):
    """Fetches and processes data for intervention candidates."""
    pipeline = [
        {"$match": {"Teachers": teacher_name, "SemesterID": selected_semester_id}},
        {"$unwind": {"path": "$Teachers", "includeArrayIndex": "teacher_idx"}},
        {"$match": {"Teachers": teacher_name}},
        {"$lookup": {"from": "students", "localField": "StudentID", "foreignField": "_id", "as": "student_info"}},
        {"$unwind": "$student_info"},
        {"$project": {
            "StudentID": "$student_info._id",
            "StudentName": "$student_info.Name",
            "programCode": "$student_info.Course",
            "Grade": {"$arrayElemAt": ["$Grades", "$teacher_idx"]},
            "SubjectCode": {"$arrayElemAt": ["$SubjectCodes", "$teacher_idx"]}
        }}
    ]

    try:
        candidates_data = list(db.grades.aggregate(pipeline))
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

    if not candidates_data:
        return pd.DataFrame()

    df = pd.DataFrame(candidates_data)
    df['Risk Flag'] = df['Grade'].apply(get_risk_flag)
    df_at_risk = df[df['Risk Flag'].notna()].copy()

    if df_at_risk.empty:
        return pd.DataFrame()

    program_codes = df_at_risk['programCode'].unique().tolist()
    curriculum_info = {
        c['programCode']: c['programName']
        for c in db.curriculum.find({"programCode": {"$in": program_codes}}, {"programCode": 1, "programName": 1})
    }
    df_at_risk['programName'] = df_at_risk['programCode'].map(curriculum_info).fillna("N/A")

    return df_at_risk

def display_intervention_candidates(df):
    """Displays the list of intervention candidates."""
    df.rename(columns={
        "StudentID": "Student ID",
        "StudentName": "Student Name",
        "Grade": "Current Grade"
    }, inplace=True)

    display_df = df[[
        "Student ID", "Student Name", "programCode", "programName", "Current Grade", "Risk Flag"
    ]]

    st.dataframe(display_df.reset_index(drop=True), use_container_width=True)

    st.markdown("### 💾 Download Report")
    excel_bytes = generate_excel(display_df, "intervention_candidates_report.xlsx")
    st.download_button(
        label="⬇️ Download as Excel",
        data=excel_bytes,
        file_name="intervention_candidates_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

def intervention_candidates_list_panel(db, teacher_name=None):
    """Main function to display the intervention candidates list."""
    st.header("🧑‍🏫 Intervention Candidates List")
    st.info("This report lists students at academic risk based on low or missing grades for the selected semester.")

    if teacher_name is None:
        st.warning("Please select a teacher from the main faculty page.")
        return

    try:
        semesters = list(db.semesters.find({}, {"_id": 1, "Semester": 1, "SchoolYear": 1}))
        semester_order = {"First": 1, "Second": 2, "Summer": 3}
        semesters.sort(key=lambda s: (s.get("SchoolYear", 0), semester_order.get(s.get("Semester"), -1)), reverse=True)
        semester_options = {s["_id"]: f"{s['Semester']} - {s['SchoolYear']}" for s in semesters}
        global selected_semester_id
        selected_semester_id = st.selectbox(
            "Select Semester",
            options=[""] + list(semester_options.keys()),
            format_func=lambda x: semester_options.get(x, "Select..."),
            key="intervention_semester"
        )
    except Exception as e:
        st.error(f"Error fetching semesters: {e}")
        return

    if not selected_semester_id:
        st.info("Please select a semester to view the list.")
        return

    df_at_risk = get_intervention_candidates_data(db, teacher_name, selected_semester_id)

    if df_at_risk.empty:
        st.success("✅ No students are currently identified as at-risk for this semester.")
        return

    display_intervention_candidates(df_at_risk)
