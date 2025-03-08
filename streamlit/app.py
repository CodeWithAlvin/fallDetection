# app.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import bcrypt
import os
from datetime import datetime, timedelta
import pymongo
from pymongo import MongoClient
from dotenv import load_dotenv
import json
import requests
from pathlib import Path
import re
import google.generativeai as genai

# Page configuration
st.set_page_config(
    page_title="Fall Detection Dashboard",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load environment variables
load_dotenv()

# MongoDB Connection
@st.cache_resource
def init_connection():
    mongo_uri = os.getenv("MONGO_URI")
    client = MongoClient(mongo_uri)
    return client

client = init_connection()
db = client[os.getenv("DB_NAME")]
fall_collection = db[os.getenv("COLLECTION_NAME")]
user_collection = db["users"]
patient_collection = db["patients"]


class LanguageModel:
    def __init__(self, model_name, system_instruction, api_key):
        self.model_name = model_name
        self.system_instruction = system_instruction

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=self.system_instruction
        )

    def generate_content(self, text):
        response = self.model.generate_content(text)
        return response.text


# Authentication functions
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_user(username, password, email, role="caretaker"):
    # Check if username already exists
    if user_collection.find_one({"username": username}):
        return False
    
    hashed_password = hash_password(password)
    user = {
        "username": username,
        "password": hashed_password,
        "email": email,
        "role": role,
        "created_at": datetime.now()
    }
    user_collection.insert_one(user)
    return True

# Login and Registration Pages
def login_page():
    st.title("Fall Detection Monitoring System")
    st.subheader("Login")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")
        
        if submit_button:
            user = user_collection.find_one({"username": username})
            if user and check_password(password, user["password"]):
                st.session_state["authenticated"] = True
                st.session_state["username"] = username
                st.session_state["role"] = user["role"]
                st.success("Login successful!")
                st.session_state["page"] = "dahsboard"
                
            else:
                st.error("Invalid username or password")
    
    if st.button("Register a new account"):
        st.session_state["page"] = "register"

def register_page():
    st.title("Fall Detection Monitoring System")
    st.subheader("Register")
    
    with st.form("register_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        email = st.text_input("Email")
        submit_button = st.form_submit_button("Register")
        
        if submit_button:
            if not username or not password:
                st.error("Username and password are required")
            elif password != confirm_password:
                st.error("Passwords do not match")
            elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                st.error("Invalid email format")
            else:
                if create_user(username, password, email):
                    st.success("Registration successful! Please login.")
                    st.session_state["page"] = "login"
                    
                else:
                    st.error("Username already exists")
    
    if st.button("Back to Login"):
        st.session_state["page"] = "login"
        

# Dashboard functions
def get_fall_data(days=30, device_id=None):
    query = {}
    if device_id:
        query["device_id"] = device_id
    
    if days:
        start_date = datetime.now() - timedelta(days=days)
        query["timestamp"] = {"$gte": start_date}
    
    cursor = fall_collection.find(query)
    data = list(cursor)
    return pd.DataFrame(data) if data else pd.DataFrame()

def get_patient_info(device_id):
    patient = patient_collection.find_one({"device_id": device_id})
    return patient

def save_patient_info(patient_data):
    # Check if patient with this device_id already exists
    existing = patient_collection.find_one({"device_id": patient_data["device_id"]})
    
    if existing:
        patient_collection.update_one(
            {"_id": existing["_id"]},
            {"$set": patient_data}
        )
        return "Patient information updated successfully"
    else:
        patient_data["created_at"] = datetime.now()
        patient_collection.insert_one(patient_data)
        return "New patient added successfully"

def get_all_patients():
    cursor = patient_collection.find({})
    patients = list(cursor)
    return patients

# Dashboard UI
def main_dashboard():
    st.title("Fall Detection Monitoring Dashboard")
    
    # Sidebar for navigation and patient selection
    with st.sidebar:
        st.header(f"Welcome, {st.session_state['username']}")
        
        # Navigation
        page = st.radio("Navigation", ["Dashboard", "Patient Management", "Settings"])
        
        # Patient selection
        st.subheader("Select Patient")
        patients = get_all_patients()
        patient_options = ["All Patients"] + [f"{p['name']} ({p['device_id']})" for p in patients]
        selected_patient = st.selectbox("Choose patient", patient_options)
        
        # Time range selection
        st.subheader("Time Range")
        days = st.slider("Show data for last n days", 1, 90, 30)
        
        # Logout button
        if st.button("Logout"):
            st.session_state["authenticated"] = False
            
    
    # Extract device_id from selection
    selected_device_id = None
    if selected_patient != "All Patients":
        selected_device_id = selected_patient.split("(")[1].split(")")[0]
    
    # Main content based on navigation
    if page == "Dashboard":
        show_dashboard(days, selected_device_id)
    elif page == "Patient Management":
        show_patient_management(selected_device_id)
    elif page == "Settings":
        show_settings()

def show_dashboard(days, device_id=None):
    st.header("Fall Detection Events")
    
    # Get data
    df = get_fall_data(days, device_id)
    
    if df.empty:
        st.info("No fall detection data available for the selected criteria.")
        return
    
    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Events", len(df))
    
    with col2:
        if "detection" in df.columns:
            fall_count = df[df["detection"] == True].shape[0]
            st.metric("Fall Events", fall_count)
        else:
            st.metric("Fall Events", "N/A")
    
    with col3:
        if "alert_type" in df.columns:
            real_alerts = df[df["alert_type"] == "real alert"].shape[0]
            st.metric("Real Alerts", real_alerts)
        else:
            st.metric("Real Alerts", "N/A")
    
    with col4:
        if "sms_sent" in df.columns:
            sms_sent = df[df["sms_sent"] == "Yes"].shape[0]
            st.metric("SMS Notifications", sms_sent)
        else:
            st.metric("SMS Notifications", "N/A")
    
    # Distribution of alert types
    if "alert_type" in df.columns:
        st.subheader("Alert Type Distribution")
        alert_counts = df["alert_type"].value_counts().reset_index()
        alert_counts.columns = ["Alert Type", "Count"]
        
        fig = px.pie(alert_counts, values="Count", names="Alert Type", 
                    title="Distribution of Alert Types",
                    hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
    
    # Recent events table
    st.subheader("Recent Events")
    # Format the timestamp for display
    if not df.empty and "timestamp" in df.columns:
        df_display = df.copy()
        df_display = df_display.drop(columns=["_id","timestamp","detection"])
        print(df_display.columns)
        # columns_to_display = [col for col in df_display.columns if col != "_id"]
        st.dataframe(df_display.head(10), use_container_width=True)
    
    # Patient information if a specific patient is selected
    if device_id:
        patient_info = get_patient_info(device_id)
        if patient_info:
            st.subheader(f"Patient Information: {patient_info.get('name', 'Unknown')}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Age:** {patient_info.get('age', 'N/A')}")
                st.write(f"**Gender:** {patient_info.get('gender', 'N/A')}")
                st.write(f"**Device ID:** {patient_info.get('device_id', 'N/A')}")
            
            with col2:
                st.write(f"**Emergency Contact:** {patient_info.get('emergency_contact', 'N/A')}")
                st.write(f"**Medical Conditions:** {patient_info.get('medical_conditions', 'N/A')}")
                st.write(f"**Mobility Aids:** {patient_info.get('mobility_aids', 'N/A')}")
            

def show_patient_management(selected_device_id=None):
    st.header("Patient Management")
    
    # Tabs for different functions
    tab1, tab2 = st.tabs(["Edit Patient", "Add New Patient"])
    
    # Edit Patient
    with tab1:
        patient_to_edit = None
        
        # If a device_id is passed, select that patient automatically
        if selected_device_id:
            patient_to_edit = get_patient_info(selected_device_id)
        else:
            # Otherwise, let the user select from a dropdown
            patients = get_all_patients()
            if patients:
                patient_options = [f"{p['name']} ({p['device_id']})" for p in patients]
                selected = st.selectbox("Select patient to edit", patient_options)
                device_id = selected.split("(")[1].split(")")[0]
                patient_to_edit = get_patient_info(device_id)
            else:
                st.info("No patients in the database. Add a new patient first.")
        
        if patient_to_edit:
            with st.form("edit_patient_form"):
                st.subheader(f"Edit Patient: {patient_to_edit.get('name', '')}")
                
                name = st.text_input("Full Name", value=patient_to_edit.get("name", ""))
                age = st.number_input("Age", min_value=0, max_value=120, value=int(patient_to_edit.get("age", 0)))
                gender = st.selectbox("Gender", ["Male", "Female", "Other"], index=["Male", "Female", "Other"].index(patient_to_edit.get("gender", "Other")))
                device_id = st.text_input("Device ID", value=patient_to_edit.get("device_id", ""), disabled=True)
                emergency_contact = st.text_input("Emergency Contact", value=patient_to_edit.get("emergency_contact", ""))
                medical_conditions = st.text_area("Medical Conditions", value=patient_to_edit.get("medical_conditions", ""))
                mobility_aids = st.text_input("Mobility Aids", value=patient_to_edit.get("mobility_aids", ""))
                notes = st.text_area("Additional Notes", value=patient_to_edit.get("notes", ""))
                
                submit = st.form_submit_button("Update Patient Information")
                
                if submit:
                    patient_data = {
                        "name": name,
                        "age": age,
                        "gender": gender,
                        "device_id": device_id,
                        "emergency_contact": emergency_contact,
                        "medical_conditions": medical_conditions,
                        "mobility_aids": mobility_aids,
                        "notes": notes,
                        "updated_at": datetime.now()
                    }
                    
                    result = save_patient_info(patient_data)
                    st.success(result)
    
    # Add New Patient
    with tab2:
        with st.form("add_patient_form"):
            st.subheader("Add New Patient")
            
            name = st.text_input("Full Name")
            age = st.number_input("Age", min_value=0, max_value=120, value=0)
            gender = st.selectbox("Gender", ["Male", "Female", "Other"])
            device_id = st.text_input("Device ID")
            emergency_contact = st.text_input("Emergency Contact")
            medical_conditions = st.text_area("Medical Conditions")
            mobility_aids = st.text_input("Mobility Aids")
            notes = st.text_area("Additional Notes")
            
            submit = st.form_submit_button("Add New Patient")
            
            if submit:
                if not name or not device_id:
                    st.error("Name and Device ID are required fields")
                else:
                    patient_data = {
                        "name": name,
                        "age": age,
                        "gender": gender,
                        "device_id": device_id,
                        "emergency_contact": emergency_contact,
                        "medical_conditions": medical_conditions,
                        "mobility_aids": mobility_aids,
                        "notes": notes,
                        "created_at": datetime.now()
                    }
                    
                    result = save_patient_info(patient_data)
                    st.success(result)

def show_settings():
    st.header("Settings")
    
    # Account settings
    st.subheader("Account Settings")
    user = user_collection.find_one({"username": st.session_state["username"]})
    
    if user:
        with st.form("account_settings"):
            email = st.text_input("Email", value=user.get("email", ""))
            
            col1, col2 = st.columns(2)
            with col1:
                password = st.text_input("New Password (leave blank to keep current)", type="password")
            with col2:
                confirm_password = st.text_input("Confirm New Password", type="password")
            
            submit = st.form_submit_button("Update Settings")
            
            if submit:
                updates = {"email": email}
                
                if password:
                    if password != confirm_password:
                        st.error("Passwords do not match")
                    else:
                        updates["password"] = hash_password(password)
                
                user_collection.update_one(
                    {"_id": user["_id"]},
                    {"$set": updates}
                )
                st.success("Settings updated successfully")
    
    # Notification settings
    st.subheader("Notification Settings")
    
    with st.form("notification_settings"):
        email_notifications = st.checkbox("Email Notifications")
        sms_notifications = st.checkbox("SMS Notifications")
        
        st.form_submit_button("Save Notification Settings")
    
    # About section
    st.subheader("About")
    st.write("Fall Detection Monitoring Dashboard v1.0")
    st.write("This application helps caretakers monitor fall detection events for elderly patients.")
    st.write("© 2025 Fall Detection Monitoring System")

# Initialize session states
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if "page" not in st.session_state:
    st.session_state["page"] = "login"

# Main app logic
if not st.session_state["authenticated"]:
    if st.session_state["page"] == "login":
        login_page()
    elif st.session_state["page"] == "register":
        register_page()
else:
    main_dashboard()