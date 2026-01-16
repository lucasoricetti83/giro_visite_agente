import streamlit as st
import pandas as pd
from datetime import datetime
from math import radians, cos, sin, asin, sqrt

# Funzione per calcolare la distanza
def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371

st.set_page_config(page_title="Giro Visite", page_icon="🚗")
st.title("🚗 Il Mio Giro Visite")

# --- COLLO DI BOTTIGLIA: IL LINK ---
# Assicurati che il link finisca con /edit?usp=sharing
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/edit?usp=sharing"

def load_data(url):
    try:
        # Trasforma il link per il download diretto
        csv_url = url.replace('/edit?usp=sharing', '/export?format=csv')
        return pd.read_csv(csv_url)
    except Exception as e:
        st.error(f"Errore tecnico nel caricamento: {e}")
        return None

df = load_data(URL_FOGLIO)

if df is not None:
    try:
        # Verifichiamo che le colonne esistano (evita crash se scritte male nel foglio)
        colonne_necessarie = ['Nome Cliente', 'Ultima Visita', 'Frequenza (giorni)', 'visitare', 'Latitudine', 'Longitudine']
        ancora_colonne = [c for c in colonne_necessarie if c not in df.columns]
        
        if ancora_colonne:
            st.error(f"Mancano queste colonne nel foglio Google: {ancora_colonne}")
        else:
            # Pulizia dati
            df['Ultima Visita'] = pd.to_datetime(df['Ultima Visita'], dayfirst=True)
            oggi = datetime.now()
            df['Giorni Passati'] = (oggi - df['Ultima Visita']).dt.days

            # Filtro
            clienti_filtrati = df[
                (df['Giorni Passati'] >= df['Frequenza (giorni)']) & 
                (df['visitare'].astype(str).str.upper() == 'SI')
            ].copy()

            st.write(f"### 📍 Clienti pronti per oggi: {len(clienti_filtrati)}")
            
            if not clienti_filtrati.empty:
                st.dataframe(clienti_filtrati[['Nome Cliente', 'Indirizzo', 'Giorni Passati']])
                
                if st.button("🚀 Mostra Mappa e Calcola"):
                    st.map(clienti_filtrati[['Latitudine', 'Longitudine']])
            else:
                st.info("Nessun cliente da visitare trovato (controlla le date o la colonna 'visitare').")
                
    except Exception as e:
        st.error(f"Errore nell'elaborazione dei dati: {e}")
