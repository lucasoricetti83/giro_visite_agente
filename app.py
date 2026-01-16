import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Gestione Visite Agente", layout="wide")
st.title("🚗 Il Mio Giro Visite")

# Link del tuo foglio Google
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv"

@st.cache_data(ttl=60)
def get_clean_data(url):
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip().str.lower()
    
    # --- SUPER PULIZIA NUMERICA ---
    # Forza latitudine, longitudine e frequenza a essere numeri puri
    for col in ['latitudine', 'longitudine', 'frequenza (giorni)']:
        if col in df.columns:
            # Rimuove tutto ciò che non è numero, punto o meno
            df[col] = df[col].astype(str).str.replace(',', '.').str.replace(r'[^0-9.-]', '', regex=True)
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # --- GESTIONE DATE ---
    df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
    return df

try:
    df_raw = get_clean_data(URL_FOGLIO)
    
    # Prepariamo la colonna "VAI" (checkbox)
    if 'visitare' not in df_raw.columns:
        df_raw['visitare'] = "NO"
    df_raw['vai'] = df_raw['visitare'].astype(str).str.upper().str.strip() == 'SI'

    # Rimuoviamo righe inutilizzabili (senza nome o senza coordinate)
    df_pulito = df_raw.dropna(subset=['nome cliente', 'latitudine', 'longitudine']).copy()

    st.write("### 📋 Elenco Clienti")
    st.info("Spunta la colonna **VAI** per selezionare i clienti che vuoi visitare oggi.")

    # TABELLA INTERATTIVA
    # Mostriamo solo le colonne utili per la scelta
    df_visualizzazione = df_pulito[['vai', 'nome cliente', 'indirizzo', 'ultima visita', 'frequenza (giorni)']]
    
    edited_df = st.data_editor(
        df_visualizzazione,
        column_config={
            "vai": st.column_config.CheckboxColumn("VAI", default=False),
            "ultima visita": st.column_config.DateColumn("Ultima Visita", format="DD/MM/YYYY"),
            "frequenza (giorni)": "Frequenza",
            "nome cliente": "Cliente",
            "indirizzo": "Indirizzo"
        },
        disabled=["nome cliente", "indirizzo", "ultima visita", "frequenza (giorni)"],
        hide_index=True,
        use_container_width=True
    )

    # Filtriamo i selezionati dall'utente nell'app
    nomi_selezionati = edited_df[edited_df['vai'] == True]['nome cliente'].tolist()
    clienti_per_giro = df_pulito[df_pulito['nome cliente'].isin(nomi_selezionati)].copy()

    st.divider()

    if not clienti_per_giro.empty:
        # Prepariamo i nomi colonne per la mappa di Streamlit (lat/lon)
        mappa_df = clienti_per_giro.rename(columns={'latitudine': 'latitude', 'longitudine': 'longitude'})
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.write("### 🚗 Navigazione")
            for _, row in clienti_per_giro.iterrows():
                # Box per ogni cliente selezionato
                with st.container(border=True):
                    st.markdown(f"**{row['nome cliente']}**")
                    st.caption(f"📍 {row['indirizzo']}")
                    # Link ottimizzato per Google Maps
                    google_maps_url = f"https://www.google.com/maps/search/?api=1&query={row['latitudine']},{row['longitudine']}"
                    st.link_button(f"Apri Navigatore", google_maps_url, use_container_width=True)
        
        with col2:
            st.write("### 📍 Mappa")
            st.map(mappa_df[['latitude', 'longitude']], color="#FF0000")
            
    else:
        st.warning("Seleziona uno o più clienti dalla tabella sopra per vederli sulla mappa.")

except Exception as e:
    st.error(f"Errore nel caricamento: {e}")
    st.info("💡 Controlla che il tuo Foglio Google non abbia celle con errori (#N/A) o scritte strane nelle colonne numeriche.")
