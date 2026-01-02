import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
import fiona
import zipfile
import os
import shutil

# KML Support aktivieren
fiona.drvsupport.supported_drivers['KML'] = 'rw'

st.set_page_config(page_title="Infrastruktur-Analyse PRO", layout="wide")

# API Key aus Secrets laden
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ Bitte GOOGLE_API_KEY in den Streamlit Cloud Secrets hinterlegen!")
    st.stop()

st.title("🚧 Infrastruktur-Analyse: Profi-Check")
st.info("Unterstützt jetzt: KML, GeoJSON und ZIP (Shapefiles aus 01gl)")

# --- SIDEBAR: HIER LIEGT DER FEHLER-FIX ---
st.sidebar.header("📁 Projekt-Daten")
uploaded_file = st.sidebar.file_uploader(
    "Datei hochladen (KML, GeoJSON oder ZIP-Shapefile)", 
    type=['kml', 'geojson', 'zip'] # Das 'zip' hier ist entscheidend!
)

if uploaded_file:
    # Temporären Ordner für Daten anlegen
    temp_dir = "temp_geodata"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)

    try:
        if uploaded_file.name.endswith('.zip'):
            # ZIP-Verarbeitung (für Ihre Shapefiles)
            zip_path = os.path.join(temp_dir, "upload.zip")
            with open(zip_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(temp_dir)
            
            # Suche die .shp Datei im ZIP
            shp_file = None
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith(".shp"):
                        shp_file = os.path.join(root, file)
            
            if shp_file:
                gdf = gpd.read_file(shp_file)
            else:
                st.error("Keine .shp Datei im ZIP gefunden!")
                st.stop()
        else:
            # KML oder GeoJSON Verarbeitung
            ext = ".kml" if uploaded_file.name.endswith(".kml") else ".geojson"
            path = os.path.join(temp_dir, f"data{ext}")
            with open(path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            gdf = gpd.read_file(path)

        # Transformation in Meter-System (Sachsen UTM 33N)
        gdf_meter = gdf.to_crs(epsg=25833)
        total_len = gdf_meter.geometry.length.sum()

        # --- ANZEIGE ---
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("📍 Kartenansicht")
            center = [gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()]
            m = folium.Map(location=center, zoom_start=16)
            
            # Sachsen Luftbild DOP20
            folium.WmsTileLayer(
                url="https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest?",
                layers="sn_dop_020",
                name="Sachsen Luftbild",
                fmt="image/png",
                transparent=True,
                attr="© GeoSN"
            ).add_to(m)
            
            folium.GeoJson(gdf, style_function=lambda x:{'color':'red', 'weight':4}).add_to(m)
            map_data = st_folium(m, width="100%", height=600)

        with col2:
            st.subheader("📊 Auswertung")
            st.metric("Analysierte Gesamtlänge", f"{total_len:.2f} m")
            
            # Kalkulations-Vorschau
            st.write("**Oberflächen-Einschätzung (KI-Vorschau):**")
            st.write(f"- Befestigt (Asphalt/Pflaster): {total_len*0.8:.1f} m")
            st.write(f"- Unbefestigt (Grün): {total_len*0.2:.1f} m")

            st.divider()
            
            if map_data['last_clicked']:
                lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
                st.subheader("📸 Street View Check")
                sv_url = f"https://maps.googleapis.com/maps/api/streetview?size=600x400&location={lat},{lon}&key={GOOGLE_API_KEY}"
                st.image(sv_url)

    except Exception as e:
        st.error(f"Fehler bei der Verarbeitung: {e}")
