import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from ..reports.student_progress_tracker import student_progress_tracker_panel

def registrar_panel(db, df_merged, semesters_map):
    """
    Displays the registrar's dashboard, including semester/subject filters,
    statistics, student lists, and various charts.
    """
    st.header("Registrar Dashboard")

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
            st.markdown(
                f"""
                <div style="
                    border: 2px solid #4CAF50;
                    padding: 16px;
                    border-radius: 10px;
                    background-color: #000000;
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    margin-bottom: 20px;
                    color: white;
                ">
                    <strong>🗓️ Semester:</strong> {selected_semester}<br>
                    <strong>📚 Subject:</strong> {selected_subject} - {subject_description}<br>
                    <strong>👥 Total Enrolled:</strong> {total_enrolled}<br>
                    <strong>📊 Total Students This Semester:</strong> {total_students_sem}<br>
                    <strong>🎓 School Year:</strong> {school_year_str}<br>
                    <strong>👩‍🏫 Teacher(s):</strong> {teachers_str}<br>
                    <strong>📈 General Percentile Average (GPA):</strong> {gpa_value if gpa_value is not None else "N/A"}<br>
                    <strong>⬆️ Students Above GPA:</strong> {above_count if above_count is not None else "N/A"}<br>
                    <strong>⬇️ Students Below GPA:</strong> {below_count if below_count is not None else "N/A"}
                </div>
                """,
                unsafe_allow_html=True,
            )

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

            # ----------------- HISTOGRAM -----------------
            st.markdown("### Grade Distribution Histogram")
            fig_hist = px.histogram(
                filtered,
                x="Grade",
                title=f"Grade Distribution for {selected_subject}",
                nbins=20,
                template="plotly_dark"
            )
            fig_hist.update_layout(
                xaxis_title="Grade",
                yaxis_title="Number of Students",
                bargap=0.1
            )
            st.plotly_chart(fig_hist, use_container_width=True)

            # ----------------- STUDENT PROGRESS TRACKER -----------------
            with st.expander("Show Student Progress Tracker"):
                student_progress_tracker_panel(db, selected_subject, df_merged)
