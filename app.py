import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
from streamlit_js_eval import streamlit_js_eval

# --- CONFIGURAZIONI ---
st.set_page_config(page_title="Giro Visite Pro & Agenda", layout="wide")

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

# --- SIDEBAR: IMPOSTAZIONI GLOBALI ---
st.sidebar.title("🛠️ Pannello di Controllo")

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
st.sidebar.subheader("⏰ Orari e Tempi")
ora_inizio = st.sidebar.time_input("Inizio lavoro", time(9, 0))
ora_fine = st.sidebar.time_input("Fine lavoro", time(18, 0))
durata_visita = st.sidebar.slider("Durata visita (min)", 15, 90, 45)

# --- CARICAMENTO DATI ---
try:
    df_raw = load_data("https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132")
    
    tab1, tab2 = st.tabs(["🚀 Giro del Giorno", "📅 Agenda 8 Settimane"])

    # --- TAB 1: GIRO GIORNALIERO ---
    with tab1:
        st.header("Pianificazione Giornaliera Ottimizzata")
        if st.button("🚀 Genera Percorso di Oggi"):
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
                    prossimo.update({'arrivo': arrivo.strftime("%H:%M"), 'km': round(dist, 1)})
                    giro.append(prossimo)
                    orario_attuale, pos_attuale = partenza, (prossimo['latitude'], prossimo['longitude'])
                    urgenti.remove(prossimo)
                else: break

            if giro:
                c1, c2 = st.columns(2)
                with c1:
                    for i, r in enumerate(giro):
                        st.info(f"**{i+1}. {r['nome cliente']}**\n\nArrivo ore: {r['arrivo']} ({r['km']} km)")
                        st.link_button(f"Naviga verso {r['nome cliente']}", f"https://www.google.com/maps/dir/?api=1&destination={r['latitude']},{r['longitude']}")
                with c2: st.map(pd.DataFrame(giro).rename(columns={'latitude':'lat','longitude':'lon'}))
            else: st.warning("Nessun cliente programmabile con questi orari.")

    # --- TAB 2: AGENDA 8 SETTIMANE ---
    with tab2:
        st.header("🗓️ Panoramica Strategica (8 Settimane)")
        st.write("Simulazione delle visite basata sulle frequenze impostate nel foglio Google.")
        
        # Simulazione
        data_sim = datetime.now().date()
        agenda_futura = []
        df_sim = df_raw.copy()
        
        for sett in range(1, 9):
            clienti_settimana = []
            # Simuliamo 5 giorni lavorativi per settimana
            for giorno in range(5):
                corrente = data_sim + timedelta(weeks=sett-1, days=giorno)
                df_sim['giorni_da_ultima'] = (pd.to_datetime(corrente) - df_sim['ultima visita']).dt.days
                
                # Troviamo chi è "scaduto" in quel giorno simulato
                da_visitare = df_sim[df_sim['giorni_da_ultima'] >= df_sim['frequenza (giorni)']].to_dict('records')
                
                # Per non complicare troppo, simuliamo un limite di 6 visite al giorno per l'agenda futura
                contatore = 0
                for c in da_visitare:
                    if contatore < 6:
                        agenda_futura.append({'Settimana': f"Sett. {sett}", 'Data': corrente, 'Cliente': c['nome cliente'], 'Città': c['indirizzo']})
                        # Aggiorniamo la data dell'ultima visita nella simulazione per quel cliente
                        df_sim.loc[df_sim['nome cliente'] == c['nome cliente'], 'ultima visita'] = pd.to_datetime(corrente)
                        contatore += 1
            
        if agenda_futura:
            df_agenda = pd.DataFrame(agenda_futura)
            
            # Grafico del carico
            st.bar_chart(df_agenda.groupby('Settimana').size())
            
            # Filtro per settimana
            sett_scelta = st.selectbox("Seleziona settimana per il dettaglio:", [f"Sett. {i}" for i in range(1, 9)])
            st.dataframe(df_agenda[df_agenda['Settimana'] == sett_scelta][['Data', 'Cliente', 'Città']], use_container_width=True, hide_index=True)
        else:
            st.info("Nessuna visita prevista. Controlla che le frequenze nel foglio Google siano popolate correttamente.")

except Exception as e:
    st.error(f"Errore: {e}")
