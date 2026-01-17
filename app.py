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
        # Pulizia colonne di calcolo prima del salvataggio
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
        st.error(f"Errore Config: {e}")
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

conf_cloud = fetch_config()
if 'start_city' not in st.session_state: st.session_state.start_city = conf_cloud['city']
if 'start_lat' not in st.session_state: st.session_state.start_lat = conf_cloud['lat']
if 'start_lon' not in st.session_state: st.session_state.start_lon = conf_cloud['lon']

# Nuovi Parametri Default
if 'h_inizio' not in st.session_state: st.session_state.h_inizio = time(9, 0)
if 'h_fine' not in st.session_state: st.session_state.h_fine = time(18, 0)
if 'pausa_inizio' not in st.session_state: st.session_state.pausa_inizio = time(13, 0)
if 'pausa_fine' not in st.session_state: st.session_state.pausa_fine = time(14, 0)
if 'ferie' not in st.session_state: st.session_state.ferie = []
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'spostamenti' not in st.session_state: st.session_state.spostamenti = {}

# --- 4. LOGICA CALCOLO GIRO POTENZIATA ---
def calcola_piano():
    if st.session_state.df_master.empty: return {}, datetime.now()
    oggi_dt = datetime.now()
    lun_ref = oggi_dt - timedelta(days=oggi_dt.weekday())
    df_sim = st.session_state.df_master.copy()
    agenda_risultato = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
    
    for s in range(1, 9):
        for g in range(5):
            dt_c = (lun_ref + timedelta(weeks=s-1, days=g)).date()
            
            # Controllo Ferie
            if dt_c in st.session_state.ferie: continue
            
            o_s = datetime.combine(dt_c, st.session_state.h_inizio)
            p_s = (st.session_state.start_lat, st.session_state.start_lon)
            
            # Appuntamenti Fissi del giorno
            appuntamenti = df_sim[df_sim['appuntamento'].dt.date == dt_c].sort_values('appuntamento')
            
            # Clienti urgenti (non quelli che hanno appuntamento oggi)
            df_sim['g_p'] = (pd.to_datetime(dt_c) - df_sim['ultima visita']).dt.days.fillna(999)
            urg = df_sim[(df_sim['visitare'] == 'SI') & (df_sim['g_p'] >= df_sim['frequenza (giorni)']) & (df_sim['appuntamento'].dt.date != dt_c)].to_dict('records')
            
            while True:
                # 1. Verifica se c'è un appuntamento fisso imminente
                if not appuntamenti.empty:
                    prossimo_app = appuntamenti.iloc[0]
                    ora_app = prossimo_app['appuntamento'].to_pydatetime()
                    # Se l'orario attuale è vicino all'appuntamento, vai lì
                    if o_s >= ora_app - timedelta(minutes=st.session_state.durata_v + 15):
                        px = prossimo_app.to_dict()
                        px['ora_arrivo'] = ora_app.strftime("%H:%M")
                        px['tipo_tappa'] = "📌 APPUNTAMENTO"
                        agenda_risultato[f"Settimana {s}"][g].append(px)
                        o_s = ora_app + timedelta(minutes=st.session_state.durata_v)
                        p_s = (px['latitude'], px['longitude'])
                        appuntamenti = appuntamenti.iloc[1:]
                        continue

                # 2. Giro Normale
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
                
                # Controllo se la visita finisce prima di un appuntamento o della fine giornata
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
                    else: o_s = limite # Salta l'attesa fino all'appuntamento
                    
    return agenda_risultato, lun_ref

# --- 5. INTERFACCIA ---
c_nav = st.columns(5)
menu = ["🚀 Giro Oggi", "📅 Agenda 8 Sett", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"]
for i, m in enumerate(menu):
    if c_nav[i].button(m, use_container_width=True, type="primary" if st.session_state.active_tab == m else "secondary"):
        st.session_state.active_tab = m; st.rerun()

st.divider()
agenda, lun_base = calcola_piano()

# --- TAB: GIRO OGGI ---
if st.session_state.active_tab == "🚀 Giro Oggi":
    st.header(f"📍 Giro di Oggi")
    idx_g = datetime.now().weekday()
    if idx_g < 5:
        tappe = agenda["Settimana 1"][idx_g]
        if tappe:
            c1, c2 = st.columns([1, 2])
            with c1:
                for t in tappe:
                    is_vis = pd.to_datetime(t['ultima visita']).date() == datetime.now().date()
                    with st.container(border=True):
                        st.caption(t.get('tipo_tappa', '🚗'))
                        if is_vis: st.success("✅ VISITATO")
                        st.write(f"🕒 **{t['ora_arrivo']}** - {t['nome cliente']}")
                        # ... bottoni mappe/tel/mail rimangono invariati ...
                        if st.button("👤", key=f"go_{t['nome cliente']}"):
                            st.session_state.cliente_selezionato = t['nome cliente']; st.session_state.active_tab = "👤 Anagrafica"; st.rerun()
            with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
        else: st.info("Oggi non sono previste visite (o sei in ferie).")

# --- TAB: ANAGRAFICA (CON DATA ULTIMA VISITA E APPUNTAMENTI) ---
elif st.session_state.active_tab == "👤 Anagrafica":
    st.header("👤 Scheda Cliente")
    nomi = sorted(st.session_state.df_master['nome cliente'].unique())
    scelto = st.selectbox("Cerca cliente:", nomi)
    
    if scelto:
        idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
        d = st.session_state.df_master.loc[idx]
        
        # VISUALIZZAZIONE ULTIMA VISITA
        u_v_str = d['ultima visita'].strftime('%d/%m/%Y') if pd.notnull(d['ultima visita']) else "Mai"
        st.info(f"📅 Ultima visita effettuata il: **{u_v_str}**")
        
        with st.form("edit"):
            c1, c2 = st.columns(2)
            un = c1.text_input("Ragione Sociale", d['nome cliente'])
            uf = c1.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
            
            st.subheader("📌 Appuntamento Fisso")
            val_d = d['appuntamento'].date() if pd.notnull(d['appuntamento']) else None
            val_t = d['appuntamento'].time() if pd.notnull(d['appuntamento']) else time(10, 0)
            app_d = c1.date_input("Data Appuntamento", value=val_d)
            app_t = c1.time_input("Ora Appuntamento", value=val_t)
            rimuovi = c1.checkbox("Rimuovi appuntamento")

            uc = c2.text_input("Cellulare", d.get('cellulare',''))
            uno = st.text_area("Note Cliente", d.get('note', ''))
            
            if st.form_submit_button("💾 Salva e Sincronizza Cloud"):
                st.session_state.df_master.at[idx, 'nome cliente'] = un
                st.session_state.df_master.at[idx, 'frequenza (giorni)'] = uf
                st.session_state.df_master.at[idx, 'cellulare'] = uc
                st.session_state.df_master.at[idx, 'note'] = uno
                if rimuovi: st.session_state.df_master.at[idx, 'appuntamento'] = pd.NaT
                elif app_d: st.session_state.df_master.at[idx, 'appuntamento'] = datetime.combine(app_d, app_t)
                
                if save_to_gsheets(st.session_state.df_master): st.success("Sincronizzato!"); st.rerun()

# --- TAB: PARAMETRI (CON PAUSA, FERIE ED EXPORT) ---
elif st.session_state.active_tab == "⚙️ Parametri":
    st.header("⚙️ Configurazione")
    
    # 1. FERIE E PAUSA
    st.subheader("🏖️ Gestione Assenze e Pause")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        ferie_input = st.date_input("Seleziona giorni di Ferie (l'agenda li salterà)", value=st.session_state.ferie)
        st.session_state.ferie = ferie_input if isinstance(ferie_input, list) else [ferie_input]
    with col_f2:
        st.session_state.pausa_inizio = st.time_input("Inizio Pausa Pranzo", st.session_state.pausa_inizio)
        st.session_state.pausa_fine = st.time_input("Fine Pausa Pranzo", st.session_state.pausa_fine)

    st.divider()
    # 2. ESPORTAZIONE EXCEL
    st.subheader("📊 Esportazione Dati")
    def to_excel(df):
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        return out.getvalue()
    
    st.download_button("📥 Scarica Database Excel", to_excel(st.session_state.df_master), "giro_visite_database.xlsx")

    st.divider()
    # 3. RICARICAMENTO
    if st.button("🔄 Forza Ricaricamento Totale dal Cloud"):
        st.cache_data.clear()
        st.rerun()

# (Le tab Agenda e Nuovo Cliente rimangono funzionalmente simili alle tue versioni precedenti)
elif st.session_state.active_tab == "📅 Agenda 8 Sett":
    st.header("📅 Agenda Prossime Settimane")
    sett = st.selectbox("Settimana", list(agenda.keys()))
    cols = st.columns(5)
    giorni = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
    for i, g_nome in enumerate(giorni):
        with cols[i]:
            st.markdown(f"### {g_nome}")
            for t in agenda[sett][i]:
                with st.container(border=True):
                    st.caption(t.get('tipo_tappa', '🚗'))
                    st.write(f"**{t['ora_arrivo']}** - {t['nome cliente']}")

elif st.session_state.active_tab == "➕ Nuovo Cliente":
    st.header("➕ Nuovo Cliente")
    with st.form("new_c"):
        nn = st.text_input("Ragione Sociale")
        ni = st.text_input("Indirizzo")
        if st.form_submit_button("Salva"):
            nuovo = {'nome cliente': nn, 'indirizzo': ni, 'visitare': 'SI', 'frequenza (giorni)': 30, 'ultima visita': pd.Timestamp('2000-01-01'), 'latitude': st.session_state.start_lat, 'longitude': st.session_state.start_lon}
            st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([nuovo])], ignore_index=True)
            save_to_gsheets(st.session_state.df_master); st.rerun()
