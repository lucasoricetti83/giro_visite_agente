import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
from streamlit_js_eval import streamlit_js_eval

# --- CONFIGURAZIONI E FUNZIONI ---
st.set_page_config(page_title="Giro Visite Smart", layout="wide")

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

# --- SIDEBAR: PUNTO DI PARTENZA ---
st.sidebar.header("📍 Punto di Partenza")
metodo_partenza = st.sidebar.radio("Come vuoi impostare la partenza?", ["Digita Luogo", "GPS", "Coordinate Manuali"])

start_lat, start_lon = 43.1924, 13.5797 # Default

if metodo_partenza == "Digita Luogo":
    luogo_nome = st.sidebar.text_input("Inserisci città o indirizzo:", "Fermo")
    if luogo_nome:
        try:
            geolocator = Nominatim(user_agent="giro_visite_app")
            location = geolocator.geocode(luogo_nome)
            if location:
                start_lat, start_lon = location.latitude, location.longitude
                st.sidebar.success(f"Trovato: {location.address[:30]}...")
            else:
                st.sidebar.error("Luogo non trovato.")
        except:
            st.sidebar.warning("Servizio di ricerca momentaneamente occupato.")

elif metodo_partenza == "GPS":
    loc = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps')
    if loc:
        start_lat, start_lon = loc['latitude'], loc['longitude']
        st.sidebar.success("GPS Attivo")

else:
    start_lat = st.sidebar.number_input("Lat", value=start_lat)
    start_lon = st.sidebar.number_input("Lon", value=start_lon)

# --- SIDEBAR: ORARIO LAVORATIVO ---
st.sidebar.header("⏰ Orario di Lavoro")
ora_inizio = st.sidebar.time_input("Inizio lavoro", time(9, 0))
ora_fine = st.sidebar.time_input("Fine lavoro", time(18, 0))
durata_visita = st.sidebar.slider("Durata media visita (minuti)", 15, 120, 45)
velocita_media = st.sidebar.slider("Velocità media (km/h)", 30, 90, 50)

# --- LOGICA CALCOLO GIRO ---
try:
    df_raw = load_data("https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132")
    
    st.title("🚗 Il Tuo Giro Visite su Misura")
    
    if st.button("🚀 Calcola Giro in base all'orario"):
        # Filtro urgenza
        oggi = datetime.now()
        df_raw['giorni_passati'] = (oggi - df_raw['ultima visita']).dt.days
        urgenti = df_raw[(df_raw['giorni_passati'] >= df_raw['frequenza (giorni)']) | (df_raw['visitare'].astype(str).str.upper() == 'SI')].to_dict('records')

        giro = []
        orario_attuale = datetime.combine(oggi.date(), ora_inizio)
        limite_fine = datetime.combine(oggi.date(), ora_fine)
        pos_attuale = (start_lat, start_lon)

        while urgenti:
            # Trova il più vicino
            prossimo = min(urgenti, key=lambda x: haversine(pos_attuale[0], pos_attuale[1], x['latitude'], x['longitude']))
            dist = haversine(pos_attuale[0], pos_attuale[1], prossimo['latitude'], prossimo['longitude'])
            
            # Calcola tempi
            tempo_viaggio = (dist / velocita_media) * 60 # in minuti
            arrivo = orario_attuale + timedelta(minutes=tempo_viaggio)
            partenza = arrivo + timedelta(minutes=durata_visita)

            if partenza <= limite_fine:
                prossimo['arrivo'] = arrivo.strftime("%H:%M")
                prossimo['partenza'] = partenza.strftime("%H:%M")
                prossimo['km'] = round(dist, 1)
                giro.append(prossimo)
                orario_attuale = partenza
                pos_attuale = (prossimo['latitude'], prossimo['longitude'])
                urgenti.remove(prossimo)
            else:
                break # Non c'è più tempo per altre visite

        if giro:
            st.success(f"Giro completato! Riesci a fare {len(giro)} visite entro le {ora_fine.strftime('%H:%M')}.")
            
            col1, col2 = st.columns([1, 1])
            with col1:
                for i, r in enumerate(giro):
                    with st.container(border=True):
                        st.markdown(f"**{i+1}. {r['nome cliente']}**")
                        st.write(f"🕒 Arrivo: {r['arrivo']} | Saluti: {r['partenza']}")
                        st.caption(f"📍 {r['indirizzo']} ({r['km']} km da tappa precedente)")
                        nav_url = f"https://www.google.com/maps/dir/?api=1&origin={pos_attuale[0]},{pos_attuale[1]}&destination={r['latitude']},{r['longitude']}&travelmode=driving"
                        st.link_button("🚗 Naviga", nav_url)
            
            with col2:
                map_df = pd.DataFrame(giro).rename(columns={'latitude': 'lat', 'longitude': 'lon'})
                st.map(map_df[['lat', 'lon']])
        else:
            st.warning("Con questi orari non riesci a fare nessuna visita. Prova ad aumentare l'orario di lavoro o ridurre la durata delle visite.")

except Exception as e:
    st.error(f"Errore: {e}")
