{\rtf1\ansi\ansicpg1252\cocoartf2822
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww14840\viewh10600\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 import streamlit as st\
import pandas as pd\
from datetime import datetime\
from math import radians, cos, sin, asin, sqrt\
\
# --- FUNZIONI MATEMATICHE ---\
def haversine(lon1, lat1, lon2, lat2):\
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])\
    dlon = lon2 - lon1\
    dlat = lat2 - lat1\
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2\
    c = 2 * asin(sqrt(a))\
    return c * 6371\
\
# --- CONFIGURAZIONE APP ---\
st.set_page_config(page_title="Il Mio Giro Visite", page_icon="\uc0\u55357 \u56983 ")\
st.title("\uc0\u55357 \u56983  Gestione Giro Visite")\
\
# Caricamento file\
uploaded_file = st.file_uploader("Carica il tuo file clienti.csv", type="csv")\
\
if uploaded_file:\
    # Leggiamo il file (sep=';' perch\'e9 \'e8 il formato standard dei CSV italiani)\
    df = pd.read_csv(uploaded_file, sep=';', decimal=',')\
    \
    # Parametri nella barra laterale\
    st.sidebar.header("Impostazioni")\
    ore_disp = st.sidebar.slider("Ore disponibili", 1, 12, 8)\
    velocita = st.sidebar.number_input("Velocit\'e0 media (km/h)", value=40)\
    \
    # Coordinate di partenza (puoi cambiarle qui con le tue)\
    CASA_LAT = 43.1932389\
    CASA_LON = 13.5792209\
\
    if st.button("Calcola Giro di Oggi"):\
        # Preparazione dati\
        df['Ultima Visita'] = pd.to_datetime(df['Ultima Visita'], dayfirst=True)\
        oggi = datetime.now()\
        df['Giorni Passati'] = (oggi - df['Ultima Visita']).dt.days\
        clienti_da_visitare = df[df['Giorni Passati'] >= df['Frequenza (giorni)']].copy()\
\
        # Algoritmo di calcolo\
        tempo_impiegato = 0\
        ore_max_minuti = ore_disp * 60\
        posizione_attuale = \{'lat': CASA_LAT, 'lon': CASA_LON\}\
        giro_visite = []\
\
        while tempo_impiegato < ore_max_minuti and not clienti_da_visitare.empty:\
            distanza_migliore = float('inf')\
            prossimo_idx = -1\
\
            for index, row in clienti_da_visitare.iterrows():\
                dist = haversine(posizione_attuale['lon'], posizione_attuale['lat'],\
                                 row['Longitudine'], row['Latitudine'])\
                if dist < distanza_migliore:\
                    distanza_migliore = dist\
                    prossimo_idx = index\
\
            if prossimo_idx != -1:\
                cliente = clienti_da_visitare.loc[prossimo_idx]\
                tempo_viaggio = (distanza_migliore / velocita) * 60\
                tempo_totale_tappa = tempo_viaggio + cliente['Durata']\
\
                if (tempo_impiegato + tempo_totale_tappa) <= ore_max_minuti:\
                    tempo_impiegato += tempo_totale_tappa\
                    giro_visite.append(\{\
                        'Nome': cliente['Nome Cliente'],\
                        'Indirizzo': cliente['Indirizzo'],\
                        'Viaggio': round(tempo_viaggio),\
                        'Visita': cliente['Durata']\
                    \})\
                    posizione_attuale = \{'lat': cliente['Latitudine'], 'lon': cliente['Longitudine']\}\
                    clienti_da_visitare = clienti_da_visitare.drop(prossimo_idx)\
                else: break\
            else: break\
\
        # Visualizzazione Risultati\
        st.header("\uc0\u55357 \u56523  Itinerario Consigliato")\
        st.info(f"Tempo totale stimato: \{int(tempo_impiegato // 60)\}h \{int(tempo_impiegato % 60)\}min")\
        \
        for i, tappa in enumerate(giro_visite):\
            with st.expander(f"\{i+1\}. \{tappa['Nome']\}"):\
                st.write(f"\uc0\u55357 \u56525  **Indirizzo:** \{tappa['Indirizzo']\}")\
                st.write(f"\uc0\u55357 \u56983  **Guida:** \{tappa['Viaggio']\} min")\
                st.write(f"\uc0\u9201 \u65039  **Durata Visita:** \{tappa['Visita']\} min")\
                st.text_area("Inserisci report visita", key=f"report_\{i\}")}