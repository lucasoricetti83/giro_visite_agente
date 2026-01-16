import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
from streamlit_js_eval import streamlit_js_eval

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Giro Visite & CRM Pro", layout="wide")

# --- FUNZIONI DI CALCOLO ---
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371

@st.cache_data(ttl=60)
def fetch_data(url):
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

# --- INIZIALIZZAZIONE SESSION STATE ---
if 'start_lat' not in st.session_state: st.session_state.start_lat = 43.1924
if 'start_lon' not in st.session_state: st.session_state.start_lon = 13.5797
if 'h_inizio' not in st.session_state: st.session_state.h_inizio = time(9, 0)
if 'h_fine' not in st.session_state: st.session_state.h_fine = time(18, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'spostamenti' not in st.session_state: st.session_state.spostamenti = {}

URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132"

if 'df_master' not in st.session_state:
    st.session_state.df_master = fetch_data(URL_FOGLIO)

# --- LOGICA CALCOLO AGENDA ---
def calcola_agenda_completa():
    oggi = datetime.now()
    lunedi_ref = oggi - timedelta(days=oggi.weekday())
    df_sim = st.session_state.df_master.copy()
    piano = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
    
    for s in range(1, 9):
        for g in range(5):
            data_corrente = (lunedi_ref + timedelta(weeks=s-1, days=g)).date()
            data_logica = st.session_state.spostamenti.get(data_corrente, data_corrente)
            
            df_sim['g_passati'] = (pd.to_datetime(data_logica) - df_sim['ultima visita']).dt.days
            urg = df_sim[df_sim['g_passati'] >= df_sim['frequenza (giorni)']].to_dict('records')
            
            o_sim = datetime.combine(data_corrente, st.session_state.h_inizio)
            limite_sim = datetime.combine(data_corrente, st.session_state.h_fine)
            p_sim = (st.session_state.start_lat, st.session_state.start_lon)
            
            while urg:
                px = min(urg, key=lambda x: haversine(p
