import streamlit as st
import pandas as pd
from helpers import faculty_helper

def assign_teacher_to_subject_ui(db):
    st.subheader("Assign Teacher to Subject")

    subjects = faculty_helper.get_all_subjects(db)
    if subjects.empty:
        st.warning("No subjects found.")
        return

    subject_list = subjects['_id'].tolist()
    selected_subject = st.selectbox("Select Subject", [""] + subject_list)

    teachers = faculty_helper.get_all_teachers(db)
    if not teachers:
        st.warning("No teachers found.")
        return

    teacher_list = sorted(list(set(teachers)))
    selected_teacher = st.selectbox("Select Teacher", [""] + teacher_list)

    if st.button("Assign Teacher"):
        if selected_subject and selected_teacher:
            success = faculty_helper.update_subject_teacher(db, selected_subject, selected_teacher)
            if success:
                st.success(f"Successfully assigned {selected_teacher} to {selected_subject}")
            else:
                st.error("Failed to assign teacher.")
        else:
            st.warning("Please select a subject and a teacher.")


def view_students_in_subject_ui(db):
    st.subheader("View Students in Subject")

    subjects = faculty_helper.get_all_subjects(db)
    if subjects.empty:
        st.warning("No subjects found.")
        return

    subject_list = subjects['_id'].tolist()
    selected_subject = st.selectbox("Select Subject", [""] + subject_list)

    if selected_subject:
        students = faculty_helper.get_students_in_subject(db, selected_subject)
        if not students:
            st.info(f"No students enrolled in {selected_subject}")
            return

        st.dataframe(pd.DataFrame(students))


def new_faculty_panel(db):
    st.title("Faculty Tasks")

    menu = ["Assign Teacher to Subject", "View Students in Subject"]
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Assign Teacher to Subject":
        assign_teacher_to_subject_ui(db)
    elif choice == "View Students in Subject":
        view_students_in_subject_ui(db)
