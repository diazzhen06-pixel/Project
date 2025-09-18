import pandas as pd
import streamlit as st
import plotly.express as px
from helpers.utils import generate_excel
from helpers.data_helper import get_programs

def get_grade_distribution_data(db, teacher_name, semester_id, program_code=None, program_name=None):
    """
    Fetches grade distribution data for a given teacher and semester.
    Returns a pandas DataFrame.
    """
    if not teacher_name or not semester_id:
        return pd.DataFrame()

    pipeline = [
        {"$match": {"SemesterID": semester_id}},
        {"$unwind": {"path": "$Teachers", "includeArrayIndex": "teacher_idx"}},
        {"$unwind": {"path": "$Grades", "includeArrayIndex": "grade_idx"}},
        {"$match": {"$expr": {"$and": [
            {"$eq": ["$Teachers", teacher_name]},
            {"$eq": ["$teacher_idx", "$grade_idx"]}
        ]}}},
        {"$lookup": {
            "from": "students",
            "localField": "StudentID",
            "foreignField": "_id",
            "as": "student_info"
        }},
        {"$unwind": "$student_info"},
        {"$lookup": {
            "from": "curriculum",
            "localField": "student_info.Course",
            "foreignField": "programCode",
            "as": "curriculum_info"
        }},
        {"$unwind": {"path": "$curriculum_info", "preserveNullAndEmptyArrays": True}},
    ]

    # Add program filters if provided
    if program_code:
        pipeline.append({"$match": {"student_info.Course": program_code}})
    if program_name:
        pipeline.append({"$match": {"curriculum_info.programName": program_name}})

    pipeline.extend([
        {"$group": {
            "_id": {
                "programCode": "$student_info.Course",
                "programName": {"$ifNull": ["$curriculum_info.programName", "$student_info.Course"]}
            },
            "grades": {"$push": "$Grades"}
        }}
    ]

    try:
        data = list(db.grades.aggregate(pipeline))
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"An error occurred during aggregation: {e}")
        return pd.DataFrame()

def process_grade_distribution_data(df):
    """
    Processes the raw grade distribution data to calculate percentages.
    Returns a formatted DataFrame.
    """
    if df.empty:
        return pd.DataFrame()

    records = []
    for _, row in df.iterrows():
        program_code = row["_id"]["programCode"]
        program_name = row["_id"]["programName"]
        grades = pd.Series(row["grades"])
        total_grades = len(grades)

        if total_grades == 0:
            continue

        bins = {
            "95-100(%)": ((grades >= 95) & (grades <= 100)).sum(),
            "90-94(%)": ((grades >= 90) & (grades <= 94)).sum(),
            "85-89(%)": ((grades >= 85) & (grades <= 89)).sum(),
            "80-84(%)": ((grades >= 80) & (grades <= 84)).sum(),
            "75-79(%)": ((grades >= 75) & (grades <= 79)).sum(),
            "Below 75(%)": (grades < 75).sum()
        }

        record = {
            "programCode": program_code,
            "programName": program_name,
            "Total": total_grades
        }

        for key, value in bins.items():
            percentage = (value / total_grades) * 100 if total_grades > 0 else 0
            record[key] = f"{percentage:.2f}%"

        records.append(record)

    if not records:
        return pd.DataFrame()

    df_processed = pd.DataFrame(records)
    column_order = [
        "programCode", "programName", "95-100(%)", "90-94(%)", "85-89(%)",
        "80-84(%)", "75-79(%)", "Below 75(%)", "Total"
    ]

    for col in column_order:
        if col not in df_processed:
            df_processed[col] = 0 if col != 'Total' else '0.00%'

    return df_processed[column_order]

def display_grade_distribution_histograms(df_raw, db):
    """Displays grade distribution histograms for each program."""
    st.markdown("### Grade Distribution Histograms")

    # Explode the grades list to have one grade per row
    df_grades = df_raw.explode('grades').rename(columns={'grades': 'Grade'})

    # Extract program info
    df_grades['programCode'] = df_grades['_id'].apply(lambda x: x['programCode'])
    df_grades['programName'] = df_grades['_id'].apply(lambda x: x['programName'])


    for program_name, group in df_grades.groupby('programName'):
        st.markdown(f"#### {program_name}")

        fig = px.histogram(
            group,
            x="Grade",
            title=f"Grade Distribution for {program_name}",
            nbins=20,
            template="plotly_dark"
        )
        fig.update_layout(
            xaxis_title="Grade",
            yaxis_title="Number of Students",
            bargap=0.1
        )
        st.plotly_chart(fig, use_container_width=True)

def class_grade_distribution_report(db, teacher_name):
    """Main function to display the class grade distribution report."""
    st.header("📊 Class Grade Distribution")
    st.info("This report shows the grade distribution across different programs for the selected semester.")

    programs_df = get_programs(db)
    program_codes = [""] + sorted(programs_df["programCode"].unique())
    program_names = [""] + sorted(programs_df["programName"].unique())

    col1, col2, col3 = st.columns(3)
    with col1:
        try:
            semesters = list(db.semesters.find({}, {"_id": 1, "Semester": 1, "SchoolYear": 1}))
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
    with col2:
        selected_program_code = st.selectbox("Filter by Program Code", program_codes)
    with col3:
        if selected_program_code:
            program_name_options = [""] + sorted(programs_df[programs_df["programCode"] == selected_program_code]["programName"].unique())
        else:
            program_name_options = program_names
        selected_program_name = st.selectbox("Filter by Program Name", program_name_options)


    if not selected_semester_id:
        st.info("Please select a semester to view the report.")
        return

    df_raw = get_grade_distribution_data(db, teacher_name, selected_semester_id, selected_program_code, selected_program_name)
    if df_raw.empty:
        st.warning("No data found for the selected criteria.")
        return

    df_dist = process_grade_distribution_data(df_raw.copy())
    st.markdown("### Grade Distribution by Program")
    st.dataframe(df_dist, use_container_width=True)

    st.markdown("### 💾 Download Report")
    excel_bytes = generate_excel(df_dist, "grade_distribution_report.xlsx")
    st.download_button(
        label="⬇️ Download as Excel",
        data=excel_bytes,
        file_name=f"GradeDistribution_{teacher_name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    display_grade_distribution_histograms(df_raw, db)
