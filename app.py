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

URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNZIONI DI SALVATAGGIO ---
def save_to_gsheets(df):
    try:
        cols_to_save = [c for c in df.columns if c not in ['g_p', 'ora_arrivo', 'tipo_tappa', 'color']]
        conn.update(spreadsheet=URL_FOGLIO, data=df[cols_to_save])
        st.cache_data.clear() 
        return True
    except Exception as e:
        st.error(f"Errore Cloud: {e}")
        return False

def save_config_cloud(city, lat, lon):
    try:
        df_conf = pd.DataFrame([{'citta': city, 'lat': lat, 'lon': lon}])
        conn.update(spreadsheet=URL_FOGLIO, worksheet="Config", data=df_conf)
        st.cache_data.clear()
        return True
    except: return False

# --- 2. UTILS ---
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    return 2 * 6371 * asin(sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2))

def get_coords(address):
    try:
        geolocator = Nominatim(user_agent="giro_visite_v6")
        location = geolocator.geocode(address)
        return (location.latitude, location.longitude) if location else None
    except: return None

@st.cache_data(ttl=0) 
def fetch_data():
    try:
        df = conn.read(spreadsheet=URL_FOGLIO)
        df.columns = df.columns.str.strip().str.lower()
        colonne = ['contatto', 'referente', 'posizione referente', 'mail', 'telefono', 'cellulare', 'note', 'visitare', 'indirizzo', 'ultima visita', 'frequenza (giorni)', 'nome cliente', 'latitude', 'longitude', 'appuntamento']
        for col in colonne:
            if col not in df.columns: df[col] = ""
        for c in ['latitude', 'longitude', 'frequenza (giorni)']:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '.'), errors='coerce')
        df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
        df['appuntamento'] = pd.to_datetime(df['appuntamento'], errors='coerce')
        df['visitare'] = df['visitare'].fillna("SI").astype(str).str.upper()
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except Exception as e:
        st.error(f"Errore fetch: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=0)
def fetch_config():
    try:
        df_conf = conn.read(spreadsheet=URL_FOGLIO, worksheet="Config")
        return {'city': str(df_conf.iloc[0]['citta']), 'lat': float(df_conf.iloc[0]['lat']), 'lon': float(df_conf.iloc[0]['lon'])}
    except: return {'city': "Ancona", 'lat': 43.6158, 'lon': 13.5189}

# --- 3. STATO DELL'APP ---
if 'active_tab' not in st.session_state: st.session_state.active_tab = "🚀 Giro Oggi"
if 'df_master' not in st.session_state: st.session_state.df_master = fetch_data()

conf_cloud = fetch_config()
if 'start_city' not in st.session_state: st.session_state.start_city = conf_cloud['city']
if 'start_lat' not in st.session_state: st.session_state.start_lat = conf_cloud['lat']
if 'start_lon' not in st.session_state: st.session_state.start_lon = conf_cloud['lon']

# Parametri Default
if 'h_inizio' not in st.session_state: st.session_state.h_inizio = time(9, 0)
if 'h_fine' not in st.session_state: st.session_state.h_fine = time(18, 0)
if 'pausa_inizio' not in st.session_state: st.session_state.pausa_inizio = time(13, 0)
if 'pausa_fine' not in st.session_state: st.session_state.pausa_fine = time(14, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'ferie' not in st.session_state: st.session_state.ferie = (datetime.now().date(), datetime.now().date())
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
            if dt_c in st.session_state.ferie: continue
            o_s, p_s = datetime.combine(dt_c, st.session_state.h_inizio), (st.session_state.start_lat, st.session_state.start_lon)
            
            appuntamenti = df_sim[(df_sim['visitare'] == 'SI') & (df_sim['appuntamento'].dt.date == dt_c)].sort_values('appuntamento')
            urg = df_sim[(df_sim['visitare'] == 'SI') & ((pd.to_datetime(dt_c) - df_sim['ultima visita']).dt.days.fillna(999) >= df_sim['frequenza (giorni)']) & (df_sim['appuntamento'].dt.date != dt_c)].to_dict('records')
            
            while True:
                if not appuntamenti.empty:
                    prossimo_app = appuntamenti.iloc[0]
                    ora_app = prossimo_app['appuntamento'].to_pydatetime()
                    if o_s >= ora_app - timedelta(minutes=st.session_state.durata_v + 15):
                        px = prossimo_app.to_dict()
                        px['ora_arrivo'] = ora_app.strftime("%H:%M")
                        px['tipo_tappa'] = "📌 APPUNTAMENTO"
                        agenda_risultato[f"Settimana {s}"][g].append(px)
                        o_s, p_s = ora_app + timedelta(minutes=st.session_state.durata_v), (px['latitude'], px['longitude'])
                        appuntamenti = appuntamenti.iloc[1:]; continue
                if not urg: break
                px = min(urg, key=lambda x: haversine(p_s[0], p_s[1], x['latitude'], x['longitude']))
                arr = o_s + timedelta(minutes=(haversine(p_s[0], p_s[1], px['latitude'], px['longitude'])/50)*60)
                if arr >= datetime.combine(dt_c, st.session_state.pausa_inizio) and arr < datetime.combine(dt_c, st.session_state.pausa_fine):
                    o_s = datetime.combine(dt_c, st.session_state.pausa_fine); continue
                fine_v = arr + timedelta(minutes=st.session_state.durata_v)
                limite = appuntamenti.iloc[0]['appuntamento'].to_pydatetime() if not appuntamenti.empty else datetime.combine(dt_c, st.session_state.h_fine)
                if fine_v <= limite:
                    px['ora_arrivo'] = arr.strftime("%H:%M")
                    px['tipo_tappa'] = "🚗 Giro"
                    agenda_risultato[f"Settimana {s}"][g].append(px)
                    df_sim.loc[df_sim['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(dt_c)
                    o_s, p_s = fine_v, (px['latitude'], px['longitude'])
                    urg.remove(px)
                else:
                    if appuntamenti.empty: break
                    else: o_s = limite
    return agenda_risultato, lun_ref

# --- 5. INTERFACCIA ---
nav = st.columns(6)
menu = ["🚀 Giro Oggi", "📅 Agenda 8 Sett", "🗺️ Mappa Clienti", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"]
for i, m in enumerate(menu):
    if nav[i].button(m, use_container_width=True, type="primary" if st.session_state.active_tab == m else "secondary"):
        st.session_state.active_tab = m; st.rerun()

st.divider()
agenda, lun_base = calcola_piano()

# --- TAB: ANAGRAFICA (MODIFICA + ELIMINA) ---
if st.session_state.active_tab == "👤 Anagrafica":
    st.header("👤 Gestione Anagrafica")
    nomi = sorted(st.session_state.df_master['nome cliente'].unique())
    scelto = st.selectbox("Seleziona cliente:", nomi)
    if scelto:
        idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
        d = st.session_state.df_master.loc[idx]
        with st.form("edit_anag"):
            c1, c2 = st.columns(2)
            un = c1.text_input("Ragione Sociale", d['nome cliente'])
            ui = c1.text_input("Indirizzo", d.get('indirizzo', ''))
            uf = c1.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
            scelta_v = c1.selectbox("Includere nel Giro?", ["SI", "NO"], index=0 if d['visitare'] == "SI" else 1)
            ut = c2.text_input("Telefono", d.get('telefono', ''))
            uc = c2.text_input("Cellulare", d.get('cellulare', ''))
            um = c2.text_input("Mail", d.get('mail', ''))
            uno = st.text_area("Note", d.get('note', ''))
            if st.form_submit_button("💾 Salva Modifiche"):
                st.session_state.df_master.at[idx, 'nome cliente'] = un
                st.session_state.df_master.at[idx, 'indirizzo'] = ui
                st.session_state.df_master.at[idx, 'frequenza (giorni)'] = uf
                st.session_state.df_master.at[idx, 'visitare'] = scelta_v
                st.session_state.df_master.at[idx, 'telefono'] = ut
                st.session_state.df_master.at[idx, 'cellulare'] = uc
                st.session_state.df_master.at[idx, 'mail'] = um
                st.session_state.df_master.at[idx, 'note'] = uno
                if save_to_gsheets(st.session_state.df_master): st.rerun()
        
        st.divider()
        with st.expander("🗑️ ELIMINA CLIENTE"):
            st.warning(f"Attenzione! Stai per eliminare {scelto}.")
            conferma = st.checkbox("Confermo l'eliminazione definitiva")
            if st.button("❌ CANCELLA ORA"):
                if conferma:
                    st.session_state.df_master = st.session_state.df_master.drop(idx)
                    if save_to_gsheets(st.session_state.df_master): st.rerun()

# --- TAB: NUOVO CLIENTE (PULSANTE GPS FISICO) ---
elif st.session_state.active_tab == "➕ Nuovo Cliente":
    st.header("➕ Registrazione Nuovo Cliente")
    
    # PULSANTE GPS ESPLICITO
    st.subheader("📍 Geolocalizzazione")
    c_gps, c_coords = st.columns([1, 2])
    
    pos_rilevata = None
    with c_gps:
        if st.button("🎯 CATTURA POSIZIONE GPS ATTUALE"):
            pos_rilevata = streamlit_js_eval(js_expressions='navigator.geolocation.getCurrentPosition((pos) => { return pos.coords; })', target_id='gps_new_btn')
    
    if pos_rilevata:
        st.success(f"✅ Coordinate acquisite: {pos_rilevata['latitude']}, {pos_rilevata['longitude']}")

    with st.form("new_crm_form"):
        c1, c2 = st.columns(2)
        nn = c1.text_input("Ragione Sociale *")
        nr = c1.text_input("Referente")
        nf = c1.number_input("Frequenza Visite (gg)", value=30)
        
        nt = c2.text_input("Telefono Fisso")
        nc = c2.text_input("Cellulare")
        nm = c2.text_input("Email")
        
        st.divider()
        st.subheader("🏠 Indirizzo (se non usi il GPS)")
        via = st.text_input("Via e Civico")
        cit = st.text_input("Città")
        no = st.text_area("Note iniziali")

        if st.form_submit_button("✅ CREA E SALVA NEL CLOUD"):
            if nn and (cit or pos_rilevata):
                lat, lon = (None, None)
                if pos_rilevata:
                    lat, lon = pos_rilevata['latitude'], pos_rilevata['longitude']
                else:
                    coords = get_coords(f"{via}, {cit}")
                    if coords: lat, lon = coords
                
                if lat:
                    nuovo = {
                        'nome cliente': nn, 'indirizzo': f"{via}, {cit}", 'referente': nr,
                        'telefono': nt, 'cellulare': nc, 'mail': nm, 'note': no,
                        'visitare': 'SI', 'frequenza (giorni)': nf,
                        'latitude': lat, 'longitude': lon,
                        'ultima visita': pd.Timestamp('2000-01-01'), 'appuntamento': pd.NaT
                    }
                    st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([nuovo])], ignore_index=True)
                    if save_to_gsheets(st.session_state.df_master):
                        st.success(f"Cliente {nn} salvato!"); st.rerun()
                else: st.error("Impossibile trovare la posizione.")
            else: st.warning("Inserisci Ragione Sociale e Città (o premi il tasto GPS).")

# --- ALTRE TAB (GIRO OGGI, MAPPA, PARAMETRI, AGENDA) ---
elif st.session_state.active_tab == "🚀 Giro Oggi":
    st.header("📍 Giro di Oggi")
    idx_g = datetime.now().weekday()
    if idx_g < 5:
        tappe = agenda["Settimana 1"][idx_g]
        if tappe:
            c1, c2 = st.columns([1, 2])
            with c1:
                for t in tappe:
                    with st.container(border=True):
                        st.write(f"🕒 **{t['ora_arrivo']}** - {t['nome cliente']}")
                        cols = st.columns(5)
                        cols[0].link_button("🚗", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}")
                        if t.get('cellulare'): cols[1].link_button("📱", f"tel:{t['cellulare']}")
                        if cols[4].button("👤", key=f"go_{t['nome cliente']}"):
                            st.session_state.cliente_selezionato = t['nome cliente']; st.session_state.active_tab = "👤 Anagrafica"; st.rerun()
            with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))

elif st.session_state.active_tab == "🗺️ Mappa Clienti":
    st.header("🗺️ Mappa Globale")
    df_m = st.session_state.df_master.copy()
    df_m['color'] = df_m['visitare'].apply(lambda x: "#28a745" if x == "SI" else "#dc3545")
    st.map(df_m, latitude='latitude', longitude='longitude', color='color', size=25)

elif st.session_state.active_tab == "⚙️ Parametri":
    st.header("⚙️ Configurazione")
    nc = st.text_input("Città di Partenza:", st.session_state.start_city)
    if nc != st.session_state.start_city:
        coords = get_coords(nc)
        if coords and save_config_cloud(nc, coords[0], coords[1]):
            st.session_state.start_city, st.session_state.start_lat, st.session_state.start_lon = nc, coords[0], coords[1]
            st.rerun()
    st.divider()
    def to_excel(df):
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer: df.to_excel(writer, index=False)
        return out.getvalue()
    st.download_button("📥 Scarica Excel", data=to_excel(st.session_state.df_master), file_name="crm_giro.xlsx")

elif st.session_state.active_tab == "📅 Agenda 8 Sett":
    st.header("📅 Agenda")
    sett = st.selectbox("Settimana", list(agenda.keys()))
    cols = st.columns(5)
    for i, g in enumerate(["Lun", "Mar", "Mer", "Gio", "Ven"]):
        with cols[i]:
            st.subheader(g)
            for t in agenda[sett][i]:
                with st.container(border=True):
                    st.write(f"**{t['ora_arrivo']}** - {t['nome cliente']}")
