import streamlit as st
import pandas as pd
from datetime import datetime
from math import radians, cos, sin, asin, sqrt

# --- FUNZIONI MATEMATICHE ---
def haversine(lat1, lon1, lat2, lon2):
    """Calcola la distanza in km tra due punti"""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371

st.set_page_config(page_title="Pianificatore Giro Visite", layout="wide")
st.title("🚗 Il Mio Giro Visite Ottimizzato")

URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132"

@st.cache_data(ttl=60)
def load_data(url):
    df = pd.read_csv(url, sep=None, engine='python')
    df.columns = df.columns.str.strip().str.lower()
    for col in ['latitude', 'longitude', 'frequenza (giorni)']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.').str.strip(), errors='coerce')
    df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
    return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])

try:
    df_raw = load_data(URL_FOGLIO)
    
    # --- SIDEBAR: IMPOSTAZIONI GIRO ---
    st.sidebar.header("⚙️ Impostazioni Giro")
    num_max_visite = st.sidebar.slider("Numero massimo di visite", 1, 15, 8)
    
    # Coordinate di partenza (Default: Fermo/Ascoli)
    st.sidebar.subheader("📍 Punto di Partenza")
    start_lat = st.sidebar.number_input("Latitudine Partenza", value=43.193, format="%.4f")
    start_lon = st.sidebar.number_input("Longitudine Partenza", value=13.579, format="%.4f")

    # --- CALCOLO URGENZA ---
    oggi = datetime.now()
    df_raw['giorni_passati'] = (oggi - df_raw['ultima visita']).dt.days
    
    # Clienti che hanno superato la frequenza o che hai già segnato come "SI"
    clienti_urgenti = df_raw[
        (df_raw['giorni_passati'] >= df_raw['frequenza (giorni)']) | 
        (df_raw['visitare'].astype(str).str.upper() == 'SI')
    ].copy()

    st.write(f"### 🔎 Clienti che necessitano di visita: {len(clienti_urgenti)}")

    if st.button("🚀 Genera Giro Ottimizzato di Oggi"):
        if not clienti_urgenti.empty:
            # --- ALGORITMO DI OTTIMIZZAZIONE ---
            giro = []
            rimanenti = clienti_urgenti.to_dict('records')
            pos_attuale = (start_lat, start_lon)

            while rimanenti and len(giro) < num_max_visite:
                # Trova il più vicino alla posizione attuale
                prossimo = min(rimanenti, key=lambda x: haversine(pos_attuale[0], pos_attuale[1], x['latitude'], x['longitude']))
                dist = haversine(pos_attuale[0], pos_attuale[1], prossimo['latitude'], prossimo['longitude'])
                
                prossimo['distanza_tappa'] = dist
                giro.append(prossimo)
                pos_attuale = (prossimo['latitude'], prossimo['longitude'])
                rimanenti.remove(prossimo)

            df_giro = pd.DataFrame(giro)

            # --- VISUALIZZAZIONE RISULTATI ---
            st.success(f"Giro generato con {len(df_giro)} tappe!")
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.write("### 📋 Ordine delle Visite")
                for idx, row in df_giro.iterrows():
                    with st.container(border=True):
                        st.markdown(f"**Tappa {idx+1}: {row['nome cliente']}**")
                        st.caption(f"📍 {row['indirizzo']} (a {row['distanza_tappa']:.1f} km)")
                        nav_url = f"https://www.google.com/maps/dir/?api=1&destination={row['latitude']},{row['longitude']}"
                        st.link_button("🚗 Vai a questa tappa", nav_url, use_container_width=True)

            with col2:
                st.write("### 📍 Mappa del Percorso")
                map_df = df_giro.rename(columns={'latitude': 'lat', 'longitude': 'lon'})
                st.map(map_df[['lat', 'lon']])
        else:
            st.warning("Nessun cliente urgente trovato. Controlla le date nel foglio Google.")

except Exception as e:
    st.error(f"Errore: {e}")
