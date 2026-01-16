import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Giro Visite Professionale", layout="wide")
st.title("🚗 Gestione Visite")

# Link specifico con il GID del tuo foglio dati
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132"

@st.cache_data(ttl=60)
def load_and_clean_data(url):
    # Leggiamo il file lasciando che Pandas capisca se usa , o ;
    df = pd.read_csv(url, sep=None, engine='python')
    
    # Pulizia nomi colonne
    df.columns = df.columns.str.strip().str.lower()
    
    # Selettore colonne fondamentali (mappa i nomi italiani a quelli che servono)
    # Cerchiamo di capire come si chiamano le tue colonne anche se variano
    col_map = {
        'nome cliente': 'cliente',
        'indirizzo': 'indirizzo',
        'ultima visita': 'ultima_visita',
        'frequenza (giorni)': 'frequenza',
        'latitude': 'lat',
        'longitude': 'lon',
        'visitare': 'visitare'
    }
    
    # Pulizia specifica per i numeri italiani (con la virgola)
    for col in ['latitude', 'longitude', 'frequenza (giorni)']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(',', '.').str.strip()
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Pulizia Date
    df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
    
    return df

try:
    df_raw = load_and_clean_data(URL_FOGLIO)
    
    # Rimuoviamo righe senza nome o coordinate
    df_clean = df_raw.dropna(subset=['nome cliente', 'latitude', 'longitude']).copy()

    # Creiamo la selezione "VAI"
    if 'visitare' not in df_clean.columns:
        df_clean['visitare'] = "NO"
    df_clean['vai'] = df_clean['visitare'].astype(str).str.upper() == 'SI'

    st.subheader("📋 Lista Clienti")
    
    # Editor interattivo
    edited_df = st.data_editor(
        df_clean[['vai', 'nome cliente', 'indirizzo', 'ultima visita', 'frequenza (giorni)']],
        column_config={
            "vai": st.column_config.CheckboxColumn("VAI"),
            "ultima visita": st.column_config.DateColumn("Ultima Visita", format="DD/MM/YYYY"),
        },
        disabled=["nome cliente", "indirizzo", "ultima visita", "frequenza (giorni)"],
        hide_index=True,
        use_container_width=True
    )

    # Filtro clienti scelti
    nomi_scelti = edited_df[edited_df['vai'] == True]['nome cliente'].tolist()
    clienti_giro = df_clean[df_clean['nome cliente'].isin(nomi_scelti)].copy()

    st.divider()

    if not clienti_giro.empty:
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.write("### 🚗 Destinazioni")
            for _, row in clienti_giro.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{row['nome cliente']}**")
                    # Link Google Maps per navigazione
                    nav_url = f"https://www.google.com/maps/search/?api=1&query={row['latitude']},{row['longitude']}"
                    st.link_button("Avvia Navigatore", nav_url, use_container_width=True)
        
        with col2:
            st.write("### 📍 Mappa")
            # Prepariamo i nomi per st.map
            map_data = clienti_giro.rename(columns={'latitude': 'lat', 'longitude': 'lon'})
            st.map(map_data[['lat', 'lon']])
    else:
        st.info("Spunta i clienti nella tabella sopra per vederli sulla mappa.")

except Exception as e:
    st.error(f"Errore durante il caricamento: {e}")
    st.info("Verifica che i nomi delle colonne nel foglio siano: nome cliente, indirizzo, ultima visita, frequenza (giorni), latitude, longitude, visitare")
