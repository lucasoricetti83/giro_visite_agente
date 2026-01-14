import streamlit as st
import pandas as pd
from datetime import datetime
from math import radians, cos, sin, asin, sqrt

# --- FUNZIONI MATEMATICHE ---
def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371

# --- CONFIGURAZIONE APP ---
st.set_page_config(page_title="Il Mio Giro Visite", page_icon="🚗")
st.title("🚗 Gestione Giro Visite")

uploaded_file = st.file_uploader("Carica il tuo file clienti.csv", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file, sep=';', decimal=',')
    st.sidebar.header("Impostazioni")
    ore_disp = st.sidebar.slider("Ore disponibili", 1, 12, 8)
    velocita = st.sidebar.number_input("Velocità media (km/h)", value=40)
    
    CASA_LAT = 43.1932389
    CASA_LON = 13.5792209

    if st.button("Calcola Giro di Oggi"):
        df['Ultima Visita'] = pd.to_datetime(df['Ultima Visita'], dayfirst=True)
        oggi = datetime.now()
        df['Giorni Passati'] = (oggi - df['Ultima Visita']).dt.days
        clienti_da_visitare = df[df['Giorni Passati'] >= df['Frequenza (giorni)']].copy()

        tempo_impiegato = 0
        ore_max_minuti = ore_disp * 60
        posizione_attuale = {'lat': CASA_LAT, 'lon': CASA_LON}
        giro_visite = []

        while tempo_impiegato < ore_max_minuti and not clienti_da_visitare.empty:
            distanza_migliore = float('inf')
            prossimo_idx = -1
            for index, row in clienti_da_visitare.iterrows():
                dist = haversine(posizione_attuale['lon'], posizione_attuale['lat'],
                                 row['Longitudine'], row['Latitudine'])
                if dist < distanza_migliore:
                    distanza_migliore = dist
                    prossimo_idx = index
            if prossimo_idx != -1:
                cliente = clienti_da_visitare.loc[prossimo_idx]
                tempo_viaggio = (distanza_migliore / velocita) * 60
                tempo_totale_tappa = tempo_viaggio + cliente['Durata']
                if (tempo_impiegato + tempo_totale_tappa) <= ore_max_minuti:
                    tempo_impiegato += tempo_totale_tappa
                    giro_visite.append({
                        'Nome': cliente['Nome Cliente'],
                        'Indirizzo': cliente['Indirizzo'],
                        'Viaggio': round(tempo_viaggio),
                        'Visita': cliente['Durata']
                    })
                    posizione_attuale = {'lat': cliente['Latitudine'], 'lon': cliente['Longitudine']}
                    clienti_da_visitare = clienti_da_visitare.drop(prossimo_idx)
                else: break
            else: break

        st.header("📋 Itinerario Consigliato")
        st.info(f"Tempo totale stimato: {int(tempo_impiegato // 60)}h {int(tempo_impiegato % 60)}min")
        for i, tappa in enumerate(giro_visite):
            with st.expander(f"{i+1}. {tappa['Nome']}"):
                st.write(f"📍 **Indirizzo:** {tappa['Indirizzo']}")
                st.write(f"🚗 **Guida:** {tappa['Viaggio']} min")
                st.write(f"⏱️ **Durata Visita:** {tappa['Visita']} min")
                st.text_area("Inserisci report visita", key=f"report_{i}")
