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

# --- FUNZIONI DI SALVATAGGIO CLOUD ---
def save_to_gsheets(df):
    try:
        cols_to_save = [c for c in df.columns if c not in ['g_p', 'ora_arrivo']]
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
        if location: return location.latitude, location.longitude
        return None
    except: return None

@st.cache_data(ttl=0) 
def fetch_data():
    try:
        df = conn.read(spreadsheet=URL_FOGLIO)
        df.columns = df.columns.str.strip().str.lower()
        colonne_crm = ['contatto', 'referente', 'posizione referente', 'mail', 'telefono', 'cellulare', 'note', 'visitare', 'indirizzo', 'ultima visita', 'frequenza (giorni)', 'nome cliente', 'latitude', 'longitude', 'appuntamento']
        for col in colonne_crm:
            if col not in df.columns: df[col] = ""
        for c in ['latitude', 'longitude', 'frequenza (giorni)']:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '.'), errors='coerce')
        df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
        # Gestione colonna appuntamento
        df['appuntamento'] = pd.to_datetime(df['appuntamento'], errors='coerce')
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except Exception as e:
        st.error(f"Errore fetch dati: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=0)
def fetch_config():
    try:
        df_conf = conn.read(spreadsheet=URL_FOGLIO, worksheet="Config")
        return {
            'city': str(df_conf.iloc[0]['citta']),
            'lat': float(df_conf.iloc[0]['lat']),
            'lon': float(df_conf.iloc[0]['lon'])
        }
    except:
        return {'city': "Ancona", 'lat': 43.6158, 'lon': 13.5189}

# --- 4. CALCOLO PIANO ---
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

# --- TAB: GIRO OGGI ---
if st.session_state.active_tab == "🚀 Giro Oggi":
    st.header(f"📍 Partenza da: {st.session_state.start_city}")
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
                                        if save_to_gsheets(st.session_state.df_master): st.rerun()
            with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
        else: st.info("Nessuna visita programmata.")

# --- TAB: AGENDA 8 SETTIMANE ---
elif st.session_state.active_tab == "📅 Agenda 8 Sett":
    st.header("📅 Programmazione 8 Settimane")
    settimana_sel = st.selectbox("Seleziona Settimana", list(agenda.keys()))
    giorni = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
    cols = st.columns(5)
    for i, g_nome in enumerate(giorni):
        with cols[i]:
            st.markdown(f"### {g_nome}")
            dt_visual = (lun_base + timedelta(weeks=int(settimana_sel.split()[1])-1, days=i)).strftime("%d/%m")
            st.caption(dt_visual)
            for tappa in agenda[settimana_sel][i]:
                with st.container(border=True):
                    st.write(f"**{tappa['ora_arrivo']}**")
                    st.write(tappa['nome cliente'])
                    if st.button("👤", key=f"ag_{settimana_sel}_{i}_{tappa['nome cliente']}"):
                        st.session_state.cliente_selezionato = tappa['nome cliente']; st.session_state.active_tab = "👤 Anagrafica"; st.rerun()

# --- TAB: ANAGRAFICA ---
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
            uf = c1.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
            stato_v = "SI" if str(d.get('visitare', 'SI')).upper() == "SI" else "NO"
            uv = c1.selectbox("Includere nel Giro?", ["SI", "NO"], index=0 if stato_v == "SI" else 1)
            uc = c2.text_input("Cellulare", d.get('cellulare',''))
            um = c2.text_input("Mail", d.get('mail',''))
            uno = st.text_area("Note Cliente", d.get('note', ''))
            if st.form_submit_button("💾 Salva e Sincronizza Cloud"):
                st.session_state.df_master.at[idx, 'nome cliente'] = un
                st.session_state.df_master.at[idx, 'indirizzo'] = ui
                st.session_state.df_master.at[idx, 'frequenza (giorni)'] = uf
                st.session_state.df_master.at[idx, 'visitare'] = uv
                st.session_state.df_master.at[idx, 'cellulare'] = uc
                st.session_state.df_master.at[idx, 'mail'] = um
                st.session_state.df_master.at[idx, 'note'] = uno
                if save_to_gsheets(st.session_state.df_master): st.success("Sincronizzato!"); st.rerun()

# --- TAB: NUOVO CLIENTE ---
elif st.session_state.active_tab == "➕ Nuovo Cliente":
    st.header("➕ Nuovo Cliente")
    with st.form("new"):
        nn = st.text_input("Ragione Sociale *")
        ni = st.text_input("Indirizzo")
        nv = st.selectbox("Includere nel giro?", ["SI", "NO"])
        if st.form_submit_button("✅ Aggiungi al Cloud"):
            if nn:
                nuovo = {'nome cliente': nn, 'indirizzo': ni, 'visitare': nv, 'frequenza (giorni)': 30, 'ultima visita': pd.Timestamp('2000-01-01'), 'latitude': st.session_state.start_lat, 'longitude': st.session_state.start_lon}
                st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([nuovo])], ignore_index=True)
                if save_to_gsheets(st.session_state.df_master): st.success("Cliente aggiunto!"); st.rerun()

# --- TAB: PARAMETRI ---
elif st.session_state.active_tab == "⚙️ Parametri":
    st.header("⚙️ Configurazione")
    
    st.subheader("📍 Posizione di Partenza")
    if st.button("🎯 Usa mia posizione GPS attuale"):
        pos = streamlit_js_eval(js_expressions='navigator.geolocation.getCurrentPosition((position) => { return position.coords; })', target_id='gps_v2')
        if pos:
            lat, lon = pos['latitude'], pos['longitude']
            if save_config_cloud("Posizione GPS", lat, lon):
                st.session_state.start_lat, st.session_state.start_lon, st.session_state.start_city = lat, lon, "Posizione GPS"
                st.success("📍 Posizione GPS salvata permanentemente!")
                st.rerun()
    
    nc = st.text_input("Oppure scrivi Città:", st.session_state.start_city)
    if nc != st.session_state.start_city and nc != "Posizione GPS":
        co = get_coords(nc)
        if co:
            if save_config_cloud(nc, co[0], co[1]):
                st.session_state.start_city, st.session_state.start_lat, st.session_state.start_lon = nc, co[0], co[1]
                st.success(f"📍 Partenza fissata a {nc} per le prossime sessioni!")
                st.rerun()

    st.divider()
    st.subheader("⏰ Orari Lavoro")
    c1, c2 = st.columns(2)
    st.session_state.h_inizio = c1.time_input("Inizio Giornata", st.session_state.h_inizio)
    st.session_state.h_fine = c2.time_input("Fine Giornata", st.session_state.h_fine)
    st.session_state.durata_v = st.slider("Minuti per visita", 15, 120, st.session_state.durata_v)
    
    st.divider()
    st.subheader("🔄 Sposta Giorno")
    c_s1, c_s2 = st.columns(2)
    d_da = c_s1.date_input("Sposta giorno:", datetime.now())
    d_a = c_s2.date_input("Al giorno:", datetime.now() + timedelta(days=1))
    if st.button("Esegui Scambio"):
        st.session_state.spostamenti[d_da], st.session_state.spostamenti[d_a] = d_a, d_da
        st.success("Giro scambiato!")

    st.divider()
    if st.button("🔄 Forza Ricaricamento Totale dal Cloud"):
        st.cache_data.clear()
        st.rerun()
