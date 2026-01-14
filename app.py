import streamlit as st
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
st.set_page_config(page_title="Giro Visite Selettivo", page_icon="🚗")
st.title("🚗 Pianificatore con Selezione Clienti")

uploaded_file = st.file_uploader("Carica il file clienti.csv", type=['csv'])

if uploaded_file:
    df = pd.read_csv(uploaded_file, sep=';', decimal=',')
    
    # Pulizia Date
    df['Ultima Visita'] = pd.to_datetime(df['Ultima Visita'], dayfirst=True)
    oggi = datetime.now()
    df['Giorni Passati'] = (oggi - df['Ultima Visita']).dt.days

    # --- NUOVA LOGICA DI FILTRO ---
    # Filtriamo chi è scaduto E ha "SI" nella colonna 'visitare'
    # .str.upper() serve per evitare errori tra "si", "Si", "SI"
    clienti_filtrati = df[
        (df['Giorni Passati'] >= df['Frequenza (giorni)']) & 
        (df['visitare'].get_values().astype(str).str.upper() == 'SI')
    ].copy()

    st.sidebar.header("Parametri Giro")
    ore_disp = st.sidebar.slider("Ore disponibili", 1, 12, 8)
    velocita = st.sidebar.number_input("Velocità media (km/h)", value=40)
    
    casa_lat = 43.1932389
    casa_lon = 13.5792209

    st.write(f"### Clienti pronti per il giro: {len(clienti_filtrati)}")
    st.dataframe(clienti_filtrati[['Nome Cliente', 'Indirizzo', 'Giorni Passati']])

    if st.button("🚀 Calcola Itinerario per i selezionati"):
        if clienti_filtrati.empty:
            st.warning("Nessun cliente da visitare selezionato (controlla la colonna 'visitare' nel file).")
        else:
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
                        giro_visite.append({
                            'Nome': c['Nome Cliente'],
                            'Indirizzo': c['Indirizzo'],
                            'Viaggio': round(t_viaggio),
                            'Visita': c['Durata']
                        })
                        pos_attuale = {'lat': c['Latitudine'], 'lon': c['Longitudine']}
                        clienti_filtrati = clienti_filtrati.drop(prox_idx)
                    else: break
                else: break

            st.success(f"Giro Calcolato: {len(giro_visite)} tappe.")
            for i, tappa in enumerate(giro_visite):
                with st.expander(f"{i+1}. {tappa['Nome']}"):
                    st.write(f"📍 {tappa['Indirizzo']}")
                    st.write(f"🚗 Guida: {tappa['Viaggio']} min | ⏱️ Visita: {tappa['Visita']} min")

else:
    st.info("Carica il file clienti per iniziare.")
