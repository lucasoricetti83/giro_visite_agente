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
        cols_to_save = [c for c in df.columns if c not in ['g_p', 'ora_arrivo', 'tipo_tappa']]
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
    except Exception as e:
        st.error(f"Errore salvataggio Config: {e}")
        return False

# --- 2. UTILS ---
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    return 2 * 6371 * asin(sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2))

def get_coords(city_name):
    try:
        geolocator = Nominatim(user_agent="giro_visite_app_v4")
        location = geolocator.geocode(city_name)
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
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except Exception as e:
        st.error(f"Errore caricamento: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=0)
def fetch_config():
    try:
        df_conf = conn.read(spreadsheet=URL_FOGLIO, worksheet="Config")
        return {'city': str(df_conf.iloc[0]['citta']), 'lat': float(df_conf.iloc[0]['lat']), 'lon': float(df_conf.iloc[0]['lon'])}
    except: return {'city': "Ancona", 'lat': 43.6158, 'lon': 13.5189}

# --- 3. STATO DELL'APP ---
if 'active_tab' not in st.session_state: st.session_state.active_tab = "🚀 Giro Oggi"
if 'cliente_selezionato' not in st.session_state: st.session_state.cliente_selezionato = None
if 'df_master' not in st.session_state: st.session_state.df_master = fetch_data()

# Caricamento posizione persistente
conf_cloud = fetch_config()
if 'start_city' not in st.session_state: st.session_state.start_city = conf_cloud['city']
if 'start_lat' not in st.session_state: st.session_state.start_lat = conf_cloud['lat']
if 'start_lon' not in st.session_state: st.session_state.start_lon = conf_cloud['lon']

# Parametri Orari e Assenze (CORRETTO PER EVITARE ERRORE)
if 'h_inizio' not in st.session_state: st.session_state.h_inizio = time(9, 0)
if 'h_fine' not in st.session_state: st.session_state.h_fine = time(18, 0)
if 'pausa_inizio' not in st.session_state: st.session_state.pausa_inizio = time(13, 0)
if 'pausa_fine' not in st.session_state: st.session_state.pausa_fine = time(14, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45

# Inizializziamo le ferie come un intervallo (oggi - oggi) per evitare il crash
if 'ferie' not in st.session_state: 
    st.session_state.ferie = (datetime.now().date(), datetime.now().date())

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
            
            o_s = datetime.combine(dt_c, st.session_state.h_inizio)
            p_s = (st.session_state.start_lat, st.session_state.start_lon)
            
            appuntamenti = df_sim[df_sim['appuntamento'].dt.date == dt_c].sort_values('appuntamento')
            df_sim['g_p'] = (pd.to_datetime(dt_c) - df_sim['ultima visita']).dt.days.fillna(999)
            urg = df_sim[(df_sim['visitare'] == 'SI') & (df_sim['g_p'] >= df_sim['frequenza (giorni)']) & (df_sim['appuntamento'].dt.date != dt_c)].to_dict('records')
            
            while True:
                if not appuntamenti.empty:
                    prossimo_app = appuntamenti.iloc[0]
                    ora_app = prossimo_app['appuntamento'].to_pydatetime()
                    if o_s >= ora_app - timedelta(minutes=st.session_state.durata_v + 15):
                        px = prossimo_app.to_dict()
                        px['ora_arrivo'] = ora_app.strftime("%H:%M")
                        px['tipo_tappa'] = "📌 APPUNTAMENTO"
                        agenda_risultato[f"Settimana {s}"][g].append(px)
                        o_s = ora_app + timedelta(minutes=st.session_state.durata_v)
                        p_s = (px['latitude'], px['longitude'])
                        appuntamenti = appuntamenti.iloc[1:]
                        continue

                if not urg: break
                px = min(urg, key=lambda x: haversine(p_s[0], p_s[1], x['latitude'], x['longitude']))
                dist = haversine(p_s[0], p_s[1], px['latitude'], px['longitude'])
                arr = o_s + timedelta(minutes=(dist/50)*60)
                
                # Gestione Pausa Pranzo
                p_inizio = datetime.combine(dt_c, st.session_state.pausa_inizio)
                p_fine = datetime.combine(dt_c, st.session_state.pausa_fine)
                if arr >= p_inizio and arr < p_fine:
                    o_s = p_fine
                    continue

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
nav = st.columns(5)
menu = ["🚀 Giro Oggi", "📅 Agenda 8 Sett", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"]
for i, m in enumerate(menu):
    if nav[i].button(m, use_container_width=True, type="primary" if st.session_state.active_tab == m else "secondary"):
        st.session_state.active_tab = m; st.rerun()

st.divider()
agenda, lun_base = calcola_piano()

# --- TAB: GIRO OGGI ---
if st.session_state.active_tab == "🚀 Giro Oggi":
    st.header(f"📍 Giro di Oggi (Partenza: {st.session_state.start_city})")
    idx_g = datetime.now().weekday()
    if idx_g < 5:
        tappe = agenda["Settimana 1"][idx_g]
        if tappe:
            c1, c2 = st.columns([1, 2])
            with c1:
                for t in tappe:
                    with st.container(border=True):
                        st.caption(t.get('tipo_tappa', '🚗'))
                        st.write(f"🕒 **{t['ora_arrivo']}** - {t['nome cliente']}")
                        if st.button("👤", key=f"go_{t['nome cliente']}"):
                            st.session_state.cliente_selezionato = t['nome cliente']; st.session_state.active_tab = "👤 Anagrafica"; st.rerun()
            with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
        else: st.info("Nessuna visita per oggi.")

# --- TAB: ANAGRAFICA ---
elif st.session_state.active_tab == "👤 Anagrafica":
    st.header("👤 Scheda Cliente")
    nomi = sorted(st.session_state.df_master['nome cliente'].unique())
    scelto = st.selectbox("Cerca cliente:", nomi)
    if scelto:
        idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
        d = st.session_state.df_master.loc[idx]
        st.info(f"📅 Ultima visita: **{d['ultima visita'].strftime('%d/%m/%Y') if pd.notnull(d['ultima visita']) else 'Mai'}**")
        with st.form("edit"):
            c1, c2 = st.columns(2)
            un = c1.text_input("Ragione Sociale", d['nome cliente'])
            uf = c1.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
            app_d = c1.date_input("Data Appuntamento", value=d['appuntamento'].date() if pd.notnull(d['appuntamento']) else None)
            app_t = c1.time_input("Ora Appuntamento", value=d['appuntamento'].time() if pd.notnull(d['appuntamento']) else time(10, 0))
            rimuovi = c1.checkbox("Rimuovi appuntamento")
            uc = c2.text_input("Cellulare", d.get('cellulare',''))
            uno = st.text_area("Note", d.get('note', ''))
            if st.form_submit_button("💾 Salva"):
                st.session_state.df_master.at[idx, 'nome cliente'] = un
                st.session_state.df_master.at[idx, 'frequenza (giorni)'] = uf
                st.session_state.df_master.at[idx, 'cellulare'] = uc
                st.session_state.df_master.at[idx, 'note'] = uno
                if rimuovi: st.session_state.df_master.at[idx, 'appuntamento'] = pd.NaT
                elif app_d: st.session_state.df_master.at[idx, 'appuntamento'] = datetime.combine(app_d, app_t)
                save_to_gsheets(st.session_state.df_master); st.rerun()

# --- TAB: PARAMETRI (REINTEGRATA COMPLETAMENTE) ---
elif st.session_state.active_tab == "⚙️ Parametri":
    st.header("⚙️ Configurazione")
    
    # 1. GEOLOCALIZZAZIONE E PARTENZA PERSISTENTE
    st.subheader("📍 Punto di Partenza (Sincronizzato Cloud)")
    c_gps, c_city = st.columns([1, 2])
    
    with c_gps:
        if st.button("🎯 Rileva GPS"):
            pos = streamlit_js_eval(js_expressions='navigator.geolocation.getCurrentPosition((position) => { return position.coords; })', target_id='gps_p')
            if pos:
                lat, lon = pos['latitude'], pos['longitude']
                if save_config_cloud("Posizione GPS", lat, lon):
                    st.session_state.start_lat, st.session_state.start_lon, st.session_state.start_city = lat, lon, "Posizione GPS"
                    st.success("📍 GPS salvato!")
                    st.rerun()

    with c_city:
        nc = st.text_input("Cambia Città di Partenza:", st.session_state.start_city)
        if nc != st.session_state.start_city and nc != "Posizione GPS":
            co = get_coords(nc)
            if co:
                if save_config_cloud(nc, co[0], co[1]):
                    st.session_state.start_city, st.session_state.start_lat, st.session_state.start_lon = nc, co[0], co[1]
                    st.success(f"📍 Partenza fissata a {nc}!")
                    st.rerun()

    st.divider()
    
    # 2. ORARI LAVORATIVI E PAUSA
    st.subheader("⏰ Orari e Pause")
    co1, co2 = st.columns(2)
    st.session_state.h_inizio = co1.time_input("Inizio Lavoro", st.session_state.h_inizio)
    st.session_state.h_fine = co2.time_input("Fine Lavoro", st.session_state.h_fine)
    
    cp1, cp2 = st.columns(2)
    st.session_state.pausa_inizio = cp1.time_input("Inizio Pausa Pranzo", st.session_state.pausa_inizio)
    st.session_state.pausa_fine = cp2.time_input("Fine Pausa Pranzo", st.session_state.pausa_fine)
    
    st.session_state.durata_v = st.slider("Minuti per ogni visita", 15, 120, st.session_state.durata_v)

    st.divider()

    # 3. FERIE E ASSENZE
    st.subheader("🏖️ Giorni di Chiusura / Ferie")
    ferie_sel = st.date_input("Seleziona i giorni in cui NON lavori", value=st.session_state.ferie)
    st.session_state.ferie = ferie_sel if isinstance(ferie_sel, list) else [ferie_sel]

    st.divider()

    # 4. ESPORTAZIONE EXCEL
    st.subheader("📊 Esportazione")
    def to_excel(df):
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        return out.getvalue()
    st.download_button("📥 Scarica Database Excel", to_excel(st.session_state.df_master), "database_crm.xlsx")

    if st.button("🔄 Ricarica forzata Cloud"):
        st.cache_data.clear()
        st.rerun()

# --- ALTRE TAB ---
elif st.session_state.active_tab == "📅 Agenda 8 Sett":
    st.header("📅 Agenda")
    sett = st.selectbox("Settimana", list(agenda.keys()))
    cols = st.columns(5)
    g_nomi = ["Lun", "Mar", "Mer", "Gio", "Ven"]
    for i, g in enumerate(g_nomi):
        with cols[i]:
            st.subheader(g)
            for t in agenda[sett][i]:
                with st.container(border=True):
                    st.caption(t.get('tipo_tappa', '🚗'))
                    st.write(f"**{t['ora_arrivo']}** - {t['nome cliente']}")

elif st.session_state.active_tab == "➕ Nuovo Cliente":
    st.header("➕ Nuovo")
    with st.form("n"):
        nn = st.text_input("Nome Cliente")
        ni = st.text_input("Indirizzo")
        if st.form_submit_button("Salva"):
            nuovo = {'nome cliente': nn, 'indirizzo': ni, 'visitare': 'SI', 'frequenza (giorni)': 30, 'ultima visita': pd.Timestamp('2000-01-01'), 'latitude': st.session_state.start_lat, 'longitude': st.session_state.start_lon}
            st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([nuovo])], ignore_index=True)
            save_to_gsheets(st.session_state.df_master); st.rerun()
