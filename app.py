import streamlit as st
import pandas as pd
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
from streamlit_js_eval import streamlit_js_eval # Nuova libreria per il GPS

# --- FUNZIONI ---
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371

st.set_page_config(page_title="Giro Visite GPS", layout="wide")
st.title("🚗 Giro Visite con GPS")

URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132"

@st.cache_data(ttl=60)
def load_data(url):
    df = pd.read_csv(url, sep=None, engine='python')
    df.columns = df.columns.str.strip().str.lower()
    for col in ['latitude', 'longitude', 'frequenza (giorni)']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce')
    df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
    return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])

try:
    df_raw = load_data(URL_FOGLIO)
    
    st.sidebar.header("📍 Partenza")
    
    # --- LOGICA GPS ---
    loc = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='get_location')
    
    if st.sidebar.button("🎯 Rileva Posizione GPS"):
        st.sidebar.info("Rilevamento in corso... assicurati di aver dato il permesso al browser.")

    # Se il GPS restituisce le coordinate, le usiamo come default
    default_lat = 43.1924 # Default Fermo/Monte San Pietrangeli
    default_lon = 13.5797
    
    if loc:
        default_lat = loc['latitude']
        default_lon = loc['longitude']
        st.sidebar.success(f"Posizione rilevata: {default_lat:.4f}, {default_lon:.4f}")

    start_lat = st.sidebar.number_input("Latitudine Partenza", value=default_lat, format="%.6f")
    start_lon = st.sidebar.number_input("Longitudine Partenza", value=default_lon, format="%.6f")

    # --- CALCOLO GIRO ---
    num_max = st.sidebar.slider("Clienti da visitare", 1, 15, 8)
    
    oggi = datetime.now()
    df_raw['giorni_passati'] = (oggi - df_raw['ultima visita']).dt.days
    clienti_urgenti = df_raw[
        (df_raw['giorni_passati'] >= df_raw['frequenza (giorni)']) | 
        (df_raw['visitare'].astype(str).str.upper() == 'SI')
    ].copy()

    if st.button("🚀 Calcola il miglior giro da qui"):
        if not clienti_urgenti.empty:
            giro = []
            rimanenti = clienti_urgenti.to_dict('records')
            pos_attuale = (start_lat, start_lon)

            while rimanenti and len(giro) < num_max:
                prossimo = min(rimanenti, key=lambda x: haversine(pos_attuale[0], pos_attuale[1], x['latitude'], x['longitude']))
                dist = haversine(pos_attuale[0], pos_attuale[1], prossimo['latitude'], prossimo['longitude'])
                prossimo['dist_tappa'] = dist
                giro.append(prossimo)
                pos_attuale = (prossimo['latitude'], prossimo['longitude'])
                rimanenti.remove(prossimo)

            st.success(f"Percorso calcolato partendo dalla tua posizione attuale!")
            
            col1, col2 = st.columns([1, 1])
            with col1:
                for i, r in enumerate(giro):
                    with st.container(border=True):
                        st.write(f"**{i+1}. {r['nome cliente']}** ({r['dist_tappa']:.1f} km)")
                        nav_url = f"https://www.google.com/maps/dir/?api=1&origin={start_lat},{start_lon}&destination={r['latitude']},{r['longitude']}&travelmode=driving"
                        st.link_button(f"Vai a {r['nome cliente']}", nav_url, use_container_width=True)
            
            with col2:
                map_df = pd.DataFrame(giro).rename(columns={'latitude': 'lat', 'longitude': 'lon'})
                st.map(map_df[['lat', 'lon']])
        else:
            st.warning("Nessun cliente da visitare trovato.")

except Exception as e:
    st.error(f"Errore: {e}")
