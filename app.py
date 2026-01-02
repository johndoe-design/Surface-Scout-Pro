import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
import fiona
import zipfile
import os
import shutil

# KML Support
fiona.drvsupport.supported_drivers['KML'] = 'rw'

st.set_page_config(page_title="Infrastruktur-Analyse PRO", layout="wide")

# API Key Check
if "GOOGLE_API_KEY" not in st.secrets:
    st.error("🔑 API Key fehlt in den Secrets!")
    st.stop()
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]

st.title("🚧 Infrastruktur-Analyse: Profi-Check")

# --- SIDEBAR ---
st.sidebar.header("📁 Projekt-Daten")
uploaded_file = st.sidebar.file_uploader("Datei hochladen", type=['kml', 'geojson', 'zip'])

if uploaded_file:
    temp_dir = "temp_geodata"
    # Der Fix: ignore_errors=True verhindert den Absturz bei Zugriffsfehlern
    shutil.rmtree(temp_dir, ignore_errors=True) 
    os.makedirs(temp_dir, exist_ok=True)

    try:
        if uploaded_file.name.endswith('.zip'):
            zip_path = os.path.join(temp_dir, "upload.zip")
            with open(zip_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(temp_dir)
            
            shp_file = None
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith(".shp"):
                        shp_file = os.path.join(root, file)
            if shp_file:
                gdf = gpd.read_file(shp_file)
            else:
                st.error("Keine .shp im ZIP!")
                st.stop()
        else:
            path = os.path.join(temp_dir, uploaded_file.name)
            with open(path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            gdf = gpd.read_file(path)

        # Berechnung & Karte (wie gehabt)
        gdf_meter = gdf.to_crs(epsg=25833)
        total_len = gdf_meter.geometry.length.sum()

        col1, col2 = st.columns([2, 1])
        with col1:
            center_gdf = gdf.to_crs(epsg=4326)
            m = folium.Map(location=[center_gdf.geometry.centroid.y.mean(), center_gdf.geometry.centroid.x.mean()], zoom_start=15)
            folium.WmsTileLayer(url="https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest?", layers="sn_dop_020", name="Sachsen Luftbild", attr="© GeoSN").add_to(m)
            folium.GeoJson(gdf, style_function=lambda x:{'color':'red', 'weight':4}).add_to(m)
            map_data = st_folium(m, width="100%", height=600)

        with col2:
            st.metric("Gesamtlänge", f"{total_len:,.2f} m".replace(",", "X").replace(".", ",").replace("X", "."))
            if map_data['last_clicked']:
                lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
                st.image(f"https://maps.googleapis.com/maps/api/streetview?size=600x400&location={lat},{lon}&source=outdoor&key={GOOGLE_API_KEY}")

    except Exception as e:
        st.error(f"Fehler: {e}")
