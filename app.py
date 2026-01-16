import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
from streamlit_js_eval import streamlit_js_eval
import io
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURAZIONE E CONNESSIONE ---
st.set_page_config(page_title="Giro Visite CRM Cloud", layout="wide")

# Link al tuo foglio Google specifico
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/edit?usp=sharing"

conn = st.connection("gsheets", type=GSheetsConnection)

def save_to_gsheets(df):
    """Salva il dataframe direttamente sul Foglio Google"""
    try:
        # Pulizia: non salviamo le colonne temporanee create per i calcoli della giornata
        cols_to_save = [c for c in df.columns if c not in ['g_p', 'ora_arrivo']]
        conn.update(spreadsheet=URL_FOGLIO, data=df[cols_to_save])
        st.cache_data.clear() 
        return True
    except Exception as e:
        st.error(f"Errore durante il salvataggio sul Cloud: {e}")
        return False

# --- 2. UTILS ---
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    return 2 * 6371 * asin(sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2))

def get_coords(city_name):
    try:
        geolocator = Nominatim(user_agent="giro_visite_app_v4")
        location = geolocator.geocode(city_name)
        if location: return location.latitude, location.longitude
        return None
    except: return None

@st.cache_data(ttl=0) 
def fetch_data():
    try:
        df = conn.read(spreadsheet=URL_FOGLIO)
        df.columns = df.columns.str.strip().str.lower()
        
        # Colonne necessarie per il CRM
        colonne_crm = ['contatto', 'referente', 'posizione referente', 'mail', 'telefono', 'cellulare', 'note', 'visitare', 'indirizzo', 'ultima visita', 'frequenza (giorni)', 'nome cliente', 'latitude', 'longitude']
        for col in colonne_crm:
            if col not in df.columns: df[col] = ""
            
        # Conversione dati
        for c in ['latitude', 'longitude', 'frequenza (giorni)']:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '.'), errors='coerce')
        
        df['visitare'] = df['visitare'].replace("", "SI").fillna("SI").astype(str).str.upper()
        df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
        if 'data_precedente' not in df.columns: df['data_precedente'] = df['ultima visita']
        
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except Exception as e:
        st.error(f"Errore nel caricamento dal Cloud: {e}")
        return pd.DataFrame()

# --- 3. STATO DELL'APP ---
if 'active_tab' not in st.session_state: st.session_state.active_tab = "🚀 Giro Oggi"
if 'cliente_selezionato' not in st.session_state: st.session_state.cliente_selezionato = None
if 'df_master' not in st.session_state:
    st.session_state.df_master = fetch_data()
if 'df_reports' not in st.session_state:
    st.session_state.df_reports = pd.DataFrame(columns=['cliente', 'data', 'nota_visita', 'esito'])

# Parametri Default
if 'start_city' not in st.session_state: st.session_state.start_city = "Ancona"
if 'start_lat' not in st.session_state: st.session_state.start_lat = 43.6158
if 'start_lon' not in st.session_state: st.session_state.start_lon = 13.5189
if 'h_inizio' not in st.session_state: st.session_state.h_inizio = time(9, 0)
if 'h_fine' not in st.session_state: st.session_state.h_fine = time(18, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'spostamenti' not in st.session_state: st.session_state.spostamenti = {}

# --- 4. LOGICA CALCOLO GIRO ---
def calcola_piano():
    if st.session_state.df_master.empty: return {}, datetime.now()
    oggi_dt = datetime.now()
    lun_ref = oggi_dt - timedelta(days=oggi_dt.weekday())
    df_sim = st.session_state.df_master.copy()
    agenda_risultato = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
    
    for s in range(1, 9):
        for g in range(5):
            dt_c = (lun_ref + timedelta(weeks=s-1, days=g)).date()
            dt_logica = st.session_state.spostamenti.get(dt_c, dt_c)
            df_sim['g_p'] = (pd.to_datetime(dt_logica) - df_sim['ultima visita']).dt.days.fillna(999)
            
            if s == 1 and g == oggi_dt.weekday():
                urg = df_sim[(df_sim['visitare'] == 'SI') & ((df_sim['g_p'] >= df_sim['frequenza (giorni)']) | (df_sim['ultima visita'].dt.date == oggi_dt.date()))].to_dict('records')
            else:
                urg = df_sim[(df_sim['visitare'] == 'SI') & (df_sim['g_p'] >= df_sim['frequenza (giorni)'])].to_dict('records')
            
            o_s, p_s = datetime.combine(dt_c, st.session_state.h_inizio), (st.session_state.start_lat, st.session_state.start_lon)
            while urg:
                px = min(urg, key=lambda x: haversine(p_s[0], p_s[1], x['latitude'], x['longitude']))
                dist = haversine(p_s[0], p_s[1], px['latitude'], px['longitude'])
                arr = o_s + timedelta(minutes=(dist/50)*60)
                fine = arr + timedelta(minutes=st.session_state.durata_v)
                if fine <= datetime.combine(dt_c, st.session_state.h_fine):
                    px['ora_arrivo'] = arr.strftime("%H:%M")
                    agenda_risultato[f"Settimana {s}"][g].append(px)
                    df_sim.loc[df_sim['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(dt_logica)
                    o_s, p_s = fine, (px['latitude'], px['longitude'])
                    urg.remove(px)
                else: break
    return agenda_risultato, lun_ref

# --- 5. NAVBAR ---
c_nav = st.columns(5)
menu = ["🚀 Giro Oggi", "📅 Agenda 8 Sett", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"]
for i, m in enumerate(menu):
    if c_nav[i].button(m, use_container_width=True, type="primary" if st.session_state.active_tab == m else "secondary"):
        st.session_state.active_tab = m; st.rerun()

st.divider()
agenda, lun_base = calcola_piano()

# --- GIRO OGGI ---
if st.session_state.active_tab == "🚀 Giro Oggi":
    st.header(f"📍 Giro di Oggi ({st.session_state.start_city})")
    idx_g = datetime.now().weekday()
    if idx_g < 5:
        tappe = agenda["Settimana 1"][idx_g]
        if tappe:
            c1, c2 = st.columns([1, 2])
            with c1:
                for t in tappe:
                    is_vis = pd.to_datetime(t['ultima visita']).date() == datetime.now().date()
                    with st.container(border=True):
                        if is_vis: st.success("✅ VISITATO")
                        st.write(f"🕒 **{t['ora_arrivo']}** - {t['nome cliente']}")
                        a = st.columns(4)
                        a[0].link_button("🚗", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}")
                        if t.get('cellulare'): a[1].link_button("📞", f"tel:{t['cellulare']}")
                        if t.get('mail'): a[2].link_button("📧", f"mailto:{t['mail']}")
                        if a[3].button("👤", key=f"go_{t['nome cliente']}"):
                            st.session_state.cliente_selezionato = t['nome cliente']; st.session_state.active_tab = "👤 Anagrafica"; st.rerun()
                        
                        if not is_vis:
                            with st.popover("📝 Report", use_container_width=True):
                                with st.form(f"f_{t['nome cliente']}"):
                                    es = st.selectbox("Esito", ["Positivo", "Richiamare", "Negativo"])
                                    no = st.text_area("Note")
                                    if st.form_submit_button("Salva nel Cloud"):
                                        idx_m = st.session_state.df_master[st.session_state.df_master['nome cliente'] == t['nome cliente']].index[0]
                                        st.session_state.df_master.at[idx_m, 'ultima visita'] = pd.to_datetime(datetime.now().date())
                                        if save_to_gsheets(st.session_state.df_master):
                                            st.rerun()
            with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
        else: st.info("Nessuna visita programmata.")

# --- ANAGRAFICA ---
elif st.session_state.active_tab == "👤 Anagrafica":
    st.header("👤 Scheda Cliente")
    nomi = sorted(st.session_state.df_master['nome cliente'].unique())
    idx_p = nomi.index(st.session_state.cliente_selezionato) if st.session_state.cliente_selezionato in nomi else 0
    scelto = st.selectbox("Cerca cliente:", nomi, index=idx_p)
    
    if scelto:
        idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
        d = st.session_state.df_master.loc[idx]
        
        with st.form("edit"):
            c1, c2 = st.columns(2)
            un = c1.text_input("Ragione Sociale", d['nome cliente'])
            ui = c1.text_input("Indirizzo", d.get('indirizzo', ''))
            ur = c1.text_input("Referente", d.get('referente', ''))
            uf = c1.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
            
            uc = c2.text_input("Cellulare", d.get('cellulare',''))
            um = c2.text_input("Mail", d.get('mail',''))
            uct = c2.text_input("Contatto Diretto", d.get('contatto', ''))
            uno = st.text_area("Note Cliente", d.get('note', ''))
            
            if st.form_submit_button("💾 Salva e Sincronizza Cloud"):
                st.session_state.df_master.at[idx, 'nome cliente'] = un
                st.session_state.df_master.at[idx, 'indirizzo'] = ui
                st.session_state.df_master.at[idx, 'referente'] = ur
                st.session_state.df_master.at[idx, 'frequenza (giorni)'] = uf
                st.session_state.df_master.at[idx, 'cellulare'] = uc
                st.session_state.df_master.at[idx, 'mail'] = um
                st.session_state.df_master.at[idx, 'contatto'] = uct
                st.session_state.df_master.at[idx, 'note'] = uno
                if save_to_gsheets(st.session_state.df_master):
                    st.success("Sincronizzato!")
                    st.rerun()

# --- NUOVO CLIENTE ---
elif st.session_state.active_tab == "➕ Nuovo Cliente":
    st.header("➕ Nuovo Cliente")
    with st.form("new"):
        nn = st.text_input("Ragione Sociale *")
        ni = st.text_input("Indirizzo")
        if st.form_submit_button("✅ Aggiungi al Cloud"):
            if nn:
                nuovo = {
                    'nome cliente': nn, 'indirizzo': ni, 'visitare': 'SI', 
                    'frequenza (giorni)': 30, 'ultima visita': pd.Timestamp('2000-01-01'),
                    'latitude': st.session_state.start_lat, 'longitude': st.session_state.start_lon
                }
                st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([nuovo])], ignore_index=True)
                if save_to_gsheets(st.session_state.df_master):
                    st.success("Cliente aggiunto!")
                    st.rerun()

# --- PARAMETRI ---
elif st.session_state.active_tab == "⚙️ Parametri":
    st.header("⚙️ Configurazione")
    nc = st.text_input("Città di Partenza:", st.session_state.start_city)
    if nc != st.session_state.start_city:
        co = get_coords(nc)
        if co:
            st.session_state.start_city, st.session_state.start_lat, st.session_state.start_lon = nc, co[0], co[1]
            st.rerun()
    st.session_state.durata_v = st.slider("Minuti per tappa", 15, 120, st.session_state.durata_v)
    
    st.divider()
    st.subheader("📊 Esportazione")
    def to_excel(df):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        return output.getvalue()
    
    st.download_button("📥 Scarica Database (Excel)", to_excel(st.session_state.df_master), "database_clienti.xlsx")
    
    if st.button("🔄 Forza Ricaricamento dal Cloud"):
        st.cache_data.clear()
        del st.session_state.df_master
        st.rerun()
