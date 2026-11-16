import streamlit as st

st.set_page_config(
    page_title="Interview Practice Assistant",
    page_icon="💼",
    layout="centered",
)

from interview_app.ui import main

main()
