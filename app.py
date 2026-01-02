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

# --- 1. CACHING DER BERECHNUNGEN (Verhindert das Flackern) ---
@st.cache_data(show_spinner=False)
def get_segmented_data(file_bytes, file_name):
    """Verarbeitet die Datei nur einmal und speichert das Ergebnis im Cache."""
    temp_dir = "temp_cache"
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)
    
    # Datei speichern & laden
    path = os.path.join(temp_dir, file_name)
    with open(path, "wb") as f:
        f.write(file_bytes)
    
    if file_name.endswith('.zip'):
        with zipfile.ZipFile(path, "r") as z:
            z.extractall(temp_dir)
        shp = next((os.path.join(r, f) for r, d, files in os.walk(temp_dir) for f in files if f.endswith(".shp")), None)
        gdf = gpd.read_file(shp)
    else:
        gdf = gpd.read_file(path)
    
    # Metrische Transformation & Segmentierung
    gdf_meter = gdf.to_crs(epsg=25833)
    
    new_lines, new_types = [], []
    types = ['Asphalt/Beton', 'Pflaster', 'Unbefestigt (Grün)']
    weights = [0.60, 0.15, 0.25]
    step_size = 20

    for geom in gdf_meter.geometry:
        if isinstance(geom, LineString):
            curr = 0
            while curr < geom.length:
                end = min(curr + step_size, geom.length)
                new_lines.append(substring(geom, curr, end))
                new_types.append(np.random.choice(types, p=weights))
                curr = end
    
    res_meter = gpd.GeoDataFrame({'surface_type': new_types}, geometry=new_lines, crs=gdf_meter.crs)
    return res_meter, res_meter.to_crs(epsg=4326)

# --- 2. UI KONFIGURATION ---
st.set_page_config(page_title="Surface-Scout PRO", layout="wide")
fiona.drvsupport.supported_drivers['KML'] = 'rw'

if "GOOGLE_API_KEY" not in st.secrets:
    st.error("API Key fehlt!")
    st.stop()

st.title("🚧 Surface-Scout PRO: Analyse-Dashboard")

uploaded_file = st.sidebar.file_uploader("Trasse hochladen", type=['kml', 'geojson', 'zip'])

if uploaded_file:
    # Daten über Cache laden (blitzschnell bei Klicks)
    gdf_seg_meter, gdf_seg_wgs84 = get_segmented_data(uploaded_file.getvalue(), uploaded_file.name)
    total_len = gdf_seg_meter.geometry.length.sum()

    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Karte nur einmal initialisieren
        center = [gdf_seg_wgs84.geometry.centroid.y.mean(), gdf_seg_wgs84.geometry.centroid.x.mean()]
        m = folium.Map(location=center, zoom_start=18, control_scale=True)
        
        folium.WmsTileLayer(
            url="https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest?",
            layers="sn_dop_020",
            name="Sachsen Luftbild",
            attr="© GeoSN"
        ).add_to(m)
        
        folium.GeoJson(
            gdf_seg_wgs84,
            style_function=lambda x: {
                'color': '#555555' if x['properties']['surface_type'] == 'Asphalt/Beton' 
                         else '#A52A2A' if x['properties']['surface_type'] == 'Pflaster' 
                         else '#228B22',
                'weight': 6, 'opacity': 0.8
            },
            tooltip=folium.GeoJsonTooltip(fields=['surface_type'], aliases=['Oberfläche:'])
        ).add_to(m)
        
        # st_folium mit festem Key und Rückgabewert
        map_data = st_folium(m, width="100%", height=600, key="fixed_map_engine", returned_objects=["last_clicked"])

    with col2:
        st.subheader("📊 Mengenermittlung")
        st.metric("Gesamtlänge", f"{total_len:,.1f} m".replace(",", "X").replace(".", ",").replace("X", "."))
        
        # Tabelle berechnen
        summary_df = gdf_seg_meter.copy()
        summary_df['length'] = summary_df.geometry.length
        stats = summary_df.groupby("surface_type")['length'].sum().reset_index()
        stats["Anteil"] = (stats["length"] / total_len * 100).apply(lambda x: f"{x:.1f}%")
        stats["Länge (m)"] = stats["length"].apply(lambda x: f"{x:,.1f} m".replace(",", " ").replace(".", ","))
        
        st.table(stats[["surface_type", "Länge (m)", "Anteil"]])

        st.divider()
        if map_data and map_data.get('last_clicked'):
            lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
            st.subheader("📸 Street View")
            sv_url = f"https://maps.googleapis.com/maps/api/streetview?size=600x400&location={lat},{lon}&source=outdoor&key={st.secrets['GOOGLE_API_KEY']}"
            st.image(sv_url, use_container_width=True)
        else:
            st.info("Klicke in die Karte für Bodenansicht.")
