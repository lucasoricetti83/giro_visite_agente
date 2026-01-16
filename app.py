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

# --- INIZIALIZZAZIONE STATO (Session State) ---
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
    # --- CREAZIONE TAB NAVIGAZIONE ---
    tab_oggi, tab_settimana, tab_parametri = st.tabs(["🚀 Giro di Oggi", "📅 Agenda 8 Settimane", "⚙️ Parametri"])

    # --- TAB 3: PARAMETRI ---
    with tab_parametri:
        st.header("⚙️ Impostazioni e Sposta Giorno")
        col_p1, col_p2 = st.columns(2)
        
        with col_p1:
            st.subheader("📍 Partenza e Orari")
            metodo = st.radio("Punto di partenza:", ["GPS", "Cerca Luogo"])
            if metodo == "GPS":
                g = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps_update')
                if g: 
                    st.session_state.start_lat, st.session_state.start_lon = g['latitude'], g['longitude']
            else:
                citta = st.text_input("Inserisci Comune:", "Fermo")
                if st.button("Trova Coordinate"):
                    loc = Nominatim(user_agent="giro_agente").geocode(citta)
                    if loc: 
                        st.session_state.start_lat, st.session_state.start_lon = loc.latitude, loc.longitude
                        st.success(f"Coordinate aggiornate per {citta}")

            st.session_state.h_inizio = st.time_input("Inizio Lavoro", st.session_state.h_inizio)
            st.session_state.h_fine = st.time_input("Fine Lavoro", st.session_state.h_fine)
            st.session_state.durata_v = st.slider("Durata Visita (min)", 15, 120, st.session_state.durata_v)

        with col_p2:
            st.subheader("🔄 Funzione Sposta Giorno")
            st.write("Scambia le visite tra due date specifiche.")
            d_da = st.date_input("Giorno da spostare:", datetime.now())
            d_a = st.date_input("Sposta al giorno:", datetime.now() + timedelta(days=1))
            
            if st.button("Conferma Scambio"):
                st.session_state.spostamenti[d_da] = d_a
                st.session_state.spostamenti[d_a] = d_da
                st.toast("Giorno spostato con successo!")

            if st.session_state.spostamenti:
                st.write("---")
                if st.button("Reset tutti gli spostamenti"):
                    st.session_state.spostamenti = {}
                    st.rerun()

    # --- LOGICA CALCOLO AGENDA (Simulazione) ---
    def calcola_piano_completo():
        oggi = datetime.now()
        lunedi_corrente = oggi - timedelta(days=oggi.weekday())
        df_sim = df_raw.copy()
        piano = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
        
        for s in range(1, 9):
            for g in range(5):
                data_attuale = (lunedi_corrente + timedelta(weeks=s-1, days=g)).date()
                # Verifica se il giorno è stato scambiato logicamente
                data_da_usare = st.session_state.spostamenti.get(data_attuale, data_attuale)
                
                df_sim['giorni_p'] = (pd.to_datetime(data_da_usare) - df_sim['ultima visita']).dt.days
                urg = df_sim[df_sim['giorni_p'] >= df_sim['frequenza (giorni)']].to_dict('records')
                
                ora_s, pos_s = datetime.combine(data_attuale, st.session_state.h_inizio), (st.session_state.start_lat, st.session_state.start_lon)
                limite_s = datetime.combine(data_attuale, st.session_state.h_fine)
                
                while urg:
                    p = min(urg, key=lambda x: haversine(pos_s[0], pos_s[1], x['latitude'], x['longitude']))
                    dist = haversine(pos_s[0], pos_s[1], p['latitude'], p['longitude'])
                    arrivo = ora_s + timedelta(minutes=(dist/50)*60)
                    fine = arrivo + timedelta(minutes=st.session_state.durata_v)
                    
                    if fine <= limite_s:
                        info = p.copy()
                        info['ora_arrivo'] = arrivo.strftime("%H:%M")
                        piano[f"Settimana {s}"][g].append(info)
                        # Aggiornamento simulato riga 118 (fissata)
                        df_sim.loc[df_sim['nome cliente'] == p['nome cliente'], 'ultima visita'] = pd.to_datetime(data_da_usare)
                        ora_s, pos_s = fine, (p['latitude'], p['longitude'])
                        urg.remove(p)
                    else: break
        return piano, lunedi_corrente

    agenda_totale, lun_ref = calcola_piano_completo()

    # --- TAB 1: GIRO DI OGGI ---
    with tab_oggi:
        oggi_dt = datetime.now()
        st.header(f"📍 Oggi: {oggi_dt.strftime('%d/%m/%Y')}")
        idx_g = oggi_dt.weekday()
        
        if idx_g < 5:
            tappe_oggi = agenda_totale["Settimana 1"][idx_g]
            if tappe_oggi:
                col_lista, col_mappa = st.columns([1, 2])
                with col_lista:
                    for t in tappe_oggi:
                        with st.container(border=True):
                            st.write(f"🕒 **{t['ora_arrivo']}**")
                            st.write(f"**{t['nome cliente']}**")
                            st.link_button("🚗 Naviga", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}", use_container_width=True)
                with col_mappa:
                    st.map(pd.DataFrame(tappe_oggi).rename(columns={'latitude':'lat','longitude':'lon'}))
            else: st.info("Nessuna visita per oggi.")
        else: st.write("Weekend: controlla l'agenda per Lunedì!")

    # --- TAB 2: AGENDA 8 SETTIMANE (5 COLONNE) ---
    with tab_settimana:
        sett_scelta = st.selectbox("Seleziona Settimana:", [f"Settimana {i}" for i in range(1, 9)])
        nomi_g = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
        cols_w = st.columns(5)
        
        for i, col_u in enumerate(cols_w):
            with col_u:
                data_g = (lun_ref + timedelta(weeks=int(sett_scelta.split()[-1])-1, days=i)).date()
                # Verifica scambio
                if data_g in st.session_state.spostamenti:
                    st.warning(f"🔄 {nomi_g[i]}")
                else:
                    st.subheader(nomi_g[i])
                st.caption(data_g.strftime("%d/%m"))
                st.divider()
                
                for vis in agenda_totale[sett_scelta][i]:
                    with st.container(border=True):
                        st.caption(vis['ora_arrivo'])
                        st.markdown(f"**{vis['nome cliente']}**")

else:
    st.error("Errore nel caricamento del Foglio Google.")
