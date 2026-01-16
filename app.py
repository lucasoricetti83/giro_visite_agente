import streamlit as st
import pandas as pd
from datetime import datetime
from math import radians, cos, sin, asin, sqrt

def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371

st.set_page_config(page_title="Giro Visite", page_icon="🚗")
st.title("🚗 Il Mio Giro Visite")

# Link del tuo foglio aggiornato
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv"

try:
    # Caricamento dati
    df = pd.read_csv(URL_FOGLIO)
    
    # Pulizia nomi colonne (toglie spazi e mette tutto in minuscolo per non sbagliare)
    df.columns = df.columns.str.strip().str.lower()
    
    # Riempire le date vuote con una data molto vecchia per non far crashare l'app
    df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce').fillna(pd.Timestamp('2000-01-01'))
    
    oggi = datetime.now()
    df['giorni_passati'] = (oggi - df['ultima visita']).dt.days

    # Filtro: Scaduti + visitare == SI (usiamo i nomi minuscoli come puliti sopra)
    # Colonna 'frequenza (giorni)' e 'visitare'
    clienti_filtrati = df[
        (df['giorni_passati'] >= df['frequenza (giorni)']) & 
        (df['visitare'].astype(str).str.upper() == 'SI')
    ].copy()

    st.sidebar.header("Parametri")
    ore_disp = st.sidebar.slider("Ore disponibili", 1, 12, 8)
    
    st.write(f"### 📍 Clienti pronti per oggi: {len(clienti_filtrati)}")
    
    if not clienti_filtrati.empty:
        st.dataframe(clienti_filtrati[['nome cliente', 'indirizzo', 'giorni_passati']])
        if st.button("🚀 Mostra Mappa"):
            # Usiamo i nomi delle colonne minuscoli
            st.map(clienti_filtrati[['latitudine', 'longitudine']])
    else:
        st.info("Nessun cliente trovato. Assicurati di aver scritto 'SI' nella colonna 'visitare' del foglio Google per i clienti con frequenza scaduta.")

except Exception as e:
    st.error(f"Errore: {e}")
