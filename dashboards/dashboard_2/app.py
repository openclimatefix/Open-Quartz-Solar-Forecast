import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timezone
import os
import requests
from PIL import Image
from dotenv import load_dotenv

from quartz_solar_forecast.pydantic_models import PVSite

# Load environment variables
load_dotenv()

if 'enphase_access_token' not in st.session_state:
    st.session_state.enphase_access_token = None
if 'enphase_system_id' not in st.session_state:
    st.session_state.enphase_system_id = None
if 'redirect_url' not in st.session_state:
    st.session_state.redirect_url = ""

# Set up the base URL for the FastAPI server
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL")

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the path to logo.png
logo_path = os.path.join(script_dir, "logo.png")
im = Image.open(logo_path)

st.set_page_config(
    page_title="Open Source Quartz Solar Forecast | Open Climate Fix",
    layout="wide",
    page_icon=im,
)
st.title("☀️ Open Source Quartz Solar Forecast")

def make_api_request(endpoint, method="GET", data=None):
    try:
        url = f"{FASTAPI_BASE_URL}{endpoint}"
        if method == "GET":
            response = requests.get(url)
        elif method == "POST":
            response = requests.post(url, json=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"API request error: {e}")
        return None

# Main app logic
st.sidebar.header("PV Site Configuration")

use_defaults = st.sidebar.checkbox("Use Default Values", value=True)

if use_defaults:
    latitude = 51.75
    longitude = -1.25
    capacity_kwp = 1.25
    st.sidebar.text(f"Default Latitude: {latitude}")
    st.sidebar.text(f"Default Longitude: {longitude}")
    st.sidebar.text(f"Default Capacity (kWp): {capacity_kwp}")
else:
    latitude = st.sidebar.number_input("Latitude", min_value=-90.0, max_value=90.0, value=51.75, step=0.01)
    longitude = st.sidebar.number_input("Longitude", min_value=-180.0, max_value=180.0, value=-1.25, step=0.01)
    capacity_kwp = st.sidebar.number_input("Capacity (kWp)", min_value=0.1, value=1.25, step=0.01)

inverter_type = st.sidebar.selectbox("Select Inverter", ["No Inverter", "Enphase", "Solis", "GivEnergy", "Solarman"])

if inverter_type == "Enphase" and not st.session_state.enphase_access_token:
    auth_url_response = make_api_request("/solar_inverters/enphase/auth_url")
    if auth_url_response:
        auth_url = auth_url_response["auth_url"]
        st.write("Please visit the following URL to authorize the application:")
        st.markdown(f"[Enphase Authorization URL]({auth_url})")
        st.write("After authorization, you will be redirected to a URL. Please copy the entire URL and paste it below:")
        
        st.session_state.redirect_url = st.text_input("Enter the redirect URL:", value=st.session_state.redirect_url)

if st.sidebar.button("Run Forecast"):
    if inverter_type == "Enphase":
        if not st.session_state.enphase_access_token or not st.session_state.enphase_system_id:
            if not st.session_state.redirect_url:
                st.error("Please enter the redirect URL to complete Enphase authorization.")
                st.stop()
            elif "?code=" not in st.session_state.redirect_url:
                st.error("Invalid redirect URL. Please make sure you copied the entire URL.")
                st.stop()
            else:
                try:
                    token_response = make_api_request("/solar_inverters/enphase/token_and_id", method="POST", data={"redirect_url": st.session_state.redirect_url})
                    if token_response:
                        st.session_state.enphase_access_token = token_response["access_token"]
                        st.session_state.enphase_system_id = token_response["enphase_system_id"]
                        st.success("Enphase authorization successful!")
                    else:
                        st.error("Failed to obtain Enphase access token and system ID.")
                        st.stop()
                except Exception as e:
                    st.error(f"Error getting access token: {str(e)}")
                    st.stop()
        else:
            st.success("Using existing Enphase authorization.")
    
    site = PVSite(
        latitude=latitude,
        longitude=longitude,
        capacity_kwp=capacity_kwp,
        inverter_type=inverter_type.lower() if inverter_type != "No Inverter" else ""
    )

    data = {
        "site": site.dict(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    forecast_data = make_api_request("/forecast/", method="POST", data=data)

    if forecast_data:
        st.success("Forecast completed successfully!")

        # Display current timestamp
        st.subheader(f"Forecast generated at: {forecast_data['timestamp']}")

        # Create three columns
        col1, col2, col3 = st.columns(3)

        predictions = pd.DataFrame(forecast_data['predictions'])
        
        # Ensure 'index' column exists and is of datetime type
        if 'index' not in predictions.columns:
            predictions['index'] = pd.to_datetime(predictions.index)
        else:
            predictions['index'] = pd.to_datetime(predictions['index'])
        
        predictions.set_index('index', inplace=True)

        # Plotting logic
        if inverter_type == "No Inverter":
            if 'power_kw' in predictions.columns:
                fig = px.line(
                    predictions.reset_index(),
                    x="index",
                    y="power_kw",
                    title="Forecasted Power Generation (No Inverter)",
                    labels={
                        "power_kw": "Forecast",
                        "index": "Time"
                    }
                )
            else:
                st.error("Expected column 'power_kw' not found in the data for No Inverter scenario.")
                st.stop()
        else:
            if 'power_kw' in predictions.columns and 'power_kw_no_live_pv' in predictions.columns:
                fig = px.line(
                    predictions.reset_index(),
                    x="index",
                    y=["power_kw", "power_kw_no_live_pv"],
                    title="Forecasted Power Generation",
                    labels={
                        "power_kw": f"Forecast with {inverter_type} data",
                        "power_kw_no_live_pv": "Forecast without live data",
                        "index": "Time"
                    }
                )
            else:
                st.error("Expected columns 'power_kw' and 'power_kw_no_live_pv' not found in the data for Inverter scenario.")
                st.stop()

        fig.update_layout(
            xaxis_title="Time",
            yaxis_title="Power (kW)",
            legend_title="Forecast Type",
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01
            )
        )

        st.plotly_chart(fig, use_container_width=True)

        # Display raw data
        st.subheader("Raw Forecast Data")
        st.dataframe(predictions, use_container_width=True)
    else:
        st.error("No forecast data available. Please check your inputs and try again.")