import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Gestione Clienti Live", layout="wide")
st.title("🚗 Seleziona i Clienti da Visitare")

URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv"

@st.cache_data(ttl=600) # Ricarica i dati ogni 10 minuti
def get_data(url):
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip().str.lower()
    
    # PULIZIA NUMERICA (Risolve l'errore str / float)
    for col in ['latitudine', 'longitudine', 'frequenza (giorni)']:
        if col in df.columns:
            # Rimuove spazi, cambia virgole in punti e forza a numero
            df[col] = df[col].astype(str).str.replace(',', '.').str.strip()
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Pulizia Date
    df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
    return df

try:
    df_raw = get_data(URL_FOGLIO)
    
    # Creazione colonna selezione se non esiste nel foglio
    if 'visitare' not in df_raw.columns:
        df_raw['visitare'] = "NO"
    df_raw['vai'] = df_raw['visitare'].astype(str).str.upper() == 'SI'

    # Rimuoviamo righe totalmente vuote o senza coordinate per la mappa
    df_pulito = df_raw.dropna(subset=['latitudine', 'longitudine', 'nome cliente']).copy()

    st.write("### 📝 Lista Completa Clienti")
    st.info("Usa la colonna 'VAI' per selezionare i clienti e vederli sulla mappa.")

    # EDITOR DI DATI
    edited_df = st.data_editor(
        df_pulito[['vai', 'nome cliente', 'indirizzo', 'ultima visita', 'frequenza (giorni)']],
        column_config={
            "vai": st.column_config.CheckboxColumn("VAI", default=False),
            "ultima visita": st.column_config.DateColumn("Ultima Visita", format="DD/MM/YYYY"),
        },
        disabled=["nome cliente", "indirizzo", "ultima visita", "frequenza (giorni)"],
        hide_index=True,
        use_container_width=True
    )

    # FILTRO SELEZIONATI
    nomi_selezionati = edited_df[edited_df['vai'] == True]['nome cliente'].tolist()
    clienti_per_giro = df_pulito[df_pulito['nome cliente'].isin(nomi_selezionati)].copy()

    st.divider()

    if not clienti_per_giro.empty:
        # Ridenominazione per st.map
        mappa_df = clienti_per_giro.rename(columns={'latitudine': 'latitude', 'longitudine': 'longitude'})
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.write("### 📋 Riepilogo Selezione")
            for _, row in clienti_per_giro.iterrows():
                with st.container(border=True):
                    st.write(f"**{row['nome cliente']}**")
                    # Link diretto a Google Maps
                    url_maps = f"https://www.google.com/maps/search/?api=1&query={row['latitudine']},{row['longitudine']}"
                    st.link_button("🚗 Naviga", url_maps)
        
        with col2:
            st.write("### 📍 Mappa del Giro")
            st.map(mappa_df[['latitude', 'longitude']])
            
    else:
        st.warning("Seleziona almeno un cliente dalla tabella sopra cliccando su 'VAI'.")

except Exception as e:
    st.error(f"Si è verificato un errore: {e}")
