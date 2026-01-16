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
                px = min(urg, key=lambda x: haversine(p_sim[0], p_sim[1], x['latitude'], x['longitude']))
                dist = haversine(p_sim[0], p_sim[1], px['latitude'], px['longitude'])
                arr = o_sim + timedelta(minutes=(dist/50)*60)
                fine = arr + timedelta(minutes=st.session_state.durata_v)
                
                if fine <= limite_sim:
                    info = px.copy()
                    info['ora_arrivo'] = arr.strftime("%H:%M")
                    piano[f"Settimana {s}"][g].append(info)
                    df_sim.loc[df_sim['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(data_logica)
                    o_sim, p_sim = fine, (px['latitude'], px['longitude'])
                    urg.remove(px)
                else: break
    return piano, lunedi_ref

# --- INTERFACCIA ---
if not st.session_state.df_master.empty:
    agenda_totale, lun_ref = calcola_agenda_completa()
    
    tab_oggi, tab_settimana, tab_anagrafica, tab_parametri = st.tabs([
        "🚀 Giro di Oggi", "📅 Agenda 8 Settimane", "👤 Anagrafica", "⚙️ Parametri"
    ])

    # --- TAB 1: OGGI ---
    with tab_oggi:
        oggi_dt = datetime.now()
        st.header(f"📍 Giro del Giorno: {oggi_dt.strftime('%d/%m/%Y')}")
        idx_g = oggi_dt.weekday()
        if idx_g < 5:
            tappe = agenda_totale["Settimana 1"][idx_g]
            if tappe:
                c1, c2 = st.columns([1, 2])
                with c1:
                    for t in tappe:
                        with st.container(border=True):
                            st.write(f"🕒 **{t['ora_arrivo']}** - {t['nome cliente']}")
                            st.link_button("🚗 Naviga", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}", use_container_width=True)
                with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
            else: st.info("Nessuna visita programmata per oggi.")
        else: st.write("È weekend! Controlla la programmazione settimanale.")

    # --- TAB 2: SETTIMANALE ---
    with tab_settimana:
        sett_scelta = st.selectbox("Seleziona Settimana:", [f"Settimana {i}" for i in range(1, 9)])
        cols = st.columns(5)
        nomi_g = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
        for i, col in enumerate(cols):
            with col:
                d_g = (lun_ref + timedelta(weeks=int(sett_scelta.split()[-1])-1, days=i)).date()
                if d_g in st.session_state.spostamenti: st.warning(f"🔄 {nomi_g[i]}")
                else: st.subheader(nomi_g[i])
                st.caption(d_g.strftime("%d/%m"))
                for v in agenda_totale[sett_scelta][i]:
                    with st.container(border=True):
                        st.caption(v['ora_arrivo'])
                        st.write(f"**{v['nome cliente']}**")

    # --- TAB 3: ANAGRAFICA ---
    with tab_anagrafica:
        st.header("👤 Scheda Cliente")
        nomi = sorted(st.session_state.df_master['nome cliente'].unique())
        scelto = st.selectbox("Cerca Cliente:", nomi)
        if scelto:
            idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
            d = st.session_state.df_master.loc[idx]
            with st.form("edit_c"):
                ca1, ca2 = st.columns(2)
                with ca1:
                    n_nome = st.text_input("Nome", d['nome cliente'])
                    n_ind = st.text_input("Indirizzo", d['indirizzo'])
                    n_freq = st.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
                with ca2:
                    n_lat = st.number_input("Lat", value=float(d['latitude']), format="%.6f")
                    n_lon = st.number_input("Lon", value=float(d['longitude']), format="%.6f")
                    n_data = st.date_input("Ultima Visita", d['ultima visita'].date())
                if st.form_submit_button("Salva Modifiche Locale"):
                    st.session_state.df_master.at[idx, 'nome cliente'] = n_nome
                    st.session_state.df_master.at[idx, 'indirizzo'] = n_ind
                    st.session_state.df_master.at[idx, 'frequenza (giorni)'] = n_freq
                    st.session_state.df_master.at[idx, 'latitude'] = n_lat
                    st.session_state.df_master.at[idx, 'longitude'] = n_lon
                    st.session_state.df_master.at[idx, 'ultima visita'] = pd.to_datetime(n_data)
                    st.success("Dati aggiornati!")
                    st.rerun()

    # --- TAB 4: PARAMETRI ---
    with tab_parametri:
        st.header("⚙️ Impostazioni")
        cp1, cp2 = st.columns(2)
        with cp1:
            if st.button("🎯 Usa Posizione GPS"):
                g = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps_final')
                if g: 
                    st.session_state.start_lat, st.session_state.start_lon = g['latitude'], g['longitude']
                    st.rerun()
            st.session_state.h_inizio = st.time_input("Inizio", st.session_state.h_inizio)
            st.session_state.h_fine = st.time_input("Fine", st.session_state.h_fine)
            st.session_state.durata_v = st.slider("Durata (min)", 15, 120, st.session_state.durata_v)
        with cp2:
            st.subheader("🔄 Sposta Giorno")
            d_da = st.date_input("Giorno da spostare:", datetime.now())
            d_a = st.date_input("Al giorno:", datetime.now() + timedelta(days=1))
            if st.button("Scambia"):
                st.session_state.spostamenti[d_da] = d_a
                st.session_state.spostamenti[d_a] = d_da
                st.rerun()
            if st.button("Reset Dati (Ricarica dal Foglio)"):
                del st.session_state.df_master
                st.rerun()
else:
    st.error("Nessun dato trovato. Controlla il link del Foglio Google.")
