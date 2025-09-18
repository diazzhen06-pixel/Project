import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from io import BytesIO
from helpers.utils import generate_excel

# ---------- CONSTANTS ----------
PASSING_GRADE = 75

# ---------- HELPERS ----------

def highlight_failed(val):
    """Highlight failed grades in red, passed in green."""
    color = "red" if val == "Failed" else "green"
    return f"color: {color}; font-weight: bold;"

def get_subject_data(db, teacher_name, subject_code):
    """Fetches and processes data for a specific subject taught by a teacher."""
    pipeline = [
        {"$unwind": "$SubjectCodes"},
        {"$unwind": "$Grades"},
        {"$unwind": "$Teachers"},
        {"$match": {"Teachers": teacher_name, "SubjectCodes": subject_code}},
        {"$lookup": {
            "from": "students",
            "localField": "StudentID",
            "foreignField": "_id",
            "as": "student_info"
        }},
        {"$unwind": "$student_info"},
        {"$project": {
            "StudentID": "$StudentID",
            "StudentName": "$student_info.Name",
            "Course": "$student_info.Course",
            "YearLevel": "$student_info.YearLevel",
            "Grade": "$Grades"
        }}
    ]

    grades_data = list(db.grades.aggregate(pipeline))
    if not grades_data:
        return pd.DataFrame()

    df = pd.DataFrame(grades_data)
    df["Remarks"] = df["Grade"].apply(lambda x: "Passed" if x >= PASSING_GRADE else "Failed")
    return df.sort_values(by=["YearLevel", "StudentName"]).reset_index(drop=True)

def display_class_stats(df):
    """Displays overall class statistics."""
    avg_gpa = df["Grade"].mean()
    total_students = df.shape[0]
    col1, col2 = st.columns(2)
    col1.metric("Class GPA", f"{avg_gpa:.2f}")
    col2.metric("Total Students", total_students)

def display_year_level_stats(df):
    """Displays statistics for each year level."""
    grouped_by_year = df.groupby("YearLevel")
    for year_level, group_df in grouped_by_year:
        st.markdown(f"### 🎓 Year Level {year_level}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Mean Grade", f"{group_df['Grade'].mean():.2f}")
        col2.metric("Median Grade", f"{group_df['Grade'].median():.2f}")
        col3.metric("Highest Grade", f"{group_df['Grade'].max():.2f}")
        col4.metric("Lowest Grade", f"{group_df['Grade'].min():.2f}")

        styled_df = group_df.style.applymap(highlight_failed, subset=["Remarks"])
        st.dataframe(styled_df, use_container_width=True)

        display_year_level_charts(group_df, year_level)
        st.markdown("---")

def display_year_level_charts(df, year_level):
    """Displays grade distribution and pass/fail charts for a year level."""
    # Histogram
    st.markdown(f"📊 Grade Distribution for Year Level {year_level}")
    fig_hist, ax_hist = plt.subplots(figsize=(10, 6))
    bins = range(60, 101, 5)
    n_hist, _, _ = ax_hist.hist(df["Grade"], bins=bins, edgecolor="black")
    ax_hist.set_xlabel("Grades")
    ax_hist.set_ylabel("Frequency")
    ax_hist.set_xticks(bins)
    for i in range(len(n_hist)):
        if n_hist[i] > 0:
            ax_hist.text(bins[i] + 2.5, n_hist[i], int(n_hist[i]), ha="center", va="bottom")
    st.pyplot(fig_hist)
    plt.close(fig_hist)

    # Pass vs Fail
    st.markdown(f"📊 Pass vs Fail for Year Level {year_level}")
    pass_count = df[df["Remarks"] == "Passed"].shape[0]
    fail_count = df[df["Remarks"] == "Failed"].shape[0]
    fig_pf, ax_pf = plt.subplots(figsize=(6, 4))
    bars = ax_pf.bar(["Pass", "Fail"], [pass_count, fail_count], color=["green", "red"])
    for bar in bars:
        yval = bar.get_height()
        ax_pf.text(bar.get_x() + bar.get_width() / 2, yval, int(yval), ha="center", va="bottom")
    st.pyplot(fig_pf)
    plt.close(fig_pf)

def class_report(teacher_name, db):
    """Main function to display the class report."""
    st.header("📘 Class Report")
    st.info("This report provides a detailed view of student performance in a specific subject.")

    subjects_cursor = db.subjects.find({"Teacher": teacher_name}, {"_id": 1})
    subject_list = [""] + sorted([doc["_id"] for doc in subjects_cursor])

    if len(subject_list) == 1:
        st.warning("You are not currently assigned to any subjects.")
        return

    selected_subject_code = st.selectbox("Select a Subject", subject_list, key="faculty_subject")
    if not selected_subject_code:
        return

    df_subject_grades = get_subject_data(db, teacher_name, selected_subject_code)

    if df_subject_grades.empty:
        st.warning("No grade records found for this subject under your name.")
        return

    display_class_stats(df_subject_grades)
    display_year_level_stats(df_subject_grades)

    # ---------- DOWNLOAD REPORTS ----------
    st.markdown("### 💾 Download Class Report")
    excel_bytes = generate_excel(df_subject_grades, "faculty_class_report.xlsx")
    st.download_button(
        label="⬇️ Download as Excel",
        data=excel_bytes,
        file_name=f"FacultyReport_{selected_subject_code}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
