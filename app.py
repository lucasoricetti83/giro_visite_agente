import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
from streamlit_js_eval import streamlit_js_eval

# --- 1. CONFIGURAZIONE E FUNZIONI ---
st.set_page_config(page_title="Giro Visite & CRM Pro", layout="wide")

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    d = 2 * 6371 * asin(sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2))
    return d

@st.cache_data(ttl=60)
def fetch_data(url):
    try:
        df = pd.read_csv(url, sep=None, engine='python')
        df.columns = df.columns.str.strip().str.lower()
        # Pulizia numeri
        for c in ['latitude', 'longitude', 'frequenza (giorni)']:
            if c in df.columns: 
                df[c] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce') if 'col' in locals() else pd.to_numeric(df[c].astype(str).str.replace(',', '.'), errors='coerce')
        
        # Gestione colonna 'visitare' (SI/NO)
        if 'visitare' not in df.columns:
            df['visitare'] = 'SI'
        df['visitare'] = df['visitare'].fillna('SI').astype(str).str.upper()
        
        # Gestione date vuote (non sono più un vincolo)
        df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except: return pd.DataFrame()

# --- 2. STATO DELL'APP ---
if 'df_master' not in st.session_state:
    st.session_state.df_master = fetch_data("https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132")
if 'start_lat' not in st.session_state: st.session_state.start_lat = 43.1924
if 'start_lon' not in st.session_state: st.session_state.start_lon = 13.5797
if 'h_inizio' not in st.session_state: st.session_state.h_inizio = time(9, 0)
if 'h_fine' not in st.session_state: st.session_state.h_fine = time(18, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'spostamenti' not in st.session_state: st.session_state.spostamenti = {}

# --- 3. LOGICA DI CALCOLO ---
def genera_agenda():
    if st.session_state.df_master.empty: return {}, datetime.now()
    oggi = datetime.now()
    lun_ref = oggi - timedelta(days=oggi.weekday())
    df_s = st.session_state.df_master.copy()
    piano = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
    
    for s in range(1, 9):
        for g in range(5):
            dt_c = (lun_ref + timedelta(weeks=s-1, days=g)).date()
            dt_l = st.session_state.spostamenti.get(dt_c, dt_c)
            
            # Calcolo giorni passati gestendo i valori vuoti (NaT)
            df_s['g_p'] = (pd.to_datetime(dt_l) - df_s['ultima visita']).dt.days.fillna(999)
            
            # FILTRO CRUCIALE: Solo chi ha 'visitare' == SI e frequenza scaduta
            urg = df_s[
                (df_s['visitare'] == 'SI') & 
                (df_s['g_p'] >= df_s['frequenza (giorni)'])
            ].to_dict('records')
            
            o_s, p_s = datetime.combine(dt_c, st.session_state.h_inizio), (st.session_state.start_lat, st.session_state.start_lon)
            while urg:
                px = min(urg, key=lambda x: haversine(p_s[0], p_s[1], x['latitude'], x['longitude']))
                dist = haversine(p_s[0], p_s[1], px['latitude'], px['longitude'])
                arr = o_s + timedelta(minutes=(dist/50)*60)
                if (arr + timedelta(minutes=st.session_state.durata_v)) <= datetime.combine(dt_c, st.session_state.h_fine):
                    px['ora'] = arr.strftime("%H:%M")
                    piano[f"Settimana {s}"][g].append(px)
                    df_s.loc[df_s['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(dt_l)
                    o_s, p_s = arr + timedelta(minutes=st.session_state.durata_v), (px['latitude'], px['longitude'])
                    urg.remove(px)
                else: break
    return piano, lun_ref

# --- 4. INTERFACCIA ---
if not st.session_state.df_master.empty:
    piano, lun_base = genera_agenda()
    t1, t2, t3, t4 = st.tabs(["🚀 Giro Oggi", "📅 8 Settimane", "👤 Anagrafica", "⚙️ Parametri"])

    with t1:
        st.header("Giro di Oggi")
        idx_g = datetime.now().weekday()
        if idx_g < 5:
            tappe = piano["Settimana 1"][idx_g]
            if tappe:
                c1, c2 = st.columns([1, 2])
                with c1:
                    for t in tappe:
                        with st.container(border=True):
                            st.write(f"🕒 **{t['ora']}** - {t['nome cliente']}")
                            st.link_button("🚗 Naviga", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}", use_container_width=True)
                with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
            else: st.info("Nessun cliente programmato per oggi (o tutti disabilitati).")
        else: st.write("Weekend!")

    with t2:
        s_sel = st.selectbox("Scegli Settimana:", [f"Settimana {i}" for i in range(1, 9)])
        cols = st.columns(5)
        giorni_nomi = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
        for i, col in enumerate(cols):
            with col:
                dt_g = (lun_base + timedelta(weeks=int(s_sel.split()[-1])-1, days=i)).date()
                st.subheader(giorni_nomi[i]); st.caption(dt_g.strftime("%d/%m"))
                for v in piano[s_sel][i]:
                    with st.container(border=True):
                        st.caption(v['ora']); st.write(f"**{v['nome cliente']}**")

    with t3:
        st.header("👤 Scheda Cliente")
        cerca = st.text_input("🔍 Cerca cliente:", "").lower()
        lista = [n for n in sorted(st.session_state.df_master['nome cliente'].unique()) if cerca in n.lower()]
        
        if lista:
            scelto = st.selectbox("Risultati:", lista)
            idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
            d = st.session_state.df_master.loc[idx]
            
            # Gestione data predefinita per il modulo
            val_data = d['ultima visita'].date() if pd.notnull(d['ultima visita']) else datetime.now().date()
            val_visitare = True if d['visitare'] == 'SI' else False

            with st.form("edit_crm"):
                f1, f2 = st.columns(2)
                with f1:
                    un = st.text_input("Nome Cliente", d['nome cliente'])
                    ui = st.text_input("Indirizzo", d['indirizzo'])
                    uf = st.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
                    # NUOVO TOGGLE ABILITA/DISABILITA
                    uv = st.toggle("Includi questo cliente nel Giro Visite", value=val_visitare)
                with f2:
                    ula = st.number_input("Latitudine", value=float(d['latitude']), format="%.6f")
                    ulo = st.number_input("Longitudine", value=float(d['longitude']), format="%.6f")
                    uda = st.date_input("Ultima Visita (Lascia oggi se mai visitato)", value=val_data)
                
                if st.form_submit_button("💾 Salva Modifiche Locale"):
                    st.session_state.df_master.at[idx, 'nome cliente'] = un
                    st.session_state.df_master.at[idx, 'indirizzo'] = ui
                    st.session_state.df_master.at[idx, 'frequenza (giorni)'] = uf
                    st.session_state.df_master.at[idx, 'latitude'] = ula
                    st.session_state.df_master.at[idx, 'longitude'] = ulo
                    st.session_state.df_master.at[idx, 'ultima visita'] = pd.to_datetime(uda)
                    st.session_state.df_master.at[idx, 'visitare'] = 'SI' if uv else 'NO'
                    st.success(f"Dati di {un} aggiornati!")
                    st.rerun()
        else: st.warning("Nessun cliente trovato.")

    with t4:
        st.header("⚙️ Parametri")
        # GPS, Orari e Scambio Giorni (già presenti e stabili)
        cp1, cp2 = st.columns(2)
        with cp1:
            if st.button("🎯 GPS"):
                g = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps')
                if g: st.session_state.start_lat, st.session_state.start_lon = g['latitude'], g['longitude']; st.rerun()
            st.session_state.h_inizio = st.time_input("Inizio", st.session_state.h_inizio)
            st.session_state.h_fine = st.time_input("Fine", st.session_state.h_fine)
            st.session_state.durata_v = st.slider("Minuti per visita", 15, 120, st.session_state.durata_v)
        with cp2:
            st.subheader("🔄 Sposta Giorno")
            d_da = st.date_input("Da:", datetime.now()); d_a = st.date_input("A:", datetime.now() + timedelta(days=1))
            if st.button("Scambia"): st.session_state.spostamenti[d_da] = d_a; st.session_state.spostamenti[d_a] = d_da; st.rerun()
            if st.button("Ricarica Foglio"): 
                st.cache_data.clear()
                del st.session_state.df_master
                st.rerun()
else: st.error("Errore: Collega il foglio Google correttamente.")
