import os

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

st.set_page_config(
    page_title="Interview Practice Assistant",
    page_icon="💼",
)

st.title("💼 Interview Practice Assistant")
st.caption("Create short, natural answers based on your experience and the job.")

if not api_key:
    st.error("OPENAI_API_KEY was not found in your .env file.")
    st.stop()

client = OpenAI(api_key=api_key)

if "messages" not in st.session_state:
    st.session_state.messages = []

if "job_description" not in st.session_state:
    st.session_state.job_description = ""

if "candidate_background" not in st.session_state:
    st.session_state.candidate_background = ""

with st.sidebar:
    st.header("Interview setup")

    job_description = st.text_area(
        "Job description",
        value=st.session_state.job_description,
        height=250,
        placeholder="Paste the job description here...",
    )

    candidate_background = st.text_area(
        "Your résumé or professional background",
        value=st.session_state.candidate_background,
        height=250,
        placeholder=(
            "Paste your résumé, experience, education, skills, "
            "accomplishments and certifications here..."
        ),
    )

    if st.button("Start interview", use_container_width=True):
        if not job_description.strip():
            st.warning("Please enter a job description.")
        elif not candidate_background.strip():
            st.warning("Please enter your résumé or professional background.")
        else:
            st.session_state.job_description = job_description.strip()
            st.session_state.candidate_background = candidate_background.strip()
            st.session_state.messages = []
            st.success("Interview information saved.")

    if st.button("Reset conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

if not st.session_state.job_description:
    st.info("Add the job description and your background in the sidebar.")
    st.stop()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

question = st.chat_input("Type an interview question...")

if question:
    st.session_state.messages.append(
        {"role": "user", "content": question}
    )

    with st.chat_message("user"):
        st.markdown(question)

    recent_conversation = "\n\n".join(
        f"{message['role'].upper()}: {message['content']}"
        for message in st.session_state.messages[-8:]
    )

    instructions = f"""
You are an interview-practice assistant.

JOB DESCRIPTION:
{st.session_state.job_description}

CANDIDATE BACKGROUND:
{st.session_state.candidate_background}

Write a complete answer that the candidate can speak during an interview.

Requirements:
- Answer in first person as the candidate.
- Use only facts supported by the candidate background.
- Do not use brackets, blanks, placeholders or customization suggestions.
- Do not add headings or bullet points.
- Keep ordinary answers between 70 and 110 words.
- Keep simple questions under 80 words.
- Use natural, conversational language.
- For "Tell me about yourself," summarize the candidate's current background,
  strongest relevant experience and interest in this position.
- Answer only the interview question.
"""

    try:
        with st.chat_message("assistant"):
            with st.spinner("Preparing a short answer..."):
                response = client.responses.create(
                    model="gpt-5.6-luna",
                    instructions=instructions,
                    input=recent_conversation,
                )

                answer = response.output_text
                st.markdown(answer)

        st.session_state.messages.append(
            {"role": "assistant", "content": answer}
        )

    except Exception as error:
        st.error(f"OpenAI API request failed: {error}")