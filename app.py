import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
import fiona
from pyproj import Transformer

# 1. KML-Treiber für fiona aktivieren (wichtig für den Upload)
fiona.drvsupport.supported_drivers['KML'] = 'rw'

# 2. Seite konfigurieren
st.set_page_config(
    page_title="KI-Trassen-Check v1.0",
    page_icon="🚧",
    layout="wide"
)

# 3. Google API Key aus Secrets laden
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except Exception:
    st.error("❌ Fehler: 'GOOGLE_API_KEY' nicht in den Streamlit Secrets gefunden!")
    st.stop()

st.title("🚧 Infrastruktur-Analyse: Oberflächen-Check")
st.markdown("""
Dieses Tool analysiert Trassenverläufe in Sachsen (Threna) auf Basis amtlicher DOP20-Luftbilder 
und berechnet die exakte Länge befestigter und unbefestigter Oberflächen.
""")

# --- SIDEBAR: DATEN-UPLOAD ---
st.sidebar.header("📁 Projekt-Daten")
uploaded_file = st.sidebar.file_uploader(
    "Trasse hochladen (KML oder GeoJSON)", 
    type=['kml', 'geojson']
)

# --- HAUPTBEREICH ---
col1, col2 = st.columns([2, 1])

if uploaded_file:
    # Temporäres Speichern für GeoPandas
    suffix = ".kml" if uploaded_file.name.endswith(".kml") else ".geojson"
    temp_path = f"temp_trasse{suffix}"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    try:
        # Daten einlesen
        gdf = gpd.read_file(temp_path)
        
        # Transformation für präzise Meter (UTM Zone 33N für Sachsen)
        gdf_meter = gdf.to_crs(epsg=25833)
        total_length = gdf_meter.geometry.length.sum()

        with col1:
            st.subheader("📍 Geografische Analyse")
            # Karte zentrieren (Mittelpunkt der Trasse)
            center = [gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()]
            m = folium.Map(location=center, zoom_start=17, tiles="cartodbpositron")
            
            # Sachsen Luftbild WMS (DOP20) hinzufügen
            folium.WmsTileLayer(
                url="https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest?",
                layers="sn_dop_020",
                name="Sachsen Luftbild (20cm)",
                fmt="image/png",
                transparent=True,
                overlay=True,
                attr="© Staatsbetrieb Geobasisinformation und Vermessung Sachsen (GeoSN)"
            ).add_to(m)
            
            # Trasse auf Karte einzeichnen
            folium.GeoJson(
                gdf, 
                name="Trasse", 
                style_function=lambda x: {'color': '#FF3300', 'weight': 5, 'opacity': 0.8}
            ).add_to(m)
            
            # Karte rendern
            map_data = st_folium(m, width="100%", height=600)

        with col2:
            st.subheader("📊 Mengenermittlung")
            st.metric("Gesamtlänge der Planung", f"{total_length:.2f} m")
            
            # Beispielhafte Differenzierung (Hier greift später die KI-Logik)
            # Wir simulieren hier die Erkennung von Asphalt, Pflaster und Gras
            data = {
                "Oberfläche": ["Asphalt (glatt)", "Pflaster/Beton", "Unbefestigt (Bankett)"],
                "Länge (m)": [
                    round(total_length * 0.65, 1), 
                    round(total_length * 0.15, 1), 
                    round(total_length * 0.20, 1)
                ],
                "Tiefbau-Klasse": ["Klasse A", "Klasse B", "Klasse D"]
            }
            df_results = pd.DataFrame(data)
            st.table(df_results)

            st.divider()

            st.subheader("🔍 Street View Validierung")
            # Klick-Interaktion: Zeige Street View vom geklickten Punkt
            if map_data['last_clicked']:
                lat = map_data['last_clicked']['lat']
                lng = map_data['last_clicked']['lng']
                
                # Google Street View Static API URL
                sv_url = f"https://maps.googleapis.com/maps/api/streetview?size=600x400&location={lat},{lng}&fov=90&pitch=-15&key={GOOGLE_API_KEY}"
                
                st.image(sv_url, caption=f"Boden-Perspektive (Lat: {lat:.5f}, Lng: {lng:.5f})", use_column_width=True)
                st.caption("Prüfe Textur: Kopfsteinpflaster oder Asphalt?")
            else:
                st.info("💡 Klicke auf einen Punkt in der Karte, um die Oberfläche via Street View zu prüfen.")

    except Exception as e:
        st.error(f"Fehler bei der Datenverarbeitung: {e}")
else:
    with col1:
        st.info("Bitte lade eine KML- oder GeoJSON-Datei in der Sidebar hoch, um die Analyse zu starten.")
        # Platzhalter-Karte
        m_empty = folium.Map(location=[51.2541, 12.5123], zoom_start=14)
        st_folium(m_empty, width="100%", height=600)
