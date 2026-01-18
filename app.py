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

# --- 2. FUNZIONI DI SALVATAGGIO ---
def save_to_gsheets(df):
    """Salva il dataframe su Google Sheets pulendo le colonne temporanee"""
    try:
        cols_to_save = [c for c in df.columns if c not in ['g_p', 'ora_arrivo', 'tipo_tappa', 'color']]
        conn.update(spreadsheet=URL_FOGLIO, data=df[cols_to_save])
        st.cache_data.clear() 
        return True
    except Exception as e:
        st.error(f"Errore durante il salvataggio Cloud: {e}")
        return False

def save_config_cloud(city, lat, lon):
    """Salva la configurazione del punto di partenza nel foglio 'Config'"""
    try:
        df_conf = pd.DataFrame([{'citta': city, 'lat': lat, 'lon': lon}])
        conn.update(spreadsheet=URL_FOGLIO, worksheet="Config", data=df_conf)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Errore salvataggio configurazione: {e}")
        return False

# --- 3. UTILS (GEOGRAFIA E DATI) ---
def haversine(lat1, lon1, lat2, lon2):
    """Calcola la distanza in km tra due punti"""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    return 2 * 6371 * asin(sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2))

def get_coords(address):
    """Cerca le coordinate di un indirizzo (limita la ricerca all'Italia)"""
    try:
        geolocator = Nominatim(user_agent="giro_visite_agente_v27_pro")
        location = geolocator.geocode(f"{address}, Italia", timeout=10)
        if location:
            return (location.latitude, location.longitude)
        return None
    except:
        return None

@st.cache_data(ttl=0) 
def fetch_data():
    """Scarica i dati dei clienti dal foglio Google"""
    try:
        df = conn.read(spreadsheet=URL_FOGLIO)
        df.columns = df.columns.str.strip().str.lower()
        
        # Assicura la presenza di tutte le colonne necessarie
        colonne_obbligatorie = [
            'contatto', 'referente', 'posizione referente', 'mail', 'telefono', 
            'cellulare', 'note', 'visitare', 'indirizzo', 'ultima visita', 
            'frequenza (giorni)', 'nome cliente', 'latitude', 'longitude', 'appuntamento'
        ]
        for col in colonne_obbligatorie:
            if col not in df.columns:
                df[col] = ""
        
        # Conversione tipi dati
        for c in ['latitude', 'longitude', 'frequenza (giorni)']:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '.'), errors='coerce')
            
        df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
        df['appuntamento'] = pd.to_datetime(df['appuntamento'], errors='coerce')
        df['visitare'] = df['visitare'].fillna("SI").astype(str).str.upper()
        
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except Exception as e:
        st.error(f"Errore nel caricamento dati: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=0)
def fetch_config():
    """Scarica la configurazione dal foglio Config"""
    try:
        df_conf = conn.read(spreadsheet=URL_FOGLIO, worksheet="Config")
        return {
            'city': str(df_conf.iloc[0]['citta']), 
            'lat': float(df_conf.iloc[0]['lat']), 
            'lon': float(df_conf.iloc[0]['lon'])
        }
    except:
        return {'city': "Ancona", 'lat': 43.6158, 'lon': 13.5189}

# --- 4. LOGICA CALCOLO AGENDA (11 SETTIMANE) ---
def calcola_piano():
    if st.session_state.df_master.empty:
        return {}, datetime.now(), []
        
    oggi_dt = datetime.now()
    lun_corrente = oggi_dt - timedelta(days=oggi_dt.weekday())
    lun_ref = lun_corrente - timedelta(weeks=2) # Inizia da 2 settimane fa
    
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
            if dt_c in st.session_state.ferie:
                continue
                
            o_s = datetime.combine(dt_c, st.session_state.h_inizio)
            p_s = (st.session_state.start_lat, st.session_state.start_lon)
            
            # Filtro esclusi solo per la settimana corrente
            f_esclusi = st.session_state.esclusi_oggi if (s == 2 and g == oggi_dt.weekday()) else []

            # 1. Gestione Appuntamenti Fissi
            appuntamenti = df_sim[
                (df_sim['visitare'] == 'SI') & 
                (df_sim['appuntamento'].dt.date == dt_c) & 
                (~df_sim['nome cliente'].isin(f_esclusi))
            ].sort_values('appuntamento')
            
            # 2. Calcolo urgenze (Nearest Neighbor)
            df_sim['g_p'] = (pd.to_datetime(dt_c) - df_sim['ultima visita']).dt.days.fillna(999)
            urg = df_sim[
                (df_sim['visitare'] == 'SI') & 
                (df_sim['g_p'] >= df_sim['frequenza (giorni)']) & 
                (df_sim['appuntamento'].dt.date != dt_c) & 
                (~df_sim['nome cliente'].isin(f_esclusi))
            ].to_dict('records')
            
            while True:
                if not appuntamenti.empty:
                    px = appuntamenti.iloc[0].to_dict()
                    ora_app = px['appuntamento'].to_pydatetime()
                    if o_s >= ora_app - timedelta(minutes=st.session_state.durata_v + 15):
                        px['ora_arrivo'] = ora_app.strftime("%H:%M")
                        px['tipo_tappa'] = "📌 APPUNTAMENTO"
                        agenda_risultato[s][g].append(px)
                        o_s = ora_app + timedelta(minutes=st.session_state.durata_v)
                        p_s = (px['latitude'], px['longitude'])
                        appuntamenti = appuntamenti.iloc[1:]
                        continue
                
                if not urg:
                    break
                    
                px = min(urg, key=lambda x: haversine(p_s[0], p_s[1], x['latitude'], x['longitude']))
                dist = haversine(p_s[0], p_s[1], px['latitude'], px['longitude'])
                arr = o_s + timedelta(minutes=(dist/50)*60)
                
                # Pausa pranzo
                if arr >= datetime.combine(dt_c, st.session_state.pausa_inizio) and arr < datetime.combine(dt_c, st.session_state.pausa_fine):
                    o_s = datetime.combine(dt_c, st.session_state.pausa_fine)
                    continue
                
                fine_v = arr + timedelta(minutes=st.session_state.durata_v)
                limite = appuntamenti.iloc[0]['appuntamento'].to_pydatetime() if not appuntamenti.empty else datetime.combine(dt_c, st.session_state.h_fine)
                
                if fine_v <= limite:
                    px['ora_arrivo'] = arr.strftime("%H:%M")
                    px['tipo_tappa'] = "🚗 Giro"
                    agenda_risultato[s][g].append(px)
                    # Aggiorna virtualmente l'ultima visita per la simulazione
                    df_sim.loc[df_sim['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(dt_c)
                    o_s = fine_v
                    p_s = (px['latitude'], px['longitude'])
                    urg.remove(px)
                else:
                    break
                    
    return agenda_risultato, lun_ref, etichette

# --- 5. STATO DELL'APP ---
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
for key, val in {
    'h_inizio': time(9, 0), 'h_fine': time(18, 0), 
    'pausa_inizio': time(13, 0), 'pausa_fine': time(14, 0), 
    'durata_v': 45, 'ferie': (datetime.now().date(), datetime.now().date())
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- 6. INTERFACCIA E NAVIGAZIONE ---
st.title("Giro Visite CRM Pro")
nav = st.columns(6)
menu = ["🚀 Giro Oggi", "📅 Agenda", "🗺️ Mappa Clienti", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"]

for i, m in enumerate(menu):
    if nav[i].button(m, use_container_width=True, type="primary" if st.session_state.active_tab == m else "secondary"):
        st.session_state.active_tab = m
        st.rerun()

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
                    ce1, ce2 = st.columns([3, 1])
                    ce1.write(f"❌ {e}")
                    if ce2.button("🔄 Ripristina", key=f"res_{e}"):
                        st.session_state.esclusi_oggi.remove(e)
                        st.rerun()

        tappe = agenda[2][idx_g]
        if tappe:
            c1, c2 = st.columns([1, 2])
            with c1:
                for t in tappe:
                    with st.container(border=True):
                        cn, cs = st.columns([4, 1])
                        cn.write(f"🕒 **{t['ora_arrivo']}** - {t['nome cliente']}")
                        if cs.button("🚫", key=f"sk_{t['nome cliente']}", help="Escludi per oggi"):
                            st.session_state.esclusi_oggi.append(t['nome cliente'])
                            st.rerun()
                        
                        st.caption(f"📍 {t['indirizzo']}")
                        
                        cols = st.columns(4)
                        cols[0].link_button("🚗", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}")
                        if t.get('cellulare'):
                            cols[1].link_button("📱", f"tel:{t['cellulare']}")
                        if t.get('mail'):
                            cols[2].link_button("📧", f"mailto:{t['mail']}")
                        if cols[3].button("👤", key=f"go_{t['nome cliente']}"):
                            st.session_state.cliente_selezionato = t['nome cliente']
                            st.session_state.active_tab = "👤 Anagrafica"
                            st.rerun()
            with c2: 
                m_oggi = folium.Map(location=[tappe[0]['latitude'], tappe[0]['longitude']], zoom_start=10)
                for i, t in enumerate(tappe):
                    folium.Marker(
                        [t['latitude'], t['longitude']], 
                        popup=t['nome cliente'], 
                        tooltip=f"{i+1}. {t['nome cliente']}"
                    ).add_to(m_oggi)
                st_folium(m_oggi, width="100%", height=600, key="map_oggi")
        else:
            st.info("Nessuna visita prevista per oggi.")
    else:
        st.info("Oggi è fine settimana!")

# --- TAB: MAPPA ---
elif st.session_state.active_tab == "🗺️ Mappa Clienti":
    st.header("🗺️ Mappa Interattiva")
    filtro = st.radio("Filtro:", ["Tutti i Clienti", "Visitati", "Mai Visitati"], horizontal=True)
    df_m = st.session_state.df_master.copy()
    
    if filtro == "Visitati":
        df_m = df_m[df_m['ultima visita'] > pd.Timestamp('2000-01-01')]
    elif filtro == "Mai Visitati":
        df_m = df_m[df_m['ultima visita'] <= pd.Timestamp('2000-01-01')]
    
    if not df_m.empty:
        m = folium.Map(location=[df_m['latitude'].mean(), df_m['longitude'].mean()], zoom_start=8)
        for _, row in df_m.iterrows():
            c = "green" if row['visitare'] == "SI" else "red"
            folium.Marker(
                [row['latitude'], row['longitude']], 
                popup=row['nome cliente'], 
                tooltip=row['nome cliente'], 
                icon=folium.Icon(color=c, icon="user", prefix="fa")
            ).add_to(m)
            
        out = st_folium(m, width="100%", height=600, key="main_map")
        cl = out.get("last_object_clicked_popup")
        if cl:
            if st.session_state.last_map_click == cl:
                st.session_state.cliente_selezionato = cl
                st.session_state.last_map_click = None
                st.session_state.active_tab = "👤 Anagrafica"
                st.rerun()
            else:
                st.session_state.last_map_click = cl
                st.toast(f"Tocca ancora su {cl} per aprire la scheda.")
    else:
        st.warning("Nessun cliente trovato con questo filtro.")

# --- TAB: ANAGRAFICA (VERSIONE ESTESA) ---
elif st.session_state.active_tab == "👤 Anagrafica":
    st.header("👤 Scheda Anagrafica")
    
    nomi = [""] + sorted(st.session_state.df_master['nome cliente'].unique().tolist())
    idx_d = nomi.index(st.session_state.cliente_selezionato) if st.session_state.cliente_selezionato in nomi else 0
    scelto = st.selectbox("Cerca cliente:", nomi, index=idx_d)
    
    if scelto != "":
        st.session_state.cliente_selezionato = scelto
        idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
        d = st.session_state.df_master.loc[idx]
        
        # Pulsanti Rapidi
        ca = st.columns(4)
        ca[0].link_button("🚗 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={d['latitude']},{d['longitude']}")
        if d.get('cellulare'): ca[1].link_button("📱 CHIAMA", f"tel:{d['cellulare']}")
        if d.get('mail'): ca[2].link_button("📧 MAIL", f"mailto:{d['mail']}")
        
        st.divider()
        
        # SEZIONE REPORT CON DATA VARIABILE
        with st.container(border=True):
            st.subheader("✅ Registrazione Visita Effettuata")
            if st.button("📝 APRI MODULO REPORT", type="primary", use_container_width=True):
                st.session_state.show_quick_report = True
            
            if st.session_state.get('show_quick_report', False):
                cr1, cr2 = st.columns([1, 2])
                data_v = cr1.date_input("Data della visita:", value=datetime.now().date())
                testo_v = st.text_area("Cosa è emerso?")
                
                b1, b2 = st.columns(2)
                if b1.button("💾 SALVA REPORT E AGGIORNA CRM", use_container_width=True):
                    st.session_state.df_master.at[idx, 'note'] = testo_v
                    st.session_state.df_master.at[idx, 'ultima visita'] = pd.to_datetime(data_v)
                    if save_to_gsheets(st.session_state.df_master):
                        st.success(f"Visita del {data_v.strftime('%d/%m')} salvata!")
                        st.session_state.show_quick_report = False
                        st.rerun()
                if b2.button("Annulla", use_container_width=True):
                    st.session_state.show_quick_report = False
                    st.rerun()

        st.divider()

        # Form di Modifica Anagrafica
        with st.form("edit_anag"):
            st.subheader("Dati Cliente")
            c1, c2 = st.columns(2)
            un = c1.text_input("Ragione Sociale", d['nome cliente'])
            ui = c1.text_input("Indirizzo", d['indirizzo'])
            uf = c1.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
            sv = c1.selectbox("Includere nel Giro?", ["SI", "NO"], index=0 if d['visitare'] == "SI" else 1)
            
            ut = c2.text_input("Telefono", d.get('telefono', ''))
            uc = c2.text_input("Cellulare", d.get('cellulare', ''))
            um = c2.text_input("Email", d.get('mail', ''))
            
            st.divider()
            ad = c1.date_input("Appuntamento Futuro", value=d['appuntamento'].date() if pd.notnull(d['appuntamento']) else None)
            at = c1.time_input("Ora Appuntamento", value=d['appuntamento'].time() if pd.notnull(d['appuntamento']) else time(10, 0))
            rm = c2.checkbox("Rimuovi appuntamento esistente")
            no = st.text_area("Note Storiche", d.get('note', ''))
            
            if st.form_submit_button("💾 Salva Modifiche Anagrafiche"):
                st.session_state.df_master.at[idx, ['nome cliente','indirizzo','frequenza (giorni)','visitare','telefono','cellulare','mail','note']] = [un,ui,uf,sv,ut,uc,um,no]
                st.session_state.df_master.at[idx, 'appuntamento'] = pd.NaT if rm else datetime.combine(ad, at)
                if save_to_gsheets(st.session_state.df_master):
                    st.success("Anagrafica aggiornata!"); st.rerun()
        
        with st.expander("🗑️ AREA PERICOLO"):
            if st.checkbox("Confermo eliminazione definitiva") and st.button("❌ ELIMINA CLIENTE ORA"):
                st.session_state.df_master = st.session_state.df_master.drop(idx)
                st.session_state.cliente_selezionato = None
                save_to_gsheets(st.session_state.df_master)
                st.rerun()
    else:
        st.info("Seleziona un cliente per visualizzare i dettagli.")

# --- TAB: NUOVO CLIENTE ---
elif st.session_state.active_tab == "➕ Nuovo Cliente":
    st.header("➕ Nuovo Cliente")
    if st.button("🎯 GPS"):
        pos = streamlit_js_eval(js_expressions='navigator.geolocation.getCurrentPosition((p)=>{return p.coords;})', target_id='gps_n')
        if pos: st.session_state.new_coords = (pos['latitude'], pos['longitude'])
    
    with st.form("new_cl"):
        c1, c2 = st.columns(2)
        nn = c1.text_input("Ragione Sociale *")
        nf = c1.number_input("Frequenza (gg)", value=30)
        ut = c2.text_input("Telefono")
        uc = c2.text_input("Cellulare")
        um = c2.text_input("Email")
        st.divider()
        vi = st.text_input("Indirizzo")
        cr = st.columns(3)
        cap = cr[0].text_input("CAP")
        cit = cr[1].text_input("Città *")
        pro = cr[2].text_input("Prov")
        
        if st.form_submit_button("✅ REGISTRA CLIENTE"):
            if nn and cit:
                ind = f"{vi}, {cap} {cit} {pro}".strip(", ")
                lat, lon = st.session_state.new_coords if 'new_coords' in st.session_state else (None, None)
                if not lat:
                    with st.spinner("Ricerca posizione..."):
                        lat, lon = get_coords(ind) or get_coords(cit) or (None, None)
                
                if lat:
                    nuovo = {
                        'nome cliente': nn, 'indirizzo': ind, 'visitare': 'SI', 
                        'frequenza (giorni)': nf, 'latitude': lat, 'longitude': lon, 
                        'ultima visita': pd.Timestamp('2000-01-01'), 'appuntamento': pd.NaT,
                        'telefono': ut, 'cellulare': uc, 'mail': um
                    }
                    st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([nuovo])], ignore_index=True)
                    if save_to_gsheets(st.session_state.df_master):
                        st.success("Cliente salvato!"); st.rerun()
                else:
                    st.error("Posizione non trovata. Controlla la città.")

# --- TAB: PARAMETRI ---
elif st.session_state.active_tab == "⚙️ Parametri":
    st.header("⚙️ Configurazione")
    
    # Export Excel
    def to_excel(df):
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Clienti')
        return out.getvalue()
    
    st.download_button("📥 Scarica Database Excel", data=to_excel(st.session_state.df_master), file_name="crm_giro.xlsx")
    
    st.divider()
    if st.button("🎯 IMPOSTA GPS COME BASE"):
        gps = streamlit_js_eval(js_expressions='navigator.geolocation.getCurrentPosition((p)=>{return p.coords;})', target_id='gps_p')
        if gps:
            save_config_cloud("GPS", gps['latitude'], gps['longitude'])
            st.rerun()
            
    st.divider()
    c1, c2 = st.columns(2)
    st.session_state.h_inizio = c1.time_input("Inizio Lavoro", st.session_state.h_inizio)
    st.session_state.h_fine = c2.time_input("Fine Lavoro", st.session_state.h_fine)
    st.session_state.durata_v = st.slider("Minuti per visita", 15, 120, st.session_state.durata_v)
    
    if st.button("🔄 Forza Ricarica Cloud"):
        st.cache_data.clear()
        st.rerun()

# --- TAB: AGENDA ---
elif st.session_state.active_tab == "📅 Agenda":
    agenda, lun_base_c, etichette = calcola_piano()
    dt_l = lun_base + timedelta(weeks=st.session_state.current_week_index)
    
    col_p, col_t, col_n = st.columns([1, 2, 1])
    if col_p.button("⬅️", disabled=(st.session_state.current_week_index == 0)):
        st.session_state.current_week_index -= 1
        st.rerun()
        
    col_t.markdown(f"<h3 style='text-align: center;'>{etichette[st.session_state.current_week_index]}<br><small>dal {dt_l.strftime('%d/%m')} al {(dt_l + timedelta(days=4)).strftime('%d/%m')}</small></h3>", unsafe_allow_html=True)
    
    if col_n.button("➡️", disabled=(st.session_state.current_week_index == 10)):
        st.session_state.current_week_index += 1
        st.rerun()
        
    st.divider()
    cols = st.columns(5)
    g_n = ["Lun", "Mar", "Mer", "Gio", "Ven"]
    for i, g in enumerate(g_n):
        with cols[i]:
            st.subheader(f"{g} {(dt_l + timedelta(days=i)).day}")
            for t in agenda[st.session_state.current_week_index][i]:
                with st.container(border=True):
                    st.caption(f"🕒 {t['ora_arrivo']}")
                    if st.button(t['nome cliente'], key=f"ag_{st.session_state.current_week_index}_{i}_{t['nome cliente']}", use_container_width=True):
                        st.session_state.cliente_selezionato = t['nome cliente']
                        st.session_state.active_tab = "👤 Anagrafica"
                        st.rerun()
