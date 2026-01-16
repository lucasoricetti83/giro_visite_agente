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
    df = pd.read_csv(url, sep=None, engine='python')
    df.columns = df.columns.str.strip().str.lower()
    for col in ['latitude', 'longitude', 'frequenza (giorni)']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce')
    df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
    return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])

# --- LOGICA DELL'APPLICAZIONE ---
try:
    # 1. Caricamento Dati
    URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132"
    df_raw = load_data(URL_FOGLIO)

    # 2. Sidebar - Impostazioni
    st.sidebar.title("🛠️ Impostazioni")
    
    st.sidebar.subheader("📍 Partenza")
    metodo_p = st.sidebar.radio("Scegli come impostare la partenza:", ["Digita Luogo", "GPS"])
    start_lat, start_lon = 43.1924, 13.5797

    if metodo_p == "Digita Luogo":
        luogo_input = st.sidebar.text_input("Inserisci città o indirizzo:", "Fermo")
        if luogo_input:
            try:
                geolocator = Nominatim(user_agent="giro_agente_v1")
                loc_geop = geolocator.geocode(luogo_input)
                if loc_geop:
                    start_lat, start_lon = loc_geop.latitude, loc_geop.longitude
                    st.sidebar.success(f"Posizione impostata su: {luogo_input}")
            except:
                st.sidebar.warning("Servizio di ricerca momentaneamente lento...")

    elif metodo_p == "GPS":
        g_coords = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps_loc')
        if g_coords:
            start_lat, start_lon = g_coords['latitude'], g_coords['longitude']
            st.sidebar.success("GPS Rilevato!")

    st.sidebar.subheader("⏰ Orario di Lavoro")
    h_inizio = st.sidebar.time_input("Inizio turno", time(9, 0))
    h_fine = st.sidebar.time_input("Fine turno", time(18, 0))
    durata_v = st.sidebar.slider("Durata visita (minuti)", 15, 120, 45)

    # 3. Layout Principale (Tabs)
    tab1, tab2 = st.tabs(["🚀 Giro di Oggi", "📅 Agenda 8 Settimane"])

    # --- TAB 1: GIRO GIORNALIERO ---
    with tab1:
        st.header("Pianificazione Giornaliera")
        if st.button("🚀 Calcola Giro per Oggi"):
            oggi = datetime.now()
            df_raw['giorni_passati'] = (oggi - df_raw['ultima visita']).dt.days
            urgenti = df_raw[(df_raw['giorni_passati'] >= df_raw['frequenza (giorni)']) | (df_raw['visitare'].astype(str).str.upper() == 'SI')].to_dict('records')
            
            giro_oggi = []
            ora_attuale = datetime.combine(oggi.date(), h_inizio)
            limite_f = datetime.combine(oggi.date(), h_fine)
            pos_attuale = (start_lat, start_lon)

            while urgenti:
                prox = min(urgenti, key=lambda x: haversine(pos_attuale[0], pos_attuale[1], x['latitude'], x['longitude']))
                dist = haversine(pos_attuale[0], pos_attuale[1], prox['latitude'], prox['longitude'])
                tempo_v = (dist / 50) * 60
                arrivo = ora_attuale + timedelta(minutes=tempo_v)
                partenza = arrivo + timedelta(minutes=durata_v)
                
                if partenza <= limite_f:
                    prox['ora_arrivo'] = arrivo.strftime("%H:%M")
                    giro_oggi.append(prox)
                    ora_attuale, pos_attuale = partenza, (prox['latitude'], prox['longitude'])
                    urgenti.remove(prox)
                else:
                    break

            if giro_oggi:
                c1, c2 = st.columns([1, 2])
                with c1:
                    for i, r in enumerate(giro_oggi):
                        with st.container(border=True):
                            st.write(f"**{i+1}. {r['nome cliente']}**")
                            st.caption(f"🕒 Arrivo: {r['ora_arrivo']}")
                            st.link_button("🚗 Naviga", f"https://www.google.com/maps/dir/?api=1&destination={r['latitude']},{r['longitude']}")
                with c2:
                    st.map(pd.DataFrame(giro_oggi).rename(columns={'latitude':'lat','longitude':'lon'}))
            else:
                st.warning("Nessun cliente programmabile oggi con questi orari.")

    # --- TAB 2: AGENDA 8 SETTIMANE (5 COLONNE) ---
    with tab2:
        st.header("Pianificazione Strategica 8 Settimane")
        
        # Selezione settimana
        settimana_target = st.selectbox("Seleziona la settimana da visualizzare:", [f"Settimana {i}" for i in range(1, 9)])
        
        # Simulazione
        data_base = datetime.now()
        lunedi_corrente = data_base - timedelta(days=data_base.weekday())
        
        df_sim = df_raw.copy()
        agenda_8w = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
        
        # Ciclo di simulazione per 8 settimane
        for s in range(1, 9):
            for g in range(5): # Lun-Ven
                data_sim = lunedi_corrente + timedelta(weeks=s-1, days=g)
                df_sim['giorni_da_visita'] = (pd.to_datetime(data_sim) - df_sim['ultima visita']).dt.days
                urgenti_sim = df_sim[df_sim['giorni_da_visita'] >= df_sim['frequenza (giorni)']].to_dict('records')
                
                ora_sim = datetime.combine(data_sim, h_inizio)
                limite_sim = datetime.combine(data_sim, h_fine)
                pos_sim = (start_lat, start_lon)
                
                while urgenti_sim:
                    prox = min(urgenti_sim, key=lambda x: haversine(pos_sim[0], pos_sim[1], x['latitude'], x['longitude']))
                    dist = haversine(pos_sim[0], pos_sim[1], prox['latitude'], prox['longitude'])
                    arrivo_sim = ora_sim + timedelta(minutes=(dist/50)*60)
                    partenza_sim = arrivo_sim + timedelta(minutes=durata_v)
                    
                    if partenza_sim <= limite_sim:
                        prox_info = prox.copy()
                        prox_info['ora_sim'] = arrivo_sim.strftime("%H:%M")
                        agenda_8w[f"Settimana {s}"][g].append(prox_info)
                        # Aggiorna ultima visita fittizia
                        df_sim.loc[df_sim['nome cliente'] == prox['nome cliente'], 'ultima visita'] = pd.to_datetime(data_sim)
                        ora_sim, pos_sim = partenza_sim, (prox['latitude'], prox['longitude'])
                        urgenti_sim.remove(prox)
                    else:
                        break

        # Visualizzazione a 5 colonne della settimana scelta
        nomi_giorni = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
        col_list = st.columns(5)
        
        dati_settimana = agenda_8w[settimana_target]
        
        for idx, col_ui in enumerate(col_list):
            with col_ui:
                data_titolo = lunedi_corrente + timedelta(weeks=int(settimana_target.split()[-1])-1, days=idx)
                st.markdown(f"### {nomi_giorni[idx]}")
                st.caption(data_titolo.strftime("%d/%m/%Y"))
                st.divider()
                
                visite_giorno = dati_settimana[idx]
                if visite_giorno:
                    for v in visite_giorno:
                        with st.container(border=True):
                            st.markdown(f"🕒 **{v['ora_sim']}**")
                            st.write(f"{v['nome cliente']}")
                            st.caption(f"📍 {v['indirizzo'][:20]}...")
                else:
                    st.write("---")
                    st.caption("Nessuna visita prevista")

except Exception as e:
    st.error(f"⚠️ Si è verificato un errore: {e}")
    st.info("Controlla che i nomi delle colonne nel Foglio Google siano corretti.")
