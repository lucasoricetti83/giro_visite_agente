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

# --- CONFIGURAZIONE APP ---
st.set_page_config(page_title="Giro Visite Agente", page_icon="🚗")
st.title("🚗 Il Mio Giro Visite")

# Link del tuo foglio in formato export CSV
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv"

try:
    # Caricamento dati
    df = pd.read_csv(URL_FOGLIO)
    
    # PULIZIA COLONNE: Trasformiamo tutto in minuscolo e togliamo spazi extra
    df.columns = df.columns.str.strip().str.lower()
    
    # Gestione date vuote (se manca la data, mettiamo una data vecchia)
    df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce').fillna(pd.Timestamp('2020-01-01'))
    
    # Calcolo giorni passati
    oggi = datetime.now()
    df['giorni_passati'] = (oggi - df['ultima visita']).dt.days

    # FILTRO: Scaduti (giorni passati >= frequenza) E visitare == SI
    # Nota: usiamo i nomi delle colonne tutti in minuscolo
    clienti_filtrati = df[
        (df['giorni_passati'] >= df['frequenza (giorni)']) & 
        (df['visitare'].astype(str).str.upper() == 'SI')
    ].copy()

    st.sidebar.header("Parametri Giro")
    ore_disp = st.sidebar.slider("Ore disponibili oggi", 1, 12, 8)
    
    st.write(f"### 📍 Clienti pronti per oggi: {len(clienti_filtrati)}")
    
    if not clienti_filtrati.empty:
        # Mostriamo la tabella (usando i nomi minuscoli per i dati)
        st.dataframe(clienti_filtrati[['nome cliente', 'indirizzo', 'giorni_passati']])
        
        if st.button("🚀 Calcola Percorso e Mappa"):
            st.success("Giro calcolato!")
            # Mostra i punti sulla mappa
            st.map(clienti_filtrati[['latitudine', 'longitudine']])
    else:
        st.info("Nessun cliente trovato. Ricorda di mettere 'SI' nella colonna 'visitare' sul foglio Google per i clienti che vuoi vedere oggi.")

except Exception as e:
    st.error(f"Errore tecnico: {e}")
    st.write("Verifica che nel foglio Google ci siano le colonne: Nome Cliente, Ultima Visita, frequenza (giorni), visitare, Latitudine, Longitudine")
