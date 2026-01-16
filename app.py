import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Gestione Clienti Live", layout="wide")
st.title("🚗 Il Mio Giro Visite")

# Link del foglio Google in formato CSV
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv"

@st.cache_data(ttl=60) # Ricarica i dati ogni minuto
def get_clean_data(url):
    df = pd.read_csv(url)
    # Puliamo i nomi delle colonne (tutto minuscolo e senza spazi ai lati)
    df.columns = df.columns.str.strip().str.lower()
    
    # --- PULIZIA NUMERICA PROFONDA ---
    # Queste sono le colonne che DEVONO essere numeri
    cols_numeriche = ['latitudine', 'longitudine', 'frequenza (giorni)']
    
    for col in cols_numeriche:
        if col in df.columns:
            # 1. Trasforma tutto in stringa
            # 2. Sostituisce la virgola con il punto
            # 3. Trasforma in numero (se non riesce, mette NaN)
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.').str.strip(), errors='coerce')
    
    # --- PULIZIA DATE ---
    df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
    
    # Rimuoviamo righe dove mancano dati vitali (nome o coordinate)
    df = df.dropna(subset=['nome cliente', 'latitudine', 'longitudine'])
    return df

try:
    df_raw = get_clean_data(URL_FOGLIO)
    
    # Gestione colonna selezione
    if 'visitare' not in df_raw.columns:
        df_raw['visitare'] = "NO"
    
    # Creiamo la checkbox basandoci sul testo "SI"
    df_raw['vai'] = df_raw['visitare'].astype(str).str.upper().str.strip() == 'SI'

    st.write("### 📝 Elenco Clienti")
    st.info("Seleziona chi vuoi visitare cliccando su 'VAI'")

    # EDITOR DI DATI (Tabella interattiva)
    edited_df = st.data_editor(
        df_raw[['vai', 'nome cliente', 'indirizzo', 'ultima visita', 'frequenza (giorni)']],
        column_config={
            "vai": st.column_config.CheckboxColumn("VAI", default=False),
            "ultima visita": st.column_config.DateColumn("Ultima Visita", format="DD/MM/YYYY"),
        },
        disabled=["nome cliente", "indirizzo", "ultima visita", "frequenza (giorni)"],
        hide_index=True,
        use_container_width=True
    )

    # Filtriamo i selezionati
    nomi_scelti = edited_df[edited_df['vai'] == True]['nome cliente'].tolist()
    clienti_per_giro = df_raw[df_raw['nome cliente'].isin(nomi_scelti)].copy()

    st.divider()

    if not clienti_per_giro.empty:
        # Prepariamo i dati per la mappa (rinominando per Streamlit)
        mappa_df = clienti_per_giro.rename(columns={'latitudine': 'latitude', 'longitudine': 'longitude'})
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.write("### 📋 Destinazioni Selezionate")
            for _, row in clienti_per_giro.iterrows():
                with st.expander(f"📍 {row['nome cliente']}"):
                    st.write(f"🏠 {row['indirizzo']}")
                    # LINK GOOGLE MAPS CORRETTO
                    url_google = f"https://www.google.com/maps/search/?api=1&query={row['latitudine']},{row['longitudine']}"
                    st.link_button("🚗 Apri Navigatore", url_google, use_container_width=True)
        
        with col2:
            st.write("### 📍 Posizione sulla Mappa")
            st.map(mappa_df[['latitude', 'longitude']])
            
    else:
        st.warning("👈 Spunta almeno un cliente nella colonna 'VAI' per iniziare.")

except Exception as e:
    st.error(f"Si è verificato un errore nei dati: {e}")
    st.info("Consiglio: Controlla che nel foglio Google le coordinate siano numeri e non contengano simboli o lettere.")
