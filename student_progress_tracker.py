import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from helpers.utils import generate_excel

def get_trend(grades):
    """Calculates the trend based on a list of grades."""
    if not grades or len(grades) < 2:
        return "N/A"

    grades = [g for g in grades if pd.notna(g)]

    if not grades:
        return "N/A"

    # Check for high stable performance
    if all(g >= 75 for g in grades):
        return "Stable High"

    # Check for improvement
    if grades[-1] > grades[0]:
        return "Improving"

    # Check for decline
    if grades[-1] < grades[0]:
        return "Needs Attention"

    return "Stable"

def get_grade_for_subject(row, subject_code):
    """Extracts the grade for a specific subject from a row."""
    try:
        idx = row['SubjectCodes'].index(subject_code)
        return row['Grades'][idx]
    except (ValueError, IndexError, TypeError, AttributeError):
        return None

def student_progress_tracker_panel(db, subject_code, df_full, teacher_name=None, course=None, year_level=None):
    st.header("Student Progress Tracker")

    df = df_full.copy()

    # Filter by teacher if provided
    if teacher_name:
        teacher_name_clean = str(teacher_name).strip().lower()
        df = df[df['Teachers'].apply(
            lambda lst: teacher_name_clean in [t.strip().lower() for t in lst] if isinstance(lst, list) else False
        )]

    # Filter by course/year level if provided
    if course:
        df = df[df['Course'] == course]
    if year_level:
        df = df[df['YearLevel'] == year_level]

    # Filter for the selected subject
    df_subject = df[df['SubjectCodes'].apply(lambda x: subject_code in x if isinstance(x, list) else False)].copy()
    if df_subject.empty:
        st.warning("No students found for the selected subject and teacher.")
        return

    # Extract grades for the selected subject
    df_subject['Grade'] = df_subject.apply(lambda row: get_grade_for_subject(row, subject_code), axis=1)

    # Convert grades to numeric safely
    df_subject['Grade'] = pd.to_numeric(df_subject['Grade'], errors='coerce')

    # Merge semester info
    semesters_df = pd.DataFrame(list(db.semesters.find({}, {"_id": 1, "Semester": 1})))
    semesters_df.rename(columns={'_id': 'SemesterID'}, inplace=True)
    df_subject = pd.merge(df_subject, semesters_df, on='SemesterID', how='left')

    if 'Semester' not in df_subject.columns:
        st.error("Semester information is missing.")
        return

    # Pivot table safely
    pivot_df = df_subject.pivot_table(
        index=['StudentID', 'Name', 'Course', 'YearLevel'],
        columns='Semester',
        values='Grade',
        aggfunc='mean'  # ignores NaN automatically
    ).reset_index()

    # Standardize semester column names
    rename_map = {
        '1st Sem': 'FirstSem',
        'First': 'FirstSem',
        '2nd Sem': 'SecondSem',
        'Second': 'SecondSem',
    }
    pivot_df.rename(columns={k: v for k, v in rename_map.items() if k in pivot_df.columns}, inplace=True)
    pivot_df.rename(columns={'StudentID': 'Student ID'}, inplace=True)

    # Ensure all semester columns exist
    sem_cols = ['FirstSem', 'SecondSem', 'Summer']
    for col in sem_cols:
        if col not in pivot_df.columns:
            pivot_df[col] = None

    # Calculate Overall Trend
    pivot_df['Overall Trend'] = pivot_df.apply(
        lambda row: get_trend([row[col] for col in sem_cols if pd.notna(row[col])]),
        axis=1
    )

    # Display table
    st.dataframe(
        pivot_df[['Student ID', 'Name', 'Course', 'YearLevel', 'FirstSem', 'SecondSem', 'Summer', 'Overall Trend']].fillna('N/A')
    )

    # ---------- DOWNLOAD REPORT ----------
    st.markdown("### 💾 Download Report")
    excel_bytes = generate_excel(pivot_df, "student_progress_report.xlsx")
    st.download_button(
        label="⬇️ Download as Excel",
        data=excel_bytes,
        file_name="student_progress_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # Chart
    st.subheader("Performance Chart")
    if not pivot_df.empty:
        student_options = pivot_df['Name'].tolist()
        selected_student_name = st.selectbox("Select Student to Visualize", options=student_options, key="spt_student_viz")
        if selected_student_name:
            student_data = pivot_df[pivot_df['Name'] == selected_student_name].iloc[0]
            chart_data = {'Semester': sem_cols, 'Grade': [student_data[col] for col in sem_cols]}
            chart_df = pd.DataFrame(chart_data).dropna()
            if not chart_df.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=chart_df['Semester'],
                    y=chart_df['Grade'],
                    mode='lines+markers',
                    name=selected_student_name
                ))
                fig.update_layout(title=f"Performance for {selected_student_name}",
                                  xaxis_title="Semester",
                                  yaxis_title="Grade")
                st.plotly_chart(fig)
            else:
                st.warning(f"No grade data available for {selected_student_name} to plot.")
    else:
        st.warning("No data available to display chart.")
