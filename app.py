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

# Correzione Fuso Orario Italia (Streamlit Cloud usa UTC)
ora_italiana = datetime.now() + timedelta(hours=1)

# --- FUNZIONI DI SALVATAGGIO ---
def save_to_gsheets(df):
    try:
        # Pulizia colonne temporanee usate solo per il calcolo del giro
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
        geolocator = Nominatim(user_agent="giro_visite_agente_v28")
        location = geolocator.geocode(f"{address}, Italia", timeout=10)
        return (location.latitude, location.longitude) if location else None
    except: return None

@st.cache_data(ttl=600) # Cache 10 minuti per stabilità
def fetch_data():
    try:
        df = conn.read(spreadsheet=URL_FOGLIO)
        df.columns = df.columns.str.strip().str.lower()
        # Elenco colonne obbligatorie
        colonne = ['contatto', 'referente', 'posizione referente', 'mail', 'telefono', 'cellulare', 'note', 'storico report', 'visitare', 'indirizzo', 'ultima visita', 'frequenza (giorni)', 'nome cliente', 'latitude', 'longitude', 'appuntamento']
        for col in colonne:
            if col not in df.columns: df[col] = ""
        for c in ['latitude', 'longitude', 'frequenza (giorni)']:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '.'), errors='coerce')
        df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
        df['appuntamento'] = pd.to_datetime(df['appuntamento'], errors='coerce')
        df['visitare'] = df['visitare'].fillna("SI").astype(str).str.upper()
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except: return pd.DataFrame()

@st.cache_data(ttl=600)
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

# Parametri Default
for key, val in {'h_inizio': time(9, 0), 'h_fine': time(18, 0), 'pausa_inizio': time(13, 0), 'pausa_fine': time(14, 0), 'durata_v': 45, 'ferie': (ora_italiana.date(), ora_italiana.date())}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 4. LOGICA CALCOLO GIRO ---
def calcola_piano():
    if st.session_state.df_master.empty: return {}, ora_italiana, []
    
    lun_corrente = ora_italiana - timedelta(days=ora_italiana.weekday())
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
            
            f_esclusi = st.session_state.esclusi_oggi if (s == 2 and g == ora_italiana.weekday()) else []

            appuntamenti = df_sim[(df_sim['visitare'] == 'SI') & (df_sim['appuntamento'].dt.date == dt_c) & (~df_sim['nome cliente'].isin(f_esclusi))].sort_values('appuntamento')
            df_sim['g_p'] = (pd.to_datetime(dt_c) - df_sim['ultima visita']).dt.days.fillna(999)
            urg = df_sim[(df_sim['visitare'] == 'SI') & (df_sim['g_p'] >= df_sim['frequenza (giorni)']) & (df_sim['appuntamento'].dt.date != dt_c) & (~df_sim['nome cliente'].isin(f_esclusi))].to_dict('records')
            
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
            with st.expander(f"⚠️ {len(st.session_state.esclusi_oggi)} Clienti esclusi per oggi"):
                for e in st.session_state.esclusi_oggi:
                    ce1, ce2 = st.columns([3, 1])
                    ce1.write(f"❌ {e}")
                    if ce2.button("Ripristina", key=f"res_{e}"):
                        st.session_state.esclusi_oggi.remove(e); st.rerun()

        tappe = agenda[2][idx_g]
        if tappe:
            c1, c2 = st.columns([1, 2])
            with c1:
                for t in tappe:
                    with st.container(border=True):
                        cn, cs = st.columns([4, 1])
                        cn.write(f"🕒 **{t['ora_arrivo']}** - {t['nome cliente']}")
                        if cs.button("🚫", key=f"sk_{t['nome cliente']}", help="Escludi per oggi"):
                            st.session_state.esclusi_oggi.append(t['nome cliente']); st.rerun()
                        st.caption(f"📍 {t['indirizzo']}")
                        cols = st.columns(4)
                        cols[0].link_button("🚗", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}")
                        if t.get('cellulare'): cols[1].link_button("📱", f"tel:{t['cellulare']}")
                        if cols[3].button("👤", key=f"go_{t['nome cliente']}"):
                            st.session_state.cliente_selezionato = t['nome cliente']; st.session_state.active_tab = "👤 Anagrafica"; st.rerun()
            with c2: 
                m_oggi = folium.Map(location=[tappe[0]['latitude'], tappe[0]['longitude']], zoom_start=10)
                for i, t in enumerate(tappe):
                    folium.Marker([t['latitude'], t['longitude']], popup=t['nome cliente'], tooltip=f"{i+1}. {t['nome cliente']}").add_to(m_oggi)
                st_folium(m_oggi, width="100%", height=600, key="map_oggi")
        else: st.info("Nessuna visita prevista per oggi.")
    else: st.info("Oggi è fine settimana!")

# --- TAB: MAPPA ---
elif st.session_state.active_tab == "🗺️ Mappa Clienti":
    st.header("🗺️ Mappa Interattiva Clienti")
    filtro_tipo = st.radio("Filtro clienti:", ["Tutti i Clienti", "Visitati", "Mai Visitati"], horizontal=True, key="f_map")
    df_m = st.session_state.df_master.copy()
    if filtro_tipo == "Visitati": df_m = df_m[df_m['ultima visita'] > pd.Timestamp('2000-01-01')]
    elif filtro_tipo == "Mai Visitati": df_m = df_m[df_m['ultima visita'] <= pd.Timestamp('2000-01-01')]
    if not df_m.empty:
        m = folium.Map(location=[df_m['latitude'].mean(), df_m['longitude'].mean()], zoom_start=8)
        for _, row in df_m.iterrows():
            color = "green" if row['visitare'] == "SI" else "red"
            folium.Marker(location=[row['latitude'], row['longitude']], popup=row['nome cliente'], tooltip=row['nome cliente'], icon=folium.Icon(color=color, icon="user")).add_to(m)
        output = st_folium(m, width="100%", height=600, key="main_map")
        clicked_name = output.get("last_object_clicked_popup")
        if clicked_name:
            if st.session_state.last_map_click == clicked_name:
                st.session_state.cliente_selezionato = clicked_name
                st.session_state.last_map_click = None; st.session_state.active_tab = "👤 Anagrafica"; st.rerun()
            else:
                st.session_state.last_map_click = clicked_name; st.toast(f"Tocca ancora: {clicked_name}")
    else: st.warning("Nessun cliente trovato.")

# --- TAB: ANAGRAFICA ---
elif st.session_state.active_tab == "👤 Anagrafica":
    st.header("👤 Scheda Anagrafica")
    nomi_reali = sorted(st.session_state.df_master['nome cliente'].unique())
    opzioni_ricerca = [""] + nomi_reali
    idx_default = opzioni_ricerca.index(st.session_state.cliente_selezionato) if st.session_state.cliente_selezionato in opzioni_ricerca else 0
    scelto = st.selectbox("Cerca cliente:", opzioni_ricerca, index=idx_default, key="sel_anag")
    
    if scelto and scelto != "":
        st.session_state.cliente_selezionato = scelto
        idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
        d = st.session_state.df_master.loc[idx]
        
        ca = st.columns(4)
        ca[0].link_button("🚗 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={d['latitude']},{d['longitude']}")
        if d.get('cellulare'): ca[1].link_button("📱 CHIAMA", f"tel:{d['cellulare']}")
        if d.get('mail'): ca[2].link_button("📧 MAIL", f"mailto:{d['mail']}")

        # --- SEZIONE PROSSIMA VISITA SUGGERITA ---
        st.divider()
        if pd.notnull(d['ultima visita']) and d['ultima visita'] > pd.Timestamp('2000-01-01'):
            prox_v = d['ultima visita'] + timedelta(days=int(d['frequenza (giorni)']))
            gm = (prox_v.date() - ora_italiana.date()).days
            if gm > 0: st.success(f"📅 **Prossima visita suggerita:** {prox_v.strftime('%d/%m/%Y')} (tra {gm} giorni)")
            elif gm == 0: st.warning(f"📅 **Prossima visita suggerita:** OGGI!")
            else: st.error(f"📅 **Visita SCADUTA il:** {prox_v.strftime('%d/%m/%Y')} ({abs(gm)} giorni fa)")
        else: st.info("📅 **Stato:** Mai visitato.")

        st.divider()

        # FUNZIONE: APPENA VISITATO (STORICO)
        with st.container(border=True):
            st.subheader("🏁 Azione Rapida Fine Visita")
            if st.button("✅ APPENA VISITATO", type="primary", use_container_width=True):
                st.session_state.show_quick_report = True
            
            if st.session_state.get('show_quick_report', False):
                cr1, cr2 = st.columns([1, 2])
                data_v = cr1.date_input("Data della visita:", value=ora_italiana.date())
                report_t = st.text_area("Cosa è emerso?", placeholder="Inserisci report...", key="rep_area")
                
                b1, b2 = st.columns(2)
                if b1.button("💾 SALVA REPORT IN STORICO", use_container_width=True):
                    nuovo_entry = f"[{data_v.strftime('%d/%m/%Y')}] {report_t}"
                    vecchio = str(st.session_state.df_master.at[idx, 'storico report'])
                    note_agg = nuovo_entry + "\n\n" + vecchio if vecchio != "nan" and vecchio.strip() != "" else nuovo_entry
                    st.session_state.df_master.at[idx, 'storico report'] = note_agg
                    st.session_state.df_master.at[idx, 'ultima visita'] = pd.to_datetime(data_v)
                    if save_to_gsheets(st.session_state.df_master):
                        st.success("Registrato!"); st.session_state.show_quick_report = False; st.rerun()
                if b2.button("Annulla", use_container_width=True):
                    st.session_state.show_quick_report = False; st.rerun()

        st.divider()

        with st.form("edit_form"):
            c1, c2 = st.columns(2)
            un = c1.text_input("Ragione Sociale", d['nome cliente'])
            ui = c1.text_input("Indirizzo", d['indirizzo'])
            uco = c1.text_input("Contatti", d.get('contatto', ''))
            uf = c1.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
            ut = c2.text_input("Telefono", d.get('telefono', ''))
            uc = c2.text_input("Cellulare", d.get('cellulare', ''))
            um = c2.text_input("Email", d.get('mail', ''))
            st.divider()
            app_d = c1.date_input("Appuntamento", value=d['appuntamento'].date() if pd.notnull(d['appuntamento']) else None)
            app_t = c1.time_input("Ora", value=d['appuntamento'].time() if pd.notnull(d['appuntamento']) else time(10, 0))
            rim = c2.checkbox("Rimuovi appuntamento")
            
            uno = st.text_area("Note (Annotazioni fisse)", d.get('note', ''))
            ust = st.text_area("Storico Report", d.get('storico report', ''), height=200)
            
            if st.form_submit_button("💾 Salva Modifiche"):
                st.session_state.df_master.loc[idx, ['nome cliente','indirizzo','contatto','frequenza (giorni)','telefono','cellulare','mail','note','storico report']] = [un,ui,uco,uf,ut,uc,um,uno,ust]
                if rim: st.session_state.df_master.at[idx, 'appuntamento'] = pd.NaT
                elif app_d: st.session_state.df_master.at[idx, 'appuntamento'] = datetime.combine(app_d, app_t)
                if save_to_gsheets(st.session_state.df_master): st.rerun()
        
        with st.expander("🗑️ ELIMINA CLIENTE"):
            if st.checkbox("Confermo") and st.button("❌ ELIMINA ORA"):
                st.session_state.df_master = st.session_state.df_master.drop(idx)
                st.session_state.cliente_selezionato = None
                if save_to_gsheets(st.session_state.df_master): st.rerun()
    else: st.info("Seleziona un cliente.")

# --- TAB: NUOVO CLIENTE ---
elif st.session_state.active_tab == "➕ Nuovo Cliente":
    st.header("➕ Registrazione Nuovo Cliente")
    with st.form("new_full"):
        c1, c2 = st.columns(2)
        nn = c1.text_input("Ragione Sociale *")
        nf = c1.number_input("Frequenza Visite (gg)", value=30)
        nco = c1.text_input("Contatti")
        ut = c2.text_input("Telefono")
        uc = c2.text_input("Cellulare")
        um = c2.text_input("Email")
        st.divider()
        via = st.text_input("Via e Civico")
        cit = st.text_input("Città *")
        if st.form_submit_button("✅ CREA E SALVA"):
            if nn and cit:
                indirizzo = f"{via}, {cit}"
                with st.spinner("Cerco posizione..."):
                    lat_lon = get_coords(indirizzo) or get_coords(cit)
                if lat_lon:
                    nuovo = {'nome cliente': nn, 'indirizzo': indirizzo, 'contatto': nco, 'telefono': ut, 'cellulare': uc, 'mail': um, 'note': '', 'storico report': '', 'visitare': 'SI', 'frequenza (giorni)': nf, 'latitude': lat_lon[0], 'longitude': lat_lon[1], 'ultima visita': pd.Timestamp('2000-01-01'), 'appuntamento': pd.NaT}
                    st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([nuovo])], ignore_index=True)
                    if save_to_gsheets(st.session_state.df_master): st.success("Salvato!"); st.rerun()
                else: st.error("Posizione non trovata.")

# --- TAB: PARAMETRI ---
elif st.session_state.active_tab == "⚙️ Parametri":
    st.header("⚙️ Configurazione")
    def to_excel(df):
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer: df.to_excel(writer, index=False)
        return out.getvalue()
    st.download_button(label="📥 Scarica Database Excel", data=to_excel(st.session_state.df_master), file_name="crm_giro_visite.xlsx")
    st.divider()
    if st.button("🔄 Forza Ricarica Cloud"): st.cache_data.clear(); st.rerun()

# --- TAB: AGENDA ---
elif st.session_state.active_tab == "📅 Agenda":
    agenda, lun_base_calcolato, etichette_settimane = calcola_piano()
    data_lunedi = lun_base + timedelta(weeks=st.session_state.current_week_index)
    col_prev, col_title, col_next = st.columns([1, 2, 1])
    if col_prev.button("⬅️ Precedente"): st.session_state.current_week_index -= 1; st.rerun()
    col_title.markdown(f"<h3 style='text-align: center;'>📅 {etichette_settimane[st.session_state.current_week_index]}</h3>", unsafe_allow_html=True)
    if col_next.button("Successiva ➡️"): st.session_state.current_week_index += 1; st.rerun()
    st.divider()
    cols = st.columns(5)
    g_nomi = ["Lun", "Mar", "Mer", "Gio", "Ven"]
    for i, g in enumerate(g_nomi):
        dt_g = data_lunedi + timedelta(days=i)
        with cols[i]:
            st.subheader(f"{g} {dt_g.day}")
            for t in agenda[st.session_state.current_week_index][i]:
                with st.container(border=True):
                    st.caption(f"🕒 {t['ora_arrivo']}")
                    if st.button(t['nome cliente'], key=f"ag_{st.session_state.current_week_index}_{i}_{t['nome cliente']}", use_container_width=True):
                        st.session_state.cliente_selezionato = t['nome cliente']; st.session_state.active_tab = "👤 Anagrafica"; st.rerun()
