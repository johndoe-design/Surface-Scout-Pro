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

st.set_page_config(page_title="Infrastruktur-Analyse", layout="wide")

# API Key Check
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("Bitte GOOGLE_API_KEY in Secrets hinterlegen!")
    st.stop()

# --- SIDEBAR MIT NEUEN DATEITYPEN ---
st.sidebar.header("📁 Projekt-Daten")
uploaded_file = st.sidebar.file_uploader(
    "Trasse hochladen (KML, GeoJSON oder ZIP)", 
    type=['kml', 'geojson', 'zip'] # ZIP hinzugefügt
)

if uploaded_file:
    # Aufräumen alter Daten
    if os.path.exists("temp_data"):
        shutil.rmtree("temp_data")
    os.makedirs("temp_data")

    try:
        if uploaded_file.name.endswith('.zip'):
            # ZIP Handling
            with open("temp_data/data.zip", "wb") as f:
                f.write(uploaded_file.getbuffer())
            with zipfile.ZipFile("temp_data/data.zip", "r") as z:
                z.extractall("temp_data")
            
            # Suche die .shp Datei
            shp_path = None
            for root, dirs, files in os.walk("temp_data"):
                for file in files:
                    if file.endswith(".shp"):
                        shp_path = os.path.join(root, file)
            
            if shp_path:
                gdf = gpd.read_file(shp_path)
            else:
                st.error("Keine .shp Datei im ZIP gefunden!")
                st.stop()
        else:
            # KML/GeoJSON Handling
            ext = ".kml" if uploaded_file.name.endswith(".kml") else ".geojson"
            path = f"temp_data/trasse{ext}"
            with open(path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            gdf = gpd.read_file(path)

        # --- AB HIER DIE ANALYSE (wie bisher) ---
        gdf_meter = gdf.to_crs(epsg=25833) # UTM für Sachsen
        total_len = gdf_meter.geometry.length.sum()

        col1, col2 = st.columns([2, 1])
        with col1:
            center = [gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()]
            m = folium.Map(location=center, zoom_start=16)
            folium.WmsTileLayer(
                url="https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest?",
                layers="sn_dop_020",
                name="Sachsen DOP20",
                fmt="image/png",
                transparent=True
            ).add_to(m)
            folium.GeoJson(gdf, style_function=lambda x:{'color':'red'}).add_to(m)
            map_data = st_folium(m, width="100%", height=600)

        with col2:
            st.metric("Gesamtlänge", f"{total_len:.2f} m")
            # Street View Logik...
            if map_data['last_clicked']:
                lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
                st.image(f"https://maps.googleapis.com/maps/api/streetview?size=600x400&location={lat},{lon}&key={GOOGLE_API_KEY}")

    except Exception as e:
        st.error(f"Fehler: {e}")
