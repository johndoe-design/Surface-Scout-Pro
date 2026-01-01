import streamlit as st
import folium
from streamlit_folium import st_folium
import geopandas as gpd

st.set_page_config(page_title="KI-Trassen-Check Prototyp", layout="wide")

st.title("🚧 Trassen-Analyse Test-Tool")

# Datei-Upload
uploaded_file = st.sidebar.file_uploader("Trasse hochladen (GeoJSON oder KML)", type=['geojson', 'kml'])

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Karte: Threna & Umgebung")
    # Initialisiere Karte (Beispiel Threna)
    m = folium.Map(location=[51.2541, 12.5123], zoom_start=16, tiles="cartodbpositron")
    
    # Hier binden wir den Sachsen-WMS Dienst ein für echte Luftbilder
    folium.WmsTileLayer(
        url="https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest?",
        layers="sn_dop_020",
        name="Sachsen Luftbild (20cm)",
        fmt="image/png",
        transparent=True,
        attr="© GeoSN (Sachsen)"
    ).add_to(m)

    if uploaded_file:
        # Trasse auf Karte anzeigen
        gdf = gpd.read_file(uploaded_file)
        folium.GeoJson(gdf, name="Geplante Trasse").add_to(m)
    
    st_folium(m, width=900, height=600)

with col2:
    st.subheader("KI-Analyse Ergebnis")
    if uploaded_file:
        # Hier simulieren wir die Meter-Ergebnisse (Logik aus dem vorherigen Schritt)
        st.success("Analyse abgeschlossen!")
        st.metric("Gesamtlänge", "1.240 m")
        
        st.table({
            "Oberfläche": ["Asphalt", "Pflaster", "Beton", "Unbefestigt"],
            "Meter": [850, 120, 30, 240],
            "Anteil": ["68%", "10%", "2%", "20%"]
        })
        
        st.info("💡 Klicke auf die Karte für Street View (Simuliert)")
    else:
        st.warning("Bitte lade eine Datei hoch, um die Analyse zu starten.")
