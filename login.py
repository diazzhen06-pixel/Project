import streamlit as st
from helpers.user_helper import user_helper

def login(db):
    st.title("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        user_h = user_helper({'db': db})
        user = user_h.get_user(username)

        if user and user_h.verify_password(password, user['passwordHash']):
            st.session_state['logged_in'] = True
            st.session_state['username'] = user['username']
            st.session_state['role'] = user['role']
            st.success("Logged in successfully!")
            st.rerun()
        else:
            st.error("Invalid username or password")
