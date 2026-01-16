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
    except:
        return pd.DataFrame()

# --- INIZIALIZZAZIONE SESSION STATE PER PARAMETRI ---
if 'start_lat' not in st.session_state: st.session_state.start_lat = 43.1924
if 'start_lon' not in st.session_state: st.session_state.start_lon = 13.5797
if 'h_inizio' not in st.session_state: st.session_state.h_inizio = time(9, 0)
if 'h_fine' not in st.session_state: st.session_state.h_fine = time(18, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'spostamenti' not in st.session_state: st.session_state.spostamenti = {}

# --- CARICAMENTO DATI ---
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132"
df_raw = load_data(URL_FOGLIO)

if not df_raw.empty:
    # --- NAVBAR PRINCIPALE ---
    tab_oggi, tab_settimana, tab_parametri = st.tabs(["🚀 Giro di Oggi", "📅 Agenda 8 Settimane", "⚙️ Parametri"])

    # --- TAB 3: PARAMETRI (SPOSTATO DALLA SIDEBAR) ---
    with tab_parametri:
        st.header("⚙️ Configurazione")
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("📍 Posizione e Orari")
            metodo = st.radio("Metodo partenza:", ["GPS", "Digita Luogo"])
            if metodo == "GPS":
                g = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps_p')
                if g: 
                    st.session_state.start_lat = g['latitude']
                    st.session_state.start_lon = g['longitude']
            else:
                luogo = st.text_input("Città:", "Fermo")
                if st.button("Aggiorna Luogo"):
                    try:
                        loc = Nominatim(user_agent="giro_v4").geocode(luogo)
                        if loc:
                            st.session_state.start_lat = loc.latitude
                            st.session_state.start_lon = loc.longitude
                    except: st.error("Errore geolocalizzazione")
            
            st.session_state.h_inizio = st.time_input("Inizio lavoro", st.session_state.h_inizio)
            st.session_state.h_fine = st.time_input("Fine lavoro", st.session_state.h_fine)
            st.session_state.durata_v = st.slider("Durata visita (min)", 15, 120, st.session_state.durata_v)

        with c2:
            st.subheader("🔄 Sposta Giro")
            st.write("Usa questa funzione per scambiare le visite tra due giorni.")
            data_da = st.date_input("Sposta il giro del giorno:", datetime.now())
            data_a = st.date_input("Al giorno:", datetime.now() + timedelta(days=1))
            
            if st.button("Conferma Scambio Giorno"):
                st.session_state.spostamenti[data_da] = data_a
                st.session_state.spostamenti[data_a] = data_da
                st.success(f"Giro scambiato tra {data_da.strftime('%d/%m')} e {data_a.strftime('%d/%m')}")
            
            if st.session_state.spostamenti and st.button("Reset Spostamenti"):
                st.session_state.spostamenti = {}
                st.rerun()

    # --- LOGICA CALCOLO (Comune a Tab 1 e 2) ---
    oggi = datetime.now()
    lun_corrente = oggi - timedelta(days=oggi.weekday())

    def genera_agenda_simulata(df, start_dt, n_settimane=8):
        df_sim = df.copy()
        agenda = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
        
        for s in range(1, n_settimane + 1):
            for g in range(5):
                data_attuale = lun_corrente + timedelta(weeks=s-1, days=g)
                # CONTROLLO SPOSTAMENTO
                data_logica = st.session_state.spostamenti.get(data_attuale.date(), data_attuale.date())
                
                df_sim['g_pass'] = (pd.to_datetime(data_logica) - df_sim['ultima visita']).dt.days
                urg = df_sim[df_sim['g_pass'] >= df_sim['frequenza (giorni)']].to_dict('records')
                
                o_sim, p_sim = datetime.combine(data_attuale, st.session_state.h_inizio), (st.session_state.start_lat, st.session_state.start_lon)
                while urg:
                    px = min(urg, key=lambda x: haversine(p_sim[0], p_sim[1], x['latitude'], x['longitude']))
                    dist = haversine(p_sim[0], p_sim[1], px['latitude'], px['longitude'])
                    arr = o_sim + timedelta(minutes=(dist/50)*60)
                    part = arr + timedelta(minutes=st.session_state.durata_v)
                    
                    if part <= datetime.combine(data_attuale, st.session_state.h_fine):
                        info = px.copy(); info['ora'] = arr.strftime("%H:%M")
                        agenda[f"Settimana {s}"][g].append(info)
                        df_sim.loc[df_sim['nome cliente'] == px['nome
