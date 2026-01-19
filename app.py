import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
import io
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURAZIONE E CONNESSIONE ---
st.set_page_config(page_title="Giro Visite CRM Pro", layout="wide")

URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/edit?usp=sharing"

@st.cache_resource
def get_connection():
    return st.connection("gsheets", type=GSheetsConnection)

conn = get_connection()
ora_italiana = datetime.now() + timedelta(hours=1)

# --- FUNZIONI DI SALVATAGGIO ---
def save_to_gsheets(df):
    try:
        cols_to_save = [c for c in df.columns if c not in ['g_p', 'ora_arrivo', 'tipo_tappa', 'color']]
        conn.update(spreadsheet=URL_FOGLIO, data=df[cols_to_save])
        fetch_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ Errore salvataggio: {str(e)}")
        return False

def save_config_cloud(city, lat, lon):
    try:
        df_conf = pd.DataFrame([{'citta': city, 'lat': lat, 'lon': lon}])
        conn.update(spreadsheet=URL_FOGLIO, worksheet="Config", data=df_conf)
        fetch_config.clear()
        return True
    except Exception as e:
        st.error(f"❌ Errore config: {str(e)}")
        return False

# --- 2. UTILS ---
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return 2 * 6371 * asin(sqrt(a))

def get_coords(address):
    try:
        geolocator = Nominatim(user_agent="giro_visite_agente_v26", timeout=10)
        location = geolocator.geocode(f"{address}, Italia")
        if location:
            return (location.latitude, location.longitude)
        st.warning(f"⚠️ Indirizzo non trovato: {address}")
        return None
    except Exception as e:
        st.error(f"❌ Errore geocoding: {str(e)}")
        return None

@st.cache_data(ttl=600) 
def fetch_data():
    try:
        df = conn.read(spreadsheet=URL_FOGLIO)
        df.columns = df.columns.str.strip().str.lower()
        colonne = ['contatto', 'referente', 'posizione referente', 'mail', 'telefono', 'cellulare', 'note', 'storico report', 'visitare', 'indirizzo', 'cap', 'provincia', 'ultima visita', 'frequenza (giorni)', 'nome cliente', 'latitude', 'longitude', 'appuntamento']
        for col in colonne:
            if col not in df.columns: df[col] = ""
        for c in ['latitude', 'longitude', 'frequenza (giorni)']:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '.'), errors='coerce')
        df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
        df['appuntamento'] = pd.to_datetime(df['appuntamento'], errors='coerce')
        df['visitare'] = df['visitare'].fillna("SI").astype(str).str.upper()
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except Exception as e:
        st.error(f"❌ Errore caricamento: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_config():
    try:
        df_conf = conn.read(spreadsheet=URL_FOGLIO, worksheet="Config")
        return {'city': str(df_conf.iloc[0]['citta']), 'lat': float(df_conf.iloc[0]['lat']), 'lon': float(df_conf.iloc[0]['lon'])}
    except:
        return {'city': "Ancona", 'lat': 43.6158, 'lon': 13.5189}

# --- FUNZIONE GPS MIGLIORATA ---
def render_gps_button(button_id):
    html_code = f"""
    <button onclick="getLocation()" style="padding:10px 20px; background:#FF4B4B; color:white; border:none; border-radius:5px; cursor:pointer; font-size:16px;">
        🎯 Usa GPS Attuale
    </button>
    <div id="status_{button_id}" style="margin-top:10px; font-size:14px;"></div>
    <script>
    function getLocation() {{
        const status = document.getElementById('status_{button_id}');
        if (navigator.geolocation) {{
            status.innerHTML = '🔄 Acquisizione GPS in corso...';
            navigator.geolocation.getCurrentPosition(
                function(position) {{
                    const coords = {{
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude
                    }};
                    status.innerHTML = '✅ GPS acquisito: ' + coords.latitude.toFixed(6) + ', ' + coords.longitude.toFixed(6);
                    window.parent.postMessage({{
                        type: 'streamlit:setComponentValue',
                        key: '{button_id}',
                        value: coords
                    }}, '*');
                }},
                function(error) {{
                    status.innerHTML = '❌ Errore GPS: ' + error.message;
                }},
                {{enableHighAccuracy: true, timeout: 10000, maximumAge: 0}}
            );
        }} else {{
            status.innerHTML = '❌ GPS non supportato dal browser';
        }}
    }}
    </script>
    """
    return st.components.v1.html(html_code, height=100)

# --- 3. STATO DELL'APP ---
if 'active_tab' not in st.session_state: st.session_state.active_tab = "🚀 Giro Oggi"
if 'cliente_selezionato' not in st.session_state: st.session_state.cliente_selezionato = None
if 'df_master' not in st.session_state: st.session_state.df_master = fetch_data()
if 'current_week_index' not in st.session_state: st.session_state.current_week_index = 2
if 'last_map_click' not in st.session_state: st.session_state.last_map_click = None
if 'esclusi_oggi' not in st.session_state: st.session_state.esclusi_oggi = []
if 'show_quick_report' not in st.session_state: st.session_state.show_quick_report = False

conf_cloud = fetch_config()
if 'start_lat' not in st.session_state: st.session_state.start_lat = conf_cloud['lat']
if 'start_lon' not in st.session_state: st.session_state.start_lon = conf_cloud['lon']
if 'start_city' not in st.session_state: st.session_state.start_city = conf_cloud['city']

if 'attiva_ferie' not in st.session_state: st.session_state.attiva_ferie = False
if 'ferie' not in st.session_state: st.session_state.ferie = []

for key, val in {'h_inizio': time(9, 0), 'h_fine': time(18, 0), 'pausa_inizio': time(13, 0), 'pausa_fine': time(14, 0), 'durata_v': 45}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 4. LOGICA CALCOLO GIRO ---
@st.cache_data(ttl=300)
def calcola_piano_cached(_df, ferie_attive, ferie_date, esclusi, h_inizio, h_fine, pausa_inizio, pausa_fine, durata_v, start_lat, start_lon):
    df_sim = _df.copy()
    oggi_dt = ora_italiana
    lun_corrente = oggi_dt - timedelta(days=oggi_dt.weekday())
    lun_ref = lun_corrente - timedelta(weeks=2)
    agenda_risultato = {i: {g: [] for g in range(5)} for i in range(11)}
    etichette = [f"Passata (-{2-i})" if i<2 else ("Settimana Corrente" if i==2 else f"Futura (+{i-2})") for i in range(11)]
    
    for s in range(11):
        for g in range(5):
            dt_c = (lun_ref + timedelta(weeks=s, days=g)).date()
            if ferie_attive and ferie_date and len(ferie_date) == 2:
                try:
                    f_start = ferie_date[0] if hasattr(ferie_date[0], 'year') else ferie_date[0]
                    f_end = ferie_date[1] if hasattr(ferie_date[1], 'year') else ferie_date[1]
                    if f_start <= dt_c <= f_end: continue
                except: pass

            o_s = datetime.combine(dt_c, h_inizio)
            p_s = (start_lat, start_lon)
            f_esclusi = esclusi if (s == 2 and g == ora_italiana.weekday()) else []
            appuntamenti = df_sim[(df_sim['visitare'] == 'SI') & (df_sim['appuntamento'].dt.date == dt_c) & (~df_sim['nome cliente'].isin(f_esclusi))].sort_values('appuntamento')
            df_sim['g_p'] = (pd.to_datetime(dt_c) - df_sim['ultima visita']).dt.days.fillna(999)
            urg = df_sim[(df_sim['visitare'] == 'SI') & (df_sim['g_p'] >= df_sim['frequenza (giorni)']) & (df_sim['appuntamento'].dt.date != dt_c) & (~df_sim['nome cliente'].isin(f_esclusi))].to_dict('records')
            
            while True:
                if not appuntamenti.empty:
                    px = appuntamenti.iloc[0].to_dict()
                    ora_app = px['appuntamento'].to_pydatetime()
                    if o_s >= ora_app - timedelta(minutes=durata_v + 15):
                        px['ora_arrivo'] = ora_app.strftime("%H:%M")
                        px['tipo_tappa'] = "📌 APPUNTAMENTO"
                        agenda_risultato[s][g].append(px)
                        o_s, p_s = ora_app + timedelta(minutes=durata_v), (px['latitude'], px['longitude'])
                        appuntamenti = appuntamenti.iloc[1:]; continue
                if not urg: break
                px = min(urg, key=lambda x: haversine(p_s[0], p_s[1], x['latitude'], x['longitude']))
                dist = haversine(p_s[0], p_s[1], px['latitude'], px['longitude'])
                arr = o_s + timedelta(minutes=(dist/50)*60)
                if arr >= datetime.combine(dt_c, pausa_inizio) and arr < datetime.combine(dt_c, pausa_fine):
                    o_s = datetime.combine(dt_c, pausa_fine); continue
                fine_v = arr + timedelta(minutes=durata_v)
                limite = appuntamenti.iloc[0]['appuntamento'].to_pydatetime() if not appuntamenti.empty else datetime.combine(dt_c, h_fine)
                if fine_v <= limite:
                    px['ora_arrivo'] = arr.strftime("%H:%M")
                    px['tipo_tappa'] = "🚗 Giro"
                    agenda_risultato[s][g].append(px)
                    df_sim.loc[df_sim['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(dt_c)
                    o_s, p_s = fine_v, (px['latitude'], px['longitude'])
                    urg.remove(px)
                else: break
    return agenda_risultato, lun_ref, etichette

def calcola_piano():
    return calcola_piano_cached(st.session_state.df_master, st.session_state.attiva_ferie, st.session_state.ferie, st.session_state.esclusi_oggi, st.session_state.h_inizio, st.session_state.h_fine, st.session_state.pausa_inizio, st.session_state.pausa_fine, st.session_state.durata_v, st.session_state.start_lat, st.session_state.start_lon)

# --- 5. INTERFACCIA ---
nav = st.columns(6)
menu = ["🚀 Giro Oggi", "📅 Agenda", "🗺️ Mappa Clienti", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"]
for i, m in enumerate(menu):
    if nav[i].button(m, key=f"nav_{m}", use_container_width=True, type="primary" if st.session_state.active_tab == m else "secondary"):
        st.session_state.active_tab = m; st.rerun()

st.divider()
agenda, lun_base, etichette_settimane = calcola_piano()

# --- TAB: GIRO OGGI ---
if st.session_state.active_tab == "🚀 Giro Oggi":
    st.header(f"📍 Giro di Oggi ({ora_italiana.strftime('%d/%m/%Y')})")
    idx_g = ora_italiana.weekday()
    if idx_g < 5:
        if st.session_state.esclusi_oggi:
            with st.expander(f"⚠️ {len(st.session_state.esclusi_oggi)} Clienti esclusi"):
                for e in st.session_state.esclusi_oggi:
                    ce1, ce2 = st.columns([3, 1])
                    ce1.write(f"❌ {e}")
                    if ce2.button("Ripristina", key=f"res_{e}"): st.session_state.esclusi_oggi.remove(e); st.rerun()
        tappe = agenda[2][idx_g]
        if tappe:
            c1, c2 = st.columns([1, 2])
            with c1:
                for t in tappe:
                    with st.container(border=True):
                        cn, cs = st.columns([4, 1])
                        cn.write(f"🕒 **{t['ora_arrivo']}** - {t['nome cliente']}")
                        if cs.button("🚫", key=f"sk_{t['nome cliente']}"): st.session_state.esclusi_oggi.append(t['nome cliente']); st.rerun()
                        st.caption(f"📍 {t['indirizzo']}")
                        cols = st.columns(4)
                        cols[0].link_button("🚗", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}")
                        if t.get('cellulare'): cols[1].link_button("📱", f"tel:{t['cellulare']}")
                        if cols[3].button("👤", key=f"go_{t['nome cliente']}"): st.session_state.cliente_selezionato = t['nome cliente']; st.session_state.active_tab = "👤 Anagrafica"; st.rerun()
            with c2: 
                m_oggi = folium.Map(location=[tappe[0]['latitude'], tappe[0]['longitude']], zoom_start=10)
                for i, t in enumerate(tappe):
                    folium.Marker([t['latitude'], t['longitude']], popup=t['nome cliente'], tooltip=f"{i+1}. {t['nome cliente']}").add_to(m_oggi)
                st_folium(m_oggi, width="100%", height=600, key="map_oggi_v6")
        else: st.info("✅ Nessuna visita prevista per oggi.")
    else: st.info("🏖️ Oggi è fine settimana!")

# --- TAB: MAPPA ---
elif st.session_state.active_tab == "🗺️ Mappa Clienti":
    st.header("🗺️ Mappa Interattiva Clienti")
    filtro_tipo = st.radio("Filtro:", ["Tutti", "Visitati", "Mai Visitati"], horizontal=True, key="f_map_v6")
    df_m = st.session_state.df_master.copy()
    if filtro_tipo == "Visitati": df_m = df_m[df_m['ultima visita'] > pd.Timestamp('2000-01-01')]
    elif filtro_tipo == "Mai Visitati": df_m = df_m[df_m['ultima visita'] <= pd.Timestamp('2000-01-01')]
    if not df_m.empty:
        m = folium.Map(location=[df_m['latitude'].mean(), df_m['longitude'].mean()], zoom_start=8)
        for _, row in df_m.iterrows():
            c = "green" if row['visitare'] == "SI" else "red"
            folium.Marker(location=[row['latitude'], row['longitude']], popup=row['nome cliente'], icon=folium.Icon(color=c, icon="user")).add_to(m)
        output = st_folium(m, width="100%", height=600, key="main_map_v6")
        cl = output.get("last_object_clicked_popup")
        if cl:
            if st.session_state.last_map_click == cl: st.session_state.cliente_selezionato = cl; st.session_state.active_tab = "👤 Anagrafica"; st.rerun()
            else: st.session_state.last_map_click = cl; st.toast(f"👆 Tocca ancora: {cl}")

# --- TAB: ANAGRAFICA ---
elif st.session_state.active_tab == "👤 Anagrafica":
    st.header("👤 Scheda Anagrafica")
    nomi_reali = sorted(st.session_state.df_master['nome cliente'].unique())
    opzioni = [""] + nomi_reali
    idx_def = opzioni.index(st.session_state.cliente_selezionato) if st.session_state.cliente_selezionato in opzioni else 0
    scelto = st.selectbox("Cerca cliente:", opzioni, index=idx_def, key="sel_ana_v6")
    
    if scelto != "":
        st.session_state.cliente_selezionato = scelto
        idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
        d = st.session_state.df_master.loc[idx]
        ca = st.columns(4)
        ca[0].link_button("🚗 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={d['latitude']},{d['longitude']}")
        if d.get('cellulare'): ca[1].link_button("📱 CHIAMA", f"tel:{d['cellulare']}")
        if d.get('mail'): ca[2].link_button("📧 MAIL", f"mailto:{d['mail']}")

        st.divider()
        if pd.notnull(d['ultima visita']) and d['ultima visita'] > pd.Timestamp('2000-01-01'):
            prox_v = d['ultima visita'] + timedelta(days=int(d['frequenza (giorni)']))
            gm = (prox_v.date() - ora_italiana.date()).days
            if gm > 0: st.success(f"📅 **Prossima visita:** {prox_v.strftime('%d/%m/%Y')} (tra {gm} gg)")
            elif gm == 0: st.warning("📅 **Prossima visita:** OGGI!")
            else: st.error(f"📅 **Visita SCADUTA:** {prox_v.strftime('%d/%m/%Y')} ({abs(gm)} gg fa)")
        else: st.info("📅 **Stato:** Mai visitato.")

        st.divider()
        with st.container(border=True):
            st.subheader("🏁 Azione Rapida Fine Visita")
            if st.button("✅ APPENA VISITATO", type="primary", use_container_width=True, key="btn_visit_v6"): st.session_state.show_quick_report = True
            if st.session_state.show_quick_report:
                cr1, cr2 = st.columns([1, 2])
                dv = cr1.date_input("Data visita:", value=ora_italiana.date(), key="dv_in_v6")
                rt = st.text_area("Report incontri:", placeholder="Cosa è emerso?", key="rt_in_v6")
                c_save, c_cancel = st.columns(2)
                if c_save.button("💾 SALVA", key="save_rep_v6", use_container_width=True):
                    nuovo = f"[{dv.strftime('%d/%m/%Y')}] {rt}"
                    vecchio = str(st.session_state.df_master.at[idx, 'storico report'])
                    st.session_state.df_master.at[idx, 'storico report'] = nuovo + "\n\n" + vecchio if vecchio != "nan" and vecchio.strip() != "" else nuovo
                    st.session_state.df_master.at[idx, 'ultima visita'] = pd.to_datetime(dv)
                    if save_to_gsheets(st.session_state.df_master): st.session_state.show_quick_report = False; st.success("✅ Salvato!"); st.rerun()
                if c_cancel.button("❌ Annulla", key="can_rep_v6", use_container_width=True): st.session_state.show_quick_report = False; st.rerun()

        st.divider()
        with st.form("edit_anag_v6"):
            st.subheader("✏️ Modifica Dati Cliente")
            c1, c2 = st.columns(2)
            un = c1.text_input("Ragione Sociale", d['nome cliente'])
            ui = c1.text_input("Indirizzo", d['indirizzo'])
            u_cap = c1.text_input("CAP", d.get('cap', ''))
            u_prov = c1.text_input("Provincia", d.get('provincia', ''))
            uco = c1.text_input("Contatti", d.get('contatto', ''))
            uf = c1.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
            scv = c1.selectbox("Includere?", ["SI", "NO"], index=0 if d['visitare'] == "SI" else 1)
            ut = c2.text_input("Telefono", d.get('telefono', ''))
            uc = c2.text_input("Cellulare", d.get('cellulare',''))
            um = c2.text_input("Email", d.get('mail', ''))
            st.divider()
            app_d = c1.date_input("Appuntamento", value=d['appuntamento'].date() if pd.notnull(d['appuntamento']) else None)
            app_t = c1.time_input("Ora", value=d['appuntamento'].time() if pd.notnull(d['appuntamento']) else time(10, 0))
            rim = c2.checkbox("Rimuovi appuntamento")
            uno = st.text_area("Note fisse", d.get('note', ''), height=100)
            ust = st.text_area("Storico Report", d.get('storico report', ''), height=200)
            if st.form_submit_button("💾 Salva Modifiche", use_container_width=True):
                st.session_state.df_master.loc[idx, ['nome cliente','indirizzo','cap','provincia','contatto','frequenza (giorni)','visitare','telefono','cellulare','mail','note','storico report']] = [un,ui,u_cap,u_prov,uco,uf,scv,ut,uc,um,uno,ust]
                if rim: st.session_state.df_master.at[idx, 'appuntamento'] = pd.NaT
                elif app_d: st.session_state.df_master.at[idx, 'appuntamento'] = datetime.combine(app_d, app_t)
                if save_to_gsheets(st.session_state.df_master): st.success("✅ Salvato!"); st.rerun()

        st.divider()
        with st.expander("🗑️ ELIMINA CLIENTE"):
            st.warning(f"⚠️ Eliminazione di **{scelto}** è DEFINITIVA.")
            conferma_del = st.checkbox("Confermo eliminazione", key="check_del_v6")
            if conferma_del:
                if st.button("❌ ELIMINA DEFINITIVAMENTE", type="primary", use_container_width=True, key="btn_del_v6"):
                    st.session_state.df_master = st.session_state.df_master.drop(idx)
                    if save_to_gsheets(st.session_state.df_master): st.session_state.cliente_selezionato = None; st.success("✅ Cliente eliminato."); st.rerun()

# --- TAB: NUOVO CLIENTE ---
elif st.session_state.active_tab == "➕ Nuovo Cliente":
    st.header("➕ Registrazione Nuovo Cliente")
    gps_result = render_gps_button("new_client_gps")
    if gps_result and isinstance(gps_result, dict) and 'latitude' in gps_result:
        st.session_state.new_coords = (gps_result['latitude'], gps_result['longitude'])
        st.success(f"✅ GPS acquisito: {gps_result['latitude']:.6f}, {gps_result['longitude']:.6f}")
    
    with st.form("new_full_v6"):
        c1, c2 = st.columns(2)
        nn = c1.text_input("Ragione Sociale *")
        nf = c1.number_input("Frequenza Visite (gg)", value=30)
        nco = c1.text_input("Contatti")
        ut, uc, um = c2.text_input("Tel"), c2.text_input("Cell"), c2.text_input("Email")
        st.divider()
        via = st.text_input("Via e Civico")
        ca_row = st.columns([1, 2, 1])
        n_cap = ca_row[0].text_input("CAP")
        cit = ca_row[1].text_input("Città *")
        n_prov = ca_row[2].text_input("Prov.")
        if st.form_submit_button("✅ CREA E SALVA", use_container_width=True):
            if nn and cit:
                ind_comp = f"{via}, {n_cap} {cit} {n_prov}".strip()
                lat_lon = st.session_state.get('new_coords') or get_coords(ind_comp) or get_coords(cit)
                if lat_lon:
                    nuovo = {'nome cliente': nn, 'indirizzo': via, 'cap': n_cap, 'provincia': n_prov, 'contatto': nco, 'visitare': 'SI', 'frequenza (giorni)': nf, 'latitude': lat_lon[0], 'longitude': lat_lon[1], 'ultima visita': pd.Timestamp('2000-01-01'), 'telefono': ut, 'cellulare': uc, 'mail': um}
                    st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([nuovo])], ignore_index=True)
                    if save_to_gsheets(st.session_state.df_master): st.success("✅ Cliente creato!"); st.rerun()
                else: st.error("❌ Impossibile trovare coordinate")
            else: st.warning("⚠️ Compila i campi obbligatori")

# --- TAB: PARAMETRI ---
elif st.session_state.active_tab == "⚙️ Parametri":
    st.header("⚙️ Configurazione")
    st.subheader("📍 Punto di Partenza")
    gps_base = render_gps_button("base_gps")
    if gps_base and isinstance(gps_base, dict) and 'latitude' in gps_base:
        if save_config_cloud("GPS", gps_base['latitude'], gps_base['longitude']): st.success("✅ Base GPS aggiornata!"); st.rerun()
    nc = st.text_input("Città base:", st.session_state.start_city, key="city_input_v6")
    if nc != st.session_state.start_city:
        co = get_coords(nc)
        if co: 
            if save_config_cloud(nc, co[0], co[1]): st.rerun()
    st.divider()
    st.subheader("⏰ Orari e Tempi")
    c1, c2 = st.columns(2)
    st.session_state.h_inizio = c1.time_input("Inizio Lavoro", st.session_state.h_inizio)
    st.session_state.h_fine = c2.time

# Continuazione TAB PARAMETRI (dopo "c2.time")
_input("Fine Lavoro", st.session_state.h_fine)
    c1.time_input("Inizio Lavoro", st.session_state.h_inizio)
st.session_state.h_fine = c2.time_input("Fine Lavoro", st.session_state.h_fine)
st.session_state.pausa_inizio = c1.time_input("Inizio Pausa", st.session_state.pausa_inizio)
st.session_state.pausa_fine = c2.time_input("Fine Pausa", st.session_state.pausa_fine)
st.session_state.durata_v = st.slider("Minuti per visita", 15, 120, st.session_state.durata_v)
    
    st.divider()
    st.subheader("🏖️ Filtro Ferie / Chiusura")
    st.session_state.attiva_ferie = st.checkbox("ATTIVA FILTRO FERIE", value=st.session_state.attiva_ferie)
    ferie_in = st.date_input("Periodo chiusura:", value=st.session_state.ferie if st.session_state.ferie else [], key="f_in_v6")
    
    # Gestione ferie migliorata
    if isinstance(ferie_in, (list, tuple)):
        st.session_state.ferie = list(ferie_in)
        if len(ferie_in) == 2:
            st.success(f"✅ Ferie: dal {ferie_in[0].strftime('%d/%m/%Y')} al {ferie_in[1].strftime('%d/%m/%Y')}")
        elif len(ferie_in) == 1:
            st.info("📅 Seleziona anche la data di fine")
        else:
            st.session_state.ferie = []
    else:
        st.session_state.ferie = [ferie_in] if ferie_in else []
    
    st.divider()
    
    # Export Excel
    def to_excel(df):
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer: 
            df.to_excel(writer, index=False)
        return out.getvalue()
    
    col_exp1, col_exp2 = st.columns(2)
    col_exp1.download_button(
        "📥 Esporta Database Excel", 
        data=to_excel(st.session_state.df_master), 
        file_name=f"crm_export_{ora_italiana.strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    
    if col_exp2.button("🔄 Ricarica da Cloud", use_container_width=True):
        st.cache_data.clear()
        st.session_state.df_master = fetch_data()
        st.success("✅ Dati ricaricati!")
        st.rerun()
    
    # Info sistema
    st.divider()
    with st.expander("ℹ️ Info Sistema"):
        st.write(f"**Clienti totali:** {len(st.session_state.df_master)}")
        st.write(f"**Clienti attivi:** {len(st.session_state.df_master[st.session_state.df_master['visitare'] == 'SI'])}")
        st.write(f"**Clienti mai visitati:** {len(st.session_state.df_master[st.session_state.df_master['ultima visita'] <= pd.Timestamp('2000-01-01')])}")
        st.write(f"**Ultima sincronizzazione:** {ora_italiana.strftime('%d/%m/%Y %H:%M')}")

# --- TAB: AGENDA ---
elif st.session_state.active_tab == "📅 Agenda":
    st.header("📅 Agenda Settimanale")
    
    # Navigazione settimane
    data_lunedi = lun_base + timedelta(weeks=st.session_state.current_week_index)
    col_p, col_t, col_n = st.columns([1, 2, 1])
    
    if col_p.button("⬅️ Precedente", key="agg_p_v6", use_container_width=True):
        st.session_state.current_week_index -= 1
        st.rerun()
    
    col_t.markdown(
        f"<h3 style='text-align: center;'>📅 {etichette_settimane[st.session_state.current_week_index]}</h3>", 
        unsafe_allow_html=True
    )
    
    if col_n.button("Successiva ➡️", key="agg_n_v6", use_container_width=True):
        st.session_state.current_week_index += 1
        st.rerun()
    
    # Info settimana
    data_dom = data_lunedi + timedelta(days=6)
    st.caption(f"Dal {data_lunedi.strftime('%d/%m/%Y')} al {data_dom.strftime('%d/%m/%Y')}")
    
    st.divider()
    
    # Griglia giorni
    cols = st.columns(5)
    g_nomi = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
    
    for i, g in enumerate(g_nomi):
        dt_g = data_lunedi + timedelta(days=i)
        
        with cols[i]:
            # Header giorno
            st.subheader(f"{g}")
            st.caption(f"{dt_g.strftime('%d/%m/%Y')}")
            
            # Tappe del giorno
            tappe_giorno = agenda[st.session_state.current_week_index][i]
            
            if tappe_giorno:
                # Statistiche giorno
                num_app = sum(1 for t in tappe_giorno if t.get('tipo_tappa') == "📌 APPUNTAMENTO")
                num_giro = len(tappe_giorno) - num_app
                
                if num_app > 0:
                    st.info(f"📌 {num_app} appuntament{'o' if num_app == 1 else 'i'}")
                if num_giro > 0:
                    st.success(f"🚗 {num_giro} visit{'a' if num_giro == 1 else 'e'}")
                
                st.divider()
                
                # Lista tappe
                for t in tappe_giorno:
                    with st.container(border=True):
                        # Icona tipo tappa
                        icona = "📌" if t.get('tipo_tappa') == "📌 APPUNTAMENTO" else "🚗"
                        
                        st.caption(f"{icona} {t['ora_arrivo']}")
                        
                        # Bottone cliente
                        if st.button(
                            t['nome cliente'], 
                            key=f"ag_v6_{st.session_state.current_week_index}_{i}_{t['nome cliente']}", 
                            use_container_width=True
                        ):
                            st.session_state.cliente_selezionato = t['nome cliente']
                            st.session_state.active_tab = "👤 Anagrafica"
                            st.rerun()
                        
                        # Info aggiuntive
                        if t.get('indirizzo'):
                            st.caption(f"📍 {t['indirizzo'][:30]}...")
            else:
                # Nessuna visita
                st.info("📭 Nessuna visita")
    
    # Statistiche settimana
    st.divider()
    st.subheader("📊 Statistiche Settimana")
    
    totale_visite = sum(len(agenda[st.session_state.current_week_index][g]) for g in range(5))
    totale_app = sum(
        sum(1 for t in agenda[st.session_state.current_week_index][g] if t.get('tipo_tappa') == "📌 APPUNTAMENTO") 
        for g in range(5)
    )
    totale_giro = totale_visite - totale_app
    
    stat_cols = st.columns(4)
    stat_cols[0].metric("📊 Visite Totali", totale_visite)
    stat_cols[1].metric("📌 Appuntamenti", totale_app)
    stat_cols[2].metric("🚗 Visite Giro", totale_giro)
    
    # Media giornaliera
    media_giorno = totale_visite / 5 if totale_visite > 0 else 0
    stat_cols[3].metric("📈 Media/Giorno", f"{media_giorno:.1f}")

# --- FOOTER (opzionale) ---
st.divider()
footer_cols = st.columns([2, 1])
footer_cols[0].caption("🚀 **Giro Visite CRM Pro** - Versione 2.6 Ottimizzata")
footer_cols[1].caption(f"🕐 {ora_italiana.strftime('%H:%M:%S')}")
