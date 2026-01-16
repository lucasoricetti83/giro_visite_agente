import streamlit as st
import pandas as pd

# Funzione per leggere Google Sheets in modo semplice
def load_data(url):
    # Trasforma il link di condivisione in un link di download diretto
    path = url.replace('/edit?usp=sharing', '/export?format=csv')
    return pd.read_csv(path)

# Sostituisci il link qui sotto con il TUO
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/edit?usp=sharing" 

try:
    df = load_data(URL_FOGLIO)
    st.success("✅ Dati caricati correttamente dal Foglio Google!")
    
    # Qui prosegue il resto del tuo codice (calcolo giro, mappa, ecc.)
    # ...
except Exception as e:
    st.error(f"❌ Errore nel caricamento dei dati: {e}")
    st.info("Controlla che il link del foglio sia corretto e che l'accesso sia impostato su 'Chiunque abbia il link può visualizzare'.")
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
from math import radians, cos, sin, asin, sqrt

# --- FUNZIONI UTILI ---
def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371

# --- CONFIGURAZIONE APP ---
st.set_page_config(page_title="Giro Visite Live", page_icon="📊")
st.title("📊 Gestione Visite Real-Time")

# --- CONNESSIONE GOOGLE SHEETS ---
# Inserisci qui il link del tuo foglio Google tra le virgolette
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/IL_TUO_CODICE_LUNGO_QUI/edit?usp=sharing"

conn = st.connection("gsheets", type=GSheetsConnection)

try:
    # Leggiamo i dati dal foglio
    df = conn.read(spreadsheet=URL_FOGLIO)
    
    # Conversione date
    df['Ultima Visita'] = pd.to_datetime(df['Ultima Visita'], dayfirst=True)
    oggi = datetime.now()
    df['Giorni Passati'] = (oggi - df['Ultima Visita']).dt.days

    # Filtro: Scaduti + Colonna 'visitare' = SI
    clienti_filtrati = df[
        (df['Giorni Passati'] >= df['Frequenza (giorni)']) & 
        (df['visitare'].astype(str).str.upper() == 'SI')
    ].copy()

    st.sidebar.header("Parametri Giro")
    ore_disp = st.sidebar.slider("Ore disponibili", 1, 12, 8)
    velocita = st.sidebar.number_input("Velocità media (km/h)", value=40)
    
    casa_lat = 43.1932389
    casa_lon = 13.5792209

    st.write(f"### 📍 Clienti da visitare oggi: {len(clienti_filtrati)}")
    
    if st.button("🚀 Calcola Itinerario Ottimale"):
        if clienti_filtrati.empty:
            st.warning("Nessun cliente selezionato con 'SI' nel foglio.")
        else:
            # --- LOGICA CALCOLO ---
            tempo_minuti = 0
            max_minuti = ore_disp * 60
            pos_attuale = {'lat': casa_lat, 'lon': casa_lon}
            giro_visite = []

            while tempo_minuti < max_minuti and not clienti_filtrati.empty:
                dist_migliore = float('inf')
                prox_idx = -1
                for idx, row in clienti_filtrati.iterrows():
                    d = haversine(pos_attuale['lon'], pos_attuale['lat'], row['Longitudine'], row['Latitudine'])
                    if d < dist_migliore:
                        dist_migliore = d
                        prox_idx = idx
                
                if prox_idx != -1:
                    c = clienti_filtrati.loc[prox_idx]
                    t_viaggio = (dist_migliore / velocita) * 60
                    t_totale = t_viaggio + c['Durata']
                    if (tempo_minuti + t_totale) <= max_minuti:
                        tempo_minuti += t_totale
                        giro_visite.append({'Nome': c['Nome Cliente'], 'Indirizzo': c['Indirizzo'], 'Viaggio': round(t_viaggio), 'Visita': c['Durata']})
                        pos_attuale = {'lat': c['Latitudine'], 'lon': c['Longitudine']}
                        clienti_filtrati = clienti_filtrati.drop(prox_idx)
                    else: break
                else: break

            st.success(f"Giro pronto!")
            for i, tappa in enumerate(giro_visite):
                with st.expander(f"{i+1}. {tappa['Nome']}"):
                    st.write(f"🏠 {tappa['Indirizzo']}")
                    st.write(f"🚗 Guida: {tappa['Viaggio']} min | ⏱️ Visita: {tappa['Visita']} min")
                    st.text_area("Report visita:", key=f"rep_{i}")

except Exception as e:
    st.error(f"Errore di connessione al foglio: {e}")
    st.info("Assicurati che il link del foglio sia corretto e che l'accesso sia impostato su 'Editor'.")
