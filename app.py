import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
from streamlit_js_eval import streamlit_js_eval

# --- 1. CONFIGURAZIONE E CALCOLI ---
st.set_page_config(page_title="Giro Visite Pro", layout="wide")

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    d = 2 * 6371 * asin(sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2))
    return d

@st.cache_data(ttl=60)
def fetch_data(url):
    try:
        df = pd.read_csv(url, sep=None, engine='python')
        df.columns = df.columns.str.strip().str.lower()
        for c in ['latitude', 'longitude', 'frequenza (giorni)']:
            if c in df.columns: df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '.'), errors='coerce')
        df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except: return pd.DataFrame()

# --- 2. INIZIALIZZAZIONE SESSION STATE ---
if 'df_master' not in st.session_state:
    st.session_state.df_master = fetch_data("https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132")
if 'start_lat' not in st.session_state: st.session_state.start_lat = 43.1924
if 'start_lon' not in st.session_state: st.session_state.start_lon = 13.5797
if 'h_inizio' not in st.session_state: st.session_state.h_inizio = time(9, 0)
if 'h_fine' not in st.session_state: st.session_state.h_fine = time(18, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'spostamenti' not in st.session_state: st.session_state.spostamenti = {}

# --- 3. LOGICA CALCOLO AGENDA ---
def genera_piano():
    oggi = datetime.now()
    lun_ref = oggi - timedelta(days=oggi.weekday())
    df_s = st.session_state.df_master.copy()
    agenda = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
    for s in range(1, 9):
        for g in range(5):
            dt_c = (lun_ref + timedelta(weeks=s-1, days=g)).date()
            dt_l = st.session_state.spostamenti.get(dt_c, dt_c)
            df_s['g_p'] = (pd.to_datetime(dt_l) - df_s['ultima visita']).dt.days
            urg = df_s[df_s['g_p'] >= df_s['frequenza (giorni)']].to_dict('records')
            o_s, p_s = datetime.combine(dt_c, st.session_state.h_inizio), (st.session_state.start_lat, st.session_state.start_lon)
            while urg:
                px = min(urg, key=lambda x: haversine(p_s[0], p_s[1], x['latitude'], x['longitude']))
                arr = o_s + timedelta(minutes=(haversine(p_s[0], p_s[1], px['latitude'], px['longitude'])/50)*60)
                fine = arr + timedelta(minutes=st.session_state.durata_v)
                if fine <= datetime.combine(dt_c, st.session_state.h_fine):
                    px['ora'] = arr.strftime("%H:%M")
                    agenda[f"Settimana {s}"][g].append(px)
                    df_s.loc[df_s['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(dt_l)
                    o_s, p_s = fine, (px['latitude'], px['longitude'])
                    urg.remove(px)
                else: break
    return agenda, lun_ref

# --- 4. INTERFACCIA TABS ---
if not st.session_state.df_master.empty:
    piano, lun_base = genera_piano()
    t1, t2, t3, t4 = st.tabs(["🚀 Giro Oggi", "📅 8 Settimane", "👤 Anagrafica", "⚙️ Parametri"])

    with t1:
        st.header(f"Giro di Oggi")
        idx_g = datetime.now().weekday()
        if idx_g < 5:
            tappe = piano["Settimana 1"][idx
