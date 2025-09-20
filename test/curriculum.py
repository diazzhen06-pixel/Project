import os
import pandas as pd
import streamlit as st
from pymongo import MongoClient
from dotenv import load_dotenv

# ----------------- CURRICULUM DB CONNECTION -----------------
@st.cache_resource
def get_curriculum_db():
    """Connect to the curriculum MongoDB and return the database."""
    load_dotenv()
    username = os.getenv("CURR_USER", "Cluster11861")
    password = os.getenv("CURR_PASS", "fWAZMMp4WFL7lyts")
    try:
        uri = f"mongodb+srv://{username}:{password}@cluster0.l7fdbmf.mongodb.net/mit261"
        client = MongoClient(uri)
        return client["mit261"]
    except Exception as e:
        st.error(f"❌ Curriculum database connection failed: {e}")
        return None

# ----------------- CURRICULUM OVERVIEW -----------------
def display_curriculum_overview(curriculum_col):
    """Display the full curriculum as a table."""
    if curriculum_col is None:
        st.error("❌ Curriculum collection is not available.")
        return

    st.markdown("### 🎓 Curriculum Overview")
    curr_data = list(curriculum_col.find())
    
    if not curr_data:
        st.warning("⚠️ No curriculum data found.")
        return

    # Flatten subjects for table display
    subjects_list = []
    for cur in curr_data:
        for subj in cur.get("subjects", []):
            subjects_list.append({
                "Year": subj.get("year", "N/A"),
                "Semester": subj.get("semester", "N/A"),
                "Code": subj.get("code", "N/A"),
                "Name": subj.get("name", "N/A"),
                "Units": subj.get("unit", "N/A"),
                "PreRequisites": ", ".join(subj.get("preRequisites", [])) if subj.get("preRequisites") else ""
            })

    if subjects_list:
        df = pd.DataFrame(subjects_list)
        df.sort_values(by=["Year", "Semester"], inplace=True)
        st.dataframe(df, hide_index=True)
    else:
        st.info("⚠️ No subjects available in the curriculum.")

# ----------------- PREDICTIVE RECOMMENDATIONS -----------------
def display_recommendations(df_academic, current_year, current_semester, curriculum_col):
    """
    Recommend subjects for the next semester based on curriculum and past failures.
    df_academic: DataFrame containing student academic records with 'SubjectCode' and 'FinalGrade'.
    """
    if curriculum_col is None:
        st.error("❌ Curriculum collection is not available.")
        return

    st.markdown("### 📌 Recommended Subjects")

    curr_data = list(curriculum_col.find())
    if not curr_data:
        st.warning("⚠️ Curriculum not found.")
        return

    # Flatten curriculum subjects
    curriculum_subjects = []
    for cur in curr_data:
        for subj in cur.get("subjects", []):
            curriculum_subjects.append(subj)

    # Identify failed subjects
    if "FinalGrade" in df_academic.columns and "SubjectCode" in df_academic.columns:
        failed_codes = df_academic[df_academic["FinalGrade"] < 75]["SubjectCode"].tolist()
    else:
        failed_codes = []

    recommendations = []
    for subj in curriculum_subjects:
        # Determine next semester
        next_year = current_year
        next_sem = "First" if current_semester == "Second" else "Second"
        if current_semester == "Second":
            next_year += 1

        # Retake failed subjects
        if subj.get("code") in failed_codes:
            recommendations.append((subj, "🔄 Retake"))
            continue

        # Check next semester eligibility
        if subj.get("year") == next_year and subj.get("semester") == next_sem:
            blocked = any(pre in failed_codes for pre in subj.get("preRequisites", []))
            recommendations.append((subj, "⛔ Blocked" if blocked else "✅ Allowed"))

    # Display recommendations
    if recommendations:
        df_rec = pd.DataFrame([{
            "Code": s.get("code", "N/A"),
            "Name": s.get("name", "N/A"),
            "Year": s.get("year", "N/A"),
            "Semester": s.get("semester", "N/A"),
            "Units": s.get("unit", "N/A"),
            "Status": status
        } for s, status in recommendations])
        st.dataframe(df_rec, hide_index=True)
    else:
        st.info("✅ No recommended subjects available.")
