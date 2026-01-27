import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from geopy.geocoders import Nominatim
import io
import time as time_module  # Importa time con alias per evitare conflitti
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
        calcola_piano_cached.clear()
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
    """Geocoding: da indirizzo a coordinate"""
    try:
        geolocator = Nominatim(user_agent="giro_visite_agente_v27", timeout=10)
        location = geolocator.geocode(f"{address}, Italia")
        if location:
            return (location.latitude, location.longitude)
        st.warning(f"⚠️ Indirizzo non trovato: {address}")
        return None
    except Exception as e:
        st.error(f"❌ Errore geocoding: {str(e)}")
        return None

def reverse_geocode(lat, lon):
    """Reverse geocoding: da coordinate a indirizzo"""
    try:
        geolocator = Nominatim(user_agent="giro_visite_agente_v27", timeout=10)
        location = geolocator.reverse(f"{lat}, {lon}", language='it')
        if location and location.raw.get('address'):
            addr = location.raw['address']
            return {
                'via': f"{addr.get('road', '')} {addr.get('house_number', '')}".strip(),
                'cap': addr.get('postcode', ''),
                'citta': addr.get('city') or addr.get('town') or addr.get('village', ''),
                'provincia': addr.get('state', ''),
                'indirizzo_completo': location.address
            }
        return None
    except Exception as e:
        st.error(f"❌ Errore reverse geocoding: {str(e)}")
        return None

@st.cache_data(ttl=600) 
def fetch_data():
    try:
        df = conn.read(spreadsheet=URL_FOGLIO)
        df.columns = df.columns.str.strip().str.lower()
        colonne = ['contatto', 'referente', 'posizione referente', 'mail', 'telefono', 'cellulare', 'note', 'storico report', 'visitare', 'indirizzo', 'cap', 'provincia', 'ultima visita', 'frequenza (giorni)', 'nome cliente', 'latitude', 'longitude', 'appuntamento']
        for col in colonne:
            if col not in df.columns:
                df[col] = ""
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

# --- FUNZIONE GPS CORRETTA ---
def render_gps_button(button_id):
    """Componente GPS che comunica correttamente con Streamlit"""
    html_code = f"""
    <div id="gps-container-{button_id}" style="width:100%;">
        <button onclick="getLocation_{button_id}()" 
                style="padding:12px 24px; background:#FF4B4B; color:white; border:none; 
                       border-radius:8px; cursor:pointer; font-size:16px; width:100%; 
                       font-weight:600; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            🎯 Usa GPS Attuale
        </button>
        <div id="status-{button_id}" style="margin-top:12px; font-size:14px; padding:8px; 
                                            border-radius:4px; text-align:center;"></div>
    </div>
    
    <script>
    function getLocation_{button_id}() {{
        const status = document.getElementById('status-{button_id}');
        
        if (!navigator.geolocation) {{
            status.innerHTML = '❌ Geolocalizzazione non supportata dal browser';
            status.style.backgroundColor = '#ffebee';
            status.style.color = '#c62828';
            return;
        }}
        
        status.innerHTML = '🔄 Acquisizione posizione GPS in corso...';
        status.style.backgroundColor = '#fff3e0';
        status.style.color = '#e65100';
        
        navigator.geolocation.getCurrentPosition(
            function(position) {{
                const lat = position.coords.latitude;
                const lon = position.coords.longitude;
                const accuracy = position.coords.accuracy;
                
                status.innerHTML = '✅ GPS acquisito: ' + lat.toFixed(6) + ', ' + lon.toFixed(6) + 
                                   '<br>Precisione: ±' + Math.round(accuracy) + ' metri';
                status.style.backgroundColor = '#e8f5e9';
                status.style.color = '#2e7d32';
                
                // Invia i dati a Streamlit usando postMessage
                const data = {{
                    latitude: lat,
                    longitude: lon,
                    accuracy: accuracy,
                    timestamp: new Date().getTime()
                }};
                
                // Prova diversi metodi di comunicazione
                window.parent.postMessage({{
                    isStreamlitMessage: true,
                    type: 'streamlit:setComponentValue',
                    data: data
                }}, '*');
                
                // Fallback: salva in sessionStorage
                sessionStorage.setItem('gps_data_{button_id}', JSON.stringify(data));
                
                console.log('GPS data sent:', data);
            }},
            function(error) {{
                let errorMsg = '';
                switch(error.code) {{
                    case error.PERMISSION_DENIED:
                        errorMsg = '❌ Permesso negato.<br>Autorizza l\\'accesso alla posizione nelle impostazioni del browser.';
                        break;
                    case error.POSITION_UNAVAILABLE:
                        errorMsg = '❌ Posizione non disponibile.<br>Verifica di essere all\\'aperto o vicino a una finestra.';
                        break;
                    case error.TIMEOUT:
                        errorMsg = '❌ Timeout della richiesta.<br>Riprova tra qualche secondo.';
                        break;
                    default:
                        errorMsg = '❌ Errore sconosciuto: ' + error.message;
                }}
                status.innerHTML = errorMsg;
                status.style.backgroundColor = '#ffebee';
                status.style.color = '#c62828';
                console.error('GPS error:', error);
            }},
            {{
                enableHighAccuracy: true,
                timeout: 20000,
                maximumAge: 0
            }}
        );
    }}
    
    // Auto-check sessionStorage al caricamento
    window.addEventListener('load', function() {{
        const savedData = sessionStorage.getItem('gps_data_{button_id}');
        if (savedData) {{
            const data = JSON.parse(savedData);
            const status = document.getElementById('status-{button_id}');
            status.innerHTML = '✅ Dati GPS salvati: ' + data.latitude.toFixed(6) + ', ' + data.longitude.toFixed(6);
            status.style.backgroundColor = '#e8f5e9';
            status.style.color = '#2e7d32';
        }}
    }});
    </script>
    """
    
    result = st.components.v1.html(html_code, height=130)
    
    # Prova a leggere da sessionStorage come fallback
    if result is None:
        # Aggiungi un piccolo script per recuperare i dati
        check_script = f"""
        <script>
        const data = sessionStorage.getItem('gps_data_{button_id}');
        if (data) {{
            window.parent.postMessage({{
                isStreamlitMessage: true,
                type: 'streamlit:setComponentValue',
                data: JSON.parse(data)
            }}, '*');
        }}
        </script>
        """
        st.components.v1.html(check_script, height=0)
    
    return result

# --- 3. STATO DELL'APP ---
if 'active_tab' not in st.session_state: 
    st.session_state.active_tab = "🚀 Giro Oggi"
if 'cliente_selezionato' not in st.session_state: 
    st.session_state.cliente_selezionato = None
if 'df_master' not in st.session_state: 
    st.session_state.df_master = fetch_data()
if 'current_week_index' not in st.session_state: 
    st.session_state.current_week_index = 2
if 'last_map_click' not in st.session_state: 
    st.session_state.last_map_click = None
if 'esclusi_oggi' not in st.session_state: 
    st.session_state.esclusi_oggi = []
if 'show_quick_report' not in st.session_state: 
    st.session_state.show_quick_report = False

# Stato GPS
if 'new_coords' not in st.session_state:
    st.session_state.new_coords = None
if 'gps_address' not in st.session_state:
    st.session_state.gps_address = {}
if 'last_geocoded_coords' not in st.session_state:
    st.session_state.last_geocoded_coords = None

conf_cloud = fetch_config()
if 'start_lat' not in st.session_state: 
    st.session_state.start_lat = conf_cloud['lat']
if 'start_lon' not in st.session_state: 
    st.session_state.start_lon = conf_cloud['lon']
if 'start_city' not in st.session_state: 
    st.session_state.start_city = conf_cloud['city']

if 'attiva_ferie' not in st.session_state: 
    st.session_state.attiva_ferie = False
if 'ferie' not in st.session_state: 
    st.session_state.ferie = []

for key, val in {'h_inizio': time(9, 0), 'h_fine': time(18, 0), 'pausa_inizio': time(13, 0), 'pausa_fine': time(14, 0), 'durata_v': 45}.items():
    if key not in st.session_state: 
        st.session_state[key] = val

# --- 4. LOGICA CALCOLO GIRO ---
@st.cache_data(ttl=300)
def calcola_piano_cached(_df, ferie_attive, ferie_date, esclusi, h_inizio, h_fine, pausa_inizio, pausa_fine, durata_v, start_lat, start_lon, data_hash):
    df_sim = _df.copy()
    oggi_dt = ora_italiana
    lun_corrente = oggi_dt - timedelta(days=oggi_dt.weekday())
    lun_ref = lun_corrente - timedelta(weeks=2)
    agenda_risultato = {i: {g: [] for g in range(5)} for i in range(11)}
    etichette = [f"Passata (-{2-i})" if i < 2 else ("Settimana Corrente" if i == 2 else f"Futura (+{i-2})") for i in range(11)]
    
    for s in range(11):
        for g in range(5):
            dt_c = (lun_ref + timedelta(weeks=s, days=g)).date()
            if ferie_attive and ferie_date and len(ferie_date) == 2:
                try:
                    f_start = ferie_date[0] if hasattr(ferie_date[0], 'year') else ferie_date[0]
                    f_end = ferie_date[1] if hasattr(ferie_date[1], 'year') else ferie_date[1]
                    if f_start <= dt_c <= f_end:
                        continue
                except:
                    pass

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
                        appuntamenti = appuntamenti.iloc[1:]
                        continue
                if not urg:
                    break
                px = min(urg, key=lambda x: haversine(p_s[0], p_s[1], x['latitude'], x['longitude']))
                dist = haversine(p_s[0], p_s[1], px['latitude'], px['longitude'])
                arr = o_s + timedelta(minutes=(dist / 50) * 60)
                if arr >= datetime.combine(dt_c, pausa_inizio) and arr < datetime.combine(dt_c, pausa_fine):
                    o_s = datetime.combine(dt_c, pausa_fine)
                    continue
                fine_v = arr + timedelta(minutes=durata_v)
                limite = appuntamenti.iloc[0]['appuntamento'].to_pydatetime() if not appuntamenti.empty else datetime.combine(dt_c, h_fine)
                if fine_v <= limite:
                    px['ora_arrivo'] = arr.strftime("%H:%M")
                    px['tipo_tappa'] = "🚗 Giro"
                    agenda_risultato[s][g].append(px)
                    df_sim.loc[df_sim['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(dt_c)
                    o_s, p_s = fine_v, (px['latitude'], px['longitude'])
                    urg.remove(px)
                else:
                    break
    return agenda_risultato, lun_ref, etichette

def calcola_piano():
    """Wrapper per calcola_piano_cached - include hash per invalidare cache"""
    # Crea hash basato sul numero di appuntamenti (NON usare .sum() con datetime!)
    num_appuntamenti = st.session_state.df_master['appuntamento'].notna().sum()
    num_clienti = len(st.session_state.df_master)
    data_hash = hash(f"{num_clienti}_{num_appuntamenti}")
    
    return calcola_piano_cached(
        st.session_state.df_master, 
        st.session_state.attiva_ferie, 
        st.session_state.ferie, 
        st.session_state.esclusi_oggi, 
        st.session_state.h_inizio, 
        st.session_state.h_fine, 
        st.session_state.pausa_inizio, 
        st.session_state.pausa_fine, 
        st.session_state.durata_v, 
        st.session_state.start_lat, 
        st.session_state.start_lon,
        data_hash
    )

# --- 5. INTERFACCIA ---
nav = st.columns(6)
menu = ["🚀 Giro Oggi", "📅 Agenda", "🗺️ Mappa Clienti", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"]
for i, m in enumerate(menu):
    if nav[i].button(m, key=f"nav_{m}", use_container_width=True, type="primary" if st.session_state.active_tab == m else "secondary"):
        st.session_state.active_tab = m
        st.rerun()

st.divider()
agenda, lun_base, etichette_settimane = calcola_piano()

# --- TAB: GIRO OGGI ---
if st.session_state.active_tab == "🚀 Giro Oggi":
    col_header, col_refresh = st.columns([5, 1])
    with col_header:
        st.header(f"📍 Giro di Oggi ({ora_italiana.strftime('%d/%m/%Y')})")
    with col_refresh:
        if st.button("🔄", use_container_width=True, help="Aggiorna giro", key="refresh_giro_btn"):
            calcola_piano_cached.clear()
            st.rerun()
    
    idx_g = ora_italiana.weekday()
    
    if idx_g < 5:
        # Mostra clienti esclusi se presenti
        if st.session_state.esclusi_oggi:
            with st.expander(f"🚫 Clienti esclusi oggi ({len(st.session_state.esclusi_oggi)})", expanded=False):
                for cliente_escluso in st.session_state.esclusi_oggi:
                    col_e1, col_e2 = st.columns([4, 1])
                    col_e1.write(cliente_escluso)
                    if col_e2.button("♻️", key=f"restore_{cliente_escluso}", help="Ripristina"):
                        st.session_state.esclusi_oggi.remove(cliente_escluso)
                        calcola_piano_cached.clear()
                        st.rerun()
        
        # Recupera le tappe di oggi
        tappe_oggi = agenda[2][idx_g]  # Settimana corrente (indice 2), giorno corrente
        
        if tappe_oggi:
            # Statistiche rapide
            num_appuntamenti = sum(1 for t in tappe_oggi if t.get('tipo_tappa') == "📌 APPUNTAMENTO")
            num_giro = len(tappe_oggi) - num_appuntamenti
            
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            col_stat1.metric("📊 Visite Totali", len(tappe_oggi))
            col_stat2.metric("📌 Appuntamenti", num_appuntamenti)
            col_stat3.metric("🚗 Visite Giro", num_giro)
            
            st.divider()
            
            # Mappa del giro
            st.subheader("🗺️ Percorso di Oggi")
            
            # Crea mappa centrata sul punto di partenza
            m = folium.Map(
                location=[st.session_state.start_lat, st.session_state.start_lon], 
                zoom_start=10
            )
            
            # Aggiungi marker punto di partenza
            folium.Marker(
                location=[st.session_state.start_lat, st.session_state.start_lon],
                popup="🏠 Punto di Partenza",
                icon=folium.Icon(color="blue", icon="home")
            ).add_to(m)
            
            # Coordinate per la polyline del percorso
            route_coords = [(st.session_state.start_lat, st.session_state.start_lon)]
            
            # Aggiungi marker per ogni tappa
            for i, tappa in enumerate(tappe_oggi, 1):
                color = "red" if tappa.get('tipo_tappa') == "📌 APPUNTAMENTO" else "green"
                icon_symbol = "star" if tappa.get('tipo_tappa') == "📌 APPUNTAMENTO" else "user"
                
                popup_html = f"""
                <b>{i}. {tappa['nome cliente']}</b><br>
                ⏰ {tappa['ora_arrivo']}<br>
                {tappa.get('tipo_tappa', '')}<br>
                📍 {tappa.get('indirizzo', 'N/A')}
                """
                
                folium.Marker(
                    location=[tappa['latitude'], tappa['longitude']],
                    popup=folium.Popup(popup_html, max_width=300),
                    icon=folium.Icon(color=color, icon=icon_symbol)
                ).add_to(m)
                
                # Aggiungi alla route
                route_coords.append((tappa['latitude'], tappa['longitude']))
                
                # Aggiungi numero tappa
                folium.Marker(
                    location=[tappa['latitude'], tappa['longitude']],
                    icon=folium.DivIcon(
                        html=f'<div style="font-size: 12px; font-weight: bold; color: white; background: {"#c0392b" if color == "red" else "#27ae60"}; border-radius: 50%; width: 24px; height: 24px; text-align: center; line-height: 24px;">{i}</div>'
                    )
                ).add_to(m)
            
            # Disegna percorso
            if len(route_coords) > 1:
                folium.PolyLine(
                    route_coords,
                    weight=3,
                    color='#3498db',
                    opacity=0.8
                ).add_to(m)
            
            # Fit bounds per mostrare tutti i marker
            if route_coords:
                m.fit_bounds(route_coords)
            
            st_folium(m, width="100%", height=400, key="map_giro_oggi")
            
            st.divider()
            
            # Lista tappe dettagliata
            st.subheader("📋 Dettaglio Tappe")
            
            for i, tappa in enumerate(tappe_oggi, 1):
                with st.container(border=True):
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        tipo_icon = "📌" if tappa.get('tipo_tappa') == "📌 APPUNTAMENTO" else "🚗"
                        st.markdown(f"### {i}. {tipo_icon} {tappa['nome cliente']}")
                        st.caption(f"⏰ Arrivo previsto: **{tappa['ora_arrivo']}**")
                        if tappa.get('indirizzo'):
                            st.caption(f"📍 {tappa['indirizzo']}")
                    
                    with col2:
                        # Pulsanti azione
                        nav_url = f"https://www.google.com/maps/dir/?api=1&destination={tappa['latitude']},{tappa['longitude']}"
                        st.link_button("🚗 NAVIGA", nav_url, use_container_width=True)
                        
                        if tappa.get('cellulare'):
                            st.link_button(f"📱 {tappa['cellulare']}", f"tel:{tappa['cellulare']}", use_container_width=True)
                    
                    with col3:
                        # Pulsante per escludere dal giro
                        if st.button("❌", key=f"escludi_{tappa['nome cliente']}", help="Escludi dal giro di oggi"):
                            st.session_state.esclusi_oggi.append(tappa['nome cliente'])
                            calcola_piano_cached.clear()
                            st.rerun()
                        
                        # Pulsante per aprire scheda cliente
                        if st.button("👤", key=f"scheda_{tappa['nome cliente']}", help="Apri scheda cliente"):
                            st.session_state.cliente_selezionato = tappa['nome cliente']
                            st.session_state.active_tab = "👤 Anagrafica"
                            st.rerun()
            
            st.divider()
            
            # Navigazione completa
            st.subheader("🧭 Navigazione Completa")
            
            # Costruisci URL per navigazione multi-tappa
            if tappe_oggi:
                waypoints = "|".join([f"{t['latitude']},{t['longitude']}" for t in tappe_oggi[:-1]]) if len(tappe_oggi) > 1 else ""
                destination = f"{tappe_oggi[-1]['latitude']},{tappe_oggi[-1]['longitude']}"
                origin = f"{st.session_state.start_lat},{st.session_state.start_lon}"
                
                if waypoints:
                    nav_completa_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}&waypoints={waypoints}&travelmode=driving"
                else:
                    nav_completa_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}&travelmode=driving"
                
                st.link_button("🗺️ AVVIA NAVIGAZIONE COMPLETA (Google Maps)", nav_completa_url, use_container_width=True, type="primary")
        
        else:
            st.info("📭 Nessuna visita pianificata per oggi.")
            st.markdown("""
            **Possibili motivi:**
            - Tutti i clienti sono stati visitati di recente
            - Nessun cliente ha raggiunto la frequenza di visita
            - Hai escluso tutti i clienti dal giro
            """)
            
            if st.session_state.esclusi_oggi:
                if st.button("♻️ Ripristina tutti i clienti esclusi", use_container_width=True):
                    st.session_state.esclusi_oggi = []
                    calcola_piano_cached.clear()
                    st.rerun()
    
    else:
        # Weekend
        st.warning("🏖️ Oggi è weekend! Il giro visite è attivo solo dal Lunedì al Venerdì.")
        st.info("Consulta la sezione **📅 Agenda** per vedere le visite pianificate per la prossima settimana.")

# --- TAB: MAPPA ---
elif st.session_state.active_tab == "🗺️ Mappa Clienti":
    st.header("🗺️ Mappa Interattiva Clienti")
    filtro_tipo = st.radio("Filtro:", ["Tutti", "Visitati", "Mai Visitati"], horizontal=True, key="f_map_v7")
    df_m = st.session_state.df_master.copy()
    if filtro_tipo == "Visitati":
        df_m = df_m[df_m['ultima visita'] > pd.Timestamp('2000-01-01')]
    elif filtro_tipo == "Mai Visitati":
        df_m = df_m[df_m['ultima visita'] <= pd.Timestamp('2000-01-01')]
    
    if not df_m.empty:
        m = folium.Map(location=[df_m['latitude'].mean(), df_m['longitude'].mean()], zoom_start=8)
        for _, row in df_m.iterrows():
            c = "green" if row['visitare'] == "SI" else "red"
            folium.Marker(
                location=[row['latitude'], row['longitude']], 
                popup=row['nome cliente'], 
                icon=folium.Icon(color=c, icon="user")
            ).add_to(m)
        output = st_folium(m, width="100%", height=600, key="main_map_v7")
        cl = output.get("last_object_clicked_popup")
        if cl:
            if st.session_state.last_map_click == cl:
                st.session_state.cliente_selezionato = cl
                st.session_state.active_tab = "👤 Anagrafica"
                st.rerun()
            else:
                st.session_state.last_map_click = cl
                st.toast(f"👆 Tocca ancora: {cl}")
    else:
        st.info("Nessun cliente trovato con i filtri selezionati.")

# --- TAB: ANAGRAFICA ---
elif st.session_state.active_tab == "👤 Anagrafica":
    st.header("👤 Scheda Anagrafica")
    nomi_reali = sorted(st.session_state.df_master['nome cliente'].unique())
    opzioni = [""] + nomi_reali
    idx_def = opzioni.index(st.session_state.cliente_selezionato) if st.session_state.cliente_selezionato in opzioni else 0
    scelto = st.selectbox("Cerca cliente:", opzioni, index=idx_def, key="sel_ana_v7")
    
    if scelto != "":
        st.session_state.cliente_selezionato = scelto
        idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
        d = st.session_state.df_master.loc[idx]
        ca = st.columns(4)
        ca[0].link_button("🚗 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={d['latitude']},{d['longitude']}")
        if d.get('cellulare'):
            ca[1].link_button("📱 CHIAMA", f"tel:{d['cellulare']}")
        if d.get('mail'):
            ca[2].link_button("📧 MAIL", f"mailto:{d['mail']}")

        st.divider()
        if pd.notnull(d['ultima visita']) and d['ultima visita'] > pd.Timestamp('2000-01-01'):
            prox_v = d['ultima visita'] + timedelta(days=int(d['frequenza (giorni)']))
            gm = (prox_v.date() - ora_italiana.date()).days
            if gm > 0:
                st.success(f"📅 **Prossima visita:** {prox_v.strftime('%d/%m/%Y')} (tra {gm} gg)")
            elif gm == 0:
                st.warning("📅 **Prossima visita:** OGGI!")
            else:
                st.error(f"📅 **Visita SCADUTA:** {prox_v.strftime('%d/%m/%Y')} ({abs(gm)} gg fa)")
        else:
            st.info("📅 **Stato:** Mai visitato.")

        st.divider()
        with st.container(border=True):
            st.subheader("🏁 Azione Rapida Fine Visita")
            if st.button("✅ APPENA VISITATO", type="primary", use_container_width=True, key="btn_visit_v7"):
                st.session_state.show_quick_report = True
            if st.session_state.show_quick_report:
                cr1, cr2 = st.columns([1, 2])
                dv = cr1.date_input("Data visita:", value=ora_italiana.date(), key="dv_in_v7")
                rt = st.text_area("Report incontri:", placeholder="Cosa è emerso?", key="rt_in_v7")
                c_save, c_cancel = st.columns(2)
                if c_save.button("💾 SALVA", key="save_rep_v7", use_container_width=True):
                    nuovo = f"[{dv.strftime('%d/%m/%Y')}] {rt}"
                    vecchio = str(st.session_state.df_master.at[idx, 'storico report'])
                    st.session_state.df_master.at[idx, 'storico report'] = nuovo + "\n\n" + vecchio if vecchio != "nan" and vecchio.strip() != "" else nuovo
                    st.session_state.df_master.at[idx, 'ultima visita'] = pd.to_datetime(dv)
                    if save_to_gsheets(st.session_state.df_master):
                        st.session_state.show_quick_report = False
                        st.success("✅ Salvato!")
                        st.rerun()
                if c_cancel.button("❌ Annulla", key="can_rep_v7", use_container_width=True):
                    st.session_state.show_quick_report = False
                    st.rerun()

        st.divider()
        with st.form("edit_anag_v7"):
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
            uc = c2.text_input("Cellulare", d.get('cellulare', ''))
            um = c2.text_input("Email", d.get('mail', ''))
            st.divider()
            app_d = c1.date_input("Appuntamento", value=d['appuntamento'].date() if pd.notnull(d['appuntamento']) else None)
            app_t = c1.time_input("Ora", value=d['appuntamento'].time() if pd.notnull(d['appuntamento']) else time(10, 0))
            rim = c2.checkbox("Rimuovi appuntamento")
            uno = st.text_area("Note fisse", d.get('note', ''), height=100)
            ust = st.text_area("Storico Report", d.get('storico report', ''), height=200)
            if st.form_submit_button("💾 Salva Modifiche", use_container_width=True):
                st.session_state.df_master.loc[idx, ['nome cliente', 'indirizzo', 'cap', 'provincia', 'contatto', 'frequenza (giorni)', 'visitare', 'telefono', 'cellulare', 'mail', 'note', 'storico report']] = [un, ui, u_cap, u_prov, uco, uf, scv, ut, uc, um, uno, ust]
                if rim:
                    st.session_state.df_master.at[idx, 'appuntamento'] = pd.NaT
                elif app_d:
                    st.session_state.df_master.at[idx, 'appuntamento'] = datetime.combine(app_d, app_t)
                if save_to_gsheets(st.session_state.df_master):
                    st.success("✅ Salvato!")
                    st.rerun()

        st.divider()
        with st.expander("🗑️ ELIMINA CLIENTE"):
            st.warning(f"⚠️ Eliminazione di **{scelto}** è DEFINITIVA.")
            conferma_del = st.checkbox("Confermo eliminazione", key="check_del_v7")
            if conferma_del:
                if st.button("❌ ELIMINA DEFINITIVAMENTE", type="primary", use_container_width=True, key="btn_del_v7"):
                    st.session_state.df_master = st.session_state.df_master.drop(idx)
                    if save_to_gsheets(st.session_state.df_master):
                        st.session_state.cliente_selezionato = None
                        st.success("✅ Cliente eliminato.")
                        st.rerun()

# --- TAB: NUOVO CLIENTE ---
elif st.session_state.active_tab == "➕ Nuovo Cliente":
    st.header("➕ Registrazione Nuovo Cliente")
    
    # --- SEZIONE GPS ---
    st.subheader("📍 Acquisizione Posizione GPS")
    
    col_gps1, col_gps2 = st.columns([3, 1])
    
    with col_gps1:
        gps_result = render_gps_button("new_client_gps")
    
    # Processa risultato GPS
    if gps_result:
        if isinstance(gps_result, dict) and 'latitude' in gps_result and 'longitude' in gps_result:
            # Salva coordinate
            st.session_state.new_coords = (gps_result['latitude'], gps_result['longitude'])
            
            # Controlla se non abbiamo già fatto il reverse geocoding per queste coordinate
            coords_key = f"{gps_result['latitude']:.6f}_{gps_result['longitude']:.6f}"
            
            if st.session_state.get('last_geocoded_coords') != coords_key:
                st.session_state.last_geocoded_coords = coords_key
                
                # Fai reverse geocoding
                with st.spinner("🔍 Conversione coordinate in indirizzo..."):
                    addr_info = reverse_geocode(gps_result['latitude'], gps_result['longitude'])
                    
                    if addr_info:
                        st.session_state.gps_address = addr_info
                        st.success(f"✅ Indirizzo trovato: {addr_info['indirizzo_completo']}")
                    else:
                        st.session_state.gps_address = {}
                        st.warning("⚠️ Coordinate GPS acquisite ma indirizzo non trovato. Compila manualmente.")
    
    # Mostra coordinate salvate
    if st.session_state.get('new_coords'):
        with col_gps2:
            st.metric(
                "📍 Coordinate", 
                f"{st.session_state.new_coords[0]:.5f}\n{st.session_state.new_coords[1]:.5f}",
                help="Latitudine e Longitudine acquisite"
            )
            
            if st.button("🗑️ Rimuovi GPS", use_container_width=True, key="clear_gps_nc"):
                st.session_state.new_coords = None
                st.session_state.gps_address = {}
                st.session_state.last_geocoded_coords = None
                st.rerun()
    
    st.divider()
    
    # --- FORM NUOVO CLIENTE ---
    with st.form("new_client_form_v8", clear_on_submit=False):
        st.subheader("📝 Informazioni Cliente")
        
        c1, c2 = st.columns(2)
        
        # Dati principali
        nome_cliente = c1.text_input("Ragione Sociale *", key="nc_nome_v8")
        freq_visite = c1.number_input("Frequenza Visite (giorni)", min_value=1, value=30, key="nc_freq_v8")
        contatti_ref = c1.text_input("Referente / Contatti", key="nc_ref_v8")
        
        telefono = c2.text_input("Telefono", key="nc_tel_v8")
        cellulare = c2.text_input("Cellulare", key="nc_cell_v8")
        email = c2.text_input("Email", key="nc_email_v8")
        
        st.divider()
        st.subheader("📍 Indirizzo")
        
        # Pre-compila con dati GPS se disponibili
        gps_addr = st.session_state.get('gps_address', {})
        
        if gps_addr:
            st.info("💡 Campi compilati automaticamente dal GPS. Verifica e correggi se necessario.")
        
        via_civico = st.text_input(
            "Via e Numero Civico", 
            value=gps_addr.get('via', ''),
            key="nc_via_v8"
        )
        
        addr_cols = st.columns([1, 2, 1])
        cap = addr_cols[0].text_input(
            "CAP", 
            value=gps_addr.get('cap', ''),
            key="nc_cap_v8"
        )
        citta = addr_cols[1].text_input(
            "Città *", 
            value=gps_addr.get('citta', ''),
            key="nc_citta_v8"
        )
        provincia = addr_cols[2].text_input(
            "Provincia", 
            value=gps_addr.get('provincia', ''),
            max_chars=2,
            key="nc_prov_v8"
        )
        
        st.divider()
        note_iniziali = st.text_area(
            "Note Iniziali (opzionale)", 
            placeholder="Aggiungi eventuali note sul cliente...",
            height=100,
            key="nc_note_v8"
        )
        
        # Bottoni azione
        col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 1])
        
        btn_salva = col_btn1.form_submit_button(
            "✅ CREA E SALVA CLIENTE", 
            use_container_width=True, 
            type="primary"
        )
        
        btn_reset = col_btn2.form_submit_button(
            "🔄 Svuota Form", 
            use_container_width=True
        )
        
        # Gestione submit
        if btn_reset:
            st.session_state.new_coords = None
            st.session_state.gps_address = {}
            st.session_state.last_geocoded_coords = None
            st.rerun()
        
        if btn_salva:
            # Validazione
            errori = []
            if not nome_cliente or nome_cliente.strip() == "":
                errori.append("❌ Inserisci la Ragione Sociale")
            if not citta or citta.strip() == "":
                errori.append("❌ Inserisci la Città")
            
            if errori:
                for err in errori:
                    st.error(err)
            else:
                # Determina coordinate
                coordinate_finale = None
                
                if st.session_state.get('new_coords'):
                    # Usa coordinate GPS
                    coordinate_finale = st.session_state.new_coords
                    st.info("📍 Usando coordinate da GPS")
                else:
                    # Geocoding da indirizzo
                    indirizzo_completo = f"{via_civico}, {cap} {citta} {provincia}".strip()
                    
                    with st.spinner("🔍 Ricerca coordinate da indirizzo..."):
                        coordinate_finale = get_coords(indirizzo_completo)
                        
                        if not coordinate_finale:
                            # Prova solo con la città
                            coordinate_finale = get_coords(citta)
                
                # Salva cliente
                if coordinate_finale:
                    nuovo_cliente = {
                        'nome cliente': nome_cliente.strip(),
                        'indirizzo': via_civico.strip(),
                        'cap': cap.strip(),
                        'provincia': provincia.strip().upper(),
                        'contatto': contatti_ref.strip(),
                        'visitare': 'SI',
                        'frequenza (giorni)': freq_visite,
                        'latitude': coordinate_finale[0],
                        'longitude': coordinate_finale[1],
                        'ultima visita': pd.Timestamp('2000-01-01'),
                        'telefono': telefono.strip(),
                        'cellulare': cellulare.strip(),
                        'mail': email.strip(),
                        'note': note_iniziali.strip(),
                        'storico report': '',
                        'appuntamento': pd.NaT,
                        'referente': '',
                        'posizione referente': ''
                    }
                    
                    # Aggiungi al dataframe
                    st.session_state.df_master = pd.concat(
                        [st.session_state.df_master, pd.DataFrame([nuovo_cliente])], 
                        ignore_index=True
                    )
                    
                    # Salva su Google Sheets
                    if save_to_gsheets(st.session_state.df_master):
                        st.success(f"✅ Cliente **{nome_cliente}** creato con successo!")
                        
                        # Reset stato GPS
                        st.session_state.new_coords = None
                        st.session_state.gps_address = {}
                        st.session_state.last_geocoded_coords = None
                        st.session_state.cliente_selezionato = nome_cliente
                        
                        # Opzione per andare alla scheda
                        st.info("👉 Vai al tab 'Anagrafica' per vedere i dettagli del cliente")
                        
                        time_module.sleep(2)
                        st.rerun()
                    else:
                        st.error("❌ Errore durante il salvataggio su Google Sheets")
                else:
                    st.error("❌ Impossibile determinare le coordinate. Usa il GPS o verifica l'indirizzo inserito.")
    
    # Istruzioni
    st.divider()
    with st.expander("📖 Istruzioni d'uso", expanded=False):
        st.markdown("""
        ### 🎯 Metodo GPS (Consigliato se sei sul posto)
        1. Clicca il pulsante **"🎯 Usa GPS Attuale"**
        2. **Autorizza** il browser ad accedere alla posizione
        3. Attendi che appaia il messaggio di conferma verde
        4. I campi indirizzo verranno **compilati automaticamente**
        5. Verifica e correggi eventuali dati se necessario
        6. Compila gli altri campi obbligatori (Ragione Sociale)
        7. Clicca **"✅ CREA E SALVA CLIENTE"**
        
        ### ✍️ Metodo Manuale
        1. Compila **tutti i campi manualmente**
        2. Il sistema cercherà le coordinate dall'indirizzo inserito
        3. Clicca **"✅ CREA E SALVA CLIENTE"**
        
        ### ⚠️ Note Importanti
        - Il GPS funziona solo su **HTTPS** o **localhost**
        - La precisione dipende dal dispositivo (solitamente 5-50 metri)
        - Se sei all'interno di un edificio, avvicinati a una finestra
        - Puoi sempre modificare i dati auto-compilati dal GPS
        - I campi contrassegnati con * sono **obbligatori**
        
        ### 🔧 Risoluzione Problemi
        - **"Permesso negato"**: Autorizza la geolocalizzazione nelle impostazioni del browser
        - **"Timeout"**: Riprova tra qualche secondo o spostati all'aperto
        - **"Posizione non disponibile"**: Verifica che il GPS del dispositivo sia attivo
        """)

# --- TAB: PARAMETRI ---
elif st.session_state.active_tab == "⚙️ Parametri":
    st.header("⚙️ Configurazione")
    st.subheader("📍 Punto di Partenza")
    gps_base = render_gps_button("base_gps")
    if gps_base and isinstance(gps_base, dict) and 'latitude' in gps_base:
        if save_config_cloud("GPS", gps_base['latitude'], gps_base['longitude']): 
            st.success("✅ Base GPS aggiornata!")
            st.rerun()
    nc = st.text_input("Città base:", st.session_state.start_city, key="city_input_v7")
    if nc != st.session_state.start_city:
        co = get_coords(nc)
        if co and save_config_cloud(nc, co[0], co[1]): 
            st.rerun()
    
    st.divider()
    st.subheader("⏰ Orari e Tempi")
    c1, c2 = st.columns(2)
    st.session_state.h_inizio = c1.time_input("Inizio Lavoro", st.session_state.h_inizio)
    st.session_state.h_fine = c2.time_input("Fine Lavoro", st.session_state.h_fine)
    st.session_state.pausa_inizio = c1.time_input("Inizio Pausa", st.session_state.pausa_inizio)
    st.session_state.pausa_fine = c2.time_input("Fine Pausa", st.session_state.pausa_fine)
    st.session_state.durata_v = st.slider("Minuti per visita", 15, 120, st.session_state.durata_v)
    
    st.divider()
    st.subheader("🏖️ Filtro Ferie / Chiusura")
    st.session_state.attiva_ferie = st.checkbox("ATTIVA FILTRO FERIE", value=st.session_state.attiva_ferie)
    ferie_in = st.date_input("Periodo chiusura:", value=st.session_state.ferie if st.session_state.ferie else [], key="f_in_v7")
    
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
        use_container_width=True,
        key="export_excel_v7"
    )
    
    if col_exp2.button("🔄 Ricarica da Cloud", use_container_width=True, key="reload_cloud_v7"):
        st.cache_data.clear()
        st.session_state.df_master = fetch_data()
        st.success("✅ Dati ricaricati!")
        st.rerun()
    
    st.divider()
    with st.expander("ℹ️ Info Sistema"):
        st.write(f"**Clienti totali:** {len(st.session_state.df_master)}")
        st.write(f"**Clienti attivi:** {len(st.session_state.df_master[st.session_state.df_master['visitare'] == 'SI'])}")
        st.write(f"**Clienti mai visitati:** {len(st.session_state.df_master[st.session_state.df_master['ultima visita'] <= pd.Timestamp('2000-01-01')])}")
        st.write(f"**Ultima sincronizzazione:** {ora_italiana.strftime('%d/%m/%Y %H:%M')}")

# --- TAB: AGENDA ---
elif st.session_state.active_tab == "📅 Agenda":
    st.header("📅 Agenda Settimanale")
    
    data_lunedi = lun_base + timedelta(weeks=st.session_state.current_week_index)
    col_p, col_t, col_n = st.columns([1, 2, 1])
    
    if col_p.button("⬅️ Precedente", key="agg_p_v7", use_container_width=True):
        st.session_state.current_week_index -= 1
        st.rerun()
    
    col_t.markdown(f"<h3 style='text-align: center;'>📅 {etichette_settimane[st.session_state.current_week_index]}</h3>", unsafe_allow_html=True)
    
    if col_n.button("Successiva ➡️", key="agg_n_v7", use_container_width=True):
        st.session_state.current_week_index += 1
        st.rerun()
    
    data_dom = data_lunedi + timedelta(days=6)
    st.caption(f"Dal {data_lunedi.strftime('%d/%m/%Y')} al {data_dom.strftime('%d/%m/%Y')}")
    
    st.divider()
    
    cols = st.columns(5)
    g_nomi = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
    
    for i, g in enumerate(g_nomi):
        dt_g = data_lunedi + timedelta(days=i)
        
        with cols[i]:
            st.subheader(f"{g}")
            st.caption(f"{dt_g.strftime('%d/%m/%Y')}")
            
            tappe_giorno = agenda[st.session_state.current_week_index][i]
            
            if tappe_giorno:
                num_app = sum(1 for t in tappe_giorno if t.get('tipo_tappa') == "📌 APPUNTAMENTO")
                num_giro = len(tappe_giorno) - num_app
                
                if num_app > 0:
                    st.info(f"📌 {num_app} appuntament{'o' if num_app == 1 else 'i'}")
                if num_giro > 0:
                    st.success(f"🚗 {num_giro} visit{'a' if num_giro == 1 else 'e'}")
                
                st.divider()
                
                for t in tappe_giorno:
                    with st.container(border=True):
                        icona = "📌" if t.get('tipo_tappa') == "📌 APPUNTAMENTO" else "🚗"
                        st.caption(f"{icona} {t['ora_arrivo']}")
                        
                        if st.button(t['nome cliente'], key=f"ag_v7_{st.session_state.current_week_index}_{i}_{t['nome cliente']}", use_container_width=True):
                            st.session_state.cliente_selezionato = t['nome cliente']
                            st.session_state.active_tab = "👤 Anagrafica"
                            st.rerun()
                        
                        if t.get('indirizzo'):
                            st.caption(f"📍 {t['indirizzo'][:30]}...")
            else:
                st.info("📭 Nessuna visita")
    
    st.divider()
    st.subheader("📊 Statistiche Settimana")
    
    totale_visite = sum(len(agenda[st.session_state.current_week_index][g]) for g in range(5))
    totale_app = sum(sum(1 for t in agenda[st.session_state.current_week_index][g] if t.get('tipo_tappa') == "📌 APPUNTAMENTO") for g in range(5))
    totale_giro = totale_visite - totale_app
    
    stat_cols = st.columns(4)
    stat_cols[0].metric("📊 Visite Totali", totale_visite)
    stat_cols[1].metric("📌 Appuntamenti", totale_app)
    stat_cols[2].metric("🚗 Visite Giro", totale_giro)
    
    media_giorno = totale_visite / 5 if totale_visite > 0 else 0
    stat_cols[3].metric("📈 Media/Giorno", f"{media_giorno:.1f}")

# --- FOOTER ---
st.divider()
footer_cols = st.columns([2, 1])
footer_cols[0].caption("🚀 **Giro Visite CRM Pro** - Versione 2.8 Corretta")
footer_cols[1].caption(f"🕐 {ora_italiana.strftime('%H:%M:%S')}")
