import streamlit as st
import pandas as pd
from datetime import datetime
from math import radians, cos, sin, asin, sqrt

# --- FUNZIONI ---
def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371

st.set_page_config(page_title="Gestione Clienti Live", layout="wide")
st.title("🚗 Seleziona i Clienti da Visitare")

URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv"

try:
    # 1. Carichiamo tutti i dati
    df_raw = pd.read_csv(URL_FOGLIO)
    df_raw.columns = df_raw.columns.str.strip().str.lower()
    
    # 2. Pulizia Date
    df_raw['ultima visita'] = pd.to_datetime(df_raw['ultima visita'], dayfirst=True, errors='coerce')
    
    # Creiamo una colonna "Seleziona" nell'app (inizialmente basata su cosa c'è nel foglio)
    if 'visitare' not in df_raw.columns:
        df_raw['visitare'] = "NO"
    
    # Convertiamo la colonna visitare in valori Booleani (True/False) per avere le checkbox nell'app
    df_raw['vai'] = df_raw['visitare'].astype(str).str.upper() == 'SI'

    st.write("### 📝 Lista Completa Clienti")
    st.info("Spunta i clienti che vuoi includere nel giro di oggi nella colonna 'VAI'")

    # 3. EDITOR DI DATI (Qui puoi scegliere chi visitare)
    # Mostriamo solo le colonne principali per non fare confusione
    edited_df = st.data_editor(
        df_raw[['vai', 'nome cliente', 'indirizzo', 'ultima visita', 'frequenza (giorni)']],
        column_config={
            "vai": st.column_config.CheckboxColumn("VAI", default=False),
            "ultima visita": st.column_config.DateColumn("Ultima Visita", format="DD/MM/YYYY"),
        },
        disabled=["nome cliente", "indirizzo", "ultima visita", "frequenza (giorni)"], # Blocca le altre colonne
        hide_index=True,
    )

    # 4. FILTRIAMO I SELEZIONATI
    clienti_per_giro = edited_df[edited_df['vai'] == True].copy()

    # Recuperiamo le coordinate per i selezionati dal dataframe originale
    clienti_per_giro = clienti_per_giro.merge(df_raw[['nome cliente', 'latitudine', 'longitudine']], on='nome cliente')

    st.divider()

    if not clienti_per_giro.empty:
        st.success(f"Hai selezionato {len(clienti_per_giro)} clienti.")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.write("### 📋 Riepilogo Selezione")
            for n in clienti_per_giro['nome cliente']:
                st.write(f"- {n}")
        
        with col2:
            st.write("### 📍 Mappa del Giro")
            st.map(clienti_per_giro[['latitudine', 'longitudine']])
            
        if st.button("🗺️ Apri tutti su Google Maps (Sperimentale)"):
            # Genera un link con più tappe (funziona meglio su PC che su iPhone)
            base_url = "https://www.google.com/maps/dir/"
            coords = "/".join([f"{r['latitudine']},{r['longitudine']}" for i, r in clienti_per_giro.iterrows()])
            st.link_button("👉 Clicca per l'itinerario", base_url + coords)
            
    else:
        st.warning("Seleziona almeno un cliente dalla tabella sopra per vedere la mappa.")

except Exception as e:
    st.error(f"Errore: {e}")
