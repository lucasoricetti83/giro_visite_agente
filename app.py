import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
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
st.set_page_config(page_title="Pianificatore 4 Settimane", layout="wide")
st.title("🗓️ Programmazione Visite Mensile (4 Settimane)")

# --- SIDEBAR IMPOSTAZIONI ---
st.sidebar.header("Parametri di Pianificazione")
ore_lavoro_giorno = st.sidebar.slider("Ore lavorative al giorno", 1, 12, 8)
velocita_media = st.sidebar.number_input("Velocità media (km/h)", value=40)
casa_lat = st.sidebar.number_input("Latitudine Partenza", value=43.1932389, format="%.7f")
casa_lon = st.sidebar.number_input("Longitudine Partenza", value=13.5792209, format="%.7f")

# --- CARICAMENTO FILE ---
uploaded_file = st.file_uploader("Carica il file clienti.csv", type=['csv'])

if uploaded_file:
    df = pd.read_csv(uploaded_file, sep=';', decimal=',')
    df['Ultima Visita'] = pd.to_datetime(df['Ultima Visita'], dayfirst=True)
    
    if st.button("🚀 GENERA PIANO 4 SETTIMANE"):
        # Creiamo una copia per non sporcare il database originale durante la simulazione
        df_simulazione = df.copy()
        data_simulata = datetime.now()
        
        # Creiamo 4 Tab (schede) nell'app per le 4 settimane
        tab1, tab2, tab3, tab4 = st.tabs(["Settimana 1", "Settimana 2", "Settimana 3", "Settimana 4"])
        tabs = [tab1, tab2, tab3, tab4]

        for sett in range(4):
            with tabs[sett]:
                st.header(f"📅 Settimana {sett + 1}")
                
                # Simuliamo 5 giorni lavorativi (Lun-Ven)
                for giorno in ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]:
                    # Calcola chi è "scaduto" in questa data simulata
                    df_simulazione['Giorni Passati'] = (data_simulata - df_simulazione['Ultima Visita']).dt.days
                    clienti_da_visitare = df_simulazione[df_simulazione['Giorni Passati'] >= df_simulazione['Frequenza (giorni)']].copy()
                    
                    tempo_minuti = 0
                    max_minuti = ore_lavoro_giorno * 60
                    pos_attuale = {'lat': casa_lat, 'lon': casa_lon}
                    giro_del_giorno = []

                    while tempo_minuti < max_minuti and not clienti_da_visitare.empty:
                        dist_migliore = float('inf')
                        prox_idx = -1
                        for idx, row in clienti_da_visitare.iterrows():
                            d = haversine(pos_attuale['lon'], pos_attuale['lat'], row['Longitudine'], row['Latitudine'])
                            if d < dist_migliore:
                                dist_migliore = d
                                prox_idx = idx
                        
                        if prox_idx != -1:
                            c = clienti_da_visitare.loc[prox_idx]
                            t_viaggio = (dist_migliore / velocita_media) * 60
                            t_totale = t_viaggio + c['Durata']
                            
                            if (tempo_minuti + t_totale) <= max_minuti:
                                tempo_minuti += t_totale
                                giro_del_giorno.append(f"{c['Nome Cliente']} ({c['Indirizzo']})")
                                # Aggiorniamo l'ultima visita simulata per questo cliente
                                df_simulazione.at[prox_idx, 'Ultima Visita'] = data_simulata
                                pos_attuale = {'lat': c['Latitudine'], 'lon': c['Longitudine']}
                                clienti_da_visitare = clienti_da_visitare.drop(prox_idx)
                            else: break
                        else: break
                    
                    # Mostra il giro del giorno
                    with st.expander(f"📍 {giorno}"):
                        if giro_del_giorno:
                            for t in giro_del_giorno:
                                st.write(f"- {t}")
                            st.caption(f"Tempo stimato: {int(tempo_minuti//60)}h {int(tempo_minuti%60)}min")
                        else:
                            st.write("Nessuna visita programmata.")
                    
                    # Avanziamo di un giorno nella simulazione
                    data_simulata += timedelta(days=1)
