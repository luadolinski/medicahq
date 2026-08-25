import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from datetime import datetime, timedelta
import random
import hashlib
import json
import google.generativeai as genai

# -------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# -------------------------------------------------------------
st.set_page_config(
    page_title="Médica HQ | Residencias & Revalida",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------------------
# CONFIGURACIÓN DE GEMINI API
# -------------------------------------------------------------
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")

model = None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # Probamos primero con el identificador estándar actual
        model = genai.GenerativeModel("gemini-1.5-flash")
    except Exception:
        try:
            model = genai.GenerativeModel("gemini-1.5-flash-latest")
        except Exception:
            model = None

# -------------------------------------------------------------
# BASE DE DATOS LOCAL (SQLite Persistente)
# -------------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect("medica_hq.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Tabla de Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            nombre TEXT
        )
    ''')
    
    # Tabla de Choices
    c.execute('''
        CREATE TABLE IF NOT EXISTS choices (
            id TEXT PRIMARY KEY,
            examen_origen TEXT,
            area TEXT,
            tema TEXT,
            incidencia TEXT,
            pregunta TEXT,
            opcion_a TEXT,
            opcion_b TEXT,
            opcion_c TEXT,
            opcion_d TEXT,
            correcta TEXT,
            justificacion TEXT,
            drive_link TEXT,
            next_review DATE,
            interval_days INTEGER,
            ease_factor REAL,
            repetitions INTEGER
        )
    ''')
    
    # Tabla de Historial / Errores
    c.execute('''
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            choice_id TEXT,
            fecha TIMESTAMP,
            respuesta_dada TEXT,
            es_correcta INTEGER,
            flag_duda INTEGER,
            motivo_error TEXT,
            regla_oro TEXT,
            FOREIGN KEY (choice_id) REFERENCES choices (id)
        )
    ''')
    
    # Migración automática de columna faltante
    try:
        c.execute("ALTER TABLE error_log ADD COLUMN username TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Crear usuario inicial por defecto
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users VALUES (?, ?, ?)", ("doctores", hash_password("medicos2026"), "Dra. Luana"))
        
    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------
# CONTROL DE SESIÓN
# -------------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None

def login_form():
    st.title("🩺 Médica HQ | Ingreso a la Plataforma")
    st.caption("Plataforma de Alto Rendimiento para Residencias de Argentina y Revalida de Brasil")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        u_input = st.text_input("Usuario", key="login_user")
        p_input = st.text_input("Contraseña", type="password", key="login_pass")
        
        if st.button("Iniciar Sesión", use_container_width=True):
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", (u_input.lower(), hash_password(p_input)))
            usr = c.fetchone()
            conn.close()
            
            if usr:
                st.session_state.authenticated = True
                st.session_state.current_user = usr["username"]
                st.session_state.user_name = usr["nombre"]
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
                
    with col2:
        with st.expander("Crear una nueva cuenta"):
            new_u = st.text_input("Nuevo Usuario")
            new_n = st.text_input("Tu Nombre")
            new_p = st.text_input("Nueva Contraseña", type="password")
            if st.button("Registrarse"):
                if new_u and new_p:
                    conn = get_db_connection()
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO users VALUES (?, ?, ?)", (new_u.lower(), hash_password(new_p), new_n))
                        conn.commit()
                        st.success("Cuenta creada exitosamente. Ya podés iniciar sesión.")
                    except:
                        st.error("El usuario ya existe.")
                    conn.close()

if not st.session_state.authenticated:
    login_form()
    st.stop()

# -------------------------------------------------------------
# BARRA LATERAL
# -------------------------------------------------------------
st.sidebar.markdown(f"👤 **{st.session_state.user_name}** (`@{st.session_state.current_user}`)")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state.authenticated = False
    st.session_state.current_user = None
    st.rerun()

st.sidebar.markdown("---")
filtro_pais = st.sidebar.selectbox("Enfoque de Examen", ["🔀 Modo Dual / Integrado", "🇦🇷 Solo Argentina", "🇧🇷 Solo Brasil"])

menu = st.sidebar.radio(
    "Navegación Principal",
    [
        "🏠 Dashboard & Repaso SRS",
        "📅 Cronograma Semanal Detallado",
        "📚 Temario, Algoritmos & Quiz",
        "✨ Generador de Choices con IA",
        "📝 Banco de Choices & Simulacros",
        "📕 Cuaderno de Errores",
        "⚖️ Guía Comparativa AR vs BR",
        "📊 Estadísticas de Rendimiento",
        "⚙️ Cargar CSV / Exámenes"
    ]
)

# -------------------------------------------------------------
# 1. DASHBOARD & REPASO SRS
# -------------------------------------------------------------
if menu == "🏠 Dashboard & Repaso SRS":
    st.header(f"⚡ Bienvenido/a, {st.session_state.user_name}")
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM error_log WHERE username = ?", (st.session_state.current_user,))
    total_hechas = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM error_log WHERE username = ? AND es_correcta = 1", (st.session_state.current_user,))
    total_correctas = c.fetchone()[0]
    conn.close()

    precision = int((total_correctas / total_hechas * 100)) if total_hechas > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔥 Racha Activa", "14 Días")
    col2.metric("🎯 Precisión Personal", f"{precision}%")
    col3.metric("📝 Choices Realizados", str(total_hechas))
    col4.metric("📅 Estado de Meta", "Semana 1 / Tocogineco")

    st.markdown("---")
    st.subheader("🧠 Repaso Espaciado Programado para Hoy")
    
    today = str(datetime.now().date())
    conn = get_db_connection()
    due_choices = pd.read_sql("SELECT * FROM choices WHERE next_review <= ?", conn, params=(today,))
    conn.close()

    if len(due_choices) == 0:
        st.success("🎉 ¡Estás al día! No tenés preguntas pendientes de la curva del olvido.")
    else:
        st.info(f"Tenés **{len(due_choices)} choices** listos para consolidar memoria de largo plazo.")
        for idx, row in due_choices.iterrows():
            with st.expander(f"📌 {row['area']} | {row['tema']} ({row['examen_origen']})"):
                st.write(f"**{row['pregunta']}**")
                st.write(f"A) {row['opcion_a']}")
                st.write(f"B) {row['opcion_b']}")
                st.write(f"C) {row['opcion_c']}")
                st.write(f"D) {row['opcion_d']}")
                if st.button("Ver Respuesta Oficial", key=f"srs_btn_{row['id']}"):
                    st.success(f"**Opción Correcta: {row['correcta']}**")
                    st.write(row['justificacion'])

# -------------------------------------------------------------
# 2. CRONOGRAMA SEMANAL DETALLADO (SEMANAS 1 A 20)
# -------------------------------------------------------------
elif menu == "📅 Cronograma Semanal Detallado":
    st.header("📅 Cronograma Completo y Exhaustivo (Semanas 1 a 20)")
    st.caption("Planificación estructurada de 1 a 2 horas diarias de lunes a viernes para cubrir el 100% del temario oficial.")

    cronograma_desglosado = {
        "Semana 1 (Tocoginecología: Trastornos Hipertensivos)": [
            {"Día": "Lunes", "Tema Específico": "Preeclampsia sin Criterios de Severidad: Criterios diagnósticos, metas de TA, seguimiento ambulatorio y criterios de internación.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Preeclampsia con Criterios de Severidad: Criterios clínicos y de laboratorio. Protocolos de Labetalol / Hidralazina EV + Esquema de Sulfato de Magnesio (Zuspan/Sibai).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Eclampsia y Síndrome HELLP: Diagnóstico de laboratorio diferencial, complicaciones materno-fetales y manejo de urgencia en guardia.", "Meta": "Algoritmo + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Hipertensión Crónica y Preeclampsia Sobreimpuesta: Manejo farmacológico ambulatorio (Alfametildopa vs Labetalol) y Guías MSAL 2024 vs APS Brasil.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Repaso Integrador de Hipertensión en el Embarazo + Batería de 20 choices de exámenes oficiales.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 2 (Tocoginecología: Hemorragias y Salud Sexual)": [
            {"Día": "Lunes", "Tema Específico": "Hemorragias de la 1ª Mitad: Aborto (amenaza, incompleto, diferido, séptico) y Embarazo Ectópico (criterios de Metotrexato vs Quirúrgico).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Hemorragias de la 2ª Mitad: DPPNI vs Placenta Previa vs Rotura Uterina y Vasa Previa. Diagnóstico diferencial y conducta.", "Meta": "Cuadro diferencial + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Interrupción Voluntaria y Legal del Embarazo (IVE/ILE): Marco legal (Ley 27.610), plazos, esquemas de Misoprostol / Mifepristona y objeción de conciencia.", "Meta": "Lectura Ley + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Anticoncepción: Criterios Médicos de Elegibilidad OMS en puerperio y lactancia, Anticoncepción Hormonal de Emergencia y colocación de DIU/SIU.", "Meta": "Lectura Guía + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Hemorragia Postparto (Atonía Uterina) y manejo con uterotónicos + Batería semanal de choices.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 3 (Tocoginecología: Infecciones Perinatales y Control Prenatal)": [
            {"Día": "Lunes", "Tema Específico": "Sífilis Gestacional y Congénita: Interpretación de VDRL vs pruebas treponémicas, tratamiento con Penicilina Benzatínica y manejo de la pareja.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Infección Urinaria en el Embarazo (Bacteriuria Asintomática, Cistitis, Pielonefritis) + Tamizaje de Estreptococo Grupo B (SGB).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Infecciones TORCH: Toxoplasmosis gestacional (IgG/IgM/Avidez y Espiramicina), Chagas perinatal y Citomegalovirus.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Rutina de Control Prenatal, Carné Perinatal, suplementación (Hierro/Ácido fólico) y Vacunas (VSR sem 32-36, dTPa y Antigripal).", "Meta": "Lectura Guía + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Simulacro Semanal de Obstetricia e Infecciones Perinatales.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 4 (Tocoginecología: Ginecología y Patología Cervical/Mamaria)": [
            {"Día": "Lunes", "Tema Específico": "Patología Cervical: Tamizaje con Papanicolaou y test DNA-VPH (Consenso FASGO 2024 vs Directrices MS Brasil), colposcopía y manejo de LSIL/HSIL.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Infecciones del Tracto Genital Inferior: Vaginosis bacteriana, Candidiasis, Tricomoniasis y Enfermedad Pélvica Inflamatoria (EPI).", "Meta": "Cuadro diferencial + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Patología Mamaria: Nódulos mamarios benignos, mastalgia, categorización BI-RADS mamográfico y tamizaje de cáncer de mama.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Endocrinología Ginecológica: Sangrado Uterino Anormal (PALM-COEIN), Síndrome de Ovario Poliquístico (Rotterdam) y Climaterio.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Atención a Víctimas de Violencia Sexual (Profilaxis PEP, anticoncepción de urgencia) + Batería de 20 choices.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 5 (Pediatría: Infecciones Respiratorias Agudas Bajas - IRAB)": [
            {"Día": "Lunes", "Tema Específico": "Bronquiolitis Aguda: Diagnóstico clínico, factores de riesgo de gravedad, Score de Tal, oxigenoterapia y criterio de no uso de B2 ni corticoides.", "Meta": "Lectura SAP + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Neumonía Adquirida en la Comunidad (NAC): Etiologías según grupo etario, tratamiento ambulatorio con Amoxicilina y criterios de internación.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Laringitis y Crup: Diagnóstico clínico, estridor, clasificación de gravedad y dosis de Dexametasona / Adrenalina nebulizada.", "Meta": "Algoritmo + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Crisis Asmática Pediátrica: Evaluación de severidad, esquema de rescate con Salbutamol reglado y corticoides sistémicos según GINA/SAP.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Batería Integradora de IRAB Pediátricas.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 6 (Pediatría: Gastroenterología, Medio Interno y Nefrología)": [
            {"Día": "Lunes", "Tema Específico": "Diarrea Aguda y Deshidratación: Evaluación clínica de grado de deshidratación y Planes de Hidratación OMS (Plan A domiciliario, Plan B con SRO, Plan C EV).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Síndrome Urémico Hemolítico (SUH): Fisiopatología por Shiga-toxina, tríada diagnóstica, soporte hídrico/transfusional y contraindicación de antibióticos.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Infección del Trato Urinario (ITU) y Fiebre sin Foco: Toma de muestra estéril, tratamiento empírico oral/EV y criterios de ecografía/CUGM.", "Meta": "Algoritmo + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Cetoacidosis Diabética Pediátrica: Protocolo estricto de hidratación con SF 0.9%, corrección de potasio e infusión de insulina continua (sin bolos).", "Meta": "Protocolo + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Batería semanal de Gastroenterología y Nefrología Pediátrica.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 7 (Pediatría: Puericultura, Crecimiento y Prevención)": [
            {"Día": "Lunes", "Tema Específico": "Hitos del Crecimiento y Neurodesarrollo: Evaluación motora, lenguaje y social por etapas, tamizaje de autismo (M-CHAT) y pautas de alarma.", "Meta": "Tablas desarrollo + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Nutrición Infantil: Lactancia materna exclusiva, alimentación complementaria y pautas de suplementación con Hierro/Vitaminas (SAP vs MS Brasil).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Trastornos Nutricionales: Diagnóstico antropométrico de Desnutrición (Marasmo vs Kwashiorkor), Sobrepeso y Obesidad (IMC > Pc 97).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Pautas de Crianza y Prevención de Accidentes: Sueño Seguro SAP (posición supina, colecho de riesgo) y sospecha de Maltrato/Abuso Infantil.", "Meta": "Lectura Guías + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Simulacro Semanal de Puericultura y Desarrollo Infantil.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 8 (Pediatría: Vacunación, Neonatología y Exantemáticas)": [
            {"Día": "Lunes", "Tema Específico": "Calendario Nacional de Vacunación: Esquemas completos en lactantes e ingreso escolar, puesta al día y vacunas específicas (BCG, Rotavirus, Triple Viral, VPH).", "Meta": "Tablas vacunas + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Neonatología Inmediata: Test de APGAR, examen físico neonatal y Reanimación Cardiopulmonar Neonatal (algoritmo SAP/SBP).", "Meta": "Algoritmo RCP + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Ictericia Neonatal: Fisiológica vs Patológica (incompatibilidad ABO/Rh), indicación de Luminoterapia y Exanguinotransfusión.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Enfermedades Exantemáticas: Sarampión, Rubéola, Varicela, Eritema Infeccioso, Roséola, Escarlatina y Enfermedad de Kawasaki.", "Meta": "Cuadro diferencial + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Pesquisa Neonatal (Test del talón, OEA, reflejo rojo) + Batería de 20 choices.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 9 (Clínica Médica: Cardiología y Urgencias Vasculares)": [
            {"Día": "Lunes", "Tema Específico": "Hipertensión Arterial Sistémica (HAS): Criterios diagnósticos en consultorio/MAPA/MDPA, metas de control y tratamiento escalonado (IECA/ARA-II, BCC, Tiazidas).", "Meta": "Lectura SAHA + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Crisis Hipertensivas: Urgencia vs Emergencia Hipertensiva (daño de órgano blanco) y manejo endovenoso con Labetalol / Nitroprusiato.", "Meta": "Algoritmo + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Síndrome Coronario Agudo: IAM con elevación del ST (ECG, ventana terapéutica, angioplastia vs trombolíticos) y SCA sin elevación del ST (doble antiagregación).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Insuficiencia Cardíaca (IC): IC con FE reducida y los 4 pilares farmacológicos con impacto en sobrevida (iSGLT2, ARNI/IECA, BB, Antagonistas Aldosterona).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Fibrilación Auricular (estratificación CHA2DS2-VASc y anticoagulación) + Batería de 20 choices.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 10 (Clínica Médica: Infectología y Arbovirosis)": [
            {"Día": "Lunes", "Tema Específico": "Dengue y Arbovirosis Urbanas: Fases clínicas, signos de alarma, clasificación por Grupos A, B, C, D y protocolo de reposición con cristaloides.", "Meta": "Guías MSAL/MS + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Tuberculosis (TBC): Diagnóstico con GeneXpert / Baciloscopía, esquema RIPE (2RIPE/4RI) y manejo de Tuberculosis Latente en contactos estrechos.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "VIH / SIDA: Diagnóstico serológico, inicio de TARV y profilaxis de infecciones oportunistas (Pneumocystis, Toxoplasmosis, Criptococo).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Infecciones del SNC: Meningitis bacteriana aguda (punción lumbar, LCR, antibiótico empírico + Dexametasona y quimioprofilaxis a contactos).", "Meta": "Cuadro LCR + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Sepsis y Shock Séptico (Criterios Sepsis-3, bundle de la primera hora) + Batería de choices.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 11 (Clínica Médica: Endocrinología y Metabolismo)": [
            {"Día": "Lunes", "Tema Específico": "Diabetes Mellitus Tipo 2: Diagnóstico, metas de HbA1c, cambios en estilo de vida y farmacoterapia oral (Metformina, iSGLT2, agonistas GLP-1).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Insulinoterapia en DM: Indicaciones, esquemas basal-bolo y prevención de hipoglucemias.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Cetoacidosis Diabética (CAD) y Estado Hiperglucémico Hiperosmolar (EHH) en adultos: Criterios diferenciales, fluidoterapia, potasio e insulina EV.", "Meta": "Protocolo + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Patología Tiroidea: Hipotiroidismo primario y subclínico (TSH/T4L, dosis Levotiroxina), Hipertiroidismo y Enfermedad de Graves.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Manejo de Dislipemias y Riesgo Cardiovascular Global + Batería de choices.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 12 (Clínica Médica: Neumonología, Nefrología y Neurología)": [
            {"Día": "Lunes", "Tema Específico": "Asma y EPOC en el Adulto: Diagnóstico espirométrico, clasificación GOLD (A, B, E), manejo crónico y tratamiento de exacerbaciones.", "Meta": "Lectura GINA/GOLD + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Neumonía Adquirida en la Comunidad (NAC): Score CURB-65 y esquemas antibióticos empíricos en internación vs ambulatorio.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Medio Interno y Trastornos Hidroelectrolíticos: Hiponatremia (cálculo de corrección) e Hiperkalemia grave (Gluconato de calcio y medidas de desplazamiento).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Accidente Cerebrovascular (ACV): ACV Isquémico agudo, escala NIHSS, ventana para rtPA endovenoso (<4.5 h) y manejo de TA.", "Meta": "Algoritmo ACV + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Cefaleas (Migraña, Tensional, Cluster y Red Flags) + Batería semanal de 20 choices.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 13 (Clínica Médica: Gastroenterología, Hematología y Endemias Brasil)": [
            {"Día": "Lunes", "Tema Específico": "Hemorragia Digestiva Alta (HDA variceal vs no variceal), Úlcera péptica, erradicación de H. pylori y Pancreatitis Aguda (Atlanta).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Hepatopatías Crónicas: Cirrosis y sus complicaciones (Ascitis, Peritonitis Bacteriana Espontánea, Encefalopatía Hepática).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Hematología: Diagnóstico diferencial de Anemias (Ferropénica, Megaloblástica por B12/Folato, Anemia de Enfermedades Crónicas, Hemolíticas).", "Meta": "Algoritmo anemias + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Endemias Revalida Brasil: Leishmaniasis Visceral (Calazar), Chagas agudo/crónico, Esporotricosis, Esquistosomiasis y Accidentes Ofídicos.", "Meta": "Guías MS Brasil + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Simulacro General de Clínica Médica (20 choices oficiales).", "Meta": "20 choices + Error Log"}
        ],
        "Semana 14 (Cirugía General: Trauma y Protocolo ATLS)": [
            {"Día": "Lunes", "Tema Específico": "Evaluación Inicial en Trauma (ABCDE): Manejo de vía aérea con protección cervical, intubación e indicaciones de cricotiroidostomía.", "Meta": "Lectura ATLS + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Trauma Torácico: Neumotórax a Tensión (diagnóstico clínico y descompresión con aguja), Hemotórax Masivo y Taponamiento Cardíaco (Beck).", "Meta": "Cuadro ATLS + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Trauma Abdominal y Pelviano: Evaluación hemodinámica, ecografía FAST, TC con contraste y criterios de laparotomía exploradora vs manejo no operatorio.", "Meta": "Algoritmo FAST + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Choque Hemorrágico en Trauma (Clases I a IV), Protocolo de Transfusión Masiva (1:1:1) y Ácido Tranexámico precoz.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Quemaduras (Fórmula de Parkland, vía aérea y quemaduras eléctricas) + Batería de choices.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 15 (Cirugía General: Abdomen Agudo Inflamatorio y Biliar)": [
            {"Día": "Lunes", "Tema Específico": "Apendicitis Aguda: Diagnóstico clínico, escala de Alvarado, ecografía/TC en casos dudosos y tratamiento quirúrgico.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Patología Biliar: Cólico biliar, Colecistitis Aguda (Criterios de Tokyo) y Colecistectomía laparoscópica.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Colangitis Aguda (Tríada de Charcot, Péntada de Reynolds y descompresión biliar urgente) y Coledocolitiasis (CPRE).", "Meta": "Algoritmo + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Diverticulitis Aguda: TC como Gold Standard, clasificación de Hinchey y tratamiento médico vs quirúrgico.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Batería Semanal de Abdomen Agudo Inflamatorio.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 16 (Cirugía General: Oclusión, Pared Abdominal y Cirugía Pediátrica)": [
            {"Día": "Lunes", "Tema Específico": "Abdomen Agudo Obstructivo: Obstrucción de intestino delgado (bridas) vs colon (cáncer, vólvulo de sigmoides) e Isquemia Mesentérica.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Patología de Pared Abdominal: Hernias inguinales (directa vs indirecta), crurales y umbilicales. Reducible vs Incarcerada vs Estrangulada.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Patología Anorrectal Benigna: Hemorroides, Fisura Anal y Abscesos/Fístulas perianales.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Cirugía Pediátrica y Ortopedia: Estenosis Hipertrófica del Píloro, Invaginación Intestinal y Cadera Dolorosa (Sinovitis vs Artritis Séptica - Kocher).", "Meta": "Cuadro comparativo + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Simulacro General de Cirugía (20 choices oficiales).", "Meta": "20 choices + Error Log"}
        ],
        "Semana 17 (Salud Pública: Epidemiología, Bioestadística y Bioética)": [
            {"Día": "Lunes", "Tema Específico": "Medidas de Frecuencia y Mortalidad: Incidencia acumulada, densidad de incidencia, prevalencia, tasa de mortalidad infantil y materna.", "Meta": "Fórmulas + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Diseños de Estudios Epidemiológicos: Transversales, Casos y Controles (Odds Ratio), Cohortes (Riesgo Relativo) y Ensayos Clínicos.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Pruebas Diagnósticas: Sensibilidad, Especificidad, Valor Predictivo Positivo (VPP) y Negativo (VPN), Curvas ROC.", "Meta": "Ejercicios + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Atención Primaria de la Salud (APS): Atributos de Starfield, Prevención Cuaternaria y Vigilancia Epidemiológica (SISA/SINAN).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Bioética: Principios bioéticos, secreto profesional y comunicación de malas noticias (Protocolo SPIKES) + Choices.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 18 (Salud Pública: Marco Legal Argentina vs Sistema SUS Brasil)": [
            {"Día": "Lunes", "Tema Específico": "Leyes Sanitarias Argentina: Ley 26.529 (Derechos del Paciente, Consentimiento e Historia Clínica) y Ley 25.929 (Parto Humanizado).", "Meta": "Lectura de Ley + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Salud Mental en Argentina: Ley 26.657 (Criterio de internación involuntaria por 'riesgo cierto e inminente', interdisciplina y derechos).", "Meta": "Lectura de Ley + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Protección de Derechos de NNyA (Ley 26.061), Identidad de Género (Ley 26.743) y Autonomía Progresiva en Salud.", "Meta": "Lectura de Ley + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Sistema Único de Saúde (SUS Brasil): Constitución de 1988 (Arts. 196-200), Ley 8.080 (Principios) y Ley 8.142 (Participación Social).", "Meta": "Lectura SUS + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Estratégia Saúde da Família (ESF): Atribuciones del equipo y territorialización + Batería de 20 choices de Leyes/SUS.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 19 (Consolidación Teórica & Simulacros Intensivos I)": [
            {"Día": "Lunes", "Tema Específico": "Simulacro Cronometrado 1: 50 Preguntas Integradoras de Tocoginecología y Pediatría.", "Meta": "Simulacro + Cuaderno de Errores"},
            {"Día": "Martes", "Tema Específico": "Revisión Focalizada: Repaso de puntos débiles detectados en el Cuaderno de Errores.", "Meta": "Flashcards SRS + Algoritmos"},
            {"Día": "Miércoles", "Tema Específico": "Simulacro Cronometrado 2: 50 Preguntas Integradoras de Clínica Médica y Cirugía General.", "Meta": "Simulacro + Cuaderno de Errores"},
            {"Día": "Jueves", "Tema Específico": "Revisión de Guía Comparativa AR vs BR (Dosis críticas, leyes y calendarios).", "Meta": "Lectura Matriz Comparativa"},
            {"Día": "Viernes", "Tema Específico": "Simulacro Completo de 100 Preguntas (Examen Oficial de Años Anteriores).", "Meta": "100 choices + Diagnóstico Metacognitivo"}
        ],
        "Semana 20 (Consolidación Teórica & Simulacros Intensivos II)": [
            {"Día": "Lunes", "Tema Específico": "Simulacro Completo 100 Preguntas: Foco en Preguntas Trampa y Distractores Frecuentes.", "Meta": "100 choices + Análisis de Errores"},
            {"Día": "Martes", "Tema Específico": "Revisión Completa del Cuaderno Blanco (Reglas de Oro personales para no volver a fallar).", "Meta": "Lectura de Reglas de Oro"},
            {"Día": "Miércoles", "Tema Específico": "Repaso Ultrarrápido de High-Yield Pearls de las 5 Grandes Áreas Troncales.", "Meta": "Flashcards High-Yield"},
            {"Día": "Jueves", "Tema Específico": "Simulacro Final de 100 Preguntas con Tiempo Real (4 horas).", "Meta": "Simulacro Final"},
            {"Día": "Viernes", "Tema Específico": "Cierre de Estudio, Estrategia de Manejo del Tiempo y Preparación Mental.", "Meta": "Consolidación y Descanso"}
        ]
    }

    sem_select = st.selectbox("Seleccioná la semana a visualizar en detalle:", list(cronograma_desglosado.keys()))
    df_sem = pd.DataFrame(cronograma_desglosado[sem_select])
    st.dataframe(df_sem, use_container_width=True, hide_index=True)
    
# -------------------------------------------------------------
# 3. TEMARIO, ALGORITMOS & QUIZ RÁPIDO
# -------------------------------------------------------------
elif menu == "📚 Temario, Algoritmos & Quiz":
    st.header("📚 Temario Clínico, Algoritmos & Autoevaluación")
    
    tema_sel = st.selectbox(
        "Seleccioná el tema a estudiar:",
        [
            "Preeclampsia y Trastornos Hipertensivos",
            "IRAB Bronquiolitis y Vías Respiratorias Pediátricas",
            "Trauma Torácico y Protocolo ATLS",
            "Dengue y Arbovirosis Urbanas",
            "Leyes Sanitarias de Argentina (26.529 / 26.657 / 27.610)"
        ]
    )

    t1, t2, t3, t4 = st.tabs(["🧠 Resumen & Algoritmo", "⚡ High-Yield Pearls", "⚖️ Comparativa AR vs BR", "📝 Quiz Rápido del Tema (5 Preguntas)"])

    with t1:
        st.subheader("Algoritmo Clínico")
        if "Preeclampsia" in tema_sel:
            st.markdown("""
            ```mermaid
            graph TD
                A[Gestante >= 20 sem con PA >= 140/90] --> B{Criterios de Severidad?<br>PA >= 160/110, Cefalea, Epigastralgia, Plaquetas < 100k}
                B -- SÍ --> C[Preeclampsia Severa]
                B -- NO --> D[Preeclampsia sin Severidad]
                C --> E[1° Labetalol 20mg EV o Hidralazina 5mg EV]
                C --> F[2° Sulfato de Magnesio: Ataque 4-5g EV + Mant 1-2g/h]
                C --> G[Planificar Finalización según Edad Gestacional]
            ```
            """, unsafe_allow_html=True)
            
        if st.button("✨ Generar Algoritmo Personalizado con IA sobre este tema"):
            if not model:
                st.error("Error: Verificá que tu API Key de Gemini esté configurada correctamente en Secrets.")
            else:
                with st.spinner("Diseñando diagrama de flujo clínico..."):
                    prompt = f"""
                    Generá un diagrama de flujo en código Mermaid.js sobre el diagnóstico y tratamiento de: {tema_sel}.
                    Reglas estrictas:
                    1. Devolvé ÚNICAMENTE el bloque de código Mermaid que empiece con 'graph TD'.
                    2. No agregues introducciones, conclusiones ni etiquetas de markdown adicionales.
                    """
                    try:
                        res = model.generate_content(prompt)
                        mermaid_code = res.text.replace("```mermaid", "").replace("```", "").strip()
                        st.markdown(f"""
                        ```mermaid
                        {mermaid_code}
                        ```
                        """)
                        st.caption("Diagrama clínico generado por IA.")
                    except Exception as err:
                        st.error(f"Ocurrió un error al contactar a la IA: {err}")

    with t2:
        st.subheader("⚡ High-Yield Pearls")
        st.write("• **Preeclampsia Severa:** PA $\\ge 160/110\\text{ mmHg}$. Primera línea: Labetalol EV o Hidralazina EV.")
        st.write("• **Prevención de Convulsiones:** Sulfato de Magnesio EV (Esquema Zuspan o Sibai).")
        st.write("• **Antídoto Magnesio:** Gluconato de Calcio al 10% EV.")

    with t3:
        st.subheader("⚖️ Diferencias Normativas Argentina vs. Brasil")
        st.write("• **Argentina:** Inicio de PAP a los 25 años (FASGO 2024); Vacuna VSR obligatoria en semanas 32-36.")
        st.write("• **Brasil:** Tamizaje cervical con rastreo molecular DNA-HPV según directrices del Ministerio de Salud.")

    with t4:
        st.subheader("🎯 Quiz Rápido de Comprobación (Solo este tema)")
        filtro_palabra = "Preeclampsia" if "Preeclampsia" in tema_sel else ("IRAB" if "IRAB" in tema_sel else "Trauma")
        conn = get_db_connection()
        quiz_q = pd.read_sql("SELECT * FROM choices WHERE tema LIKE ? LIMIT 5", conn, params=(f"%{filtro_palabra}%",))
        conn.close()

        if len(quiz_q) == 0:
            st.info("No hay choices cargados en la base de datos para este tema específico. ¡Podés crearlos con la pestaña 'Generador de Choices con IA'!")
        else:
            for idx, q_row in quiz_q.iterrows():
                st.markdown(f"**Pregunta {idx+1}:** {q_row['pregunta']}")
                ans = st.radio(
                    f"Opciones para P{idx+1}:",
                    [f"A) {q_row['opcion_a']}", f"B) {q_row['opcion_b']}", f"C) {q_row['opcion_c']}", f"D) {q_row['opcion_d']}"],
                    key=f"quiz_tema_{q_row['id']}"
                )
                if st.button(f"Comprobar P{idx+1}", key=f"btn_q_{q_row['id']}"):
                    if ans[0] == q_row['correcta']:
                        st.success(f"¡Correcto! Opción {q_row['correcta']}")
                    else:
                        st.error(f"Incorrecto. La respuesta correcta es la opción {q_row['correcta']}.")
                    st.info(q_row['justificacion'])
                st.markdown("---")

# -------------------------------------------------------------
# 4. GENERADOR AUTOMÁTICO DE CHOICES CON IA (AMPLIADO A 20)
# -------------------------------------------------------------
elif menu == "✨ Generador de Choices con IA":
    st.header("✨ Generador Automático de Choices Médicos con IA")
    st.caption("Creá baterías de preguntas inéditas basadas en casos clínicos reales ajustadas a los programas oficiales de Argentina y Brasil.")

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        tema_ia = st.text_input("Tema a evaluar:", value="Preeclampsia Severa y Manejo de Crisis")
        area_ia = st.selectbox("Especialidad:", ["Tocoginecología", "Pediatría", "Clínica Médica", "Cirugía General", "Salud Pública y Leyes"])
    with col_g2:
        enfoque_ia = st.selectbox("Estilo de Examen:", ["🇦🇷 Examen Único / CABA (Argentina)", "🇧🇷 Revalida INEP (Brasil)"])
        cant_q = st.slider("Cantidad de preguntas a generar (Máximo 20):", min_value=1, max_value=20, value=5)

    if st.button("🚀 Generar y Guardar Choices con IA"):
        if not model:
            st.error("Error al conectar con la API de Gemini. Verificá tu clave en Secrets.")
        else:
            with st.spinner(f"La IA está redactando {cant_q} casos clínicos con distractores y justificación oficial..."):
                prompt = f"""
                Actuá como miembro del comité evaluador médico de residencias médicas ({enfoque_ia}).
                Generá exactamente {cant_q} preguntas de opción múltiple de alta calidad médica sobre: '{tema_ia}' en el área de '{area_ia}'.
                
                Devolvé ÚNICAMENTE un arreglo JSON válido (sin texto antes ni después, y sin bloques adicionales de markdown) con esta estructura exacta:
                [
                  {{
                    "pregunta": "Caso clínico detallado...",
                    "opcion_a": "Texto opción A",
                    "opcion_b": "Texto opción B",
                    "opcion_c": "Texto opción C",
                    "opcion_d": "Texto opción D",
                    "correcta": "A", 
                    "justificacion": "Explicación médica detallada citando guías y consensos vigentes."
                  }}
                ]
                """
                try:
                    response = model.generate_content(prompt)
                    clean_json = response.text.replace("```json", "").replace("```", "").strip()
                    generated_list = json.loads(clean_json)

                    conn = get_db_connection()
                    c = conn.cursor()
                    guardados = 0
                    for item in generated_list:
                        new_id = f"IA-{random.randint(10000, 99999)}"
                        c.execute('''
                            INSERT INTO choices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            new_id, f"✨ IA Generada ({enfoque_ia[:8]})", area_ia, tema_ia, "Prioridad A",
                            item["pregunta"], item["opcion_a"], item["opcion_b"], item["opcion_c"], item["opcion_d"],
                            item["correcta"].upper(), item["justificacion"], "https://drive.google.com",
                            str(datetime.now().date()), 1, 2.5, 0
                        ))
                        guardados += 1
                    conn.commit()
                    conn.close()

                    st.success(f"🎉 ¡Se generaron y guardaron {guardados} choices exitosamente en tu banco de preguntas!")
                    for item in generated_list:
                        with st.expander(f"Caso Clínico Generado: {item['pregunta'][:80]}..."):
                            st.write(item['pregunta'])
                            st.write(f"A) {item['opcion_a']}")
                            st.write(f"B) {item['opcion_b']}")
                            st.write(f"C) {item['opcion_c']}")
                            st.write(f"D) {item['opcion_d']}")
                            st.success(f"Respuesta Correcta: {item['correcta']}")
                            st.info(item['justificacion'])
                except Exception as e:
                    st.error(f"Error procesando la respuesta de la IA: {e}")

# -------------------------------------------------------------
# 5. BANCO DE CHOICES & SIMULACROS
# -------------------------------------------------------------
elif menu == "📝 Banco de Choices & Simulacros":
    st.header("📝 Banco de Choices & Simulacros")

    modo_practica = st.radio(
        "Modalidad de Estudio:",
        ["📚 Por Área Específica", "🎲 Simulacro Aleatorio (Cualquier Tema)"],
        horizontal=True
    )

    conn = get_db_connection()
    if modo_practica == "📚 Por Área Específica":
        area_sel = st.selectbox("Seleccioná el Área Médica:", ["Tocoginecología", "Pediatría", "Clínica Médica", "Cirugía General", "Salud Pública y Leyes"])
        choices_df = pd.read_sql("SELECT * FROM choices WHERE area = ?", conn, params=(area_sel,))
    else:
        choices_df = pd.read_sql("SELECT * FROM choices", conn)
        choices_df = choices_df.sample(frac=1).reset_index(drop=True)
    conn.close()

    if len(choices_df) == 0:
        st.warning("No se encontraron preguntas para los filtros seleccionados.")
    else:
        q_idx = st.selectbox(
            "Seleccionar Pregunta a Resolver:",
            range(len(choices_df)),
            format_func=lambda x: f"P#{x+1}: {choices_df.iloc[x]['tema']} ({choices_df.iloc[x]['examen_origen']})"
        )
        q = choices_df.iloc[q_idx]

        st.markdown(f"#### `{q['examen_origen']}` | **{q['area']}** - *{q['tema']}*")
        st.write(f"### {q['pregunta']}")

        opciones = [
            f"A) {q['opcion_a']}",
            f"B) {q['opcion_b']}",
            f"C) {q['opcion_c']}",
            f"D) {q['opcion_d']}"
        ]

        resp_usr = st.radio("Opciones disponibles:", opciones, key=f"prax_{q['id']}")
        flag_duda = st.checkbox("🏷️ Marcar con Duda / Flag", key=f"fl_{q['id']}")

        if st.button("Confirmar Respuesta", key=f"sub_{q['id']}"):
            letra_elegida = resp_usr[0]
            es_correcta = 1 if letra_elegida == q['correcta'] else 0

            conn = get_db_connection()
            c = conn.cursor()
            c.execute('''
                INSERT INTO error_log (username, choice_id, fecha, respuesta_dada, es_correcta, flag_duda, motivo_error, regla_oro)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (st.session_state.current_user, q['id'], datetime.now(), letra_elegida, es_correcta, 1 if flag_duda else 0, "", ""))
            conn.commit()
            conn.close()

            if es_correcta:
                st.success(f"🎉 ¡CORRECTO! Opción {q['correcta']}")
            else:
                st.error(f"❌ INCORRECTO. La respuesta oficial era la opción {q['correcta']}.")

            st.info(f"**Fundamento Clínico:** {q['justificacion']}")

# -------------------------------------------------------------
# 6. CUADERNO DE ERRORES DEL USUARIO
# -------------------------------------------------------------
elif menu == "📕 Cuaderno de Errores":
    st.header(f"📕 Libro de Errores | {st.session_state.user_name}")
    st.caption("Solo se muestran las preguntas falladas o marcadas con duda en tu cuenta.")

    conn = get_db_connection()
    errores_df = pd.read_sql('''
        SELECT e.id as log_id, e.fecha, e.respuesta_dada, e.es_correcta, e.flag_duda, e.motivo_error, e.regla_oro,
               c.pregunta, c.correcta, c.justificacion, c.area, c.tema, c.examen_origen
        FROM error_log e
        JOIN choices c ON e.choice_id = c.id
        WHERE e.username = ? AND (e.es_correcta = 0 OR e.flag_duda = 1)
        ORDER BY e.fecha DESC
    ''', conn, params=(st.session_state.current_user,))
    conn.close()

    if len(errores_df) == 0:
        st.success("✨ ¡Felicitaciones! No tenés errores ni dudas registradas.")
    else:
        st.info(f"Tenés **{len(errores_df)} preguntas registradas** para análisis.")
        for idx, row in errores_df.iterrows():
            with st.expander(f"❌ {row['area']} | {row['tema']} ({row['examen_origen']}) | Marcaste: {row['respuesta_dada']} | Correcta: {row['correcta']}"):
                st.write(f"**Enunciado:** {row['pregunta']}")
                st.write(f"**Justificación:** {row['justificacion']}")
                
                motivo = st.selectbox(
                    "¿Por qué fallaste?",
                    ["Error de lectura / Apuro", "Duda 50/50", "Falta de teoría", "Confusión de dosis"],
                    key=f"mot_{row['log_id']}"
                )
                regla = st.text_input("💡 Tu regla para evitarlo la próxima:", value=row['regla_oro'] if row['regla_oro'] else "", key=f"reg_{row['log_id']}")
                
                if st.button("Guardar en mi Bitácora", key=f"save_b_{row['log_id']}"):
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("UPDATE error_log SET motivo_error = ?, regla_oro = ? WHERE id = ?", (motivo, regla, row['log_id']))
                    conn.commit()
                    conn.close()
                    st.success("Guardado en tu perfil.")

# -------------------------------------------------------------
# 7. GUÍA COMPARATIVA AR VS BR
# -------------------------------------------------------------
elif menu == "⚖️ Guía Comparativa AR vs BR":
    st.header("⚖️ Matriz Comparativa Oficial: Argentina vs. Brasil")
    st.caption("Diferencias normativas del Ministerio de Salud y del SUS.")

    comparativas = [
        {"Área": "Ginecología", "Tema": "Inicio de Citología (PAP)", "🇦🇷 Argentina": "A partir de los 25 años (FASGO 2024)", "🇧🇷 Brasil": "A partir de los 25 años / Foco en prueba molecular DNA-HPV"},
        {"Área": "Obstetricia", "Tema": "Vacuna Virus Sincicial (VSR)", "🇦🇷 Argentina": "Obligatoria en gestantes sem 32 a 36", "🇧🇷 Brasil": "No incorporada universalmente al PNI gestacional"},
        {"Área": "Salud Pública", "Tema": "Marco Legal de Salud Mental", "🇦🇷 Argentina": "Ley 26.657: Internación involuntaria solo por 'riesgo cierto e inminente'", "🇧🇷 Brasil": "Ley 10.216: Reforma Psiquiátrica y RAPS"},
        {"Área": "Salud Pública", "Tema": "Leyes Orgánicas Sanitarias", "🇦🇷 Argentina": "Ley 26.529 (Derechos) + Ley 27.610 (IVE/ILE)", "🇧🇷 Brasil": "Leyes 8.080 (SUS) y 8.142 (Participación Comunitaria)"},
        {"Área": "Infectología", "Tema": "Tuberculosis de Primera Línea", "🇦🇷 Argentina": "Pautas Técnicas: GeneXpert MTB/RIF + RIPE", "🇧🇷 Brasil": "TRM-TB (Teste Rápido Molecular) + RHZE"}
    ]
    st.dataframe(pd.DataFrame(comparativas), use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# 8. ESTADÍSTICAS DEL USUARIO
# -------------------------------------------------------------
elif menu == "📊 Estadísticas de Rendimiento":
    st.header(f"📊 Estadísticas Personales | {st.session_state.user_name}")

    conn = get_db_connection()
    metrics_df = pd.read_sql('''
        SELECT c.area, c.examen_origen, e.es_correcta
        FROM error_log e
        JOIN choices c ON e.choice_id = c.id
        WHERE e.username = ?
    ''', conn, params=(st.session_state.current_user,))
    conn.close()

    if len(metrics_df) == 0:
        st.info("Aún no tenés suficientes preguntas resueltas para generar gráficos.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Rendimiento por Especialidad")
            area_stats = metrics_df.groupby("area")["es_correcta"].agg(Total="count", Aciertos="sum").reset_index()
            area_stats["Porcentaje"] = (area_stats["Aciertos"] / area_stats["Total"]) * 100
            fig = px.bar(area_stats, x="area", y="Porcentaje", text_auto=".1f", color="Porcentaje", color_continuous_scale="Teal", labels={"Porcentaje": "% Acierto", "area": "Especialidad"})
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("Proporción Global de Aciertos")
            fig_p = px.pie(values=[metrics_df['es_correcta'].sum(), len(metrics_df)-metrics_df['es_correcta'].sum()], names=["Aciertos", "Errores"], color_discrete_sequence=["#2ecc71", "#e74c3c"])
            st.plotly_chart(fig_p, use_container_width=True)

# -------------------------------------------------------------
# 9. CARGA DE EXÁMENES CSV
# -------------------------------------------------------------
elif menu == "⚙️ Cargar CSV / Exámenes":
    st.header("⚙️ Importar Lotes de Preguntas CSV")
    st.caption("Subí tu archivo de preguntas generado.")

    uploaded_csv = st.file_uploader("Subir archivo CSV", type=["csv"])
    if uploaded_csv is not None:
        df_up = pd.read_csv(uploaded_csv)
        st.write("Vista previa:")
        st.dataframe(df_up.head(3))
        if st.button("Guardar en la Base de Datos"):
            conn = get_db_connection()
            c = conn.cursor()
            for _, r in df_up.iterrows():
                c.execute('''
                    INSERT OR REPLACE INTO choices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    str(r.get('id')), str(r.get('examen_origen')), str(r.get('area')), str(r.get('tema')),
                    str(r.get('incidencia', 'Prioridad A')), str(r.get('pregunta')), str(r.get('opcion_a')),
                    str(r.get('opcion_b')), str(r.get('opcion_c')), str(r.get('opcion_d')), str(r.get('correcta')),
                    str(r.get('justificacion', '')), str(r.get('drive_link', '')), str(datetime.now().date()), 1, 2.5, 0
                ))
            conn.commit()
            conn.close()
            st.success(f"¡Se importaron {len(df_up)} preguntas exitosamente!")
