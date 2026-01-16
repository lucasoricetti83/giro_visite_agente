import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
from streamlit_js_eval import streamlit_js_eval

# --- CONFIGURAZIONI ---
st.set_page_config(page_title="Giro Visite Pro - Dashboard", layout="wide")

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

# --- SIDEBAR: CONTROLLI ---
st.sidebar.title("⚙️ Parametri")

# Punto di Partenza
st.sidebar.subheader("📍 Partenza")
metodo_partenza = st.sidebar.radio("Scegli partenza:", ["Digita Luogo", "GPS"])
start_lat, start_lon = 43.1924, 13.5797
if metodo_partenza == "Digita Luogo":
    luogo = st.sidebar.text_input("Città/Indirizzo:", "Fermo")
    try:
        location = Nominatim(user_agent="giro_visite_app").geocode(luogo)
        if location: start_lat, start_lon = location.latitude, location.longitude
    except: pass
elif metodo_partenza == "GPS":
    loc = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps')
    if loc: start_lat, start_lon = loc['latitude'], loc['longitude']

# Orari
st.sidebar.subheader("⏰ Orari Lavoro")
ora_inizio = st.sidebar.time_input("Inizio", time(9, 0))
ora_fine = st.sidebar.time_input("Fine", time(18, 0))
durata_visita = st.sidebar.slider("Durata visita (min)", 15, 120, 45)

# --- CARICAMENTO DATI ---
try:
    df_raw = load_data("https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132")
    
    tab1, tab2 = st.tabs(["🚀 Giro di Oggi", "📅 Dashboard Settimanale"])

    # --- TAB 1: GIRO GIORNALIERO (Mappa + Navigatore) ---
    with tab1:
        st.header("Percorso Ottimizzato Oggi")
        if st.button("🚀 Calcola Percorso"):
            oggi = datetime.now()
            df_raw['giorni_passati'] = (oggi - df_raw['ultima visita']).dt.days
            urgenti = df_raw[(df_raw['giorni_passati'] >= df_raw['frequenza (giorni)']) | (df_raw['visitare'].astype(str).str.upper() == 'SI')].to_dict('records')
            
            giro, orario_attuale, pos_attuale = [], datetime.combine(oggi.date(), ora_inizio), (start_lat, start_lon)
            while urgenti:
                prossimo = min(urgenti, key=lambda x: haversine(pos_attuale[0], pos_attuale[1], x['latitude'], x['longitude']))
                dist = haversine(pos_attuale[0], pos_attuale[1], prossimo['latitude'], prossimo['longitude'])
                tempo_viaggio = (dist / 50) * 60
                arrivo = orario_attuale + timedelta(minutes=tempo_viaggio)
                partenza = arrivo + timedelta(minutes=durata_visita)
                
                if partenza <= datetime.combine(oggi.date(), ora_fine):
                    prossimo.update({'arrivo': arrivo.strftime("%H:%M")})
                    giro.append(prossimo)
                    orario_attuale, pos_attuale = partenza, (prossimo['latitude'], prossimo['longitude'])
                    urgenti.remove(prossimo)
                else: break

            if giro:
                c1, c2 = st.columns([1, 2])
                with c1:
                    for i, r in enumerate(giro):
                        with st.expander(f"Tappa {i+1}: {r['nome_cliente'] if 'nome_cliente' in r else r['nome cliente']}"):
                            st.write(f"⌚ Arrivo: {r['arrivo']}")
                            st.link_button("🚗 Naviga", f"https://www.google.com/maps/dir/?api=1&destination={r['latitude']},{r['longitude']}")
                with c2: st.map(pd.DataFrame(giro).rename(columns={'latitude':'lat','longitude':'lon'}))

    # --- TAB 2: DASHBOARD SETTIMANALE (5 COLONNE) ---
    with tab2:
        st.header("🗓️ Agenda Settimanale (Lunedì - Venerdì)")
        
        # Simulazione della settimana
        oggi = datetime.now()
        # Troviamo il lunedì della settimana corrente
        lunedi = oggi - timedelta(days=oggi.weekday())
        
        pool_clienti = df_raw.copy()
        pool_clienti['giorni_passati'] = (pd.to_datetime(lunedi) - pool_clienti['ultima visita']).dt.days
        pool_clienti = pool_clienti.sort_values(by='giorni_passati', ascending=False).to_dict('records')

        nomi_giorni = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
        cols = st.columns(5)

        for i, col in enumerate(cols):
            giorno_corrente = lunedi + timedelta(days=i)
            with col:
                st.subheader(nomi_giorni[i])
                st.caption(giorno_corrente.strftime("%d/%m/%Y"))
                
                orario_sim = datetime.combine(giorno_corrente, ora_inizio)
                limite_sim = datetime.combine(giorno_corrente, ora_fine)
                pos_sim = (start_lat, start_lon)
                
                # Riempiamo la giornata
                finito_giorno = False
                while not finito_giorno and pool_clienti:
                    prossimo = min(pool_clienti, key=lambda x: haversine(pos_sim[0], pos_sim[1], x['latitude'], x['longitude']))
                    dist = haversine(pos_sim[0], pos_sim[1], prossimo['latitude'], prossimo['longitude'])
                    tempo_viaggio = (dist / 50) * 60
                    arrivo = orario_sim + timedelta(minutes=tempo_viaggio)
                    partenza = arrivo + timedelta(minutes=durata_visita)
                    
                    if partenza <= limite_sim:
                        with st.container(border=True):
                            st.markdown(f"**{arrivo.strftime('%H:%M')}**")
                            st.write(f"{prossimo['nome cliente']}")
                            st.caption(f"📍 {prossimo['indirizzo'][:20]}...")
                        
                        orario_sim, pos_sim = partenza, (prossimo['latitude'], prossimo['longitude'])
                        pool_clienti.remove(prossimo)
                    else:
                        finito_giorno = True
                
                if orario_sim == datetime.combine(giorno_corrente, ora_inizio):
                    st.write("---")
                    st.caption("Nessuna visita")

except Exception as e:
    st.error(f"Errore: {e}")
