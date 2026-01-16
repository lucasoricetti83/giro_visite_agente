import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Gestione Clienti Live", layout="wide")
st.title("🚗 Seleziona i Clienti da Visitare")

URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv"

try:
    # 1. Carichiamo tutti i dati
    df_raw = pd.read_csv(URL_FOGLIO)
    df_raw.columns = df_raw.columns.str.strip().str.lower()
    
    # 2. Pulizia Date
    df_raw['ultima visita'] = pd.to_datetime(df_raw['ultima visita'], dayfirst=True, errors='coerce')
    
    # Prepariamo la colonna per la selezione
    if 'visitare' not in df_raw.columns:
        df_raw['visitare'] = "NO"
    
    df_raw['vai'] = df_raw['visitare'].astype(str).str.upper() == 'SI'

    st.write("### 📝 Lista Completa Clienti")
    st.info("Spunta i clienti che vuoi visitare nella colonna 'VAI'")

    # 3. EDITOR DI DATI
    edited_df = st.data_editor(
        df_raw[['vai', 'nome cliente', 'indirizzo', 'ultima visita', 'frequenza (giorni)']],
        column_config={
            "vai": st.column_config.CheckboxColumn("VAI", default=False),
            "ultima visita": st.column_config.DateColumn("Ultima Visita", format="DD/MM/YYYY"),
        },
        disabled=["nome cliente", "indirizzo", "ultima visita", "frequenza (giorni)"],
        hide_index=True,
    )

    # 4. FILTRIAMO I SELEZIONATI E RINOMINIAMO PER LA MAPPA
    # Prendiamo solo i nomi selezionati
    nomi_selezionati = edited_df[edited_df['vai'] == True]['nome cliente'].tolist()
    
    # Recuperiamo i dati completi (incluse le coordinate) dal dataframe originale
    clienti_per_giro = df_raw[df_raw['nome cliente'].isin(nomi_selezionati)].copy()

    st.divider()

    if not clienti_per_giro.empty:
        st.success(f"Hai selezionato {len(clienti_per_giro)} clienti.")
        
        # --- SOLUZIONE ERRORE MAPPA ---
        # Rinominiamo le colonne da italiano a inglese solo per il comando st.map
        mappa_df = clienti_per_giro.rename(columns={
            'latitudine': 'latitude', 
            'longitudine': 'longitude'
        })
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.write("### 📋 Riepilogo Selezione")
            for i, row in clienti_per_giro.iterrows():
                st.write(f"📍 **{row['nome cliente']}**")
                st.caption(f"{row['indirizzo']}")
        
        with col2:
            st.write("### 📍 Mappa del Giro")
            # Ora la mappa troverà 'latitude' e 'longitude' e funzionerà!
            st.map(mappa_df[['latitude', 'longitude']])
            
    else:
        st.warning("Seleziona almeno un cliente dalla tabella sopra cliccando sulla colonna 'VAI'.")

except Exception as e:
    st.error(f"Errore: {e}")
