import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
from streamlit_js_eval import streamlit_js_eval

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Giro Visite & CRM", layout="wide")

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
    except:
        return pd.DataFrame()

# --- INIZIALIZZAZIONE STATO ---
if 'start_lat' not in st.session_state: st.session_state.start_lat = 43.1924
if 'start_lon' not in st.session_state: st.session_state.start_lon = 13.5797
if 'h_inizio' not in st.session_state: st.session_state.h_inizio = time(9, 0)
if 'h_fine' not in st.session_state: st.session_state.h_fine = time(18, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'spostamenti' not in st.session_state: st.session_state.spostamenti = {}
if 'df_master' not in st.session_state:
    URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132"
    st.session_state.df_master = load_data(URL_FOGLIO)

# --- NAVIGAZIONE TABS ---
tab_oggi, tab_settimana, tab_anagrafica, tab_parametri = st.tabs([
    "🚀 Giro di Oggi", 
    "📅 Agenda 8 Settimane", 
    "👤 Anagrafica",
    "⚙️ Parametri"
])

# --- TAB 3: ANAGRAFICA (NUOVO) ---
with tab_anagrafica:
    st.header("👤 Gestione Anagrafica Clienti")
    
    nomi_clienti = sorted(st.session_state.df_master['nome cliente'].unique())
    cliente_scelto = st.selectbox("Seleziona un cliente da visualizzare/modificare:", nomi_clienti)
    
    if cliente_scelto:
        # Recupero dati cliente
        idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == cliente_scelto].index[0]
        c_dati = st.session_state.df_master.loc[idx]
        
        with st.form("form_cliente"):
            st.subheader(f"Scheda: {cliente_scelto}")
            col_a1, col_a2 = st.columns(2)
            
            with col_a1:
                nuovo_nome = st.text_input("Nome Cliente", c_dati['nome cliente'])
                nuovo_indirizzo = st.text_input("Indirizzo", c_dati['indirizzo'])
                nuova_freq = st.number_input("Frequenza Visite (giorni)", value=int(c_dati['frequenza (giorni)']))
            
            with col_a2:
                nuova_lat = st.number_input("Latitudine", value=float(c_dati['latitude']), format="%.6f")
                nuova_lon = st.number_input("Longitudine", value=float(c_dati['longitude']), format="%.6f")
                nuova_data = st.date_input("Ultima Visita", c_dati['ultima visita'].date())
            
            # Possibilità di aggiungere note (parametro extra)
            note = st.text_area("Note e Promemoria", "")
            
            if st.form_submit_button("Salva Modifiche Locale"):
                # Aggiornamento dello stato locale
                st.session_state.df_master.at[idx, 'nome cliente'] = nuovo_nome
                st.session_state.df_master.at[idx, 'indirizzo'] = nuovo_indirizzo
                st.session_state.df_master.at[idx, 'frequenza (giorni)'] = nuova_freq
                st.session_state.df_master.at[idx, 'latitude'] = nuova_lat
                st.session_state.df_master.at[idx, 'longitude'] = nuova_lon
                st.session_state.df_master.at[idx, 'ultima visita'] = pd.to_datetime(nuova_data)
                st.success(f"Dati di {cliente_scelto} aggiornati nell'app!")
                st.info("Nota: Le modifiche sono attive nell'app ma non ancora scritte sul Foglio Google.")

# --- TAB 4: PARAMETRI ---
with tab_parametri:
    st.header("⚙️ Impostazioni")
    # ... (Stessa logica dei parametri precedente)
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.subheader("📍 Partenza e Orari")
        # GPS o Cerca Luogo
        metodo = st.radio("Punto di partenza:", ["GPS", "Cerca Luogo"], key="metodo_p")
        if metodo == "GPS":
            g = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps_anag')
            if g: 
                st.session_state.start_lat, st.session_state.start_lon = g['latitude'], g['longitude']
        st.session_state.h_inizio = st.time_input("Inizio Lavoro", st.session_state.h_inizio)
        st.session_state.h_fine = st.time_input("Fine Lavoro", st.session_state.h_fine)
    with col_p2:
        st.subheader("🔄 Sposta Giorno")
        # Logica scambio giorni...

# --- LOGICA CALCOLO (Usa df_master aggiornato) ---
def calcola_piano():
    df_sim = st.session_state.df_master.copy()
    # ... (Logica di calcolo 8 settimane e giro oggi)
    # [Qui andrebbe inserita la logica di calcolo che abbiamo già perfezionato]
    return # ...

# [Restante parte del codice per TAB OGGI e TAB SETTIMANA]
