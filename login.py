import streamlit as st
import helpers.user_helper as h

def login(db):
    st.title("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
       
        user = h.get_user(db,username)

        if user and h.verify_password(password, user['passwordHash']):
            st.session_state['logged_in'] = True
            st.session_state['username'] = user['username']
            st.session_state['role'] = user['role']
            st.success("Logged in successfully!")
            st.rerun()
        else:
            st.error("Invalid username or password")
