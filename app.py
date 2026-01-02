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

# --- KONFIGURATION ---
st.set_page_config(page_title="Surface-Scout PRO: 1m Echt-Analyse", layout="wide", page_icon="🚧")
fiona.drvsupport.supported_drivers['KML'] = 'rw'
WMS_URL = "https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest?"

# --- ECHTE BILDANALYSE ---
def analyze_pixel_color(minx, miny, maxx, maxy):
    """Holt das echte Luftbild-Pixel und analysiert die Farbe (Grün vs. Grau)."""
    try:
        bbox_str = f"{minx},{miny},{maxx},{maxy}"
        params = {
            "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
            "LAYERS": "sn_dop_020", "SRS": "EPSG:25833", "BBOX": bbox_str,
            "WIDTH": "40", "HEIGHT": "40", "FORMAT": "image/png", "TRANSPARENT": "FALSE"
        }
        response = requests.get(WMS_URL, params=params, timeout=5)
        if response.status_code == 200:
            img_arr = np.asarray(bytearray(response.content), dtype=np.uint8)
            img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
            if img is None: return 'Befestigt'
            
            # HSV-Farbraum für Grün-Erkennung
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            mask_green = cv2.inRange(hsv, np.array([35, 30, 30]), np.array([90, 255, 255]))
            green_ratio = cv2.countNonZero(mask_green) / (img.shape[0] * img.shape[1])
            
            return 'Unbefestigt (Grün)' if green_ratio > 0.35 else 'Befestigt'
        return 'Befestigt'
    except:
        return 'Befestigt'

# --- VERARBEITUNG ---
@st.cache_data(show_spinner=False)
def process_high_precision_data(file_bytes, file_name):
    temp_dir = "temp_analysis_1m"
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)
    
    path = os.path.join(temp_dir, file_name)
    with open(path, "wb") as f: f.write(file_bytes)
    
    if file_name.endswith('.zip'):
        with zipfile.ZipFile(path, "r") as z: z.extractall(temp_dir)
        shp = next((os.path.join(root, f) for root, dirs, files in os.walk(temp_dir) for f in files if f.endswith(".shp")), None)
        gdf = gpd.read_file(shp)
    else:
        gdf = gpd.read_file(path)
    
    gdf_meter = gdf.to_crs(epsg=25833)
    new_lines, new_types = [], []
    step_size = 1.0 # Exakte 1-Meter-Schritte
    
    total_len = int(gdf_meter.geometry.length.sum())
    progress_bar = st.progress(0, text="Starte metergenaue Analyse...")
    processed = 0

    for geom in gdf_meter.geometry:
        if isinstance(geom, LineString):
            curr = 0
            while curr < geom.length:
                end = min(curr + step_size, geom.length)
                segment = substring(geom, curr, end)
                new_lines.append(segment)
                
                # Jedes Meter-Segment einzeln prüfen
                minx, miny, maxx, maxy = segment.bounds
                new_types.append(analyze_pixel_color(minx-1, miny-1, maxx+1, maxy+1))
                
                curr = end
                processed += 1
                if processed % 15 == 0:
                    progress_bar.progress(min(processed/total_len, 1.0), text=f"Analyse: {processed}m / {total_len}m")
    
    progress_bar.empty()
    res = gpd.GeoDataFrame({'surface_type': new_types}, geometry=new_lines, crs=gdf_meter.crs)
    return res, res.to_crs(epsg=4326)

# --- UI ---
st.title("🚧 Surface-Scout PRO: 1m Echt-Analyse")

uploaded_file = st.sidebar.file_uploader("Trasse hochladen", type=['kml', 'geojson', 'zip'])

if uploaded_file:
    with st.spinner("Analysiere Trasse Meter für Meter..."):
        gdf_seg_m, gdf_seg_w = process_high_precision_data(uploaded_file.getvalue(), uploaded_file.name)
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("📍 Analyse-Karte (1m Präzision)")
        m = folium.Map(location=[gdf_seg_w.geometry.centroid.y.mean(), gdf_seg_w.geometry.centroid.x.mean()], zoom_start=19)
        folium.WmsTileLayer(url=WMS_URL, layers="sn_dop_020", name="Sachsen Luftbild", attr="© GeoSN").add_to(m)
        
        folium.GeoJson(gdf_seg_w, style_function=lambda x: {
            'color': '#32CD32' if x['properties']['surface_type'] == 'Unbefestigt (Grün)' else '#696969',
            'weight': 6, 'opacity': 0.9
        }).add_to(m)
        map_data = st_folium(m, width="100%", height=600, key="map_1m")

    with col2:
        st.subheader("📊 Reale Mengenermittlung")
        total_m = gdf_seg_m.geometry.length.sum()
        st.metric("Gesamtlänge", f"{total_m:,.2f} m".replace(".", ","))
        
        # Stabiler Fix für die Tabellen-Berechnung
        summary_gdf = gdf_seg_m.copy()
        summary_gdf['seg_len'] = summary_gdf.geometry.length
        stats = summary_gdf.groupby("surface_type")['seg_len'].sum().reset_index()
        stats["Anteil"] = (stats["seg_len"] / total_m * 100).apply(lambda x: f"{x:.1f}%")
        stats["Länge (m)"] = stats["seg_len"].apply(lambda x: f"{x:,.1f} m".replace(".", ","))
        st.table(stats[["surface_type", "Länge (m)", "Anteil"]])

        if map_data and map_data.get('last_clicked'):
            lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
            st.image(f"https://maps.googleapis.com/maps/api/streetview?size=600x400&location={lat},{lon}&source=outdoor&key={st.secrets['GOOGLE_API_KEY']}")
