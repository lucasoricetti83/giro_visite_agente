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
    r = 6371 # Raggio della terra in km
    return c * r

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Giro Visite Agente", page_icon="🚗", layout="centered")

st.title("🚗 Pianificatore Giro Visite")
st.markdown("Carica il tuo file Excel o CSV per calcolare l'itinerario migliore di oggi.")

# --- 1. IMPOSTAZIONI NELLA SIDEBAR (Barra laterale) ---
st.sidebar.header("Impostazioni Base")
ore_lavoro_disp = st.sidebar.slider("Ore totali disponibili", 1, 12, 8)
velocita_media = st.sidebar.number_input("Velocità media (km/h)", value=40)

st.sidebar.markdown("---")
st.sidebar.subheader("Punto di Partenza")
casa_lat = st.sidebar.number_input("Latitudine Partenza", value=43.1932389, format="%.7f")
casa_lon = st.sidebar.number_input("Longitudine Partenza", value=13.5792209, format="%.7f")

# --- 2. CARICAMENTO DATI ---
uploaded_file = st.file_uploader("Scegli il file clienti (CSV con ; o Excel)", type=['csv', 'xlsx'])

if uploaded_file is not None:
    try:
        # Gestione sia di Excel che di CSV
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, sep=';', decimal=',')
        else:
            df = pd.read_excel(uploaded_file)
        
        # Pulizia date
        df['Ultima Visita'] = pd.to_datetime(df['Ultima Visita'], dayfirst=True)
        
        # Calcolo scaduti
        oggi = datetime.now()
        df['Giorni Passati'] = (oggi - df['Ultima Visita']).dt.days
        clienti_da_visitare = df[df['Giorni Passati'] >= df['Frequenza (giorni)']].copy()

        st.success(f"Database caricato! Clienti da visitare oggi: {len(clienti_da_visitare)}")

        if st.button("🚀 CALCOLA GIRO DI OGGI"):
            # --- 3. LOGICA DI CALCOLO (Nearest Neighbor) ---
            tempo_impiegato_minuti = 0
            ore_max_minuti = ore_lavoro_disp * 60
            posizione_attuale = {'lat': casa_lat, 'lon': casa_lon}
            giro_visite = []

            while tempo_impiegato_minuti < ore_max_minuti and not clienti_da_visitare.empty:
                distanza_migliore = float('inf')
                prossimo_cliente_idx = -1

                for index, row in clienti_da_visitare.iterrows():
                    dist_km = haversine(posizione_attuale['lon'], posizione_attuale['lat'],
                                        row['Longitudine'], row['Latitudine'])
                    if dist_km < distanza_migliore:
                        distanza_migliore = dist_km
                        prossimo_cliente_idx = index

                if prossimo_cliente_idx != -1:
                    cliente = clienti_da_visitare.loc[prossimo_cliente_idx]
                    tempo_viaggio = (distanza_migliore / velocita_media) * 60
                    tempo_totale_step = tempo_viaggio + cliente['Durata']

                    if (tempo_impiegato_minuti + tempo_totale_step) <= ore_max_minuti:
                        tempo_impiegato_minuti += tempo_totale_step
                        giro_visite.append({
                            'Nome': cliente['Nome Cliente'],
                            'Indirizzo': cliente['Indirizzo'],
                            'Viaggio': round(tempo_viaggio),
                            'Visita': cliente['Durata']
                        })
                        posizione_attuale = {'lat': cliente['Latitudine'], 'lon': cliente['Longitudine']}
                        clienti_da_visitare = clienti_da_visitare.drop(prossimo_cliente_idx)
                    else:
                        break
                else:
                    break

            # --- 4. RISULTATI ---
            st.divider()
            st.header("📋 Itinerario Ottimizzato")
            st.info(f"Tempo totale stimato: **{int(tempo_impiegato_minuti // 60)} ore e {int(tempo_impiegato_minuti % 60)} minuti**")

            for i, tappa in enumerate(giro_visite):
                with st.expander(f"📌 TAPPA {i+1}: {tappa['Nome']}"):
                    st.write(f"🏠 **Indirizzo:** {tappa['Indirizzo']}")
                    st.write(f"🚗 **Tempo di guida:** {tappa['Viaggio']} min")
                    st.write(f"⏱️ **Durata visita:** {tappa['Visita']} min")
                    # Campo report ottimizzato per mobile
                    st.text_area("Inserisci Report Visita:", key=f"report_{i}")
                    st.button("Salva Report", key=f"btn_{i}")

    except Exception as e:
        st.error(f"Errore nel caricamento: {e}. Controlla che il file abbia le colonne Latitudine, Longitudine, Nome Cliente, Durata, Frequenza (giorni), Ultima Visita.")

else:
    st.info("In attesa del caricamento del file clienti...")
