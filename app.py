import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
from streamlit_js_eval import streamlit_js_eval
import io
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURAZIONE E CONNESSIONE ---
st.set_page_config(page_title="Giro Visite CRM Pro", layout="wide")

URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNZIONI DI SALVATAGGIO ---
def save_to_gsheets(df):
    try:
        # Pulizia colonne di calcolo prima del salvataggio nel cloud
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
        geolocator = Nominatim(user_agent="giro_visite_v18_pro")
        location = geolocator.geocode(address, timeout=10)
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
    except: return pd.DataFrame()

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
            
            # 1. Appuntamenti Fissi
            appuntamenti = df_sim[(df_sim['visitare'] == 'SI') & (df_sim['appuntamento'].dt.date == dt_c)].sort_values('appuntamento')
            # 2. Giro automatico
            df_sim['g_p'] = (pd.to_datetime(dt_c) - df_sim['ultima visita']).dt.days.fillna(999)
            urg = df_sim[(df_sim['visitare'] == 'SI') & (df_sim['g_p'] >= df_sim['frequenza (giorni)']) & (df_sim['appuntamento'].dt.date != dt_c)].to_dict('records')
            
            while True:
                if not appuntamenti.empty:
                    px = appuntamenti.iloc[0].to_dict()
                    ora_app = px['appuntamento'].to_pydatetime()
                    if o_s >= ora_app - timedelta(minutes=st.session_state.durata_v + 15):
                        px['ora_arrivo'] = ora_app.strftime("%H:%M")
                        px['tipo_tappa'] = "📌 APPUNTAMENTO"
                        agenda_risultato[f"Settimana {s}"][g].append(px)
                        o_s, p_s = ora_app + timedelta(minutes=st.session_state.durata_v), (px['latitude'], px['longitude'])
                        appuntamenti = appuntamenti.iloc[1:]; continue

                if not urg: break
                px = min(urg, key=lambda x: haversine(p_s[0], p_s[1], x['latitude'], x['longitude']))
                dist = haversine(p_s[0], p_s[1], px['latitude'], px['longitude'])
                arr = o_s + timedelta(minutes=(dist/50)*60)
                
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
                else: break
    return agenda_risultato, lun_ref

# --- 5. INTERFACCIA ---
nav = st.columns(6)
menu = ["🚀 Giro Oggi", "📅 Agenda 8 Sett", "🗺️ Mappa Clienti", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"]
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
                        st.write(f"🕒 **{t['ora_arrivo']}** - {t['nome cliente']}")
                        cols = st.columns(4)
                        cols[0].link_button("🚗", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}")
                        if t.get('cellulare'): cols[1].link_button("📱", f"tel:{t['cellulare']}")
                        if cols[3].button("👤", key=f"go_{t['nome cliente']}"):
                            st.session_state.cliente_selezionato = t['nome cliente']; st.session_state.active_tab = "👤 Anagrafica"; st.rerun()
            with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
        else: st.info("Nessuna visita per oggi.")

# --- TAB: MAPPA ---
elif st.session_state.active_tab == "🗺️ Mappa Clienti":
    st.header("🗺️ Analisi Geografica")
    filtro = st.radio("Filtro:", ["Tutti i Clienti", "Visitati", "Mai Visitati", "Singolo Cliente"], horizontal=True)
    df_m = st.session_state.df_master.copy()
    if filtro == "Visitati": df_m = df_m[df_m['ultima visita'] > pd.Timestamp('2000-01-01')]
    elif filtro == "Mai Visitati": df_m = df_m[df_m['ultima visita'] <= pd.Timestamp('2000-01-01')]
    elif filtro == "Singolo Cliente":
        cli = st.selectbox("Scegli cliente:", sorted(df_m['nome cliente'].unique()))
        df_m = df_m[df_m['nome cliente'] == cli]
    df_m['color'] = df_m['visitare'].apply(lambda x: "#28a745" if x == "SI" else "#dc3545")
    st.map(df_m, latitude='latitude', longitude='longitude', color='color', size=25)

# --- TAB: ANAGRAFICA ---
elif st.session_state.active_tab == "👤 Anagrafica":
    st.header("👤 Scheda Anagrafica")
    nomi = sorted(st.session_state.df_master['nome cliente'].unique())
    scelto = st.selectbox("Cerca cliente:", nomi)
    if scelto:
        idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
        d = st.session_state.df_master.loc[idx]
        
        # AZIONI RAPIDE
        st.subheader("⚡ Azioni Rapide")
        c_act = st.columns(4)
        c_act[0].link_button("🚗 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={d['latitude']},{d['longitude']}")
        if d.get('cellulare'): c_act[1].link_button("📱 CHIAMA CELL", f"tel:{d['cellulare']}")
        if d.get('mail'): c_act[2].link_button("📧 INVIA MAIL", f"mailto:{d['mail']}")

        st.divider()
        with st.form("edit_anag"):
            c1, c2 = st.columns(2)
            un = c1.text_input("Ragione Sociale", d['nome cliente'])
            ui = c1.text_input("Indirizzo", d['indirizzo'])
            uf = c1.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
            scelta_v = c1.selectbox("Includere nel Giro?", ["SI", "NO"], index=0 if d['visitare'] == "SI" else 1)
            ut = c2.text_input("Telefono", d.get('telefono', ''))
            uc = c2.text_input("Cellulare", d.get('cellulare',''))
            um = c2.text_input("Email", d.get('mail',''))
            st.divider()
            st.subheader("📌 Appuntamento Fisso")
            val_d = d['appuntamento'].date() if pd.notnull(d['appuntamento']) else None
            app_d = c1.date_input("Data", value=val_d)
            app_t = c1.time_input("Ora", value=d['appuntamento'].time() if pd.notnull(d['appuntamento']) else time(10, 0))
            rimuovi_app = c2.checkbox("Rimuovi appuntamento")
            uno = st.text_area("Note", d.get('note', ''))
            if st.form_submit_button("💾 Salva Modifiche"):
                st.session_state.df_master.at[idx, ['nome cliente','indirizzo','frequenza (giorni)','visitare','telefono','cellulare','mail','note']] = [un,ui,uf,scelta_v,ut,uc,um,uno]
                if rimuovi_app: st.session_state.df_master.at[idx, 'appuntamento'] = pd.NaT
                elif app_d: st.session_state.df_master.at[idx, 'appuntamento'] = datetime.combine(app_d, app_t)
                if save_to_gsheets(st.session_state.df_master): st.rerun()
        
        st.divider()
        with st.expander("🗑️ ELIMINA CLIENTE"):
            if st.checkbox("Confermo la cancellazione definitiva") and st.button("❌ ELIMINA ORA"):
                st.session_state.df_master = st.session_state.df_master.drop(idx)
                if save_to_gsheets(st.session_state.df_master): st.rerun()

# --- TAB: NUOVO CLIENTE ---
elif st.session_state.active_tab == "➕ Nuovo Cliente":
    st.header("➕ Registrazione Nuovo Cliente")
    
    # PULSANTE GPS FUORI DAL FORM PER IPAD
    st.subheader("📍 Geolocalizzazione Attuale")
    c_gps, c_st = st.columns([1, 2])
    pos_new = None
    with c_gps:
        if st.button("🎯 USA POSIZIONE ATTUALE", key="gps_new"):
            pos_new = streamlit_js_eval(js_expressions='navigator.geolocation.getCurrentPosition((pos) => { return position.coords; })', target_id='gps_new_v18')
    if pos_new: st.success("✅ GPS Acquisito!")

    with st.form("new_full"):
        c1, c2 = st.columns(2)
        nn = c1.text_input("Ragione Sociale *")
        nf = c1.number_input("Frequenza Visite (gg)", value=30)
        ut = c2.text_input("Telefono Fisso")
        uc = c2.text_input("Cellulare")
        um = c2.text_input("Email")
        
        st.divider()
        st.subheader("🏠 Indirizzo Dettagliato")
        via = st.text_input("Via e Civico")
        ca_row = st.columns([1, 2, 1])
        cap = ca_row[0].text_input("CAP")
        cit = ca_row[1].text_input("Città *")
        pro = ca_row[2].text_input("Prov.")
        no = st.text_area("Note iniziali")

        if st.form_submit_button("✅ CREA E SALVA NEL CLOUD"):
            if nn and (cit or pos_new):
                ind_comp = f"{via}, {cap} {cit} {pro}".strip(", ")
                lat, lon = (pos_new['latitude'], pos_new['longitude']) if pos_new else (None, None)
                if not lat:
                    coords = get_coords(ind_comp)
                    if coords: lat, lon = coords
                
                if lat:
                    nuovo = {
                        'nome cliente': nn, 'indirizzo': ind_comp, 'referente': '', 'telefono': ut, 'cellulare': uc, 'mail': um, 'note': no,
                        'visitare': 'SI', 'frequenza (giorni)': nf, 'latitude': lat, 'longitude': lon,
                        'ultima visita': pd.Timestamp('2000-01-01'), 'appuntamento': pd.NaT
                    }
                    st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([nuovo])], ignore_index=True)
                    if save_to_gsheets(st.session_state.df_master):
                        st.success("Salvato correttamente!"); st.rerun()
                else: st.error("Impossibile geolocalizzare. Controlla Chrome e permessi GPS.")

# --- TAB: PARAMETRI ---
elif st.session_state.active_tab == "⚙️ Parametri":
    st.header("⚙️ Configurazione")
    
    # 1. POSIZIONE PARTENZA
    st.subheader("📍 Punto di Partenza")
    c_gps, c_city = st.columns([1, 2])
    with c_gps:
        if st.button("🎯 USA GPS ATTUALE", key="gps_param"):
            gps_p = streamlit_js_eval(js_expressions='navigator.geolocation.getCurrentPosition((pos) => { return position.coords; })', target_id='gps_param_v18')
            if gps_p:
                if save_config_cloud("Posizione GPS", gps_p['latitude'], gps_p['longitude']):
                    st.session_state.start_lat, st.session_state.start_lon, st.session_state.start_city = gps_p['latitude'], gps_p['longitude'], "Posizione GPS"
                    st.rerun()
    with c_city:
        nc = st.text_input("Oppure scrivi Città:", st.session_state.start_city)
        if nc != st.session_state.start_city and nc != "Posizione GPS":
            co = get_coords(nc)
            if co and save_config_cloud(nc, co[0], co[1]):
                st.session_state.start_city, st.session_state.start_lat, st.session_state.start_lon = nc, co[0], co[1]
                st.rerun()

    st.divider()
    # 2. ORARI E PAUSE
    st.subheader("⏰ Orari e Pause")
    co1, col2 = st.columns(2)
    st.session_state.h_inizio = co1.time_input("Inizio Lavoro", st.session_state.h_inizio)
    st.session_state.h_fine = col2.time_input("Fine Lavoro", st.session_state.h_fine)
    st.session_state.pausa_inizio = co1.time_input("Inizio Pausa", st.session_state.pausa_inizio)
    st.session_state.pausa_fine = col2.time_input("Fine Pausa", st.session_state.pausa_fine)
    st.session_state.durata_v = st.slider("Minuti per visita", 15, 120, st.session_state.durata_v)

    st.divider()
    # 3. FERIE
    st.subheader("🏖️ Gestione Ferie")
    ferie_in = st.date_input("Periodo chiusura (Inizio e Fine)", value=st.session_state.ferie)
    if isinstance(ferie_in, tuple) and len(ferie_in) == 2: st.session_state.ferie = ferie_in

    st.divider()
    # 4. ESPORTAZIONE EXCEL
    st.subheader("📊 Gestione Dati")
    def to_excel(df):
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        return out.getvalue()
    
    c_ex1, c_ex2 = st.columns(2)
    c_ex1.download_button(label="📥 Scarica Database Excel", data=to_excel(st.session_state.df_master), file_name="crm_giro_visite.xlsx")
    if c_ex2.button("🔄 Forza Ricarica Cloud"): st.cache_data.clear(); st.rerun()

# --- TAB: AGENDA ---
elif st.session_state.active_tab == "📅 Agenda 8 Sett":
    st.header("📅 Prossime Settimane")
    sett = st.selectbox("Settimana", list(agenda.keys()))
    cols = st.columns(5)
    for i, g in enumerate(["Lun", "Mar", "Mer", "Gio", "Ven"]):
        with cols[i]:
            st.subheader(g)
            for t in agenda[sett][i]:
                with st.container(border=True):
                    st.write(f"**{t['ora_arrivo']}** - {t['nome cliente']}")
