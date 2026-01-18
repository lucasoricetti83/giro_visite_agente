import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
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
        geolocator = Nominatim(user_agent="giro_visite_agente_v25")
        location = geolocator.geocode(f"{address}, Italia", timeout=10)
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
if 'cliente_selezionato' not in st.session_state: st.session_state.cliente_selezionato = None
if 'df_master' not in st.session_state: st.session_state.df_master = fetch_data()
if 'current_week_index' not in st.session_state: st.session_state.current_week_index = 2
if 'last_map_click' not in st.session_state: st.session_state.last_map_click = None
if 'esclusi_oggi' not in st.session_state: st.session_state.esclusi_oggi = []

conf_cloud = fetch_config()
if 'start_lat' not in st.session_state: st.session_state.start_lat = conf_cloud['lat']
if 'start_lon' not in st.session_state: st.session_state.start_lon = conf_cloud['lon']
if 'start_city' not in st.session_state: st.session_state.start_city = conf_cloud['city']

for key, val in {'h_inizio': time(9, 0), 'h_fine': time(18, 0), 'pausa_inizio': time(13, 0), 'pausa_fine': time(14, 0), 'durata_v': 45, 'ferie': (datetime.now().date(), datetime.now().date())}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 4. LOGICA CALCOLO GIRO ---
def calcola_piano():
    if st.session_state.df_master.empty: return {}, datetime.now(), []
    oggi_dt = datetime.now()
    lun_corrente = oggi_dt - timedelta(days=oggi_dt.weekday())
    lun_ref = lun_corrente - timedelta(weeks=2) 
    df_sim = st.session_state.df_master.copy()
    agenda_risultato = {i: {g: [] for g in range(5)} for i in range(11)}
    
    etichette = []
    for i in range(11):
        if i < 2: etichette.append(f"Passata (-{2-i})")
        elif i == 2: etichette.append("Settimana Corrente")
        else: etichette.append(f"Futura (+{i-2})")
    
    for s in range(11):
        for g in range(5):
            dt_c = (lun_ref + timedelta(weeks=s, days=g)).date()
            if dt_c in st.session_state.ferie: continue
            o_s, p_s = datetime.combine(dt_c, st.session_state.h_inizio), (st.session_state.start_lat, st.session_state.start_lon)
            
            # FILTRO ESCLUSI (Solo per oggi: s=2, g=oggi_dt.weekday())
            f_esclusi = []
            if s == 2 and g == oggi_dt.weekday():
                f_esclusi = st.session_state.esclusi_oggi

            appuntamenti = df_sim[(df_sim['visitare'] == 'SI') & 
                                 (df_sim['appuntamento'].dt.date == dt_c) & 
                                 (~df_sim['nome cliente'].isin(f_esclusi))].sort_values('appuntamento')
            
            df_sim['g_p'] = (pd.to_datetime(dt_c) - df_sim['ultima visita']).dt.days.fillna(999)
            
            urg = df_sim[(df_sim['visitare'] == 'SI') & 
                        (df_sim['g_p'] >= df_sim['frequenza (giorni)']) & 
                        (df_sim['appuntamento'].dt.date != dt_c) &
                        (~df_sim['nome cliente'].isin(f_esclusi))].to_dict('records')
            
            while True:
                if not appuntamenti.empty:
                    px = appuntamenti.iloc[0].to_dict()
                    ora_app = px['appuntamento'].to_pydatetime()
                    if o_s >= ora_app - timedelta(minutes=st.session_state.durata_v + 15):
                        px['ora_arrivo'] = ora_app.strftime("%H:%M")
                        px['tipo_tappa'] = "📌 APPUNTAMENTO"
                        agenda_risultato[s][g].append(px)
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
                    agenda_risultato[s][g].append(px)
                    df_sim.loc[df_sim['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(dt_c)
                    o_s, p_s = fine_v, (px['latitude'], px['longitude'])
                    urg.remove(px)
                else: break
    return agenda_risultato, lun_ref, etichette

# --- 5. INTERFACCIA ---
nav = st.columns(6)
menu = ["🚀 Giro Oggi", "📅 Agenda", "🗺️ Mappa Clienti", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"]
for i, m in enumerate(menu):
    if nav[i].button(m, use_container_width=True, type="primary" if st.session_state.active_tab == m else "secondary"):
        st.session_state.active_tab = m; st.rerun()

st.divider()
agenda, lun_base, etichette_settimane = calcola_piano()

# --- TAB: GIRO OGGI ---
if st.session_state.active_tab == "🚀 Giro Oggi":
    st.header(f"📍 Giro di Oggi")
    idx_g = datetime.now().weekday()
    
    if idx_g < 5:
        # Sezione Esclusi
        if st.session_state.esclusi_oggi:
            with st.expander(f"⚠️ {len(st.session_state.esclusi_oggi)} Clienti esclusi per oggi"):
                for e in st.session_state.esclusi_oggi:
                    col_e1, col_e2 = st.columns([3, 1])
                    col_e1.write(f"❌ {e}")
                    if col_e2.button("🔄 Ripristina", key=f"restore_{e}"):
                        st.session_state.esclusi_oggi.remove(e)
                        st.rerun()

        tappe = agenda[2][idx_g]
        
        if tappe:
            c1, c2 = st.columns([1, 2])
            with c1:
                for t in tappe:
                    tipo_color = "🔵" if "APPUNTAMENTO" in t['tipo_tappa'] else "🚗"
                    with st.container(border=True):
                        # Header con nome e pulsante esclusione
                        h_col1, h_col2 = st.columns([4, 1])
                        h_col1.write(f"{tipo_color} **{t['ora_arrivo']}** - {t['nome cliente']}")
                        if h_col2.button("🚫", key=f"skip_{t['nome cliente']}", help="Salta per oggi"):
                            st.session_state.esclusi_oggi.append(t['nome cliente'])
                            st.rerun()
                        
                        st.caption(f"📍 {t['indirizzo']}")
                        cols = st.columns(4)
                        cols[0].link_button("🚗", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}")
                        if t.get('cellulare'): cols[1].link_button("📱", f"tel:{t['cellulare']}")
                        if cols[3].button("👤", key=f"go_{t['nome cliente']}"):
                            st.session_state.cliente_selezionato = t['nome cliente']; st.session_state.active_tab = "👤 Anagrafica"; st.rerun()
            with c2: 
                m_oggi = folium.Map(location=[tappe[0]['latitude'], tappe[0]['longitude']], zoom_start=10)
                punti = [[st.session_state.start_lat, st.session_state.start_lon]]
                folium.Marker([st.session_state.start_lat, st.session_state.start_lon], tooltip="PARTENZA", icon=folium.Icon(color='black', icon='home')).add_to(m_oggi)
                for i, t in enumerate(tappe):
                    color_marker = 'blue' if "APPUNTAMENTO" in t['tipo_tappa'] else 'green'
                    folium.Marker([t['latitude'], t['longitude']], popup=t['nome cliente'], tooltip=f"{i+1}. {t['nome cliente']}", icon=folium.Icon(color=color_marker)).add_to(m_oggi)
                    punti.append([t['latitude'], t['longitude']])
                folium.PolyLine(punti, color="blue", weight=2.5, opacity=0.8).add_to(m_oggi)
                st_folium(m_oggi, width="100%", height=500, key="map_oggi")
        else:
            st.info("Nessuna visita prevista per oggi.")
    else:
        st.info("Oggi è fine settimana!")

# --- TAB: MAPPA ---
elif st.session_state.active_tab == "🗺️ Mappa Clienti":
    st.header("🗺️ Mappa Interattiva Clienti")
    filtro_tipo = st.radio("Filtro clienti:", ["Tutti i Clienti", "Visitati", "Mai Visitati"], horizontal=True)
    df_m = st.session_state.df_master.copy()
    if filtro_tipo == "Visitati": df_m = df_m[df_m['ultima visita'] > pd.Timestamp('2000-01-01')]
    elif filtro_tipo == "Mai Visitati": df_m = df_m[df_m['ultima visita'] <= pd.Timestamp('2000-01-01')]
    if not df_m.empty:
        m = folium.Map(location=[df_m['latitude'].mean(), df_m['longitude'].mean()], zoom_start=8)
        for _, row in df_m.iterrows():
            color = "green" if row['visitare'] == "SI" else "red"
            folium.Marker(location=[row['latitude'], row['longitude']], popup=row['nome cliente'], tooltip=row['nome cliente'], icon=folium.Icon(color=color, icon="user", prefix="fa")).add_to(m)
        output = st_folium(m, width="100%", height=600, key="main_map")
        clicked_name = output.get("last_object_clicked_popup")
        if clicked_name:
            if st.session_state.last_map_click == clicked_name:
                st.session_state.cliente_selezionato = clicked_name
                st.session_state.last_map_click = None
                st.session_state.active_tab = "👤 Anagrafica"; st.rerun()
            else:
                st.session_state.last_map_click = clicked_name
                st.toast(f"Selezionato: {clicked_name}. Tocca di nuovo per aprire.", icon="👤")
    else: st.warning("Nessun cliente trovato.")

# --- TAB: ANAGRAFICA ---
elif st.session_state.active_tab == "👤 Anagrafica":
    st.header("👤 Scheda Anagrafica")
    nomi_reali = sorted(st.session_state.df_master['nome cliente'].unique())
    opzioni_ricerca = [""] + nomi_reali
    idx_default = 0
    if st.session_state.cliente_selezionato in opzioni_ricerca:
        idx_default = opzioni_ricerca.index(st.session_state.cliente_selezionato)
    scelto = st.selectbox("Cerca cliente:", opzioni_ricerca, index=idx_default)
    if scelto and scelto != "":
        st.session_state.cliente_selezionato = scelto
        idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
        d = st.session_state.df_master.loc[idx]
        c_act = st.columns(4)
        c_act[0].link_button("🚗 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={d['latitude']},{d['longitude']}")
        if d.get('cellulare'): c_act[1].link_button("📱 CHIAMA", f"tel:{d['cellulare']}")
        if d.get('mail'): c_act[2].link_button("📧 MAIL", f"mailto:{d['mail']}")
        with st.form("edit_anag"):
            c1, c2 = st.columns(2)
            un, ui = c1.text_input("Ragione Sociale", d['nome cliente']), c1.text_input("Indirizzo", d['indirizzo'])
            uf, scelta_v = c1.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)'])), c1.selectbox("Includere?", ["SI", "NO"], index=0 if d['visitare'] == "SI" else 1)
            ut, uc, um = c2.text_input("Telefono", d.get('telefono', '')), c2.text_input("Cellulare", d.get('cellulare','')), c2.text_input("Email", d.get('mail',''))
            st.divider()
            app_d = c1.date_input("Data Appuntamento", value=d['appuntamento'].date() if pd.notnull(d['appuntamento']) else None)
            app_t = c1.time_input("Ora Appuntamento", value=d['appuntamento'].time() if pd.notnull(d['appuntamento']) else time(10, 0))
            rimuovi = c2.checkbox("Rimuovi appuntamento")
            uno = st.text_area("Note", d.get('note', ''))
            if st.form_submit_button("💾 Salva Modifiche"):
                st.session_state.df_master.at[idx, ['nome cliente','indirizzo','frequenza (giorni)','visitare','telefono','cellulare','mail','note']] = [un,ui,uf,scelta_v,ut,uc,um,uno]
                if rimuovi: st.session_state.df_master.at[idx, 'appuntamento'] = pd.NaT
                elif app_d: st.session_state.df_master.at[idx, 'appuntamento'] = datetime.combine(app_d, app_t)
                if save_to_gsheets(st.session_state.df_master): st.rerun()
        st.divider()
        with st.expander("🗑️ ELIMINA CLIENTE"):
            if st.checkbox("Confermo eliminazione") and st.button("❌ ELIMINA ORA"):
                st.session_state.df_master = st.session_state.df_master.drop(idx)
                st.session_state.cliente_selezionato = None
                if save_to_gsheets(st.session_state.df_master): st.rerun()
    else:
        st.info("Seleziona un cliente per visualizzare la scheda.")
        st.session_state.cliente_selezionato = None

# --- TAB: NUOVO CLIENTE ---
elif st.session_state.active_tab == "➕ Nuovo Cliente":
    st.header("➕ Registrazione Nuovo Cliente")
    if st.button("🎯 USA POSIZIONE GPS ATTUALE"):
        pos_new = streamlit_js_eval(js_expressions='navigator.geolocation.getCurrentPosition((pos) => { return pos.coords; })', target_id='gps_new_v21')
        if pos_new: st.session_state.new_coords = (pos_new['latitude'], pos_new['longitude'])
    with st.form("new_full"):
        c1, c2 = st.columns(2)
        nn, nf = c1.text_input("Ragione Sociale *"), c1.number_input("Frequenza Visite (gg)", value=30)
        ut, uc, um = c2.text_input("Telefono"), c2.text_input("Cellulare"), c2.text_input("Email")
        st.divider()
        via = st.text_input("Via e Civico")
        ca_row = st.columns([1, 2, 1])
        cap, cit, pro = ca_row[0].text_input("CAP"), ca_row[1].text_input("Città *"), ca_row[2].text_input("Prov.")
        st.divider()
        m_lat = st.text_input("Latitudine Manuale (opzionale)")
        m_lon = st.text_input("Longitudine Manuale (opzionale)")
        if st.form_submit_button("✅ CREA E SALVA"):
            if nn and cit:
                ind_comp = f"{via}, {cap} {cit} {pro}".strip(", ").strip()
                lat, lon = None, None
                if m_lat and m_lon: lat, lon = float(m_lat), float(m_lon)
                elif 'new_coords' in st.session_state: lat, lon = st.session_state.new_coords
                else:
                    with st.spinner("Cerco la posizione..."):
                        lat, lon = get_coords(ind_comp) or (None, None)
                        if not lat and via: lat, lon = get_coords(f"{via}, {cit}") or (None, None)
                        if not lat: lat, lon = get_coords(cit) or (None, None)
                if lat:
                    nuovo = {'nome cliente': nn, 'indirizzo': ind_comp, 'referente': '', 'telefono': ut, 'cellulare': uc, 'mail': um, 'note': '', 'visitare': 'SI', 'frequenza (giorni)': nf, 'latitude': lat, 'longitude': lon, 'ultima visita': pd.Timestamp('2000-01-01'), 'appuntamento': pd.NaT}
                    st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([nuovo])], ignore_index=True)
                    if save_to_gsheets(st.session_state.df_master):
                        st.success("✅ Cliente salvato!"); st.rerun()
                else: st.error("❌ Impossibile trovare la città.")
            else: st.warning("⚠️ Nome e Città sono obbligatori.")

# --- TAB: PARAMETRI ---
elif st.session_state.active_tab == "⚙️ Parametri":
    st.header("⚙️ Configurazione")
    st.subheader("📍 Punto di Partenza")
    if st.button("🎯 USA GPS ATTUALE"):
        gps_p = streamlit_js_eval(js_expressions='navigator.geolocation.getCurrentPosition((pos) => { return pos.coords; })', target_id='gps_param_v21')
        if gps_p:
            if save_config_cloud("Posizione GPS", gps_p['latitude'], gps_p['longitude']):
                st.session_state.start_lat, st.session_state.start_lon, st.session_state.start_city = gps_p['latitude'], gps_p['longitude'], "Posizione GPS"
                st.rerun()
    nc = st.text_input("Oppure scrivi Città:", st.session_state.start_city)
    if nc != st.session_state.start_city and nc != "Posizione GPS":
        co = get_coords(nc)
        if co and save_config_cloud(nc, co[0], co[1]):
            st.session_state.start_city, st.session_state.start_lat, st.session_state.start_lon = nc, co[0], co[1]
            st.rerun()
    st.divider()
    co1, col2 = st.columns(2)
    st.session_state.h_inizio, st.session_state.h_fine = co1.time_input("Inizio Lavoro", st.session_state.h_inizio), col2.time_input("Fine Lavoro", st.session_state.h_fine)
    st.session_state.pausa_inizio, st.session_state.pausa_fine = co1.time_input("Inizio Pausa", st.session_state.pausa_inizio), col2.time_input("Fine Pausa", st.session_state.pausa_fine)
    st.session_state.durata_v = st.slider("Minuti per visita", 15, 120, st.session_state.durata_v)
    st.divider()
    ferie_in = st.date_input("Periodo chiusura", value=st.session_state.ferie)
    if isinstance(ferie_in, tuple) and len(ferie_in) == 2: st.session_state.ferie = ferie_in
    st.divider()
    def to_excel(df):
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer: df.to_excel(writer, index=False)
        return out.getvalue()
    st.download_button(label="📥 Scarica Database Excel", data=to_excel(st.session_state.df_master), file_name="crm_giro_visite.xlsx")
    if st.button("🔄 Forza Ricarica Cloud"): st.cache_data.clear(); st.rerun()

# --- TAB: AGENDA ---
elif st.session_state.active_tab == "📅 Agenda":
    agenda, lun_base_calcolato, etichette_settimane = calcola_piano()
    data_lunedi = lun_base + timedelta(weeks=st.session_state.current_week_index)
    data_venerdi = data_lunedi + timedelta(days=4)
    range_date = f"dal {data_lunedi.strftime('%d/%m')} al {data_venerdi.strftime('%d/%m')}"
    col_prev, col_title, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("⬅️ Precedente", disabled=(st.session_state.current_week_index == 0), use_container_width=True):
            st.session_state.current_week_index -= 1; st.rerun()
    with col_title:
        titolo_sett = etichette_settimane[st.session_state.current_week_index]
        st.markdown(f"<h3 style='text-align: center; margin-bottom: 0;'>📅 {titolo_sett}</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: center; color: #666; font-size: 1.1em;'>{range_date}</p>", unsafe_allow_html=True)
    with col_next:
        if st.button("Successiva ➡️", disabled=(st.session_state.current_week_index == 10), use_container_width=True):
            st.session_state.current_week_index += 1; st.rerun()
    st.divider()
    cols = st.columns(5)
    g_nomi = ["Lun", "Mar", "Mer", "Gio", "Ven"]
    for i, g in enumerate(g_nomi):
        data_giorno = data_lunedi + timedelta(days=i)
        with cols[i]:
            st.subheader(f"{g} {data_giorno.day}")
            for t in agenda[st.session_state.current_week_index][i]:
                with st.container(border=True):
                    st.caption(f"🕒 {t['ora_arrivo']}")
                    if st.button(t['nome cliente'], key=f"btn_agg_{st.session_state.current_week_index}_{i}_{t['nome cliente']}", use_container_width=True):
                        st.session_state.cliente_selezionato = t['nome cliente']
                        st.session_state.active_tab = "👤 Anagrafica"
                        st.rerun()
