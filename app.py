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
        # Pulizia numerica
        for col in ['latitude', 'longitude', 'frequenza (giorni)']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce')
        # Pulizia date
        df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except Exception as e:
        st.error(f"Errore nel caricamento del foglio: {e}")
        return pd.DataFrame()

# --- LOGICA APPLICATIVA ---
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132"
df_raw = load_data(URL_FOGLIO)

if not df_raw.empty:
    # --- SIDEBAR ---
    st.sidebar.title("⚙️ Parametri")
    
    st.sidebar.subheader("📍 Partenza")
    metodo_p = st.sidebar.radio("Imposta punto di partenza:", ["GPS", "Digita Luogo"])
    start_lat, start_lon = 43.1924, 13.5797

    if metodo_p == "GPS":
        g_coords = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps_loc')
        if g_coords:
            start_lat, start_lon = g_coords['latitude'], g_coords['longitude']
            st.sidebar.success("GPS Rilevato")
    else:
        luogo_in = st.sidebar.text_input("Città/Indirizzo:", "Fermo")
        if luogo_in:
            try:
                geolocator = Nominatim(user_agent="giro_agente_v3")
                loc = geolocator.geocode(luogo_in)
                if loc: start_lat, start_lon = loc.latitude, loc.longitude
            except: pass

    st.sidebar.subheader("⏰ Orari Lavoro")
    h_inizio = st.sidebar.time_input("Inizio", time(9, 0))
    h_fine = st.sidebar.time_input("Fine", time(18, 0))
    durata_v = st.sidebar.slider("Durata visita (min)", 15, 120, 45)

    # --- TABS ---
    tab1, tab2 = st.tabs(["🚀 Giro di Oggi", "📅 Agenda 8 Settimane"])

    # --- TAB 1: GIRO DI OGGI (AUTOMATICO) ---
    with tab1:
        oggi = datetime.now()
        st.header(f"Agenda del Giorno: {oggi.strftime('%d/%m/%Y')}")
        
        # Filtro urgenza corretto (Risolve SyntaxError linea 76)
        df_lavoro = df_raw.copy()
        df_lavoro['giorni_passati'] = (oggi - df_lavoro['ultima visita']).dt.days
        
        # Selezione clienti: o scaduti o con "SI" nel foglio
        urgenti = df_lavoro[
            (df_lavoro['giorni_passati'] >= df_lavoro['frequenza (giorni)']) | 
            (df_lavoro['visitare'].astype(str).str.upper() == 'SI')
        ].to_dict('records')
        
        giro_oggi = []
        ora_attuale = datetime.combine(oggi.date(), h_inizio)
        limite_f = datetime.combine(oggi.date(), h_fine)
        pos_attuale = (start_lat, start_lon)

        # Calcolo sequenza
        while urgenti:
            prox = min(urgenti, key=lambda x: haversine(pos_attuale[0], pos_attuale[1], x['latitude'], x['longitude']))
            dist = haversine(pos_attuale[0], pos_attuale[1], prox['latitude'], prox['longitude'])
            tempo_v = (dist / 50) * 60  # 50km/h media
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
                st.subheader("📍 Cronologia Visite")
                for i, r in enumerate(giro_oggi):
                    with st.container(border=True):
                        st.markdown(f"**{r['ora_arrivo']}** - {r['nome cliente']}")
                        st.caption(f"🏠 {r['indirizzo']}")
                        st.link_button(f"🚀 Vai da {r['nome cliente']}", f"https://www.google.com/maps/dir/?api=1&destination={r['latitude']},{r['longitude']}", use_container_width=True)
            with c2:
                st.subheader("🗺️ Mappa")
                st.map(pd.DataFrame(giro_oggi).rename(columns={'latitude':'lat','longitude':'lon'}), use_container_width=True)
        else:
            st.info("Nessuna visita urgente per oggi. Controlla le frequenze nel foglio Google.")

    # --- TAB 2: AGENDA 8 SETTIMANE (5 COLONNE) ---
    with tab2:
        st.header("Pianificazione Strategica")
        settimana_scelta = st.selectbox("Scegli settimana:", [f"Settimana {i}" for i in range(1, 9)])
        
        lun_corrente = oggi - timedelta(days=oggi.weekday())
        df_sim = df_raw.copy()
        agenda_8w = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
        
        # Simulazione ciclica
        for s in range(1, 9):
            for g in range(5):
                data_s = lun_corrente + timedelta(weeks=s-1, days=g)
                df_sim['g_pass'] = (pd.to_datetime(data_s) - df_sim['ultima visita']).dt.days
                urg_s = df_sim[df_sim['g_pass'] >= df_sim['frequenza (giorni)']].to_dict('records')
                
                o_sim, p_sim = datetime.combine(data_s, h_inizio), (start_lat, start_lon)
                while urg_s:
                    px = min(urg_s, key=lambda x: haversine(p_sim[0], p_sim[1], x['latitude'], x['longitude']))
                    dx = haversine(p_sim[0], p_sim[1], px['latitude'], px['longitude'])
                    ar = o_sim + timedelta(minutes=(dx/50)*60)
                    pa = ar + timedelta(minutes=durata_v)
                    if pa <= datetime.combine(data_s, h_fine):
                        px_c = px.copy()
                        px_c['ora_s'] = ar.strftime("%H:%M")
                        agenda_8w[f"Settimana {s}"][g].append(px_c)
                        df_sim.loc[df_sim['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(data_s)
                        o_sim, p_sim = pa, (px['latitude'], px['longitude'])
                        urg_s.remove(px)
                    else: break

        # Layout 5 Colonne
        nomi_g = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
        col_view = st.columns(5)
        dati_sett = agenda_8w[settimana_scelta]
        
        for idx, col_ui in enumerate(col_view):
            with col_ui:
                data_ui = lun_corrente + timedelta(weeks=int(settimana_scelta.split()[-1])-1, days=idx)
                st.markdown(f"#### {nomi_g[idx]}")
                st.caption(data_ui.strftime("%d/%m"))
                st.divider()
                for visit in dati_sett[idx]:
                    with st.container(border=True):
                        st.caption(visit['ora_s'])
                        st.write(f"**{visit['nome cliente']}**")

else:
    st.warning("Dati non disponibili. Controlla il link del foglio Google.")
