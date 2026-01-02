import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
import fiona
import zipfile
import os
import shutil
import numpy as np
from shapely.ops import substring
from shapely.geometry import LineString

# --- KONFIGURATION ---
st.set_page_config(page_title="Infrastruktur-Analyse PRO", layout="wide", page_icon="🚧")
fiona.drvsupport.supported_drivers['KML'] = 'rw'

# --- HILFSFUNKTIONEN ---
def style_function(feature):
    """Bestimmt die Farbe basierend auf dem Oberflächentyp."""
    surf_type = feature['properties']['surface_type']
    if surf_type == 'Asphalt/Beton':
        return {'color': '#555555', 'weight': 5} # Dunkelgrau
    elif surf_type == 'Pflaster':
        return {'color': '#A52A2A', 'weight': 5} # Ziegelrot
    else:
        return {'color': '#228B22', 'weight': 5} # Waldgrün

def segment_and_classify(gdf_meter, step_size=30):
    """
    Simuliert eine KI-Analyse: Zerschneidet die Linie in 'step_size' Meter Stücke
    und weist basierend auf Wahrscheinlichkeiten einen Typ zu.
    """
    new_lines = []
    new_types = []
    # Simulierte Verteilung: 60% Asphalt, 15% Pflaster, 25% Grün
    types = ['Asphalt/Beton', 'Pflaster', 'Unbefestigt (Grün)']
    weights = [0.60, 0.15, 0.25]

    for geom in gdf_meter.geometry:
        if isinstance(geom, LineString):
            length = geom.length
            current_dist = 0
            while current_dist < length:
                # Segment ausschneiden
                end_dist = min(current_dist + step_size, length)
                segment = substring(geom, current_dist, end_dist)
                new_lines.append(segment)
                # Zufälligen Typ basierend auf Gewichtung zuweisen
                chosen_type = np.random.choice(types, p=weights)
                new_types.append(chosen_type)
                current_dist = end_dist
    
    # Neues GeoDataFrame mit den segmentierten Daten erstellen
    gdf_segments = gpd.GeoDataFrame(
        {'surface_type': new_types}, 
        geometry=new_lines, 
        crs=gdf_meter.crs
    )
    return gdf_segments

# --- HAUPTANWENDUNG ---
if "GOOGLE_API_KEY" not in st.secrets:
    st.error("🔑 API Key fehlt in den Secrets!")
    st.stop()
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]

st.title("🚧 Infrastruktur-Analyse: Profi-Check (Visuell)")

# Sidebar
st.sidebar.header("📁 Projekt-Daten")
uploaded_file = st.sidebar.file_uploader("Datei hochladen (KML, GeoJSON, ZIP)", type=['kml', 'geojson', 'zip'])

if uploaded_file:
    # Daten laden (wie gehabt)
    temp_dir = "temp_geodata"
    shutil.rmtree(temp_dir, ignore_errors=True) 
    os.makedirs(temp_dir, exist_ok=True)

    try:
        if uploaded_file.name.endswith('.zip'):
            zip_path = os.path.join(temp_dir, "upload.zip")
            with open(zip_path, "wb") as f: f.write(uploaded_file.getbuffer())
            with zipfile.ZipFile(zip_path, "r") as z: z.extractall(temp_dir)
            shp_file = next((os.path.join(r, f) for r, d, files in os.walk(temp_dir) for f in files if f.endswith(".shp")), None)
            gdf_raw = gpd.read_file(shp_file)
        else:
            path = os.path.join(temp_dir, uploaded_file.name)
            with open(path, "wb") as f: f.write(uploaded_file.getbuffer())
            gdf_raw = gpd.read_file(path)

        # 1. In Meter umwandeln
        gdf_meter = gdf_raw.to_crs(epsg=25833)
        total_len_raw = gdf_meter.geometry.length.sum()

        # 2. NEU: Segmentierung und Klassifizierung durchführen
        with st.spinner("Führe Oberflächen-Segmentierung durch..."):
            gdf_segments_meter = segment_and_classify(gdf_meter)
            # Für die Karte zurück nach WGS84
            gdf_segments_wgs84 = gdf_segments_meter.to_crs(epsg=4326)

        # --- LAYOUT ---
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("📍 Bunte Kartenansicht")
            center = [gdf_segments_wgs84.geometry.centroid.y.mean(), gdf_segments_wgs84.geometry.centroid.x.mean()]
            m = folium.Map(location=center, zoom_start=17)
            folium.WmsTileLayer(url="https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest?", layers="sn_dop_020", name="Sachsen Luftbild", attr="© GeoSN").add_to(m)
            
            # NEU: Die segmentierten Linien mit der Style-Funktion hinzufügen
            folium.GeoJson(
                gdf_segments_wgs84,
                style_function=style_function,
                tooltip=folium.GeoJsonTooltip(fields=['surface_type'], aliases=['Typ:'])
            ).add_to(m)
            
            map_data = st_folium(m, width="100%", height=600, key="color_map")

        with col2:
            st.subheader("📊 Auswertung")
            st.metric("Gesamtlänge", f"{total_len_raw:,.2f} m".replace(",", "X").replace(".", ",").replace("X", "."))
            
            # NEU: Tabelle basiert jetzt auf den echten Segmenten der Karte
            st.write("**Detaillierte Oberflächen-Kalkulation:**")
            # Gruppieren und Summieren der Längen pro Typ
            summary = gdf_segments_meter.groupby("surface_type").geometry.length.sum().reset_index()
            summary.columns = ["Kategorie", "Länge (raw)"]
            summary["Länge (m)"] = summary["Länge (raw)"].apply(lambda x: f"{x:,.1f} m".replace(",", "X").replace(".", ",").replace("X", "."))
            summary["Anteil"] = (summary["Länge (raw)"] / total_len_raw * 100).apply(lambda x: f"{x:.1f}%")
            
            st.table(summary[["Kategorie", "Länge (m)", "Anteil"]])

            st.divider()
            st.subheader("📸 Street View Check")
            if map_data and map_data.get('last_clicked'):
                lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
                sv_url = f"https://maps.googleapis.com/maps/api/streetview?size=600x400&location={lat},{lon}&source=outdoor&key={GOOGLE_API_KEY}"
                st.image(sv_url, caption=f"Ansicht bei {lat:.5f}, {lon:.5f}")
            else:
                st.info("Klicke auf ein farbiges Segment, um die Oberfläche zu prüfen.")

    except Exception as e:
        st.error(f"Fehler: {e}")
