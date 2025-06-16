# app.py
import streamlit as st
from reports import process_report, audit_report, alarm_report
import json

st.set_page_config(page_title="Reporting System", layout="wide")

def load_db_config():
    try:
        with open('db_config.json') as config_file:
            config = json.load(config_file)
            return config.get('databases', {})
    except FileNotFoundError:
        st.error("Configuration file not found")
        return {}
    except json.JSONDecodeError:
        st.error("Invalid JSON configuration")
        return {}
databases = load_db_config()


# st.title("📊 Reporting System")
col1, col2 = st.columns([1, 4])

with col1:
    st.image("alivus_logo.png", width=80)  # Adjust path and width as needed

with col2:
    st.title("📊 Reporting System")
# Fully hide Streamlit header/footer and extra elements
hide_streamlit_style = """
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .stApp > header {display: none;}
        .viewerBadge_container__1QSob {display: none;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- initialize session state for report type if not already set ---
if "report_type" not in st.session_state:
    st.session_state.report_type = None

# --- buttons in the sidebar ---
st.sidebar.header("Choose a report")
if st.sidebar.button("Process Report"):
    st.session_state.report_type = "Process Report"
if st.sidebar.button("Audit Report"):
    st.session_state.report_type = "Audit Report"
if st.sidebar.button("Alarm Report"):
    st.session_state.report_type = "Alarm Report"

# st.session_state.report_type = "Process Report"


# --- render the chosen report ---
if st.session_state.report_type == "Process Report":
    process_report.show(databases)
elif st.session_state.report_type == "Audit Report":
    audit_report.show(databases)
elif st.session_state.report_type == "Alarm Report":
    alarm_report.show(databases)
else:
    st.info("Please select a report from the sidebar.")

# report_type = st.sidebar.selectbox(
#     "Select Report Type",
#     ["Process Report", "Audit Report", "Alarm Report"]
# )

# if report_type == "Process Report":
#     process_report.show(databases)
# elif report_type == "Audit Report":
#     audit_report.show(databases)
# elif report_type == "Alarm Report":
#     alarm_report.show(databases)