import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
from streamlit_js_eval import streamlit_js_eval

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Giro Visite 8 Settimane", layout="wide")

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371

@st.cache_data(ttl=60)
def load_data(url):
    df = pd.read_csv(url, sep=None, engine='python')
    df.columns = df.columns.str.strip().str.lower()
    for col in ['latitude', 'longitude', 'frequenza (giorni)']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce')
    df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
    return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])

# --- SIDEBAR: PARAMETRI ---
st.sidebar.title("🛠️ Impostazioni")
metodo_p = st.sidebar.radio("Partenza:", ["Digita Luogo", "GPS"])
start_lat, start_lon = 43.1924, 13.5797

if metodo_p == "Digita Luogo":
    luogo = st.sidebar.text_input("Città di partenza:", "Fermo")
    try:
        loc = Nominatim(user_agent="giro_app").geocode(luogo)
        if loc: start_lat, start_lon = loc.latitude, loc.longitude
    except: pass
elif metodo_p == "GPS":
    g = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps')
    if g: start_lat, start_lon = g['latitude'], g['longitude']

st.sidebar.subheader("⏰ Orario Lavoro")
h_inizio = st.sidebar.time_input("Inizio", time(9, 0))
h_fine = st.sidebar.time_input("Fine", time(18, 0))
durata_v = st.sidebar.slider("Durata visita (min)", 15, 120, 45)

# --- CARICAMENTO ---
try:
    df_raw = load_data("https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132")
    
    tab1, tab2 = st.tabs(["🚀 Giro di Oggi", "📅 Agenda 8 Settimane"])

    # --- TAB 1: OGGI (Classico) ---
    with tab1:
        st.header("Percorso per Oggi")
        if st.button("🚀 Calcola Giro Odierno"):
            # Logica giro singolo (omessa qui per brevità ma presente nel tuo file)
            st.info("Funzione calcolo giornaliero attiva.")

    # --- TAB 2: AGENDA 8 SETTIMANE (Novità) ---
    with tab2:
        st.header("🗓️ Pianificazione Strategica 8 Settimane")
        
        # 1. Scelta della settimana
        settimana_target = st.selectbox(
            "Quale settimana vuoi visualizzare?", 
            [f"Settimana {i}" for i in range(1, 9)],
            index=0
        )
        st.write(f"### Dettaglio: {settimana_target}")
        
        # 2. Simulazione 8 settimane
        oggi = datetime.now()
        lunedi_corrente = oggi - timedelta(days=oggi.weekday())
        
        df_sim = df_raw.copy()
        agenda_completa = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
        
        # Algoritmo di proiezione
        for s in range(1, 9):
            for g in range(5): # Lun-Ven
                data_sim = lunedi_corrente + timedelta(weeks=s-1, days=g)
                # Calcola chi è scaduto in questa data simulata
                df_sim['giorni_da_visita'] = (pd.to_datetime(data_sim) - df_sim['ultima visita']).dt.days
                urgenti = df_sim[df_sim['giorni_da_visita'] >= df_sim['frequenza (giorni)']].to_dict('records')
                
                # Riempiamo la giornata simulata
                pos_sim = (start_lat, start_lon)
                ora_sim = datetime.combine(data_sim, h_inizio)
                limite_sim = datetime.combine(data_sim, h_fine)
                
                while urgenti:
                    prox = min(urgenti, key=lambda x: haversine(pos_sim[0], pos_sim[1], x['latitude'], x['longitude']))
                    dist = haversine(pos_sim[0], pos_sim[1], prox['latitude'], prox['longitude'])
                    arrivo = ora_sim + timedelta(minutes=(dist/50)*60)
                    partenza = arrivo + timedelta(minutes=durata_v)
                    
                    if partenza <= limite_sim:
                        prox['orario'] = arrivo.strftime("%H:%M")
                        agenda_completa[f"Settimana {s}"][g].append(prox)
                        # Aggiorna l'ultima visita nella simulazione
                        df_sim.loc[df_sim['nome cliente'] == prox['nome cliente'], 'ultima visita'] = pd.to_datetime(data_sim)
                        ora_sim, pos_sim = partenza, (prox['latitude'], prox['longitude'])
                        urgenti.remove(prox)
                    else: break

        # 3. Visualizzazione a 5 Colonne per la settimana scelta
        nomi_g = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
        cols = st.columns(5)
        
        sett_dati = agenda_completa[settimana_target]
        
        for i, col in enumerate(cols):
            with col:
                data_g = lunedi_corrente + timedelta(weeks=int(settimana_target.split()[-1])-1, days=i)
                st.markdown(f"**{nomi_g[i]}**")
                st.caption(data_g.strftime("%d/%m"))
                st.divider()
                
                tappe = sett_dati[i]
                if tappe:
                    for t in tappe:
                        with st.container(border=True):
                            st.markdown(f"🕒 **{t['orario']}**")
                            st.write(f"{t['nome cliente']}")
                            st.caption(f"📍 {t['indirizzo'][:15]}...")
