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
from helpers.pdf_reporter import generate_faculty_report_pdf, generate_grade_distribution_pdf
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


def class_grade_distribution_report(db, teacher_name):
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
    df_dist = get_grade_distribution_by_faculty(db, teacher_name, selected_semester_id)

    if df_dist.empty:
        st.warning("No data found for the selected criteria.")
        return

    st.markdown("### Grade Distribution by Program")
    st.dataframe(df_dist, use_container_width=True)

    # ---------- DOWNLOAD REPORTS ----------
    st.markdown("### 💾 Download Report")
    col_download_excel, col_download_pdf = st.columns(2)

    with col_download_excel:
        excel_bytes = generate_excel(df_dist, "grade_distribution_report.xlsx")
        st.download_button(
            label="⬇️ Download as Excel",
            data=excel_bytes,
            file_name=f"GradeDistribution_{teacher_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col_download_pdf:
        pdf_bytes = generate_grade_distribution_pdf(
            data={
                "dataframe": df_dist,
                "teacher_name": teacher_name,
                "semester_id": selected_semester_id,
            }
        )
        st.download_button(
            label="⬇️ Download as PDF",
            data=pdf_bytes,
            file_name=f"GradeDistribution_{teacher_name}.pdf",
            mime="application/pdf",
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


# ---------- FACULTY DASHBOARD ----------
def faculty_dashboard(selected_teacher_name, df, subjects_map, semesters_map, db=None):
    st.subheader("👩‍🏫 Faculty Dashboard")
    st.info(f"Welcome, {selected_teacher_name}!")

    taught_subjects_df = pd.DataFrame(list(subjects_map.values()))
    taught_subjects_df["SubjectCode"] = list(subjects_map.keys())
    taught_subjects_df = taught_subjects_df[taught_subjects_df["Teacher"] == selected_teacher_name]

    if taught_subjects_df.empty:
        st.warning("You are not currently assigned to any subjects.")
        return

    st.markdown("### 📚 Your Subjects")
    selected_subject_code = st.selectbox(
        "Select a Subject", [""] + sorted(taught_subjects_df["SubjectCode"].unique()), key="faculty_subject"
    )
    if not selected_subject_code:
        return

    st.markdown(f"#### 📑 Class Report for {selected_subject_code}")

    subject_grades = []
    for _, row in df.iterrows():
        if isinstance(row["SubjectCodes"], list) and selected_subject_code in row["SubjectCodes"]:
            try:
                subject_info = subjects_map.get(selected_subject_code, {})
                if subject_info.get("Teacher") == selected_teacher_name:
                    idx = row["SubjectCodes"].index(selected_subject_code)
                    grade = pd.to_numeric(row["Grades"][idx], errors="coerce") if idx < len(row["Grades"]) else None
                    grade = min(100, grade) if pd.notna(grade) else grade
                    subject_grades.append({
                        "StudentID": row["StudentID"],
                        "StudentName": row["Name"],
                        "Course": row["Course"],
                        "YearLevel": row["YearLevel"],
                        "SemesterID": row.get("SemesterID", None),
                        "Grade": grade,
                    })
            except (ValueError, IndexError):
                continue

    if not subject_grades:
        st.warning("No grade records found for this subject under your name.")
        return

    df_subject_grades = pd.DataFrame(subject_grades).dropna(subset=["Grade"])
    df_subject_grades = df_subject_grades.sort_values(by=["YearLevel", "StudentName"]).reset_index(drop=True)
    df_subject_grades["Remarks"] = df_subject_grades["Grade"].apply(lambda x: "Passed" if x >= 75 else "Failed")

    # Overall class stats
    avg_gpa = df_subject_grades["Grade"].mean()
    total_students = df_subject_grades.shape[0]

    col1, col2 = st.columns(2)
    col1.metric("Class GPA", f"{avg_gpa:.2f}")
    col2.metric("Total Students", total_students)

    # ---------- GROUP BY YEAR ----------
    grouped_by_year = df_subject_grades.groupby("YearLevel")
    for year_level, group_df in grouped_by_year:
        st.markdown(f"### 🎓 Year Level {year_level}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Mean Grade", f"{group_df['Grade'].mean():.2f}")
        col2.metric("Median Grade", f"{group_df['Grade'].median():.2f}")
        col3.metric("Highest Grade", f"{group_df['Grade'].max():.2f}")
        col4.metric("Lowest Grade", f"{group_df['Grade'].min():.2f}")

        styled_df = group_df.style.applymap(highlight_failed, subset=["Remarks"])
        st.dataframe(styled_df, use_container_width=True)

        # Histogram
        st.markdown(f"📊 Grade Distribution for Year Level {year_level}")
        fig_hist, ax_hist = plt.subplots(figsize=(10, 6))
        bins = range(60, 101, 5)
        n_hist, bins_hist, patches_hist = ax_hist.hist(group_df["Grade"], bins=bins, edgecolor="black")
        ax_hist.set_xlabel("Grades")
        ax_hist.set_ylabel("Frequency")
        ax_hist.set_xticks(bins)
        for i in range(len(n_hist)):
            if n_hist[i] > 0:
                ax_hist.text(
                    bins_hist[i] + (bins_hist[1] - bins_hist[0]) / 2,
                    n_hist[i],
                    int(n_hist[i]),
                    ha="center",
                    va="bottom",
                )
        st.pyplot(fig_hist)
        plt.close(fig_hist)

        # Pass vs Fail
        st.markdown(f"📊 Pass vs Fail for Year Level {year_level}")
        pass_count = group_df[group_df["Remarks"] == "Passed"].shape[0]
        fail_count = group_df[group_df["Remarks"] == "Failed"].shape[0]
        fig_pf, ax_pf = plt.subplots(figsize=(6, 4))
        bars = ax_pf.bar(["Pass", "Fail"], [pass_count, fail_count], color=["green", "red"])
        for bar in bars:
            yval = bar.get_height()
            ax_pf.text(bar.get_x() + bar.get_width() / 2, yval, int(yval), ha="center", va="bottom")
        st.pyplot(fig_pf)
        plt.close(fig_pf)

        st.markdown("---")

    # ---------- DOWNLOAD REPORTS ----------
    st.markdown("### 💾 Download Class Report")
    col_download_excel, col_download_pdf = st.columns(2)

    with col_download_excel:
        excel_bytes = generate_excel(df_subject_grades, "faculty_class_report.xlsx")
        st.download_button(
            label="⬇️ Download as Excel",
            data=excel_bytes,
            file_name=f"FacultyReport_{selected_subject_code}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col_download_pdf:
        # Get one semester ID to fetch SchoolYear
        semester_id = None
        non_null_semesters = df_subject_grades["SemesterID"].dropna()
        if not non_null_semesters.empty:
            semester_id = non_null_semesters.iloc[0]

        semester_info = semesters_map.get(semester_id, "N/A")
        semester_name = semester_info
        school_year = semester_info

        subject_description = get_subject_description(selected_subject_code, db)

        pdf_bytes = generate_faculty_report_pdf(
            data={
                "dataframe": df_subject_grades,
                "semester_info": semester_name,
                "subject_description": subject_description,
                "teachers_str": selected_teacher_name,
                "subject_code": selected_subject_code,
                "avg_gpa": avg_gpa,
            }
        )
        st.download_button(
            label="⬇️ Download as PDF",
            data=pdf_bytes,
            file_name=f"FacultyReport_{selected_subject_code}.pdf",
            mime="application/pdf",
        )


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
        st.header("📘 Class Report")
        st.info("This report provides a detailed view of student performance in a specific subject.")
        faculty_dashboard(selected_teacher_name, df, subjects_map, semesters_map, db)

    elif selected_report == "📊 Class Grade Distribution":
        st.header("📊 Class Grade Distribution")
        st.info("This report shows the grade distribution across different programs for the selected semester.")
        class_grade_distribution_report(db, selected_teacher_name)

    elif selected_report == "📈 Student Progress Tracker":
        st.header("📈 Student Progress Tracker")
        st.info("This report shows the longitudinal performance for individual students.")
        student_progress_tracker_panel(db, teacher_name=selected_teacher_name)

    elif selected_report == "🔥 Subject Difficulty Heatmap":
        st.header("🔥 Subject Difficulty Heatmap")
        st.info("This report visualizes subjects with high failure or dropouts.")
        subject_difficulty_heatmap_panel(db, teacher_name=selected_teacher_name)

    elif selected_report == "🧑‍🏫 Intervention Candidates List":
        intervention_candidates_list_panel(db, teacher_name=selected_teacher_name)

    elif selected_report == "📝 Grade Submission Status":
        grade_submission_status_panel(db, teacher_name=selected_teacher_name)

    elif selected_report == "🔎 Custom Query Builder":
        custom_query_builder_panel(db)