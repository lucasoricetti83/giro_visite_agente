import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
from streamlit_js_eval import streamlit_js_eval

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Giro Visite Pro", layout="wide")

# --- FUNZIONI DI CALCOLO ---
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371

@st.cache_data(ttl=60)
def load_data(url):
    try:
        df = pd.read_csv(url, sep=None, engine='python')
        df.columns = df.columns.str.strip().str.lower()
        for col in ['latitude', 'longitude', 'frequenza (giorni)']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce')
        df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except Exception as e:
        st.error(f"Errore caricamento dati: {e}")
        return pd.DataFrame()

# --- LOGICA DELL'APPLICAZIONE ---
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132"
df_raw = load_data(URL_FOGLIO)

if not df_raw.empty:
    # 1. Sidebar - Impostazioni (sempre visibili)
    st.sidebar.title("⚙️ Parametri")
    
    st.sidebar.subheader("📍 Partenza")
    metodo_p = st.sidebar.radio("Scegli partenza:", ["GPS", "Digita Luogo"], index=0)
    start_lat, start_lon = 43.1924, 13.5797

    if metodo_p == "GPS":
        g_coords = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps_loc')
        if g_coords:
            start_lat, start_lon = g_coords['latitude'], g_coords['longitude']
            st.sidebar.success("GPS Attivo")
    else:
        luogo_input = st.sidebar.text_input("Città/Indirizzo:", "Fermo")
        if luogo_input:
            try:
                geolocator = Nominatim(user_agent="giro_agente_v2")
                loc_geop = geolocator.geocode(luogo_input)
                if loc_geop: start_lat, start_lon = loc_geop.latitude, loc_geop.longitude
            except: pass

    st.sidebar.subheader("⏰ Orari")
    h_inizio = st.sidebar.time_input("Inizio lavoro", time(9, 0))
    h_fine = st.sidebar.time_input("Fine lavoro", time(18, 0))
    durata_v = st.sidebar.slider("Durata visita (min)", 15, 120, 45)

    # 2. Tabs principali
    tab1, tab2 = st.tabs(["🚀 Giro di Oggi", "📅 Agenda 8 Settimane"])

    # --- TAB 1: GIRO DI OGGI (Calcolo automatico) ---
    with tab1:
        oggi = datetime.now()
        st.header(f"Agenda di Oggi: {oggi.strftime('%d/%m/%Y')}")
        
        # Calcolo immediato del percorso
        df_lavoro = df_raw.copy()
        df_lavoro['giorni_passati'] = (oggi - df_lavoro['ultima visita']).dt.days
        urgenti = df_lavoro[(df_lavoro['giorni_passati'] >= df_lavoro
