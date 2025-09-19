
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from helpers.utils import generate_excel

def get_trend(grades):
    """Calculates the trend based on a list of grades."""
    if not grades or len(grades) < 2:
        return "N/A"

    # Check for high stable performance
    if all(g >= 75 for g in grades if pd.notna(g)):
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
        # Find the index of the subject code
        idx = row['SubjectCodes'].index(subject_code)
        # Return the grade at the same index
        return row['Grades'][idx]
    except (ValueError, IndexError, TypeError):
        # Handle cases where subject_code is not found or lists are malformed
        return None

def student_progress_tracker_panel(db, subject_code, df_full, teacher_name=None, course=None, year_level=None):
    st.header("Student Progress Tracker")

    # Filter by teacher if provided
    if teacher_name:
        teacher_name_clean = str(teacher_name).strip().lower()
        df_full = df_full[df_full['Teachers'].apply(
            lambda lst: teacher_name_clean in [t.strip().lower() for t in lst] if isinstance(lst, list) else False
        )]

    # Filter by course if provided
    if course:
        df_full = df_full[df_full['Course'] == course]

    # Filter by year level if provided
    if year_level:
        df_full = df_full[df_full['YearLevel'] == year_level]

    # Filter the full dataframe for the selected subject
    df_subject = df_full[df_full['SubjectCodes'].apply(lambda x: subject_code in x if isinstance(x, list) else False)].copy()

    if df_subject.empty:
        st.warning("No students found for the selected subject and teacher.")
        return

    # rest of your code remains the same...


    df_subject['Grade'] = df_subject.apply(lambda row: get_grade_for_subject(row, subject_code), axis=1)

    # We need to get the semester for each grade.
    # We can join with the semesters table, but the semester is already in the df_full from app.py
    # Let's get the semester from the SemesterID
    semesters_df = pd.DataFrame(list(db.semesters.find({}, {"_id": 1, "Semester": 1})))
    semesters_df.rename(columns={'_id': 'SemesterID'}, inplace=True)
    df_subject = pd.merge(df_subject, semesters_df, on='SemesterID', how='left')


    if 'Semester' not in df_subject.columns:
        st.error("Semester information is missing.")
        return

    # Pivot table to get semesters as columns
    pivot_df = df_subject.pivot_table(index=['StudentID', 'Name', 'Course', 'YearLevel'], columns='Semester', values='Grade').reset_index()

    # Standardize semester column names
    rename_map = {
        '1st Sem': 'FirstSem',
        'First': 'FirstSem',
        '2nd Sem': 'SecondSem',
        'Second': 'SecondSem',
    }
    pivot_df.rename(columns={k: v for k, v in rename_map.items() if k in pivot_df.columns}, inplace=True)
    if 'StudentID' in pivot_df.columns:
        pivot_df.rename(columns={'StudentID': 'Student ID'}, inplace=True)

    # Define semester columns with standard names
    sem_cols = ['FirstSem', 'SecondSem', 'Summer']
    for col in sem_cols:
        if col not in pivot_df.columns:
            pivot_df[col] = None

    # Calculate Overall Trend
    trends = []
    for _, row in pivot_df.iterrows():
        grades = [row[col] for col in sem_cols if pd.notna(row[col])]
        trends.append(get_trend(grades))
    pivot_df['Overall Trend'] = trends

    # Display table
    st.dataframe(pivot_df[['Student ID', 'Name', 'Course', 'YearLevel', 'FirstSem', 'SecondSem', 'Summer', 'Overall Trend']].fillna('N/A'))

    # ---------- DOWNLOAD REPORTS ----------
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
        # Let user select a student from the filtered list
        student_options = pivot_df['Name'].tolist()
        selected_student_name = st.selectbox("Select Student to Visualize", options=student_options, key="spt_student_viz")

        if selected_student_name:
            student_data = pivot_df[pivot_df['Name'] == selected_student_name].iloc[0]

            # Prepare data for chart
            chart_data = {
                'Semester': ['FirstSem', 'SecondSem', 'Summer'],
                'Grade': [student_data['FirstSem'], student_data['SecondSem'], student_data['Summer']]
            }
            chart_df = pd.DataFrame(chart_data).dropna()

            if not chart_df.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=chart_df['Semester'],
                    y=chart_df['Grade'],
                    mode='lines+markers',
                    name=selected_student_name
                ))
                fig.update_layout(
                    title=f"Performance for {selected_student_name}",
                    xaxis_title="Semester",
                    yaxis_title="Average Grade"
                )
                st.plotly_chart(fig)

            else:
                st.warning(f"No grade data available for {selected_student_name} to plot.")
    else:
        st.warning("No data available to display chart.")
