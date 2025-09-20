import streamlit as st
import helpers.user_helper as h
from helpers.teacher_helper import get_all_teachers

def login(db):
    st.title("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        # First, try to log in as a regular user
        user = h.get_user(db, username)

        if user and h.verify_password(password, user['passwordHash']):
            st.session_state['logged_in'] = True
            st.session_state['username'] = user['username']
            st.session_state['role'] = user['role']
            st.success("Logged in successfully!")
            st.rerun()
        else:
            # If not a regular user, check if they are a teacher
            teachers = get_all_teachers(db)
            if username in teachers and username == password:
                st.session_state['logged_in'] = True
                st.session_state['username'] = username
                st.session_state['role'] = 'teacher'
                st.success("Logged in successfully as teacher!")
                st.rerun()
            else:
                st.error("Invalid username or password")
