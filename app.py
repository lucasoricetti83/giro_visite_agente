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
        
        # ELENCO COLONNE NECESSARIE - Se mancano nel foglio, le creiamo noi
        colonne_crm = ['contatto', 'referente', 'mail', 'telefono', 'cellulare', 'note', 'visitare']
        for col in colonne_crm:
            if col not in df.columns:
                df[col] = ""
        
        # Pulizia dati numerici
        for c in ['latitude', 'longitude', 'frequenza (giorni)']:
            if c in df.columns: 
                df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '.'), errors='coerce')
        
        # Default per la colonna visitare
        df['visitare'] = df['visitare'].replace("", "SI").fillna("SI").astype(str).str.upper()
        
        # Pulizia date
        df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
        
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except Exception as e:
        st.error(f"Errore nel caricamento: {e}")
        return pd.DataFrame()

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
    t1, t2, t3, t4 = st.tabs(["🚀 Giro Oggi", "📅 Agenda 8 Settimane", "👤 Anagrafica", "⚙️ Parametri"])

    with t1:
        st.header(f"📍 Giro del Giorno")
        idx_g = datetime.now().weekday()
        if idx_g < 5:
            tappe = piano["Settimana 1"][idx_g]
            if tappe:
                c1, c2 = st.columns([1, 2])
                with c1:
                    for t in tappe:
                        with st.container(border=True):
                            st.write(f"🕒 **{t['ora']}** - {t['nome cliente']}")
                            # Usiamo .get per sicurezza totale contro KeyError
                            cell = t.get('cellulare', '')
                            ref = t.get('referente', '')
                            st.caption(f"📞 {cell} | 👤 {ref}")
                            st.link_button("🚗 Naviga", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}", use_container_width=True)
                with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
            else: st.info("Nessuna visita programmata.")

    with t2:
        s_sel = st.selectbox("Scegli Settimana:", [f"Settimana {i}" for i in range(1, 9)])
        cols = st.columns(5)
        for i, col in enumerate(cols):
            with col:
                dt_g = (lun_base + timedelta(weeks=int(s_sel.split()[-1])-1, days=i)).date()
                st.subheader(dt_g.strftime("%A")); st.caption(dt_g.strftime("%d/%m"))
                for v in piano[s_sel][i]:
                    with st.container(border=True):
                        st.caption(v['ora']); st.write(f"**{v['nome cliente']}**")

    with t3:
        st.header("👤 Scheda Cliente")
        cerca = st.text_input("🔍 Cerca cliente:", "").lower()
        lista = [n for n in sorted(st.session_state.df_master['nome cliente'].unique()) if cerca in n.lower()]
        
        if lista:
            scelto = st.selectbox("Seleziona cliente:", lista)
            idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
            d = st.session_state.df_master.loc[idx]
            
            with st.form("edit_crm_final"):
                c_a, c_b = st.columns(2)
                with c_a:
                    un = st.text_input("Ragione Sociale", d['nome cliente'])
                    ui = st.text_input("Indirizzo", d['indirizzo'])
                    uf = st.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
                    uv = st.toggle("Abilita nel Giro", value=(d['visitare'] == 'SI'))
                with c_b:
                    u_ref = st.text_input("Referente", d.get('referente', ''))
                    u_cell = st.text_input("Cellulare", d.get('cellulare', ''))
                    u_mail = st.text_input("Email", d.get('mail', ''))
                    u_data = st.date_input("Ultima Visita", value=(d['ultima visita'].date() if pd.notnull(d['ultima visita']) else datetime.now().date()))

                u_note = st.text_area("Note Cliente", d.get('note', ''))
                
                if st.form_submit_button("💾 Salva Modifiche"):
                    st.session_state.df_master.at[idx, 'nome cliente'] = un
                    st.session_state.df_master.at[idx, 'indirizzo'] = ui
                    st.session_state.df_master.at[idx, 'frequenza (giorni)'] = uf
                    st.session_state.df_master.at[idx, 'visitare'] = 'SI' if uv else 'NO'
                    st.session_state.df_master.at[idx, 'referente'] = u_ref
                    st.session_state.df_master.at[idx, 'cellulare'] = u_cell
                    st.session_state.df_master.at[idx, 'mail'] = u_mail
                    st.session_state.df_master.at[idx, 'note'] = u_note
                    st.session_state.df_master.at[idx, 'ultima visita'] = pd.to_datetime(u_data)
                    st.success("Dati salvati!"); st.rerun()

    with t4:
        st.header("⚙️ Parametri")
        st.session_state.h_inizio = st.time_input("Inizio lavoro", st.session_state.h_inizio)
        st.session_state.h_fine = st.time_input("Fine lavoro", st.session_state.h_fine)
        if st.button("Reset Totale"): 
            st.cache_data.clear()
            if 'df_master' in st.session_state: del st.session_state.df_master
            st.rerun()
else:
    st.error("Errore: Collega il foglio Google correttamente.")
