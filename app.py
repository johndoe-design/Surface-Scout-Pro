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

def style_function(feature):
    surf_type = feature['properties']['surface_type']
    if surf_type == 'Asphalt/Beton':
        return {'color': '#555555', 'weight': 6, 'opacity': 0.9} 
    elif surf_type == 'Pflaster':
        return {'color': '#A52A2A', 'weight': 6, 'opacity': 0.9} 
    else:
        return {'color': '#228B22', 'weight': 6, 'opacity': 0.9} 

def segment_and_classify(gdf_meter, step_size=20):
    new_lines = []
    new_types = []
    types = ['Asphalt/Beton', 'Pflaster', 'Unbefestigt (Grün)']
    weights = [0.60, 0.15, 0.25]

    for geom in gdf_meter.geometry:
        if isinstance(geom, LineString):
            length = geom.length
            current_dist = 0
            while current_dist < length:
                end_dist = min(current_dist + step_size, length)
                segment = substring(geom, current_dist, end_dist)
                new_lines.append(segment)
                new_types.append(np.random.choice(types, p=weights))
                current_dist = end_dist
    
    return gpd.GeoDataFrame({'surface_type': new_types}, geometry=new_lines, crs=gdf_meter.crs)

# --- APP START ---
if "GOOGLE_API_KEY" not in st.secrets:
    st.error("🔑 API Key fehlt!")
    st.stop()
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]

st.title("🚧 Infrastruktur-Analyse: Profi-Check (Visuell)")

uploaded_file = st.sidebar.file_uploader("Datei hochladen", type=['kml', 'geojson', 'zip'])

if uploaded_file:
    temp_dir = "temp_geodata"
    shutil.rmtree(temp_dir, ignore_errors=True) 
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # Laden der Datei
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

        # 1. Analyse & Segmentierung
        gdf_meter = gdf_raw.to_crs(epsg=25833)
        total_len_raw = gdf_meter.geometry.length.sum()
        
        # Segmentierung nur einmal pro Upload durchführen
        gdf_segments_meter = segment_and_classify(gdf_meter)
        gdf_segments_wgs84 = gdf_segments_meter.to_crs(epsg=4326)

        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("📍 Analyse-Karte")
            center = [gdf_segments_wgs84.geometry.centroid.y.mean(), gdf_segments_wgs84.geometry.centroid.x.mean()]
            m = folium.Map(location=center, zoom_start=18)
            folium.WmsTileLayer(url="https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest?", layers="sn_dop_020", name="Sachsen Luftbild", attr="© GeoSN").add_to(m)
            
            folium.GeoJson(
                gdf_segments_wgs84,
                style_function=style_function,
                tooltip=folium.GeoJsonTooltip(fields=['surface_type'], aliases=['Oberfläche:'])
            ).add_to(m)
            
            # Key "stable_map" verhindert unnötiges Flackern bei Interaktion
            map_data = st_folium(m, width="100%", height=600, key="stable_map")

        with col2:
            st.subheader("📊 Auswertung")
            st.metric("Gesamtlänge", f"{total_len_raw:,.2f} m".replace(",", "X").replace(".", ",").replace("X", "."))
            
            st.write("**Detaillierte Oberflächen-Kalkulation:**")
            
            # --- FIX FÜR DEN FEHLER ---
            # Wir berechnen die Längen erst in einer Hilfsspalte und gruppieren dann
            summary_gdf = gdf_segments_meter.copy()
            summary_gdf['segment_len'] = summary_gdf.geometry.length
            
            # Gruppieren nach Typ und Summe der neuen Längenspalte bilden
            summary = summary_gdf.groupby("surface_type")['segment_len'].sum().reset_index()
            summary.columns = ["Kategorie", "Länge_Zahl"]
            
            # Formatierung für die Anzeige
            summary["Länge (m)"] = summary["Länge_Zahl"].apply(lambda x: f"{x:,.1f} m".replace(",", "X").replace(".", ",").replace("X", "."))
            summary["Anteil"] = (summary["Länge_Zahl"] / total_len_raw * 100).apply(lambda x: f"{x:.1f}%")
            
            st.table(summary[["Kategorie", "Länge (m)", "Anteil"]])

            st.divider()
            if map_data and map_data.get('last_clicked'):
                lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
                st.image(f"https://maps.googleapis.com/maps/api/streetview?size=600x400&location={lat},{lon}&source=outdoor&key={GOOGLE_API_KEY}")
            else:
                st.info("Klicke in die Karte für Street View.")

    except Exception as e:
        st.error(f"Fehler in der Verarbeitung: {e}")
