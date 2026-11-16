import streamlit as st

st.set_page_config(
    page_title="Interview Practice",
    page_icon="interview_app/brand/mark.png",
    layout="centered",
    initial_sidebar_state="expanded",
)

from interview_app.ui import main

main()
