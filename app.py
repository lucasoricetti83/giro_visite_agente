import streamlit as st
import pandas as pd

# Funzione di caricamento "corazzata"
def load_data(url):
    # Leggiamo il CSV forzando le colonne latitude/longitude come testo per pulirle noi
    df = pd.read_csv(url, dtype={'latitude': str, 'longitude': str})
    df.columns = df.columns.str.strip().str.lower()
    
    # Pulizia profonda: togliamo virgole e forziamo numeri
    for col in ['latitude', 'longitude', 'frequenza (giorni)']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(',', '.').str.strip()
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

# ... resto del codice ...
