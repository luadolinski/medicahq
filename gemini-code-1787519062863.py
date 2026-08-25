import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import random
import hashlib
import json
import re
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
# CONFIGURACIÓN DE GEMINI API (v3.6)
# -------------------------------------------------------------
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
model = None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-3.6-flash")
    except Exception:
        try:
            model = genai.GenerativeModel("models/gemini-3.6-flash")
        except Exception:
            model = None

# -------------------------------------------------------------
# CONEXIÓN A GOOGLE SHEETS
# -------------------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)
SPREADSHEET_URL = st.secrets.get("SPREADSHEET_URL", "")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_sheet_data(worksheet_name):
    try:
        return conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl="0s")
    except Exception:
        return pd.DataFrame()

def save_sheet_data(worksheet_name, df):
    conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=df)

# -------------------------------------------------------------
# CRONOGRAMA GLOBAL (SEMANAS 1 A 20)
# -------------------------------------------------------------
cronograma_desglosado = {
    "Semana 1 (Tocoginecología: Trastornos Hipertensivos)": [
        {"Día": "Lunes", "Tema Específico": "Preeclampsia sin Criterios de Severidad: Criterios diagnósticos, metas de TA, seguimiento ambulatorio y criterios de internación."},
        {"Día": "Martes", "Tema Específico": "Preeclampsia con Criterios de Severidad: Criterios clínicos y de laboratorio. Protocolos de Labetalol / Hidralazina EV + Esquema de Sulfato de Magnesio (Zuspan/Sibai)."},
        {"Día": "Miércoles", "Tema Específico": "Eclampsia y Síndrome HELLP: Diagnóstico de laboratorio diferencial, complicaciones materno-fetales y manejo de urgencia en guardia."},
        {"Día": "Jueves", "Tema Específico": "Hipertensión Crónica y Preeclampsia Sobreimpuesta: Manejo farmacológico ambulatorio (Alfametildopa vs Labetalol) y Guías MSAL 2024 vs APS Brasil."},
        {"Día": "Viernes", "Tema Específico": "Repaso Integrador de Hipertensión en el Embarazo + Batería de 20 choices de exámenes oficiales."}
    ],
    "Semana 2 (Tocoginecología: Hemorragias y Salud Sexual)": [
        {"Día": "Lunes", "Tema Específico": "Hemorragias de la 1ª Mitad: Aborto (amenaza, incompleto, diferido, séptico) y Embarazo Ectópico (criterios de Metotrexato vs Quirúrgico)."},
        {"Día": "Martes", "Tema Específico": "Hemorragias de la 2ª Mitad: DPPNI vs Placenta Previa vs Rotura Uterina y Vasa Previa. Diagnóstico diferencial y conducta."},
        {"Día": "Miércoles", "Tema Específico": "Interrupción Voluntaria y Legal del Embarazo (IVE/ILE): Marco legal (Ley 27.610), plazos, esquemas de Misoprostol / Mifepristona y objeción de conciencia."},
        {"Día": "Jueves", "Tema Específico": "Anticoncepción: Criterios Médicos de Elegibilidad OMS en puerperio y lactancia, Anticoncepción Hormonal de Emergencia y colocación de DIU/SIU."},
        {"Día": "Viernes", "Tema Específico": "Hemorragia Postparto (Atonía Uterina) y manejo con uterotónicos + Batería semanal de choices."}
    ],
    "Semana 3 (Tocoginecología: Infecciones Perinatales y Control Prenatal)": [
        {"Día": "Lunes", "Tema Específico": "Sífilis Gestacional y Congénita: Interpretación de VDRL vs pruebas treponémicas, tratamiento con Penicilina Benzatínica y manejo de la pareja."},
        {"Día": "Martes", "Tema Específico": "Infección Urinaria en el Embarazo (Bacteriuria Asintomática, Cistitis, Pielonefritis) + Tamizaje de Estreptococo Grupo B (SGB)."},
        {"Día": "Miércoles", "Tema Específico": "Infecciones TORCH: Toxoplasmosis gestacional (IgG/IgM/Avidez y Espiramicina), Chagas perinatal y Citomegalovirus."},
        {"Día": "Jueves", "Tema Específico": "Rutina de Control Prenatal, Carné Perinatal, suplementación (Hierro/Ácido fólico) y Vacunas (VSR sem 32-36, dTPa y Antigripal)."},
        {"Día": "Viernes", "Tema Específico": "Simulacro Semanal de Obstetricia e Infecciones Perinatales."}
    ],
    "Semana 4 (Tocoginecología: Ginecología y Patología Cervical/Mamaria)": [
        {"Día": "Lunes", "Tema Específico": "Patología Cervical: Tamizaje con Papanicolaou y test DNA-VPH (Consenso FASGO 2024 vs Directrices MS Brasil), colposcopía y manejo de LSIL/HSIL."},
        {"Día": "Martes", "Tema Específico": "Infecciones del Tracto Genital Inferior: Vaginosis bacteriana, Candidiasis, Tricomoniasis y Enfermedad Pélvica Inflamatoria (EPI)."},
        {"Día": "Miércoles", "Tema Específico": "Patología Mamaria: Nódulos mamarios benignos, mastalgia, categorización BI-RADS mamográfico y tamizaje de cáncer de mama."},
        {"Día": "Jueves", "Tema Específico": "Endocrinología Ginecológica: Sangrado Uterino Anormal (PALM-COEIN), Síndrome de Ovario Poliquístico (Rotterdam) y Climaterio."},
        {"Día": "Viernes", "Tema Específico": "Atención a Víctimas de Violencia Sexual (Profilaxis PEP, anticoncepción de urgencia) + Batería de 20 choices."}
    ],
    "Semana 5 (Pediatría: Infecciones Respiratorias Agudas Bajas - IRAB)": [
        {"Día": "Lunes", "Tema Específico": "Bronquiolitis Aguda: Diagnóstico clínico, factores de riesgo de gravedad, Score de Tal, oxigenoterapia y criterio de no uso de B2 ni corticoides."},
        {"Día": "Martes", "Tema Específico": "Neumonía Adquirida en la Comunidad (NAC): Etiologías según grupo etario, tratamiento ambulatorio con Amoxicilina y criterios de internación."},
        {"Día": "Miércoles", "Tema Específico": "Laringitis y Crup: Diagnóstico clínico, estridor, clasificación de gravedad y dosis de Dexametasona / Adrenalina nebulizada."},
        {"Día": "Jueves", "Tema Específico": "Crisis Asmática Pediátrica: Evaluación de severidad, esquema de rescate con Salbutamol reglado y corticoides sistémicos según GINA/SAP."},
        {"Día": "Viernes", "Tema Específico": "Batería Integradora de IRAB Pediátricas."}
    ],
    "Semana 6 (Pediatría: Gastroenterología, Medio Interno y Nefrología)": [
        {"Día": "Lunes", "Tema Específico": "Diarrea Aguda y Deshidratación: Evaluación clínica de grado de deshidratación y Planes de Hidratación OMS (Plan A, B con SRO, C EV)."},
        {"Día": "Martes", "Tema Específico": "Síndrome Urémico Hemolítico (SUH): Fisiopatología por Shiga-toxina, tríada diagnóstica, soporte y contraindicación de antibióticos."},
        {"Día": "Miércoles", "Tema Específico": "Infección del Trato Urinario (ITU) y Fiebre sin Foco: Toma de muestra estéril, tratamiento empírico oral/EV y criterios de ecografía/CUGM."},
        {"Día": "Jueves", "Tema Específico": "Cetoacidosis Diabética Pediátrica: Protocolo de hidratación con SF 0.9%, corrección de potasio e infusión de insulina continua."},
        {"Día": "Viernes", "Tema Específico": "Batería semanal de Gastroenterología y Nefrología Pediátrica."}
    ],
    "Semana 7 (Pediatría: Puericultura, Crecimiento y Prevención)": [
        {"Día": "Lunes", "Tema Específico": "Hitos del Crecimiento y Neurodesarrollo: Evaluación motora, lenguaje y social por etapas, tamizaje de autismo (M-CHAT) y pautas de alarma."},
        {"Día": "Martes", "Tema Específico": "Nutrición Infantil: Lactancia materna exclusiva, alimentación complementaria y pautas de suplementación con Hierro/Vitaminas."},
        {"Día": "Miércoles", "Tema Específico": "Trastornos Nutricionales: Diagnóstico antropométrico de Desnutrición (Marasmo vs Kwashiorkor), Sobrepeso y Obesidad (IMC > Pc 97)."},
        {"Día": "Jueves", "Tema Específico": "Pautas de Crianza y Prevención de Accidentes: Sueño Seguro SAP (posición supina, colecho de riesgo) y sospecha de Maltrato/Abuso Infantil."},
        {"Día": "Viernes", "Tema Específico": "Simulacro Semanal de Puericultura y Desarrollo Infantil."}
    ],
    "Semana 8 (Pediatría: Vacunación, Neonatología y Exantemáticas)": [
        {"Día": "Lunes", "Tema Específico": "Calendario Nacional de Vacunación: Esquemas completos en lactantes e ingreso escolar, puesta al día y vacunas específicas."},
        {"Día": "Martes", "Tema Específico": "Neonatología Inmediata: Test de APGAR, examen físico neonatal y Reanimación Cardiopulmonar Neonatal (algoritmo SAP/SBP)."},
        {"Día": "Miércoles", "Tema Específico": "Ictericia Neonatal: Fisiológica vs Patológica (incompatibilidad ABO/Rh), indicación de Luminoterapia y Exanguinotransfusión."},
        {"Día": "Jueves", "Tema Específico": "Enfermedades Exantemáticas: Sarampión, Rubéola, Varicela, Eritema Infeccioso, Roséola, Escarlatina y Enfermedad de Kawasaki."},
        {"Día": "Viernes", "Tema Específico": "Pesquisa Neonatal (Test del talón, OEA, reflejo rojo) + Batería de 20 choices."}
    ],
    "Semana 9 (Clínica Médica: Cardiología y Urgencias Vasculares)": [
        {"Día": "Lunes", "Tema Específico": "Hipertensión Arterial Sistémica (HAS): Criterios diagnósticos en consultorio/MAPA/MDPA, metas y tratamiento escalonado."},
        {"Día": "Martes", "Tema Específico": "Crisis Hipertensivas: Urgencia vs Emergencia Hipertensiva (daño de órgano blanco) y manejo endovenoso con Labetalol / Nitroprusiato."},
        {"Día": "Miércoles", "Tema Específico": "Síndrome Coronario Agudo: IAM con elevación del ST (ECG, ventana terapéutica, angioplastia vs trombolíticos) y SCA sin elevación del ST."},
        {"Día": "Jueves", "Tema Específico": "Insuficiencia Cardíaca (IC): IC con FE reducida y los 4 pilares farmacológicos con impacto en sobrevida (iSGLT2, ARNI/IECA, BB, ARM)."},
        {"Día": "Viernes", "Tema Específico": "Fibrilación Auricular (estratificación CHA2DS2-VASc y anticoagulación) + Batería de 20 choices."}
    ],
    "Semana 10 (Clínica Médica: Infectología y Arbovirosis)": [
        {"Día": "Lunes", "Tema Específico": "Dengue y Arbovirosis Urbanas: Fases clínicas, signos de alarma, clasificación por Grupos A, B, C, D y reposición con cristaloides."},
        {"Día": "Martes", "Tema Específico": "Tuberculosis (TBC): Diagnóstico con GeneXpert / Baciloscopía, esquema RIPE (2RIPE/4RI) y manejo de Tuberculosis Latente."},
        {"Día": "Miércoles", "Tema Específico": "VIH / SIDA: Diagnóstico serológico, inicio de TARV y profilaxis de infecciones oportunistas."},
        {"Día": "Jueves", "Tema Específico": "Infecciones del SNC: Meningitis bacteriana aguda (punción lumbar, LCR, antibiótico empírico + Dexametasona y quimioprofilaxis)."},
        {"Día": "Viernes", "Tema Específico": "Sepsis y Shock Séptico (Criterios Sepsis-3, bundle de la primera hora) + Batería de choices."}
    ],
    "Semana 11 (Clínica Médica: Endocrinología y Metabolismo)": [
        {"Día": "Lunes", "Tema Específico": "Diabetes Mellitus Tipo 2: Diagnóstico, metas de HbA1c, cambios en estilo de vida y farmacoterapia oral (Metformina, iSGLT2, GLP-1)."},
        {"Día": "Martes", "Tema Específico": "Insulinoterapia en DM: Indicaciones, esquemas basal-bolo y prevención de hipoglucemias."},
        {"Día": "Miércoles", "Tema Específico": "Cetoacidosis Diabética (CAD) y Estado Hiperglucémico Hiperosmolar (EHH): Criterios diferenciales, fluidoterapia, potasio e insulina EV."},
        {"Día": "Jueves", "Tema Específico": "Patología Tiroidea: Hipotiroidismo primario y subclínico (TSH/T4L, Levotiroxina), Hipertiroidismo y Enfermedad de Graves."},
        {"Día": "Viernes", "Tema Específico": "Manejo de Dislipemias y Riesgo Cardiovascular Global + Batería de choices."}
    ],
    "Semana 12 (Clínica Médica: Neumonología, Nefrología y Neurología)": [
        {"Día": "Lunes", "Tema Específico": "Asma y EPOC en el Adulto: Diagnóstico espirométrico, clasificación GOLD, manejo crónico y tratamiento de exacerbaciones."},
        {"Día": "Martes", "Tema Específico": "Neumonía Adquirida en la Comunidad (NAC): Score CURB-65 y esquemas antibióticos empíricos en internación vs ambulatorio."},
        {"Día": "Miércoles", "Tema Específico": "Medio Interno y Trastornos Hidroelectrolíticos: Hiponatremia (corrección) e Hiperkalemia grave (Gluconato de calcio y medidas de desplazamiento)."},
        {"Día": "Jueves", "Tema Específico": "Accidente Cerebrovascular (ACV): ACV Isquémico agudo, escala NIHSS, ventana para rtPA endovenoso (<4.5 h) y manejo de TA."},
        {"Día": "Viernes", "Tema Específico": "Cefaleas (Migraña, Tensional, Cluster y Red Flags) + Batería semanal de 20 choices."}
    ],
    "Semana 13 (Clínica Médica: Gastroenterología, Hematología y Endemias Brasil)": [
        {"Día": "Lunes", "Tema Específico": "Hemorragia Digestiva Alta (HDA variceal vs no variceal), Úlcera péptica, erradicación de H. pylori y Pancreatitis Aguda (Atlanta)."},
        {"Día": "Martes", "Tema Específico": "Hepatopatías Crónicas: Cirrosis y sus complicaciones (Ascitis, Peritonitis Bacteriana Espontánea, Encefalopatía Hepática)."},
        {"Día": "Miércoles", "Tema Específico": "Hematología: Diagnóstico diferencial de Anemias (Ferropénica, Megaloblástica por B12/Folato, Anemia de Trastornos Crónicos)."},
        {"Día": "Jueves", "Tema Específico": "Endemias Revalida Brasil: Leishmaniasis Visceral (Calazar), Chagas agudo/crónico, Esporotricosis, Esquistosomiasis y Accidentes Ofídicos."},
        {"Día": "Viernes", "Tema Específico": "Simulacro General de Clínica Médica (20 choices oficiales)."}
    ],
    "Semana 14 (Cirugía General: Trauma y Protocolo ATLS)": [
        {"Día": "Lunes", "Tema Específico": "Evaluación Inicial en Trauma (ABCDE): Manejo de vía aérea con protección cervical, intubación e indicaciones de cricotiroidostomía."},
        {"Día": "Martes", "Tema Específico": "Trauma Torácico: Neumotórax a Tensión (descompresión con aguja), Hemotórax Masivo y Taponamiento Cardíaco (Tríada de Beck)."},
        {"Día": "Miércoles", "Tema Específico": "Trauma Abdominal y Pelviano: Evaluación hemodinámica, ecografía FAST, TC con contraste y criterios de laparotomía vs manejo conservador."},
        {"Día": "Jueves", "Tema Específico": "Choque Hemorrágico en Trauma (Clases I a IV), Protocolo de Transfusión Masiva (1:1:1) y Ácido Tranexámico precoz."},
        {"Día": "Viernes", "Tema Específico": "Quemaduras (Fórmula de Parkland, vía aérea y quemaduras eléctricas) + Batería de choices."}
    ],
    "Semana 15 (Cirugía General: Abdomen Agudo Inflamatorio y Biliar)": [
        {"Día": "Lunes", "Tema Específico": "Apendicitis Aguda: Diagnóstico clínico, escala de Alvarado, ecografía/TC en casos dudosos y tratamiento quirúrgico."},
        {"Día": "Martes", "Tema Específico": "Patología Biliar: Cólico biliar, Colecistitis Aguda (Criterios de Tokyo) y Colecistectomía laparoscópica."},
        {"Día": "Miércoles", "Tema Específico": "Colangitis Aguda (Tríada de Charcot, Péntada de Reynolds y descompresión biliar urgente) y Coledocolitiasis (CPRE)."},
        {"Día": "Jueves", "Tema Específico": "Diverticulitis Aguda: TC como Gold Standard, clasificación de Hinchey y tratamiento médico vs quirúrgico."},
        {"Día": "Viernes", "Tema Específico": "Batería Semanal de Abdomen Agudo Inflamatorio."}
    ],
    "Semana 16 (Cirugía General: Oclusión, Pared Abdominal y Cirugía Pediátrica)": [
        {"Día": "Lunes", "Tema Específico": "Abdomen Agudo Obstructivo: Obstrucción de intestino delgado (bridas) vs colon (cáncer, vólvulo de sigmoides) e Isquemia Mesentérica."},
        {"Día": "Martes", "Tema Específico": "Patología de Pared Abdominal: Hernias inguinales (directa vs indirecta), crurales y umbilicales. Reducible vs Incarcerada vs Estrangulada."},
        {"Día": "Miércoles", "Tema Específico": "Patología Anorrectal Benigna: Hemorroides, Fisura Anal y Abscesos/Fístulas perianales."},
        {"Día": "Jueves", "Tema Específico": "Cirugía Pediátrica y Ortopedia: Estenosis Hipertrófica del Píloro, Invaginación Intestinal y Cadera Dolorosa (Kocher)."},
        {"Día": "Viernes", "Tema Específico": "Simulacro General de Cirugía (20 choices oficiales)."}
    ],
    "Semana 17 (Salud Pública: Epidemiología, Bioestadística y Bioética)": [
        {"Día": "Lunes", "Tema Específico": "Medidas de Frecuencia y Mortalidad: Incidencia acumulada, densidad de incidencia, prevalencia, tasa de mortalidad infantil y materna."},
        {"Día": "Martes", "Tema Específico": "Diseños de Estudios Epidemiológicos: Transversales, Casos y Controles (Odds Ratio), Cohortes (Riesgo Relativo) y Ensayos Clínicos."},
        {"Día": "Miércoles", "Tema Específico": "Pruebas Diagnósticas: Sensibilidad, Especificidad, Valor Predictivo Positivo (VPP) y Negativo (VPN), Curvas ROC."},
        {"Día": "Jueves", "Tema Específico": "Atención Primaria de la Salud (APS): Atributos de Starfield, Prevención Cuaternaria y Vigilancia Epidemiológica (SISA/SINAN)."},
        {"Día": "Viernes", "Tema Específico": "Bioética: Principios bioéticos, secreto profesional y comunicación de malas noticias (Protocolo SPIKES) + Choices."}
    ],
    "Semana 18 (Salud Pública: Marco Legal Argentina vs Sistema SUS Brasil)": [
        {"Día": "Lunes", "Tema Específico": "Leyes Sanitarias Argentina: Ley 26.529 (Derechos del Paciente, Consentimiento e Historia Clínica) y Ley 25.929 (Parto Humanizado)."},
        {"Día": "Martes", "Tema Específico": "Salud Mental en Argentina: Ley 26.657 (Criterio de internación involuntaria por 'riesgo cierto e inminente', interdisciplina y derechos)."},
        {"Día": "Miércoles", "Tema Específico": "Protección de Derechos de NNyA (Ley 26.061), Identidad de Género (Ley 26.743) y Autonomía Progresiva en Salud."},
        {"Día": "Jueves", "Tema Específico": "Sistema Único de Saúde (SUS Brasil): Constitución de 1988 (Arts. 196-200), Ley 8.080 (Principios) y Ley 8.142 (Participación Social)."},
        {"Día": "Viernes", "Tema Específico": "Estratégia Saúde da Família (ESF): Atribuciones del equipo y territorialización + Batería de 20 choices de Leyes/SUS."}
    ],
    "Semana 19 (Consolidación Teórica & Simulacros Intensivos I)": [
        {"Día": "Lunes", "Tema Específico": "Simulacro Cronometrado 1: 50 Preguntas Integradoras de Tocoginecología y Pediatría."},
        {"Día": "Martes", "Tema Específico": "Revisión Focalizada: Repaso de puntos débiles detectados en el Cuaderno de Errores."},
        {"Día": "Miércoles", "Tema Específico": "Simulacro Cronometrado 2: 50 Preguntas Integradoras de Clínica Médica y Cirugía General."},
        {"Día": "Jueves", "Tema Específico": "Revisión de Guía Comparativa AR vs BR (Dosis críticas, leyes y calendarios)."},
        {"Día": "Viernes", "Tema Específico": "Simulacro Completo de 100 Preguntas (Examen Oficial de Años Anteriores)."}
    ],
    "Semana 20 (Consolidación Teórica & Simulacros Intensivos II)": [
        {"Día": "Lunes", "Tema Específico": "Simulacro Completo 100 Preguntas: Foco en Preguntas Trampa y Distractores Frecuentes."},
        {"Día": "Martes", "Tema Específico": "Revisión Completa del Cuaderno Blanco (Reglas de Oro personales para no volver a fallar)."},
        {"Día": "Miércoles", "Tema Específico": "Repaso Ultrarrápido de High-Yield Pearls de las 5 Grandes Áreas Troncales."},
        {"Día": "Jueves", "Tema Específico": "Simulacro Final de 100 Preguntas con Tiempo Real (4 horas)."},
        {"Día": "Viernes", "Tema Específico": "Cierre de Estudio, Estrategia de Manejo del Tiempo y Preparación Mental."}
    ]
}

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
            users_df = get_sheet_data("users")
            if not users_df.empty and "username" in users_df.columns:
                user_row = users_df[users_df["username"] == u_input.lower()]
                if not user_row.empty and user_row.iloc[0]["password_hash"] == hash_password(p_input):
                    st.session_state.authenticated = True
                    st.session_state.current_user = user_row.iloc[0]["username"]
                    st.session_state.user_name = user_row.iloc[0]["nombre"]
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
            else:
                st.error("Error al conectar con la base de datos de usuarios.")
                
    with col2:
        with st.expander("Crear una nueva cuenta"):
            new_u = st.text_input("Nuevo Usuario")
            new_n = st.text_input("Tu Nombre")
            new_p = st.text_input("Nueva Contraseña", type="password")
            if st.button("Registrarse"):
                if new_u and new_p:
                    users_df = get_sheet_data("users")
                    if not users_df.empty and new_u.lower() in users_df["username"].values:
                        st.error("El usuario ya existe.")
                    else:
                        new_row = pd.DataFrame([{
                            "username": new_u.lower(),
                            "password_hash": hash_password(new_p),
                            "nombre": new_n
                        }])
                        users_updated = pd.concat([users_df, new_row], ignore_index=True)
                        save_sheet_data("users", users_updated)
                        st.success("Cuenta creada exitosamente. Ya podés iniciar sesión.")

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
    
    error_df = get_sheet_data("error_log")
    if not error_df.empty and "username" in error_df.columns:
        user_logs = error_df[error_df["username"] == st.session_state.current_user]
        total_hechas = len(user_logs)
        total_correctas = len(user_logs[user_logs["es_correcta"] == 1])
    else:
        total_hechas = 0
        total_correctas = 0

    precision = int((total_correctas / total_hechas * 100)) if total_hechas > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔥 Racha Activa", "14 Días")
    col2.metric("🎯 Precisión Personal", f"{precision}%")
    col3.metric("📝 Choices Realizados", str(total_hechas))
    col4.metric("📅 Estado de Meta", "Semana 1 / Tocogineco")

    st.markdown("---")
    st.subheader("🧠 Repaso Espaciado Programado para Hoy")
    
    today = str(datetime.now().date())
    choices_df = get_sheet_data("choices")
    
    if not choices_df.empty and "next_review" in choices_df.columns:
        due_choices = choices_df[choices_df["next_review"] <= today]
    else:
        due_choices = pd.DataFrame()

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
# 2. CRONOGRAMA SEMANAL DETALLADO
# -------------------------------------------------------------
elif menu == "📅 Cronograma Semanal Detallado":
    st.header("📅 Cronograma Completo y Exhaustivo (Semanas 1 a 20)")
    st.caption("Planificación estructurada de 1 a 2 horas diarias de lunes a viernes.")

    sem_select = st.selectbox("Seleccioná la semana a visualizar en detalle:", list(cronograma_desglosado.keys()))
    df_sem = pd.DataFrame(cronograma_desglosado[sem_select])
    st.dataframe(df_sem, use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# 3. TEMARIO, ALGORITMOS & QUIZ RÁPIDO
# -------------------------------------------------------------
elif menu == "📚 Temario, Algoritmos & Quiz":
    st.header("📚 Temario Clínico, Algoritmos & Autoevaluación")
    st.caption("Seleccioná la semana y el tema específico del cronograma para estudiar o autoevaluarte.")

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        semana_estudio = st.selectbox("1. Elegí la Semana de Estudio:", list(cronograma_desglosado.keys()))
    
    temas_de_la_semana = [f"{item['Día']}: {item['Tema Específico']}" for item in cronograma_desglosado[semana_estudio]]
    
    with col_t2:
        tema_dia_sel = st.selectbox("2. Elegí el Tema del Día:", temas_de_la_semana)

    tema_limpio = tema_dia_sel.split(":", 1)[1].strip() if ":" in tema_dia_sel else tema_dia_sel

    st.markdown(f"### 🎯 Estudiando: *{tema_limpio[:70]}...*")

    t1, t2, t3, t4 = st.tabs(["🧠 Diagrama de Flujo / Algoritmo", "⚡ High-Yield Pearls con IA", "⚖️ Comparativa AR vs BR", "📝 Quiz Rápido del Tema (5 Preguntas)"])

    with t1:
        st.subheader("Algoritmo Clínico Interactivo")
        
        if st.button("✨ Generar Algoritmo con IA para este tema", key="btn_algo_dinamico"):
            if not model:
                st.error("Error: Verificá que tu API Key de Gemini esté en Secrets.")
            else:
                with st.spinner(f"Diseñando diagrama de flujo para: {tema_limpio[:50]}..."):
                    prompt = f"""
                    Generá un diagrama de flujo en código Mermaid.js sobre el diagnóstico y conducta clínica de: {tema_limpio}.
                    
                    REGLAS DE SINTAXIS ESTRICTAS:
                    1. Empezá con 'graph TD'.
                    2. TODO el texto dentro de corchetes o llaves DEBE ir entre comillas dobles: A["Texto"] o B{{"Decisión"}}.
                    3. Cada conexión DEBE estar en una línea separada.
                    4. NO uses caracteres especiales sin comillas.
                    5. Devolvé ÚNICAMENTE el bloque Mermaid, sin texto previo ni posterior.
                    """
                    try:
                        res = model.generate_content(prompt)
                        mermaid_code = res.text.replace("```mermaid", "").replace("```", "").strip()
                        mermaid_clean = re.sub(r'(\})\s*([A-Za-z0-9_]+)', r'\1\n\2', mermaid_code)
                        mermaid_clean = re.sub(r'(\])\s*([A-Za-z0-9_]+)', r'\1\n\2', mermaid_clean)

                        st.markdown(f"""
                        ```mermaid
                        {mermaid_clean}
                        ```
                        """)
                    except Exception as err:
                        st.error(f"Error generando algoritmo: {err}")

    with t2:
        st.subheader("⚡ Resumen High-Yield & Perlas Clave")
        if st.button("✨ Generar Puntos Clave de Examen con IA", key="btn_pearls"):
            if not model:
                st.error("API de Gemini no configurada.")
            else:
                with st.spinner("Extrayendo conceptos más tomados..."):
                    p_prompt = f"Generá 4 perlas clínicas clave y de alta incidencia sobre '{tema_limpio}' para exámenes de residencia médica. Sé directo, concreto y enumerá en viñetas con negrita."
                    try:
                        p_res = model.generate_content(p_prompt)
                        st.markdown(p_res.text)
                    except Exception as err:
                        st.error(f"Error: {err}")

    with t3:
        st.subheader("⚖️ Diferencias Normativas Argentina vs. Brasil")
        if st.button("✨ Comparar Enfoque AR vs BR con IA", key="btn_comp"):
            if not model:
                st.error("API de Gemini no configurada.")
            else:
                with st.spinner("Comparando protocolos sanitarios..."):
                    c_prompt = f"Explicá brevemente las diferencias clave de protocolo o guías clínicas entre Argentina y Brasil para '{tema_limpio}'. Si son idénticos, indicalo."
                    try:
                        c_res = model.generate_content(c_prompt)
                        st.markdown(c_res.text)
                    except Exception as err:
                        st.error(f"Error: {err}")

    with t4:
        st.subheader("🎯 Quiz Rápido del Tema (5 Preguntas)")
        palabras = [w for w in tema_limpio.split() if len(w) > 4][:2]
        query_kw = palabras[0].lower() if palabras else ""
        
        choices_df = get_sheet_data("choices")
        if not choices_df.empty and "tema" in choices_df.columns:
            quiz_q = choices_df[choices_df["tema"].astype(str).str.lower().str.contains(query_kw, na=False)].head(5)
        else:
            quiz_q = pd.DataFrame()

        if len(quiz_q) == 0:
            st.info(f"No hay choices guardados sobre '{tema_limpio[:40]}...'. Podés generar preguntas en la solapa '✨ Generador de Choices con IA'.")
        else:
            for idx, (_, q_row) in enumerate(quiz_q.iterrows()):
                st.markdown(f"**Pregunta {idx+1}:** {q_row['pregunta']}")
                ans = st.radio(
                    f"Opciones para P{idx+1}:",
                    [f"A) {q_row['opcion_a']}", f"B) {q_row['opcion_b']}", f"C) {q_row['opcion_c']}", f"D) {q_row['opcion_d']}"],
                    key=f"quiz_din_{q_row['id']}"
                )
                if st.button(f"Comprobar P{idx+1}", key=f"btn_din_{q_row['id']}"):
                    if ans[0] == q_row['correcta']:
                        st.success(f"¡Correcto! Opción {q_row['correcta']}")
                    else:
                        st.error(f"Incorrecto. La respuesta oficial era la opción {q_row['correcta']}.")
                    st.info(q_row['justificacion'])
                st.markdown("---")

# -------------------------------------------------------------
# 4. GENERADOR AUTOMÁTICO DE CHOICES CON IA (AMPLIADO A 20)
# -------------------------------------------------------------
elif menu == "✨ Generador de Choices con IA":
    st.header("✨ Generador Automático de Choices Médicos con IA")
    st.caption("Creá preguntas de opción múltiple que se guardan en Google Sheets.")

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        tema_ia = st.text_input("Tema a evaluar:", value="Preeclampsia Severa y Manejo de Crisis")
        area_ia = st.selectbox("Especialidad:", ["Tocoginecología", "Pediatría", "Clínica Médica", "Cirugía General", "Salud Pública y Leyes"])
    with col_g2:
        enfoque_ia = st.selectbox("Estilo de Examen:", ["🇦🇷 Examen Único / CABA (Argentina)", "🇧🇷 Revalida INEP (Brasil)"])
        cant_q = st.slider("Cantidad de preguntas a generar (Máximo 20):", min_value=1, max_value=20, value=5)

    if st.button("🚀 Generar y Guardar Choices en Google Sheets"):
        if not model:
            st.error("Error al conectar con la API de Gemini.")
        else:
            with st.spinner(f"La IA está redactando {cant_q} casos clínicos con distractores y justificación oficial..."):
                prompt = f"""
                Actuá como miembro del comité evaluador médico de residencias médicas ({enfoque_ia}).
                Generá exactamente {cant_q} preguntas de opción múltiple de alta calidad médica sobre: '{tema_ia}' en el área de '{area_ia}'.
                
                Devolvé ÚNICAMENTE un arreglo JSON válido (sin texto antes ni después) con esta estructura exacta:
                [
                  {{
                    "pregunta": "Caso clínico detallado...",
                    "opcion_a": "Texto opción A",
                    "opcion_b": "Texto opción B",
                    "opcion_c": "Texto opción C",
                    "opcion_d": "Texto opción D",
                    "correcta": "A", 
                    "justificacion": "Explicación médica detallada citando guías vigentes."
                  }}
                ]
                """
                try:
                    response = model.generate_content(prompt)
                    clean_json = response.text.replace("```json", "").replace("```", "").strip()
                    generated_list = json.loads(clean_json)

                    choices_df = get_sheet_data("choices")
                    new_rows = []
                    for item in generated_list:
                        new_rows.append({
                            "id": f"IA-{random.randint(10000, 99999)}",
                            "examen_origen": f"✨ IA ({enfoque_ia[:8]})",
                            "area": area_ia,
                            "tema": tema_ia,
                            "incidencia": "Prioridad A",
                            "pregunta": item["pregunta"],
                            "opcion_a": item["opcion_a"],
                            "opcion_b": item["opcion_b"],
                            "opcion_c": item["opcion_c"],
                            "opcion_d": item["opcion_d"],
                            "correcta": item["correcta"].upper(),
                            "justificacion": item["justificacion"],
                            "drive_link": "https://drive.google.com",
                            "next_review": str(datetime.now().date()),
                            "interval_days": 1,
                            "ease_factor": 2.5,
                            "repetitions": 0
                        })
                    
                    updated_choices = pd.concat([choices_df, pd.DataFrame(new_rows)], ignore_index=True)
                    save_sheet_data("choices", updated_choices)

                    st.success(f"🎉 ¡Se generaron y guardaron {len(new_rows)} choices en Google Sheets!")
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

    choices_df = get_sheet_data("choices")
    if choices_df.empty:
        st.warning("No hay choices cargados en Google Sheets. Podés generarlos con IA o cargar un CSV.")
    else:
        modo_practica = st.radio("Modalidad de Estudio:", ["📚 Por Área Específica", "🎲 Simulacro Aleatorio"], horizontal=True)

        if modo_practica == "📚 Por Área Específica":
            area_sel = st.selectbox("Seleccioná el Área Médica:", choices_df["area"].dropna().unique())
            filtered_df = choices_df[choices_df["area"] == area_sel].reset_index(drop=True)
        else:
            filtered_df = choices_df.sample(frac=1).reset_index(drop=True)

        if filtered_df.empty:
            st.warning("No hay preguntas disponibles para esta selección.")
        else:
            q_idx = st.selectbox(
                "Seleccionar Pregunta a Resolver:",
                range(len(filtered_df)),
                format_func=lambda x: f"P#{x+1}: {filtered_df.iloc[x]['tema']} ({filtered_df.iloc[x]['examen_origen']})"
            )
            q = filtered_df.iloc[q_idx]

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

                error_df = get_sheet_data("error_log")
                new_log = pd.DataFrame([{
                    "id": random.randint(100000, 999999),
                    "username": st.session_state.current_user,
                    "choice_id": str(q['id']),
                    "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "respuesta_dada": letra_elegida,
                    "es_correcta": es_correcta,
                    "flag_duda": 1 if flag_duda else 0,
                    "motivo_error": "",
                    "regla_oro": ""
                }])
                save_sheet_data("error_log", pd.concat([error_df, new_log], ignore_index=True))

                if es_correcta:
                    st.success(f"🎉 ¡CORRECTO! Opción {q['correcta']}")
                else:
                    st.error(f"❌ INCORRECTO. La respuesta oficial era la opción {q['correcta']}.")

                st.info(f"**Fundamento Clínico:** {q['justificacion']}")

# -------------------------------------------------------------
# 6. CUADERNO DE ERRORES
# -------------------------------------------------------------
elif menu == "📕 Cuaderno de Errores":
    st.header(f"📕 Libro de Errores | {st.session_state.user_name}")

    error_df = get_sheet_data("error_log")
    choices_df = get_sheet_data("choices")

    if not error_df.empty and not choices_df.empty:
        user_errors = error_df[(error_df["username"] == st.session_state.current_user) & ((error_df["es_correcta"] == 0) | (error_df["flag_duda"] == 1))]
        merged = user_errors.merge(choices_df, left_on="choice_id", right_on="id", suffixes=('_log', '_choice'))
    else:
        merged = pd.DataFrame()

    if merged.empty:
        st.success("✨ ¡Felicitaciones! No tenés errores ni dudas registradas.")
    else:
        st.info(f"Tenés **{len(merged)} preguntas registradas** para análisis.")
        for idx, row in merged.iterrows():
            with st.expander(f"❌ {row['area']} | {row['tema']} ({row['examen_origen']}) | Tu opción: {row['respuesta_dada']} | Correcta: {row['correcta']}"):
                st.write(f"**Enunciado:** {row['pregunta']}")
                st.write(f"**Justificación:** {row['justificacion']}")
                
                motivo = st.selectbox("¿Por qué fallaste?", ["Error de lectura / Apuro", "Duda 50/50", "Falta de teoría", "Confusión de dosis"], key=f"mot_{row['id_log']}")
                regla = st.text_input("💡 Tu regla para evitarlo la próxima:", value=str(row['regla_oro']) if pd.notna(row['regla_oro']) else "", key=f"reg_{row['id_log']}")
                
                if st.button("Guardar en mi Bitácora", key=f"save_b_{row['id_log']}"):
                    error_df.loc[error_df["id"] == row["id_log"], "motivo_error"] = motivo
                    error_df.loc[error_df["id"] == row["id_log"], "regla_oro"] = regla
                    save_sheet_data("error_log", error_df)
                    st.success("Guardado en Google Sheets.")

# -------------------------------------------------------------
# 7. GUÍA COMPARATIVA AR VS BR
# -------------------------------------------------------------
elif menu == "⚖️ Guía Comparativa AR vs BR":
    st.header("⚖️ Matriz Comparativa Oficial: Argentina vs. Brasil")

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

    error_df = get_sheet_data("error_log")
    choices_df = get_sheet_data("choices")

    if not error_df.empty and not choices_df.empty:
        user_logs = error_df[error_df["username"] == st.session_state.current_user]
        metrics_df = user_logs.merge(choices_df, left_on="choice_id", right_on="id")
    else:
        metrics_df = pd.DataFrame()

    if metrics_df.empty:
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
    st.header("⚙️ Importar Lotes de Preguntas a Google Sheets")
    
    uploaded_csv = st.file_uploader("Subir archivo CSV", type=["csv"])
    if uploaded_csv is not None:
        df_up = pd.read_csv(uploaded_csv)
        st.write("Vista previa:")
        st.dataframe(df_up.head(3))
        if st.button("Guardar en Google Sheets"):
            choices_df = get_sheet_data("choices")
            updated = pd.concat([choices_df, df_up], ignore_index=True)
            save_sheet_data("choices", updated)
            st.success(f"¡Se agregaron {len(df_up)} preguntas a tu Google Sheet!")
