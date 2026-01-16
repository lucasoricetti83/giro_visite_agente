import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
from streamlit_js_eval import streamlit_js_eval

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Giro Visite & CRM", layout="wide")

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

# --- MEMORIA DELL'APP (Session State) ---
if 'df_master' not in st.session_state:
    URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132"
    st.session_state.df_master = fetch_data(URL_FOGLIO)

if 'start_lat' not in st.session_state: st.session_state.start_lat = 43.1924
if 'start_lon' not in st.session_state: st.session_state.start_lon = 13.5797
if 'h_inizio' not in st.session_state: st.session_state.h_inizio = time(9, 0)
if 'h_fine' not in st.session_state: st.session_state.h_fine = time(18, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'spostamenti' not in st.session_state: st.session_state.spostamenti = {}

# --- LOGICA DI CALCOLO ---
def calcola_piano():
    oggi = datetime.now()
    lun_ref = oggi - timedelta(days=oggi.weekday())
    df_sim = st.session_state.df_master.copy()
    piano = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
    
    for s in range(1, 9):
        for g in range(5):
            d_corr = (lun_ref + timedelta(weeks=s-1, days=g)).date()
            d_logica = st.session_state.spostamenti.get(d_corr, d_corr)
            df_sim['g_pass'] = (pd.to_datetime(d_logica) - df_sim['ultima visita']).dt.days
            urg = df_sim[df_sim['g_pass'] >= df_sim['frequenza (giorni)']].to_dict('records')
            
            o_s, p_s = datetime.combine(d_corr, st.session_state.h_inizio), (st.session_state.start_lat, st.session_state.start_lon)
            while urg:
                px = min(urg, key=lambda x: haversine(p_s[0], p_s[1], x['latitude'], x['longitude']))
                dist = haversine(p_s[0], p_s[1], px['latitude'], px['longitude'])
                arr = o_s + timedelta(minutes=(dist/50)*60)
                fine = arr + timedelta(minutes=st.session_state.durata_v)
                if fine <= datetime.combine(d_corr, st.session_state.h_fine):
                    info = px.copy(); info['ora'] = arr.strftime("%H:%M")
                    piano[f"Settimana {s}"][g].append(info)
                    df_sim.loc[df_sim['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(d_logica)
                    o_s, p_s = fine, (px['latitude'], px['longitude'])
                    urg.remove(px)
                else: break
    return piano, lun_ref

# --- INTERFACCIA ---
if not st.session_state.df_master.empty:
    piano_completo, lun_base = calcola_piano()
    t_oggi, t_sett, t_ana, t_par = st.tabs(["🚀 Giro di Oggi", "📅 Agenda 8 Settimane", "👤 Anagrafica", "⚙️ Parametri"])

    with t_oggi:
        oggi_dt = datetime.now()
        st.header(f"📍 Oggi: {oggi_dt.strftime('%d/%m/%Y')}")
        idx_g = oggi_dt.weekday()
        if idx_g < 5:
            tappe = piano_completo["Settimana 1"][idx_g]
            if tappe:
                c1, c2 = st.columns([1, 2])
                with c1:
                    for t in tappe:
                        with st.container(border=True):
                            st.write(f"🕒 **{t['ora']}** - {t['nome cliente']}")
                            st.link_button("🚗 Naviga", f"http://maps.google.com/?daddr={t['latitude']},{t['longitude']}", use_container_width=True)
                with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
            else: st.info("Nessuna visita programmata.")
        else: st.write("Weekend!")

    with t_sett:
        s_target = st.selectbox("Seleziona Settimana:", [f"Settimana {i}" for i in range(1, 9)])
        cols = st.columns(5)
        nomi_g = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
        for i, col in enumerate(cols):
            with col:
                d_g = (lun_base + timedelta(weeks=int(s_target.split()[-1])-1, days=i)).date()
                st.subheader(nomi_g[i]); st.caption(d_g.strftime("%d/%m"))
                for v in piano_completo[s_target][i]:
                    with st.container(border=True):
                        st.caption(v['ora']); st.write(f"**{v['nome cliente']}**")

    with t_ana:
        st.header("👤 Gestione Anagrafica")
        # --- BARRA DI RICERCA ---
        cerca = st.text_input("🔍 Cerca cliente (per nome o città):", "").lower()
        nomi_f = [n for n in sorted(st.session_state.df_master['nome cliente'].unique()) if cerca in n.lower()]
        
        if nomi_f:
            scelto = st.selectbox("Seleziona dalla lista:", nomi_f)
            idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
            d =
