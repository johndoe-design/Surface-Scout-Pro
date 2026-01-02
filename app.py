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
import requests
import cv2

# --- KONFIGURATION & TREIBER ---
st.set_page_config(page_title="Surface-Scout PRO (1m Präzision)", layout="wide", page_icon="🚧")
fiona.drvsupport.supported_drivers['KML'] = 'rw'

WMS_URL = "https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest?"

# --- BILDANALYSE-LOGIK ---
def analyze_image_patch(minx, miny, maxx, maxy):
    try:
        bbox_str = f"{minx},{miny},{maxx},{maxy}"
        params = {
            "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
            "LAYERS": "sn_dop_020", "SRS": "EPSG:25833", "BBOX": bbox_str,
            "WIDTH": "50", "HEIGHT": "50", "FORMAT": "image/png", "TRANSPARENT": "FALSE"
        }
        response = requests.get(WMS_URL, params=params, timeout=5)
        
        if response.status_code == 200:
            image_array = np.asarray(bytearray(response.content), dtype=np.uint8)
            img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            if img is None: return 'Befestigt'

            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            # Grün-Erkennung für Bankette/Grünstreifen
            lower_green = np.array([35, 30, 30])
            upper_green = np.array([90, 255, 255])
            mask_green = cv2.inRange(hsv, lower_green, upper_green)
            
            green_ratio = cv2.countNonZero(mask_green) / (img.shape[0] * img.shape[1])
            return 'Unbefestigt (Grün)' if green_ratio > 0.30 else 'Befestigt'
        return 'Befestigt'
    except:
        return 'Befestigt'

# --- VERARBEITUNG MIT CACHE ---
@st.cache_data(show_spinner=False)
def get_high_res_analysis(file_bytes, file_name):
    temp_dir = "temp_analysis"
    # Robustes Löschen des Ordners zur Vermeidung von FileNotFoundError
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)
    
    path = os.path.join(temp_dir, file_name)
    with open(path, "wb") as f: f.write(file_bytes)
    
    if file_name.endswith('.zip'):
        with zipfile.ZipFile(path, "r") as z: z.extractall(temp_dir)
        shp = next((os.path.join(r, f) for r, d, files in os.walk(temp_dir) for f in files if f.endswith(".shp")), None)
        gdf = gpd.read_file(shp)
    else:
        gdf = gpd.read_file(path)
    
    gdf_meter = gdf.to_crs(epsg=25833)
    new_lines, new_types = [], []
    step_size = 1.0 # 1-Meter Präzision

    # Fortschrittsanzeige für den Nutzer
    total_len = int(gdf_meter.geometry.length.sum())
    progress_bar = st.progress(0, text="Starte 1m-Analyse...")
    processed = 0

    for geom in gdf_meter.geometry:
        if isinstance(geom, LineString):
            curr = 0
            while curr < geom.length:
                end = min(curr + step_size, geom.length)
                segment = substring(geom, curr, end)
                new_lines.append(segment)
                
                # Geometrische Grenzen für WMS-Abfrage
                minx, miny, maxx, maxy = segment.bounds
                real_type = analyze_image_patch(minx-1, miny-1, maxx+1, maxy+1)
                new_types.append(real_type)
                
                curr = end
                processed += 1
                if processed % 20 == 0:
                    progress_bar.progress(min(processed/total_len, 1.0), text=f"Analyse: {processed}m / {total_len}m")
            
    progress_bar.empty()
    res_meter = gpd.GeoDataFrame({'surface_type': new_types}, geometry=new_lines, crs=gdf_meter.crs)
    return res_meter, res_meter.to_crs(epsg=4326)

# --- HAUPTPROGRAMM ---
if "GOOGLE_API_KEY" not in st.secrets:
    st.error("🔑 API Key fehlt in Secrets!")
    st.stop()

st.title("🚧 Surface-Scout PRO: 1m Detail-Check")

uploaded_file = st.sidebar.file_uploader("Trasse hochladen (1m Analyse)", type=['kml', 'geojson', 'zip'])

if uploaded_file:
    with st.spinner("Analysiere jeden Meter einzeln... Dies kann einen Moment dauern."):
        gdf_seg_meter, gdf_seg_wgs84 = get_high_res_analysis(uploaded_file.getvalue(), uploaded_file.name)
    
    total_len = gdf_seg_meter.geometry.length.sum()
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📍 Detail-Karte")
        m = folium.Map(location=[gdf_seg_wgs84.geometry.centroid.y.mean(), gdf_seg_wgs84.geometry.centroid.x.mean()], zoom_start=19)
        folium.WmsTileLayer(url=WMS_URL, layers="sn_dop_020", name="Sachsen Luftbild", attr="© GeoSN").add_to(m)
        
        # Segment-Farben: Grün für Unbefestigt, Grau für Befestigt
        folium.GeoJson(gdf_seg_wgs84, style_function=lambda x: {
            'color': '#32CD32' if x['properties']['surface_type'] == 'Unbefestigt (Grün)' else '#696969',
            'weight': 6, 'opacity': 0.9
        }).add_to(m)
        
        # Karte rendern
        map_data = st_folium(m, width="100%", height=600, key="fixed_1m_map", returned_objects=["last_clicked"])

    with col2:
        st.subheader("📊 Mengenermittlung")
        st.metric("Gesamtlänge", f"{total_len:,.2f} m".replace(".", ","))
        
        # Zusammenfassung der Oberflächen
        sum_df = gdf_seg_meter.copy()
        sum_df['length'] = sum_df.geometry.length
        stats = sum_df.groupby("surface_type")['length'].sum().reset_index()
        stats["Anteil"] = (stats["length"] / total_len * 100).apply(lambda x: f"{x:.1f}%")
        stats["Länge (m)"] = stats["length"].apply(lambda x: f"{x:,.1f} m".replace(".", ","))
        
        st.table(stats[["surface_type", "Länge (m)", "Anteil"]])
        
        if map_data and map_data.get('last_clicked'):
            lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
            st.image(f"https://maps.googleapis.com/maps/api/streetview?size=600x400&location={lat},{lon}&source=outdoor&key={st.secrets['GOOGLE_API_KEY']}")
