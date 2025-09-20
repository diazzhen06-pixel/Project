import sys
import os
import streamlit as st

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from utils.db import get_db
from utils.data_helper import load_data
from auth.login import login
from panels.registrar_panel import registrar_panel
from panels.faculty import faculty_panel
from panels.newfaculty import new_faculty_panel
from panels.student import student_panel

def main():
    """
    Main function for the Streamlit application.
    Handles session state, authentication, and navigation to different panels.
    """
    st.set_page_config(page_title="Student Grades Dashboard", layout="wide")
    st.title("MIT Faculty Portal")

    # --- Database and Data Loading ---
    db = get_db()

    # --- Session State and Authentication ---
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        login(db)
        st.stop()

    # --- Data Loading ---
    df_merged, semesters_map = load_data(db)

    # --- Logout Button ---
    if st.sidebar.button("Logout"):
        st.session_state['logged_in'] = False
        st.rerun()

    # --- Navigation ---
    role = st.session_state.get('role')
    nav_options = []
    if role == 'registrar':
        nav_options = ["Registrar"]
    elif role == 'faculty':
        nav_options = ["Faculty", "Faculty Tasks"]
    elif role == 'teacher':
        nav_options = ["Faculty"]
    elif role == 'student':
        nav_options = ["Student"]

    selected_nav = st.sidebar.radio("Navigation", nav_options) if nav_options else None

    # --- Panel Routing ---
    if selected_nav == "Registrar" and role == "registrar":
        registrar_panel(db, df_merged, semesters_map)
    elif selected_nav == "Faculty" and (role == "faculty" or role == "teacher"):
        faculty_panel(df_merged, semesters_map, db, role=st.session_state['role'], username=st.session_state['username'])
    elif selected_nav == "Faculty Tasks" and role == "faculty":
        new_faculty_panel(db)
    elif selected_nav == "Student" and role == "student":
        student_panel()
    elif selected_nav:
        st.warning("You do not have access to this page.")

if __name__ == "__main__":
    main()