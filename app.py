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
        
        # ELENCO COMPLETO DELLE COLONNE CRM
        colonne_necessarie = [
            'contatto', 'referente', 'posizione referente', 'mail', 
            'telefono', 'cellulare', 'note', 'visitare'
        ]
        for col in colonne_necessarie:
            if col not in df.columns: df[col] = ""
            
        for c in ['latitude', 'longitude', 'frequenza (giorni)']:
            if c in df.columns: 
                df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '.'), errors='coerce')
        
        df['visitare'] = df['visitare'].replace("", "SI").fillna("SI").astype(str).str.upper()
        df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except: return pd.DataFrame()

# --- 2. STATO DELL'APP ---
if 'start_lat' not in st.session_state: st.session_state.start_lat = 43.1924
if 'start_lon' not in st.session_state: st.session_state.start_lon = 13.5797
if 'h_inizio' not in st.session_state: st.session_state.h_inizio = time(9, 0)
if 'h_fine' not in st.session_state: st.session_state.h_fine = time(18, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'spostamenti' not in st.session_state: st.session_state.spostamenti = {}

URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132"
if 'df_master' not in st.session_state:
    st.session_state.df_master = fetch_data(URL_FOGLIO)

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
            df_s['g_p'] = (pd.to_datetime(dt_l) - df_s['ultima visita']).dt.days.fillna(999)
            urg = df_s[(df_s['visitare'] == 'SI') & (df_s['g_p'] >= df_s['frequenza (giorni)'])].to_dict('records')
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
    t_oggi, t_sett, t_ana, t_nuovo, t_par = st.tabs([
        "🚀 Giro Oggi", "📅 Agenda 8 Sett", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"
    ])

    with t_oggi:
        st.header(f"📍 Giro di Oggi")
        idx_g = datetime.now().weekday()
        if idx_g < 5:
            tappe = piano["Settimana 1"][idx_g]
            if tappe:
                c1, c2 = st.columns([1, 2])
                with c1:
                    for t in tappe:
                        with st.container(border=True):
                            st.write(f"🕒 **{t['ora']}** - {t['nome cliente']}")
                            st.caption(f"👤 {t.get('referente','')} ({t.get('posizione referente','')})")
                            st.caption(f"📞 {t.get('cellulare','')}")
                            st.link_button("🚗 Naviga", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}", use_container_width=True)
                with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
            else: st.info("Nessuna visita in programma.")

    with t_ana:
        st.header("👤 Gestione Anagrafica")
        cerca = st.text_input("🔍 Cerca cliente (nome o città):", "", key="search_ana").lower()
        lista = [n for n in sorted(st.session_state.df_master['nome cliente'].unique()) if cerca in n.lower()]
        if lista:
            scelto = st.selectbox("Seleziona cliente:", lista)
            idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
            d = st.session_state.df_master.loc[idx]
            with st.form("edit_crm_completo"):
                col1, col2 = st.columns(2)
                with col1:
                    un = st.text_input("Ragione Sociale", d['nome cliente'])
                    ui = st.text_input("Indirizzo", d['indirizzo'])
                    uf = st.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
                    um = st.text_input("Mail", d.get('mail',''))
                with col2:
                    ut = st.text_input("Telefono Fisso", d.get('telefono',''))
                    uc = st.text_input("Cellulare", d.get('cellulare',''))
                    uv = st.toggle("Abilita nel Giro", value=(d['visitare'] == 'SI'))
                    ud = st.date_input("Ultima Visita", value=(d['ultima visita'].date() if pd.notnull(d['ultima visita']) else datetime.now().date()))
                
                st.write("---")
                c3, c4 = st.columns(2)
                with c3:
                    uref = st.text_input("Referente (Nome)", d.get('referente',''))
                    upos = st.text_input("Posizione Referente", d.get('posizione referente',''))
                with c4:
                    ucon = st.text_input("Contatto (Tipo/Note rapide)", d.get('contatto',''))

                unot = st.text_area("Note Generali", d.get('note',''))
                
                if st.form_submit_button("💾 Salva Modifiche"):
                    st.session_state.df_master.at[idx, 'nome cliente'] = un
                    st.session_state.df_master.at[idx, 'indirizzo'] = ui
                    st.session_state.df_master.at[idx, 'frequenza (giorni)'] = uf
                    st.session_state.df_master.at[idx, 'mail'] = um
                    st.session_state.df_master.at[idx, 'telefono'] = ut
                    st.session_state.df_master.at[idx, 'cellulare'] = uc
                    st.session_state.df_master.at[idx, 'visitare'] = 'SI' if uv else 'NO'
                    st.session_state.df_master.at[idx, 'referente'] = uref
                    st.session_state.df_master.at[idx, 'posizione referente'] = upos
                    st.session_state.df_master.at[idx, 'contatto'] = ucon
                    st.session_state.df_master.at[idx, 'note'] = unot
                    st.session_state.df_master.at[idx, 'ultima visita'] = pd.to_datetime(ud)
                    st.success("Dati salvati!"); st.rerun()

    with t_nuovo:
        st.header("➕ Nuovo Cliente")
        new_lat, new_lon = 0.0, 0.0
        if st.button("📍 Geocalizza Posizione Attuale"):
            g_new = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps_new')
            if g_new:
                new_lat, new_lon = g_new['latitude'], g_new['longitude']
                st.success(f"Posizione fissata: {new_lat}, {new_lon}")

        with st.form("nuovo_crm"):
            nc1, nc2 = st.columns(2)
            with nc1:
                nn = st.text_input("Ragione Sociale *")
                ni = st.text_input("Indirizzo")
                nf = st.number_input("Frequenza (gg)", value=30)
                nm = st.text_input("Mail")
            with nc2:
                nt = st.text_input("Telefono Fisso")
                n_c = st.text_input("Cellulare")
                nla = st.number_input("Lat", value=new_lat if new_lat != 0 else st.session_state.start_lat, format="%.6f")
                nlo = st.number_input("Lon", value=new_lon if new_lon != 0 else st.session_state.start_lon, format="%.6f")
            
            st.write("---")
            nc3, nc4 = st.columns(2)
            with nc3:
                nr = st.text_input("Referente")
                np = st.text_input("Posizione Referente")
            with nc4:
                nco = st.text_input("Contatto")
            
            n_note = st.text_area("Note Cliente")
            
            if st.form_submit_button("✅ Aggiungi Cliente"):
                if nn:
                    rigo = {
                        'nome cliente': nn, 'indirizzo': ni, 'frequenza (giorni)': nf, 'mail': nm,
                        'telefono': nt, 'cellulare': n_c, 'latitude': nla, 'longitude': nlo,
                        'referente': nr, 'posizione referente': np, 'contatto': nco, 'note': n_note,
                        'visitare': 'SI', 'ultima visita': pd.Timestamp('2000-01-01')
                    }
                    st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([rigo])], ignore_index=True)
                    st.success(f"{nn} inserito!"); st.rerun()

    with t_par:
        st.header("⚙️ Parametri")
        st.session_state.h_inizio = st.time_input("Inizio", st.session_state.h_inizio)
        st.session_state.h_fine = st.time_input("Fine", st.session_state.h_fine)
        if st.button("Reset Dati"):
            st.cache_data.clear()
            if 'df_master' in st.session_state: del st.session_state.df_master
            st.rerun()
else:
    st.error("Dati non caricati.")
