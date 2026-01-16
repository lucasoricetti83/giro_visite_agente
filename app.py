import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Gestione Clienti Live", layout="wide")
st.title("🚗 Seleziona i Clienti da Visitare")

URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv"

try:
    # 1. Carichiamo i dati
    df_raw = pd.read_csv(URL_FOGLIO)
    df_raw.columns = df_raw.columns.str.strip().str.lower()
    
    # 2. CONVERSIONE SICURA (Risolve l'errore str / float)
    # Trasformiamo latitudine, longitudine e frequenza in numeri. 
    # Se c'è del testo, lo trasforma in "NaN" (non un numero) per non bloccare l'app.
    for col in ['latitudine', 'longitudine', 'frequenza (giorni)']:
        if col in df_raw.columns:
            # Sostituisce la virgola con il punto se necessario e converte
            df_raw[col] = pd.to_numeric(df_raw[col].astype(str).str.replace(',', '.'), errors='coerce')

    # 3. Pulizia Date
    df_raw['ultima visita'] = pd.to_datetime(df_raw['ultima visita'], dayfirst=True, errors='coerce')
    
    # Selezione iniziale
    if 'visitare' not in df_raw.columns:
        df_raw['visitare'] = "NO"
    df_raw['vai'] = df_raw['visitare'].astype(str).str.upper() == 'SI'

    st.write("### 📝 Lista Completa Clienti")
    
    # 4. EDITOR DI DATI
    # Filtriamo via le righe che hanno coordinate totalmente mancanti
    df_pulito = df_raw.dropna(subset=['latitudine', 'longitudine']).copy()

    edited_df = st.data_editor(
        df_pulito[['vai', 'nome cliente', 'indirizzo', 'ultima visita', 'frequenza (giorni)']],
        column_config={
            "vai": st.column_config.CheckboxColumn("VAI", default=False),
            "ultima visita": st.column_config.DateColumn("Ultima Visita", format="DD/MM/YYYY"),
        },
        disabled=["nome cliente", "indirizzo", "ultima visita", "frequenza (giorni)"],
        hide_index=True,
    )

    # 5. FILTRO SELEZIONATI
    nomi_selezionati = edited_df[edited_df['vai'] == True]['nome cliente'].tolist()
    clienti_per_giro = df_pulito[df_pulito['nome cliente'].isin(nomi_selezionati)].copy()

    st.divider()

    if not clienti_per_giro.empty:
        # Ridenominazione per la mappa
        mappa_df = clienti_per_giro.rename(columns={'latitudine': 'latitude', 'longitudine': 'longitude'})
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.write("### 📋 Riepilogo Selezione")
            for _, row in clienti_per_giro.iterrows():
                st.write(f"📍 **{row['nome cliente']}**")
                # Bottone per aprire Google Maps direttamente dall'app
                link_maps = f"https://www.google.com/maps/search/?api=1&query={row['latitudine']},{row['longitudine']}"
                st.link_button(f"Vai a {row['nome cliente']}", link_maps)
        
        with col2:
            st.write("### 📍 Mappa del Giro")
            st.map(mappa_df[['latitude', 'longitude']])
            
    else:
        st.warning("Seleziona almeno un cliente dalla tabella sopra.")

except Exception as e:
    st.error(f"Si è verificato un errore: {e}")
