import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
import fiona
import zipfile
import os
import shutil

# 1. KML-Unterstützung für fiona aktivieren
fiona.drvsupport.supported_drivers['KML'] = 'rw'

# 2. Seite konfigurieren
st.set_page_config(page_title="Infrastruktur-Analyse PRO", layout="wide", page_icon="🚧")

# 3. Google API Key aus Secrets laden
if "GOOGLE_API_KEY" not in st.secrets:
    st.error("🔑 Bitte GOOGLE_API_KEY in den Streamlit Cloud Secrets hinterlegen!")
    st.stop()
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]

st.title("🚧 Infrastruktur-Analyse: Profi-Check")
st.info("Unterstützt: KML, GeoJSON und ZIP (Shapefiles aus 01gl)")

# --- SIDEBAR: DATEI-UPLOAD ---
st.sidebar.header("📁 Projekt-Daten")
uploaded_file = st.sidebar.file_uploader(
    "Datei hochladen (KML, GeoJSON oder ZIP-Shapefile)", 
    type=['kml', 'geojson', 'zip']
)

if uploaded_file:
    # Temporären Ordner für Daten anlegen
    temp_dir = "temp_geodata"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)

    try:
        with st.status("Verarbeite Geodaten...", expanded=True) as status:
            if uploaded_file.name.endswith('.zip'):
                st.write("📦 Entpacke ZIP-Archiv...")
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
                    st.write(f"✅ Shapefile gefunden: {os.path.basename(shp_file)}")
                    gdf = gpd.read_file(shp_file)
                else:
                    st.error("Keine .shp Datei im ZIP gefunden!")
                    st.stop()
            else:
                st.write("📄 Lese KML/GeoJSON...")
                ext = ".kml" if uploaded_file.name.endswith(".kml") else ".geojson"
                path = os.path.join(temp_dir, f"data{ext}")
                with open(path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                gdf = gpd.read_file(path)

            # Transformation in Meter-System (Sachsen UTM 33N)
            st.write("🌍 Berechne Längen in Metern (UTM 33N)...")
            gdf_meter = gdf.to_crs(epsg=25833)
            total_len = gdf_meter.geometry.length.sum()
            status.update(label="Analyse bereit!", state="complete", expanded=False)

        # --- HAUPT-LAYOUT ---
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("📍 Kartenansicht (Luftbild Sachsen DOP20)")
            # Dynamische Zentrierung auf die Daten
            center = [gdf.to_crs(epsg=4326).geometry.centroid.y.mean(), 
                      gdf.to_crs(epsg=4326).geometry.centroid.x.mean()]
            m = folium.Map(location=center, zoom_start=17)
            
            # Amtliches Sachsen Luftbild DOP20 einbinden
            folium.WmsTileLayer(
                url="https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest?",
                layers="sn_dop_020",
                name="Sachsen Luftbild",
                fmt="image/png",
                transparent=True,
                attr="© GeoSN Sachsen"
            ).add_to(m)
            
            # Trassenverlauf in Rot einzeichnen
            folium.GeoJson(gdf, style_function=lambda x:{'color':'red', 'weight':4, 'opacity':0.7}).add_to(m)
            map_data = st_folium(m, width="100%", height=600)

        with col2:
            st.subheader("📊 Auswertung")
            st.metric("Gesamtlänge Trassennetz", f"{total_len:,.2f} m".replace(",", "X").replace(".", ",").replace("X", "."))
            
            # Kalkulations-Vorschau (Platzhalter für KI-Logik)
            st.write("**Geschätzte Oberflächen-Verteilung:**")
            st.table(pd.DataFrame({
                "Kategorie": ["Befestigt (Asphalt/Pflaster)", "Unbefestigt (Grünland)"],
                "Meter (ca.)": [f"{total_len*0.85:,.1f} m", f"{total_len*0.15:,.1f} m"],
                "Anteil": ["85%", "15%"]
            }))

            st.divider()
            
            # STREET VIEW LOGIK MIT OUTDOOR-FILTER
            if map_data['last_clicked']:
                lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
                st.subheader("📸 Street View Check")
                # source=outdoor verhindert Innenaufnahmen
                sv_url = f"https://maps.googleapis.com/maps/api/streetview?size=600x400&location={lat},{lon}&source=outdoor&key={GOOGLE_API_KEY}"
                st.image(sv_url, caption=f"Bodenansicht bei {lat:.5f}, {lon:.5f}", use_column_width=True)
                st.info("Tipp: Das Bild zeigt jetzt bevorzugt die öffentliche Straße.")
            else:
                st.info("💡 Klicke auf die Karte, um die Oberfläche via Street View zu prüfen.")

    except Exception as e:
        st.error(f"Fehler bei der Verarbeitung: {e}")
else:
    st.info("Warte auf Datei-Upload (ZIP mit Shapefiles aus Ordner 01gl)...")
