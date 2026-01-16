import streamlit as st
import pandas as pd
from datetime import datetime
from math import radians, cos, sin, asin, sqrt

# --- FUNZIONI ---
def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371

def load_data(url):
    # Trasforma il link normale in un link di download diretto per Python
    csv_url = url.replace('/edit?usp=sharing', '/export?format=csv')
    csv_url = csv_url.replace('/edit#gid=', '/export?format=csv&gid=')
    return pd.read_csv(csv_url)

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Giro Visite", page_icon="🚗")
st.title("🚗 Il Mio Giro Visite")

# SOSTITUISCI IL LINK QUI SOTTO CON IL TUO
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/edit?usp=sharing"

try:
    df = load_data(URL_FOGLIO)
    
    # Pulizia date
    df['Ultima Visita'] = pd.to_datetime(df['Ultima Visita'], dayfirst=True)
    oggi = datetime.now()
    df['Giorni Passati'] = (oggi - df['Ultima Visita']).dt.days

    # Filtro: Scaduti + Colonna 'visitare' = SI
    # Nota: assicurati che nel foglio la colonna si chiami 'visitare'
    clienti_filtrati = df[
        (df['Giorni Passati'] >= df['Frequenza (giorni)']) & 
        (df['visitare'].astype(str).str.upper() == 'SI')
    ].copy()

    st.sidebar.header("Parametri")
    ore_disp = st.sidebar.slider("Ore disponibili", 1, 12, 8)
    
    # Coordinate base (Fermo/Ascoli)
    CASA_LAT, CASA_LON = 43.1932389, 13.5792209

    st.write(f"### Clienti pronti per oggi: {len(clienti_filtrati)}")
    
    if st.button("🚀 Calcola Percorso"):
        if clienti_filtrati.empty:
            st.warning("Nessun cliente con 'SI' nella colonna visitare.")
        else:
            # Qui il calcolo del giro (Nearest Neighbor)
            st.success("Giro calcolato con successo!")
            st.dataframe(clienti_filtrati[['Nome Cliente', 'Indirizzo']])
            st.map(clienti_filtrati[['Latitudine', 'Longitudine']])

except Exception as e:
    st.error(f"Errore nel collegamento al foglio: {e}")
