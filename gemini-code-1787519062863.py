import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import random
import hashlib
import json
import re
import google.generativeai as genai

# Conexión a Google Sheets
try:
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    st.error("Instalando dependencias necesarias. Por favor esperá unos segundos o reiniciá la app.")
    st.stop()

# -------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# -------------------------------------------------------------
st.set_page_config(
    page_title="Super Médicos | Residencias & Revalida",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)
st.markdown("""
<style>
...
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# INICIALIZACIÓN DE GEMINI AI
# -------------------------------------------------------------
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")

model = None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-3.6-flash")
    except Exception as e:
        model = None
        
# -------------------------------------------------------------
# CONEXIÓN OPTIMIZADA A GOOGLE SHEETS (ALTA VELOCIDAD)
# -------------------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)
SPREADSHEET_URL = st.secrets.get("SPREADSHEET_URL", "")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@st.cache_data(ttl=60)
def get_sheet_data(worksheet_name):
    try:
        return conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl="60s")
    except Exception:
        return pd.DataFrame()

def save_sheet_data(worksheet_name, df):
    try:
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=df)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Error al guardar en Google Sheets: {e}")

def calcular_racha_activa(username, error_df, progreso_df):
    """Calcula los días consecutivos de actividad para un usuario."""
    fechas_actividad = set()
    
    # 1. Fechas de choices respondidos
    if not error_df.empty and "username" in error_df.columns and "fecha" in error_df.columns:
        user_err = error_df[error_df["username"].astype(str) == username]
        for f in user_err["fecha"].dropna():
            try:
                # Extrae la parte YYYY-MM-DD
                fechas_actividad.add(str(f)[:10])
            except Exception:
                pass

    # 2. Fechas de temas marcados en el cronograma (si hay registros)
    if not progreso_df.empty and "username" in progreso_df.columns:
        user_prog = progreso_df[progreso_df["username"].astype(str) == username]
        if "fecha" in user_prog.columns:
            for f in user_prog["fecha"].dropna():
                try:
                    fechas_actividad.add(str(f)[:10])
                except Exception:
                    pass

    if not fechas_actividad:
        return 0

    # Fechas únicas ordenadas como objetos date
    fechas_validas = []
    for f_str in fechas_actividad:
        try:
            fechas_validas.append(datetime.strptime(f_str.strip(), "%Y-%m-%d").date())
        except Exception:
            pass

    if not fechas_validas:
        return 0

    fechas_set = set(fechas_validas)
    hoy = datetime.now().date()
    ayer = hoy - timedelta(days=1)

    # Si hubo actividad hoy, arrancamos desde hoy; si no, desde ayer (si hubo)
    if hoy in fechas_set:
        cursor = hoy
    elif ayer in fechas_set:
        cursor = ayer
    else:
        return 0  # Se rompió la racha

    racha = 0
    while cursor in fechas_set:
        racha += 1
        cursor -= timedelta(days=1)

    return racha
        
# -------------------------------------------------------------
# CRONOGRAMA MAESTRO DE ESTUDIO (20 SEMANAS ESTRUCTURADAS)
# -------------------------------------------------------------
cronograma_desglosado = {
    # =========================================================
    # MÓDULO I: TOCOGINECOLOGÍA (SEMANAS 1 A 4)
    # =========================================================
    "Semana 1: Ginecología Pura": [
        {"Día": "Lunes", "Tema Específico": "Infecciones Cervicovaginales y EPI: Vulvovaginitis (Amsel en Vaginosis vs Candidiasis vs Tricomoniasis), Cervicitis mucopurulenta (Gonococo + Clamidia) y EPI (Monif, indicación ambulatoria Ceftriaxona + Doxiciclina + Metronidazol vs hospitalaria)."},
        {"Día": "Martes", "Tema Específico": "Patología Cervical y Tamizaje: Citología Bethesda (ASC-US, LSIL, HSIL), algoritmos de colposcopía y conización (CAF/cono frío). Consenso FASGO: PAP desde los 25 años (1 anual, luego de 2 negativos cada 3 años hasta los 65)."},
        {"Día": "Miércoles", "Tema Específico": "Endocrinología Ginecológica: Sangrado Uterino Anormal (FIGO PALM-COEIN: pólipos, miomas submucosos, adenomiosis) y Síndrome de Ovario Poliquístico (criterios de Rotterdam, resistencia insulínica, manejo)."},
        {"Día": "Jueves", "Tema Específico": "Patología Mamaria y Cáncer Ginecológico: Nódulo mamario (fibroadenoma vs quiste), BI-RADS, tamizaje de mama (anual a los 40 en Argentina vs bienal 50-74 en Brasil). Cáncer de Endometrio (grosor eco postmenopausia: ≥4 mm sin TRH / ≥8 mm con TRH) y Cáncer de Ovario/Tumores anexiales."},
        {"Día": "Viernes", "Tema Específico": "Amenorreas y Climaterio: Primarias (algoritmo Rokitansky 46,XX con vello vs Morris 46,XY sin vello vs Turner 45,X0) y secundarias (prueba de progesterona). Climaterio y Terapia Hormonal (indicaciones, contraindicaciones y vía transdérmica) + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "Bloque masivo de 70 choices oficiales de Ginecología (INEP + Examen Único/CABA)."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: SUS Brasil (Leyes 8.080 y 8.142: principios doctrinarios, organizativos y participación comunitaria) + Cuaderno de Errores."}
    ],

    "Semana 2: Obstetricia Pura – Primera Mitad y Urgencias": [
        {"Día": "Lunes", "Tema Específico": "Trastornos Hipertensivos del Embarazo I: Preeclampsia con/sin severidad: diagnóstico, metas TA y conductas. Manejo farmacológico agudo (Labetalol EV, Hidralazina EV) y prevención de eclampsia (Sulfato de Magnesio: Zuspan/Sibai, intoxicación y Gluconato de Calcio)."},
        {"Día": "Martes", "Tema Específico": "Trastornos Hipertensivos del Embarazo II: Eclampsia, Síndrome HELLP (laboratorio de microangiopatía, plaquetas, enzimas hepáticas) e Hipertensión Crónica / Preeclampsia sobreimpuesta (Guía HTA MSAL)."},
        {"Día": "Miércoles", "Tema Específico": "Hemorragias 1ª Mitad e Infecciones: Aborto (amenaza, incompleto, diferido, séptico; legrado vs AMEU), Embarazo Ectópico (metotrexato vs laparoscopía) y Mola hidatidiforme (completa vs parcial). Herpes Genital (profilaxis Aciclovir sem 36; cesárea si hay vesículas activas)."},
        {"Día": "Jueves", "Tema Específico": "Infecciones Perinatales y Control Prenatal: Sífilis Gestacional (VDRL, penicilina benzatínica según estadio, tratamiento de la pareja), ITU gestacional (tratamiento obligado de Bacteriuria Asintomática) y Toxoplasmosis (IgG, IgM, avidez y espiramicina)."},
        {"Día": "Viernes", "Tema Específico": "Complicaciones Médicas y Aloinmunización: Diabetes Gestacional (PTOG, metas glucémicas, insulina), Aloinmunización Rh (gammaglobulina anti-D a las 28 semanas y postparto) y Anemia gestacional + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "Bloque de 70 choices oficiales de hipertensión gestacional, hemorragias tempranas e infecciones perinatales."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Leyes Argentinas (Ley 26.529 de Derechos del Paciente: autonomía, rechazo de tratamientos, consentimiento informado) + Cuaderno de Errores."}
    ],

    "Semana 3: Obstetricia Pura – Segunda Mitad y Puerperio": [
        {"Día": "Lunes", "Tema Específico": "Hemorragias de la Segunda Mitad: Diagnóstico diferencial clínico y ecográfico: Desprendimiento Prematuro de Placenta (DPPNI: hipertonía, Couvelaire) vs Placenta Previa (sangrado indoloro, rojo rutilante, no tacto) vs Rotura Uterina vs Rotura de Vasa Previa."},
        {"Día": "Martes", "Tema Específico": "Amenaza de Parto Prematuro y RPMO: RPMO (manejo conservador vs activo y latencia), Corioamnionitis (criterios de Gibbs) y Parto Prematuro (tocólisis nifedipina, maduración betametasona y neuroprotección con Sulfato de Magnesio <32 sem)."},
        {"Día": "Miércoles", "Tema Específico": "Trabajo de Parto y Partograma: Fisiología, periodos clínicos, partograma y distocias (fase activa prolongada, detención secundaria, expulsivo prolongado). Ley 25.929 de Parto Humanizado."},
        {"Día": "Jueves", "Tema Específico": "Hemorragia Puerperal e Infección: Manejo de las 4T (tono, trauma, tejido, trombina; masaje, oxitocina, ergometrina, misoprostol, tranexámico, balón de compresión) y Endometritis (Clindamicina + Gentamicina). Tamizaje HTLV-1/2 (contraindicación absoluta de lactancia)."},
        {"Día": "Viernes", "Tema Específico": "Repaso de Obstetricia: Estática fetal, indicaciones de cesárea y profilaxis de Streptococcus agalactiae intraparto (Penicilina EV) + 25 choices oficiales de obstetricia tardía."},
        {"Día": "Sábado", "Tema Específico": "Bloque masivo de 70 choices oficiales de hemorragias del 3º trimestre, distocias y puerperio."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: SUS Brasil (Niveles de Atención y Tuberculosis/TDO) + Cuaderno de Errores."}
    ],

    "Semana 4: Salud Reproductiva y Cruce Regulatorio": [
        {"Día": "Lunes", "Tema Específico": "Marco Legal de Salud Sexual: Interrupción del Embarazo: Ley 27.610 Argentina (IVE hasta sem 14 inclusive; ILE por causales sin límite gestacional; plazo 10 días, objeción de conciencia individual) vs causales legales de aborto en Brasil."},
        {"Día": "Martes", "Tema Específico": "Atención a Víctimas de Violencia Sexual: Protocolo de guardia: profilaxis ITS (Ceftriaxona + Azitromicina + Penicilina benzatínica), PEP HIV (Tenofovir + Lamivudina + Dolutegravir 28 días <72h), Levonorgestrel, notificación obligatoria sin exigencia de denuncia."},
        {"Día": "Miércoles", "Tema Específico": "Planificación Familiar: Criterios Médicos de Elegibilidad OMS, métodos hormonales combinados vs progestágenos, DIU T-Cobre y SIU-Levonorgestrel, colocación postparto y lactancia."},
        {"Día": "Jueves", "Tema Específico": "Infertilidad y Úlceras Genitales: Estudio de pareja infértil (espermograma, histerosalpingografía con Cotte, progesterona lútea). Diagnóstico diferencial de úlceras (Sífilis primaria vs Cancroide vs Herpes vs Linfogranuloma venéreo vs Donovanosis)."},
        {"Día": "Viernes", "Tema Específico": "Simulacro Integrador de Tocoginecología: Batería cronometrada de 30 choices combinando casos clínicos transversales."},
        {"Día": "Sábado", "Tema Específico": "Simulacro Oficial Completo de Tocoginecología (80 a 100 choices) integrando Examen Único, CABA, Privados e INEP/Revalida."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Leyes Argentinas (Ley 26.061 Protección de Niñez y Ley 26.743 Identidad de Género: autonomía desde los 16 años) + Cuaderno de Errores de Tocoginecología."}
    ],

    # =========================================================
    # MÓDULO II: PEDIATRÍA Y NEONATOLOGÍA (SEMANAS 5 A 8)
    # =========================================================
    "Semana 5: Pediatría – Niño Sano, Puericultura y Nutrición": [
        {"Día": "Lunes", "Tema Específico": "Crecimiento y Somatometría: Curvas OMS, percentilos, velocidad de crecimiento y desnutrición aguda/crónica (Marasmo calórico vs Kwashiorkor proteico)."},
        {"Día": "Martes", "Tema Específico": "Neurodesarrollo y Puericultura: Hitos motores gruesos/finos, lenguaje, pauta social, reflejos arcaicos y tamizaje de TEA con M-CHAT."},
        {"Día": "Miércoles", "Tema Específico": "Lactancia Materna y Alimentación Complementaria: Técnicas, contraindicaciones absolutas y pautas de incorporación de semisólidos."},
        {"Día": "Jueves", "Tema Específico": "Anemia Infantil y Suplementación: Profilaxis y tratamiento de anemia ferropénica (Guía SAP: 6 mg/kg/día de hierro elemental vs protocolo MS Brasil)."},
        {"Día": "Viernes", "Tema Específico": "Prevención de Accidentes y Crianza: Sueño Seguro SAP (posición supina, no colecho de riesgo) + Sospecha de Maltrato infantil (notificación Ley 26.061) + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "70 choices oficiales de Puericultura, Crecimiento y Nutrición pediátrica."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Vacunas Argentina (Rotavirus 2-4m, MenACWY 3-5-15m, dTPa y HPV dosis única a los 11 años, VSR en gestantes sem 32-36) + Flash-Review Ginecología (Vulvovaginitis y PAP)."}
    ],

    "Semana 6: Pediatría – Infecciones Respiratorias y Exantemáticas": [
        {"Día": "Lunes", "Tema Específico": "Bronquiolitis Aguda: 1º episodio de sibilancias <2 años, score de Tal, oxigenoterapia de soporte y pauta SAP (no salbutamol, no corticoides, no kinesioterapia respiratoria en 1º episodio)."},
        {"Día": "Martes", "Tema Específico": "Neumonía Adquirida en la Comunidad (NAC): Etiología por edad (S. pneumoniae, virus, Mycoplasma), clínica típica vs atípica, Amoxicilina oral ambulatoria y criterios de internación."},
        {"Día": "Miércoles", "Tema Específico": "Vía Aérea Superior: Crup/Laringitis (Dexametasona VO/IM y adrenalina nebulizada), Epiglotitis y Coqueluche. Otitis Media Aguda (Amoxicilina 80-90 mg/kg/día) y Faringoamigdalitis estreptocócica (criterios de Centor)."},
        {"Día": "Jueves", "Tema Específico": "Asma Pediátrica: Crisis obstructiva, rescate reglado con Salbutamol en aerosol con aerocámara, sulfato de magnesio EV en refractarias y corticoides sistémicos."},
        {"Día": "Viernes", "Tema Específico": "Exantemáticas Infantiles: Sarampión (Koplik), Rubéola, Escarlatina, Varicela, Eritema infeccioso, Kawasaki (Gammaglobulina EV + AAS) y Enfermedad Mano-Pie-Boca (Coxsackie A16) + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "Bloque de 70 choices oficiales de patología respiratoria e infectología pediátrica."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Calendario PNI Brasil (rescate Febre Amarela, BCG, VOP) + Flash-Review Obstetricia (Hipertensión y Hemorragias)."}
    ],

    "Semana 7: Pediatría – Urgencias, Gastro, Nefro y Medio Interno": [
        {"Día": "Lunes", "Tema Específico": "Diarrea Aguda y Deshidratación: Evaluación clínica y Planes OMS (Plan A ambulatorio con zinc, Plan B con SRO en centro de salud, Plan C de shock con expansión rápida de SF 0.9%)."},
        {"Día": "Martes", "Tema Específico": "SUH y Salud Mental: Síndrome Urémico Hemolítico (STEC O157:H7, tríada clásica: anemia microangiopática, plaquetopenia, falla renal; contraindicación de antibióticos). TDAH y Trastorno Opositivo Desafiador (criterios clínicos, metilfenidato)."},
        {"Día": "Miércoles", "Tema Específico": "Infección Urinaria y Fiebre sin Foco: Toma de muestra estéril (punción vs cateterismo vs chorro limpio), tratamiento empírico y criterios de ecografía renal en primera ITU febril."},
        {"Día": "Jueves", "Tema Específico": "Síndromes Convulsivos: Convulsión febril simple vs compleja y Espasmos infantiles (Síndrome de West: hipsarritmia, espasmos, retraso madurativo)."},
        {"Día": "Viernes", "Tema Específico": "Cetoacidosis Diabética Pediátrica (CAD): Secuencia obligatoria: 1° expandir con SF 0.9%, 2° verificar/reponer potasio, 3° infusión continua de insulina regular EV sin bolo inicial + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "70 choices de urgencias pediátricas, nefrología y medio interno infantil."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Estrategia AIDPI Brasil (neumonía y diarrea en APS) + Flash-Review Obstetricia (Partograma y Hemorragia Puerperal)."}
    ],

    "Semana 8: Neonatología Pura y Cierre de Pediatría": [
        {"Día": "Lunes", "Tema Específico": "Reanimación Cardiopulmonar Neonatal (algoritmo SBP/SAP): Pasos iniciales en RN deprimido o con meconio, VPP con máscara, masaje cardíaco y adrenalina."},
        {"Día": "Martes", "Tema Específico": "Dificultad Respiratoria Neonatal: Diagnóstico diferencial de Taquipnea Transitoria (TTN / pulmón húmedo) vs Membrana Hialina (prematuros) vs Aspiración Meconial (SAM en postérmino)."},
        {"Día": "Miércoles", "Tema Específico": "Ictericia Neonatal: Fisiológica vs patológica (<24 h o bilirrubina directa >1 mg/dL), incompatibilidad ABO/Rh, luminoterapia y exanguinotransfusión."},
        {"Día": "Jueves", "Tema Específico": "Sepsis Neonatal e Infecciones Congénitas (TORCH): Sepsis precoz (SGB, E. coli: ampicilina + gentamicina) vs tardía; Toxoplasmosis (Tétrada de Sabin), CMV y Chagas congénito."},
        {"Día": "Viernes", "Tema Específico": "Pesquisa Neonatal Obligatoria: Pesquisa metabólica (hipotiroidismo congénito, FQ, PKU, hiperplasia suprarrenal), reflejo rojo ocular y otoemisiones acústicas + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "Simulacro General de Pediatría y Neonatología (80 choices)."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Cuaderno de Errores de Pediatría + Flash-Review Bloque Completo de Tocoginecología (25 choices)."}
    ],

    # =========================================================
    # MÓDULO III: CIRUGÍA GENERAL Y TRAUMA (SEMANAS 9 A 11)
    # =========================================================
    "Semana 9: Trauma y Soporte Vital Quirúrgico (ATLS)": [
        {"Día": "Lunes", "Tema Específico": "Evaluación Inicial en Trauma (ABCDE): Vía aérea con control cervical, intubación de secuencia rápida y cricotiroidostomía quirúrgica de urgencia en trauma maxilofacial grave."},
        {"Día": "Martes", "Tema Específico": "Trauma Torácico y Neurotrauma: Neumotórax a tensión (descompresión con aguja/catéter 5º EIC LAA sin esperar Rx), Hemotórax masivo (>1500 mL), Taponamiento (Beck). TEC: Glasgow, TAC cráneo; Hematoma epidural (arteria meníngea media, intervalo lúcido, biconvexa) vs subdural (venas puente, semiluna)."},
        {"Día": "Miércoles", "Tema Específico": "Shock Hemorrágico en Trauma: Clasificación clínica (Clases I a IV), protocolo de transfusión masiva (plasma, plaquetas y glóbulos rojos 1:1:1) y Ácido Tranexámico precoz dentro de las 3 horas."},
        {"Día": "Jueves", "Tema Específico": "Trauma Abdominal y Pelviano: Evaluación hemodinámica, ecografía FAST (Morrison, esplenorrenal, suprapúbico y pericárdico); paciente inestable con FAST (+) a Laparotomía; estable a TAC y manejo no operatorio (MNO)."},
        {"Día": "Viernes", "Tema Específico": "Quemaduras: Regla de los 9 de Wallace, fluidoterapia con Ringer Lactato (Parkland: 50% en primeras 8 h) y quemadura eléctrica (efecto iceberg con meta de diuresis 100-200 mL/h) + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "Bloque de 70 choices oficiales exclusivos de ATLS, quemaduras y shock hemorrágico."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Fracturas de urgencia y luxaciones (hombro anterior vs posterior, síndrome compartimental y fasciotomía) + Flash-Review IRAB pediátrica."}
    ],

    "Semana 10: Cirugía – Abdomen Agudo": [
        {"Día": "Lunes", "Tema Específico": "Apendicitis Aguda: Cronología de Murphy, semiología peritoneal (Blumberg, Rovsing, psoas), escala de Alvarado e indicación quirúrgica inmediata laparoscópica/convencional."},
        {"Día": "Martes", "Tema Específico": "Patología Biliar Aguda: Colecistitis aguda litiásica (signo de Murphy ecográfico, engrosamiento de pared vesicular >4 mm, colecistectomía precoz) vs Cólico biliar simple."},
        {"Día": "Miércoles", "Tema Específico": "Infección Biliar Grave: Colangitis aguda supurativa (Tríada de Charcot, Péntada de Reynolds, descompresión urgente por CPRE + antibióticos EV) y Coledocolitiasis."},
        {"Día": "Jueves", "Tema Específico": "Diverticulitis Aguda de Colon Izquierdo: TAC con contraste como estándar de oro, clasificación de Hinchey (I a IV) y contraindicación formal de colonoscopía en agudo."},
        {"Día": "Viernes", "Tema Específico": "Abdomen Obstructivo y Cáncer Colorrectal: Bridas vs Vólvulo sigmoideo (signo del grano de café) e Isquemia mesentérica. Pesquisa CCR (sangre oculta/colonoscopía a los 50 años) y operación de Hartmann en obstrucción maligna + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "70 choices de abdomen agudo inflamatorio, obstructivo y patología biliar."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Pancreatitis aguda (criterios de Atlanta, abordaje step-up de necrosis infectada con drenaje percutáneo previo a cirugía) + Flash-Review Deshidratación infantil y SUH."}
    ],

    "Semana 11: Cirugía – Pared, Proctología, Urología y Pediátrica": [
        {"Día": "Lunes", "Tema Específico": "Pared Abdominal: Hernia inguinal indirecta (anillo profundo, lateral a epigástricos) vs Directa (Hesselbach) vs Crural/Femoral (por debajo de ligamento inguinal, alto riesgo de estrangulamiento)."},
        {"Día": "Martes", "Tema Específico": "Patología Anorrectal Benigna: Hemorroides internas (grados I a IV, indoloras) vs externas trombosadas, Fisura anal (línea media posterior, dolor defecatorio) y Absceso perianal (drenaje de urgencia)."},
        {"Día": "Miércoles", "Tema Específico": "Urología Quirúrgica: Cólico renoureteral (TAC sin contraste, tamsulosina si <10 mm) y Escroto agudo (Torsión testicular con Eco-Doppler y orquidopexia bilateral <6 h vs Epididimitis con Prehn positivo)."},
        {"Día": "Jueves", "Tema Específico": "Cirugía Pediátrica de Urgencia: Estenosis hipertrófica de píloro (vómitos no biliares en proyectil, alcalosis metabólica hipoclorémica), Invaginación intestinal (ecografía en diana) y Artritis séptica de cadera (Kocher)."},
        {"Día": "Viernes", "Tema Específico": "Esófago y Complicaciones Post-Qx: ERGE, Barrett, Acalasia (manometría, pico de pájaro). Fiebre postoperatoria (4W: Wind atelectasia 24-48h, Water ITU 72h, Wound infección herida >5d, Walking TVP/TEP) + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "Simulacro General de Cirugía General y Trauma (80 choices)."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Cuaderno de Errores de Cirugía + Flash-Review Neonatología y Puericultura (25 choices)."}
    ],

    # =========================================================
    # MÓDULO IV: CLÍNICA MÉDICA Y SUBESPECIALIDADES (SEMANAS 12 A 15)
    # =========================================================
    "Semana 12: Clínica Médica – Cardiología y Urgencias": [
        {"Día": "Lunes", "Tema Específico": "Hipertensión Arterial: Criterios diagnósticos, monitoreo MAPA/MDPA, HTA guardapolvo blanco y enmascarada, metas y combinaciones farmacológicas (Guía HTA MSAL)."},
        {"Día": "Martes", "Tema Específico": "Crisis Hipertensivas: Urgencia vs Emergencia hipertensiva (definida por daño agudo de órgano blanco: encéfalo, corazón, riñón, retina) y manejo EV con Labetalol o Nitroprusiato."},
        {"Día": "Miércoles", "Tema Específico": "Síndrome Coronario Agudo: IAM con elevación del ST (tiempos de reperfusión: angioplastia puerta-balón <90-120 min vs fibrinolíticos <30 min, DAPT con AAS + Ticagrelor/Clopidogrel, anticoagulación, estatinas) y SCA sin ST."},
        {"Día": "Jueves", "Tema Específico": "Insuficiencia Cardíaca y Valvulopatías: Cuádruple terapia en ICFEr con impacto en mortalidad (iSGLT2, ARNI o IECA/ARA2, Betabloqueantes, Espironolactona). Estenosis aórtica e insuficiencia mitral."},
        {"Día": "Viernes", "Tema Específico": "Arritmias y Fibrilación Auricular: Estratificación de riesgo tromboembólico con CHA₂DS₂-VASc, indicación de anticoagulación (DOACs vs Warfarina) y control de frecuencia vs ritmo + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "Bloque de 70 choices de cardiología clínica y urgencias vasculares."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Tablas de Riesgo Cardiovascular Global (MSAL) y criterios de estatinas en prevención primaria + Flash-Review ATLS y Vía aérea."}
    ],

    "Semana 13: Clínica Médica – Endocrino, Medio Interno y Gastro": [
        {"Día": "Lunes", "Tema Específico": "Diabetes Mellitus Tipo 2: Criterios diagnósticos (ayunas ≥126, PTOG ≥200, HbA1c ≥6.5%), metas y farmacoterapia combinada precoz (Metformina + iSGLT2 / análogos GLP-1 en alto riesgo CV/renal; Guía MSAL)."},
        {"Día": "Martes", "Tema Específico": "Crisis Glucémicas y Patología Digestiva: CAD y EHH (secuencia: SF 0.9%, corregir potasio antes de insulina, goteo insulina regular EV). Enfermedad Celíaca (anti-tTG IgA + IgA total, biopsia Marsh) y EII (Crohn vs Colitis Ulcerosa)."},
        {"Día": "Miércoles", "Tema Específico": "Patología Tiroidea: Hipotiroidismo primario y subclínico (indicaciones de Levotiroxina, TSH, Anti-TPO), Hipertiroidismo (Enfermedad de Graves: TRAB, tionamidas, betabloqueantes) y evaluación del nódulo tiroideo."},
        {"Día": "Jueves", "Tema Específico": "Trastornos Hidroelectrolíticos Críticos: Hiponatremia (osmolaridad, volemia; SF 3% en síntomas neurológicos graves; velocidad <8-10 mEq/L/día para evitar mielinólisis) e Hiperkalemia grave (Gluconato de Calcio EV + medidas de redistribución)."},
        {"Día": "Viernes", "Tema Específico": "Nefrología y Hepatopatías: ERC (estadios KDIGO, nefroprotección con iSGLT2 e IECA/ARA2), Síndrome Nefrótico vs Nefrítico, y Cirrosis con ascitis y PBE (PMN ≥250/mm³, Ceftriaxona + Albúmina) + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "70 choices de endocrinología, medio interno, nefrología y hepatología clínica."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Protocolos de insulinoterapia en APS de Brasil + Flash-Review Abdomen agudo y Hernias."}
    ],

    "Semana 14: Clínica Médica – Neumo, Neuro y Reumatología": [
        {"Día": "Lunes", "Tema Específico": "Asma y EPOC en el Adulto: Espirometría diagnóstica (VEF1/CVF <0.70 post-BD), clasificación GOLD, tratamiento escalonado y exacerbaciones (broncodilatadores, corticoides sistémicos y antibióticos según Anthonisen)."},
        {"Día": "Martes", "Tema Específico": "Neumonía y TEP: Neumonía Adquirida en la Comunidad (criterios CURB-65, esquemas ambulatorios vs sala general) y Tromboembolismo Pulmonar (score Wells, dímero D, AngioTAC de tórax y anticoagulación)."},
        {"Día": "Miércoles", "Tema Específico": "Accidente Cerebrovascular (ACV): ACV isquémico agudo, escala NIHSS, TAC de cráneo simple sin contraste para descartar sangrado, ventana terapéutica rtPA EV (<4.5 h) y metas de TA (TAS <185, TAD <110)."},
        {"Día": "Jueves", "Tema Específico": "Cefaleas y Banderas Rojas: Migraña (triptanes en crisis y profilaxis con betabloqueantes/topiramato), Cefalea tensional, en racimos/cluster (O₂ 100%) y sospecha de hemorragia subaracnoidea."},
        {"Día": "Viernes", "Tema Específico": "Reumatología y Cáncer de Piel: Monoartritis aguda (líquido sinovial: Gota vs Artritis séptica), Artritis Reumatoidea (Anti-CCP, Metotrexato precoz) y Lupus (ACR/EULAR, FAN, anti-DNA, anti-Sm). Melanoma (ABCDE, biopsia escisional) vs Ca basocelular y espinocelular + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "70 choices de neumonología, neurología, reumatología y dermatología clínica."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Intoxicaciones por psicofármacos y abstinencia alcohólica (CIWA-Ar y benzodiazepinas) + Flash-Review Preeclampsia y Hemorragias obstétricas."}
    ],

    "Semana 15: Clínica Médica – Infecto, Hemato y Endemias": [
        {"Día": "Lunes", "Tema Específico": "Dengue y Arbovirosis: Fases clínicas (febril, crítica, recuperación), signos de alarma, clasificación por gravedad OMS (Grupo A ambulatorio, B supervisado, C shock compensado con cristaloides EV, D shock descompensado)."},
        {"Día": "Martes", "Tema Específico": "Tuberculosis: Sintomático respiratorio (>15 días tos y catarro), diagnóstico rápido molecular GeneXpert MTB/RIF, esquema RIPE (2RIPE/4RI) y tratamiento de Tuberculosis Latente."},
        {"Día": "Miércoles", "Tema Específico": "VIH y Sepsis: Diagnóstico VIH, inicio de TARV, profilaxis oportunistas (Cotrimoxazol en CD4 <200 para PCP). Criterios Sepsis-3 y bundle de resucitación de la 1ª hora (cristaloides a 30 mL/kg y hemocultivos previos a ATB)."},
        {"Día": "Jueves", "Tema Específico": "Hematología Clínica: Algoritmo de Anemias por VCM: microcítica (ferropénica vs talasemia), normocítica y macrocítica (déficit B12 vs folato); trombocitopenias (PTI) y coagulopatías (CID)."},
        {"Día": "Viernes", "Tema Específico": "Endemias Regionales: Leishmaniasis visceral/Kala-Azar (Glucantime/Anfotericina B), Paracoccidioidomicosis (timón de barco), accidentes ofídicos (botrópico vs crotálico) y Chagas agudo/crónico (Benznidazol). Lepra/Hanseniasis (paucibacilar vs multibacilar, esquema PQT) + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "Simulacro General de Clínica Médica (80 choices)."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Cuaderno de Errores de Clínica Médica + Flash-Review Cirugía General y ATLS (25 choices)."}
    ],

    # =========================================================
    # MÓDULO V: SALUD PÚBLICA, SALUD MENTAL Y LEYES (SEMANAS 16 A 18)
    # =========================================================
    "Semana 16: Salud Pública – Epidemiología, Bioestadística y Bioética": [
        {"Día": "Lunes", "Tema Específico": "Medidas de Frecuencia y Mortalidad: Incidencia acumulada, densidad de incidencia, prevalencia y cálculo de tasas de mortalidad infantil (neonatal precoz vs tardía vs postneonatal) y Razón de Mortalidad Materna."},
        {"Día": "Martes", "Tema Específico": "Diseños de Estudios Epidemiológicos: Transversales (prevalencia), Casos y Controles (Odds Ratio, retrospectivos), Cohortes (Incidencia y Riesgo Relativo) y Ensayos Clínicos Controlados Aleatorizados."},
        {"Día": "Miércoles", "Tema Específico": "Pruebas Diagnósticas: Tablas 2x2: Sensibilidad, Especificidad, VPP, VPN, Curvas ROC y tipos de sesgos (selección, información, confusión)."},
        {"Día": "Jueves", "Tema Específico": "Vigilancia Epidemiológica: Notificación obligatoria en SINAN (Brasil) y sistema SISA (Argentina). Niveles de prevención (primaria, secundaria, terciaria, cuaternaria)."},
        {"Día": "Viernes", "Tema Específico": "Bioética, SPIKES y Paliativos: Principios de bioética (Autonomía, Beneficencia, No Maleficencia, Justicia), Secreto profesional y confidencialidad en adolescentes; Protocolo SPIKES. Cuidados paliativos (escalera OMS, morfina) + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "70 ejercicios y choices de epidemiología clínica, bioestadística y bioética."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Salud Ocupacional en Brasil (emisión de CAT, neumoconiosis y dermatosis laborales) + Flash-Review Vacunas y Puericultura."}
    ],

    "Semana 17: Salud Mental y Emergencias Psiquiátricas": [
        {"Día": "Lunes", "Tema Específico": "Emergencias Psiquiátricas en Guardia: Agitación psicomotora y conducta violenta: desescalamiento verbal -> contención física -> sedación farmacológica de primera línea (Haloperidol IM +/- Lorazepam)."},
        {"Día": "Martes", "Tema Específico": "Evaluación del Riesgo de Suicidio: Factores de riesgo mayores, signos de alarma, valoración de letalidad, medidas inmediatas de seguridad y criterios de internación."},
        {"Día": "Miércoles", "Tema Específico": "Síndromes Mentales Orgánicos: Delirium / Síndrome Confusional Agudo (inicio agudo, curso fluctuante, inatención, reversibilidad, causa clínica subyacente) vs Demencias (Alzheimer, Vascular, Lewy)."},
        {"Día": "Jueves", "Tema Específico": "Trastornos Psiquiátricos Mayores en APS: Trastorno Depresivo Mayor (diagnóstico, ISRS e interacciones), Trastorno de Ansiedad Generalizada y Trastorno de Pánico."},
        {"Día": "Viernes", "Tema Específico": "Consumo Problemático y TCA: Síndrome de Abstinencia Alcohólica (CIWA-Ar, prevención de delirium tremens con benzodiazepinas). Anorexia nerviosa vs Bulimia nerviosa (criterios de internación) + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "70 choices de emergencias psiquiátricas, psicofarmacología y salud mental ambulatoria."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Ley 26.657 de Salud Mental Argentina (internación involuntaria bajo criterio estricto de 'riesgo cierto e inminente', equipo interdisciplinario, hospitales generales) + Flash-Review Diabetes y CAD."}
    ],

    "Semana 18: Choque Regulatorio – Leyes Argentinas vs Sistema SUS": [
        {"Día": "Lunes", "Tema Específico": "Leyes Sanitarias Argentina I: Ley 26.529 (Derechos del Paciente, Historia Clínica y Consentimiento: autonomía de la voluntad, rechazo de tratamientos, constancia en HC) y Ley 25.929 (Parto Humanizado)."},
        {"Día": "Martes", "Tema Específico": "Leyes Sanitarias Argentina II: Ley 27.610 (IVE/ILE: plazos semana 14, causales, objeción de conciencia individual) y Ley 26.061 (Protección Integral de Niñas, Niños y Adolescentes y denuncia obligatoria)."},
        {"Día": "Miércoles", "Tema Específico": "Leyes Sanitarias Argentina III: Ley 26.743 (Identidad de Género: autonomía y toma de decisiones a partir de los 16 años) y Código Civil en autonomía en salud."},
        {"Día": "Jueves", "Tema Específico": "Marco Legal Brasil I: Constitución Federal 1988 (Art. 196 a 200), Ley 8.080/1990 (Principios: Universalidad, Integralidad, Equidad, Descentralización, Regionalización) y Ley 8.142/1990 (Consejos y Conferencias con 50% usuarios)."},
        {"Día": "Viernes", "Tema Específico": "Marco Legal Brasil II: Estratégia Saúde da Família (ESF: estructura de UBS, territorialización, adscripción, rol del Agente Comunitario de Salud - ACS), Acesso Avançado y Poblaciones Específicas (Salud Indígena DSEI, PNAISP) + 25 choices."},
        {"Día": "Sábado", "Tema Específico": "Maratón Legal: 50 choices de Leyes Sanitarias de Argentina + 50 choices de SUS y ESF de Brasil."},
        {"Día": "Domingo", "Tema Específico": "Módulo Satélite: Resoluciones operativas del SUS (NOB 96 y NOAS) + Cuaderno de Errores de todo el bloque legal."}
    ],

    # =========================================================
    # MÓDULO VI: CONSOLIDACIÓN Y SIMULACROS CRONOMETRADOS (SEMANAS 19 Y 20)
    # =========================================================
    "Semana 19: Simulacros Integradores por Áreas Cruzadas": [
        {"Día": "Lunes", "Tema Específico": "Simulacro 1 (100 preguntas cronometradas): 50 preguntas de Tocoginecología + 50 de Pediatría (formato cruzado 50% INEP / 50% Examen Único)."},
        {"Día": "Martes", "Tema Específico": "Corrección minuciosa del Simulacro 1 y transcripción analítica de dudas al Cuaderno de Errores."},
        {"Día": "Miércoles", "Tema Específico": "Simulacro 2 (100 preguntas cronometradas): 40 preguntas de Clínica Médica + 30 de Cirugía General + 30 de Salud Pública y Leyes."},
        {"Día": "Jueves", "Tema Específico": "Corrección minuciosa del Simulacro 2 y resolución de dudas puntuales en consensos oficiales."},
        {"Día": "Viernes", "Tema Específico": "Repaso de tablas críticas de memoria: dosis antimicrobianas de urgencia, metas tensionales y puntos de corte de laboratorio."},
        {"Día": "Sábado", "Tema Específico": "Simulacro Oficial Completo Revalida INEP en tiempo estricto de examen."},
        {"Día": "Domingo", "Tema Específico": "Corrección comentada y análisis de distractores del Revalida."}
    ],

    "Semana 20: Puesta a Punto Final y Calibración de Velocidad": [
        {"Día": "Lunes", "Tema Específico": "Simulacro Oficial Completo Examen Único / CABA de 100 preguntas en 2 horas y media."},
        {"Día": "Martes", "Tema Específico": "Análisis de preguntas dudosas y repaso de letra chica en leyes argentinas y SUS."},
        {"Día": "Miércoles", "Tema Específico": "Repaso ultrarrápido de síntesis de alto rendimiento por especialidad."},
        {"Día": "Jueves", "Tema Específico": "Simulacro Final de 100 Preguntas Mixtas simulando condiciones exactas de examen."},
        {"Día": "Viernes", "Tema Específico": "Cierre de estudio, calibración del ritmo de 1 minuto por pregunta y descanso mental pre-examen."}
    ]
}
import math

def obtener_cronograma_personalizado(modalidad_plan):
    """
    Retorna el cronograma adaptado según la duración elegida por el usuario,
    manteniendo la estructura original o aplicando compresión/filtrado.
    """
    # 1. Tu plan base original intacto
    if modalidad_plan == "🌟 Completo Estándar (20 Semanas)":
        return cronograma_desglosado

    # 2. Extraer todos los ítems ordenados
    todos_los_items = []
    for sem_nombre, dias in cronograma_desglosado.items():
        for d in dias:
            todos_los_items.append({
                "modulo": sem_nombre.split(":")[0],
                "tema": d["Tema Específico"]
            })

    # 3. Plan Crash 5 Semanas: Filtrado High-Yield (lo más tomado)
    if modalidad_plan == "🎯 High-Yield / Solo lo Más Tomado (5 Semanas)":
        palabras_clave_hy = [
            "preeclampsia", "hemorragia", "parto", "aborto", "ectópico",
            "bronquiolitis", "neumonía", "nac", "deshidratación", "suh", "reanimación", "ictericia",
            "atls", "trauma", "apendicitis", "colecistitis", "obstrucción", "hernia",
            "hipertensión", "hta", "coronario", "diabetes", "cad", "acv", "dengue", "tuberculosis", "tbc",
            "epidemiología", "diseños", "pruebas diagnósticas", "bioética", "8.080", "27.610", "26.529", "simulacro"
        ]
        items_filtrados = [
            item for item in todos_los_items
            if any(k in item["tema"].lower() for k in palabras_clave_hy)
        ]
        return _repartir_en_semanas(items_filtrados, semanas=5)

    # 4. Planes de 15, 12 y 10 semanas: 100% del temario compactado
    semanas_map = {
        "⚡ Completo Acelerado (15 Semanas)": 15,
        "🔥 Intensivo Doble Turno (12 Semanas)": 12,
        "🚀 Intensivo Crash (10 Semanas)": 10
    }
    semanas_meta = semanas_map.get(modalidad_plan, 20)
    return _repartir_en_semanas(todos_los_items, semanas=semanas_meta)


def _repartir_en_semanas(lista_items, semanas):
    """Distribui os temas agrupando-os de imediato por dia da semana."""
    total = len(lista_items)
    items_por_semana = math.ceil(total / semanas)
    cronograma_res = {}
    
    dias_base = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

    idx = 0
    for s in range(1, semanas + 1):
        clave_semana = f"Semana {s} (de {semanas})"
        dias_lista = []
        
        # Agrupar temas da semana por cada um dos 7 dias
        temas_por_dia = {d: [] for d in dias_base}
        
        for i in range(items_por_semana):
            if idx < total:
                dia_atribuido = dias_base[i % 7]
                temas_por_dia[dia_atribuido].append(lista_items[idx]["tema"])
                idx += 1
                
        # Construir os registos mantendo os temas do mesmo dia juntos
        for dia_nome in dias_base:
            lista_temas_dia = temas_por_dia[dia_nome]
            if not lista_temas_dia:
                continue
                
            if len(lista_temas_dia) == 1:
                dias_lista.append({
                    "Día": dia_nome,
                    "Tema Específico": lista_temas_dia[0]
                })
            else:
                for n_tema, texto_tema in enumerate(lista_temas_dia, start=1):
                    # Identificador visual com seta para subtemas
                    prefixo = "📌" if n_tema == 1 else "↳"
                    dias_lista.append({
                        "Día": f"{dia_nome} — {prefixo} Tema {n_tema}",
                        "Tema Específico": texto_tema
                    })
                
        if dias_lista:
            cronograma_res[clave_semana] = dias_lista

    return cronograma_res
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
            # Acceso directo e instantáneo para no depender de la latencia de red
            if u_input.lower() == "luana" and p_input == "medica2026":
                st.session_state.authenticated = True
                st.session_state.current_user = "luana"
                st.session_state.user_name = "Dra. Luana"
                st.rerun()

            with st.spinner("Verificando credenciales..."):
                users_df = get_sheet_data("users")
                if not users_df.empty and "username" in users_df.columns:
                    user_row = users_df[users_df["username"].astype(str).str.lower() == u_input.lower()]
                    if not user_row.empty and str(user_row.iloc[0]["password_hash"]) == hash_password(p_input):
                        st.session_state.authenticated = True
                        st.session_state.current_user = str(user_row.iloc[0]["username"])
                        st.session_state.user_name = str(user_row.iloc[0]["nombre"])
                        st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos.")
                else:
                    st.error("No se pudo conectar con la lista de usuarios. Verificá los permisos de la planilla.")
                
    with col2:
        with st.expander("Crear una nueva cuenta"):
            new_u = st.text_input("Nuevo Usuario")
            new_n = st.text_input("Tu Nombre")
            new_p = st.text_input("Nueva Contraseña", type="password")
            if st.button("Registrarse"):
                if new_u and new_p:
                    with st.spinner("Registrando usuario en Google Sheets..."):
                        users_df = get_sheet_data("users")
                        if not users_df.empty and new_u.lower() in users_df["username"].astype(str).str.lower().values:
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
st.sidebar.markdown("---")
modalidad_cronograma = st.sidebar.selectbox(
    "📅 Modalidad de Cronograma:",
    [
        "🌟 Completo Estándar (20 Semanas)",
        "⚡ Completo Acelerado (15 Semanas)",
        "🔥 Intensivo Doble Turno (12 Semanas)",
        "🚀 Intensivo Crash (10 Semanas)",
        "🎯 High-Yield / Solo lo Más Tomado (5 Semanas)"
    ],
    index=0  # Por defecto siempre carga el tuyo de 20 semanas
)

# Cronograma dinámico según el usuario activo
cronograma_activo = obtener_cronograma_personalizado(modalidad_cronograma)

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
# 1. DASHBOARD & REPASO ESPACIADO INTELIGENTE (SIN SATURACIÓN)
# -------------------------------------------------------------
if menu == "🏠 Dashboard & Repaso SRS":
    st.header(f"⚡ Bienvenido/a, {st.session_state.user_name}")
    
    # Cargar datos para métricas
    error_df = get_sheet_data("error_log")
    progreso_df = get_sheet_data("progreso_temas")

    if not error_df.empty and "username" in error_df.columns:
        user_logs = error_df[error_df["username"].astype(str) == st.session_state.current_user]
        total_hechas = len(user_logs)
        total_correctas = len(user_logs[user_logs["es_correcta"] == 1])
        hechas_ids = set(user_logs["choice_id"].astype(str))
        errores_ids = set(user_logs[user_logs["es_correcta"] == 0]["choice_id"].astype(str))
    else:
        total_hechas = 0
        total_correctas = 0
        hechas_ids = set()
        errores_ids = set()

    precision = int((total_correctas / total_hechas * 100)) if total_hechas > 0 else 0
    
    # Cálculo de la Racha Real
    racha_actual = calcular_racha_activa(st.session_state.current_user, error_df, progreso_df)
    texto_racha = f"{racha_actual} Días" if racha_actual != 1 else "1 Día"

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔥 Racha Activa", texto_racha)
    col2.metric("🎯 Precisión Personal", f"{precision}%")
    col3.metric("📝 Choices Realizados", str(total_hechas))
    col4.metric("📅 Enfoque Actual", "Semana Activa")

    st.markdown("---")
    st.subheader("🧠 Repaso Focalizado del Día")

    choices_df = get_sheet_data("choices")
    if choices_df.empty:
        st.info("No hay choices en la base de datos.")
    else:
        # 2. Selector de Semana para alinear al cronograma
        c_sem, c_cant = st.columns([3, 1])
        with c_sem:
          semana_activa = st.selectbox(
    "Seleccioná la semana del cronograma para tu repaso de hoy:",
    list(cronograma_activo.keys()),
    index=0
)
        with c_cant:
            dosis_diaria = st.slider("Límite diario de choices:", min_value=5, max_value=30, value=10, step=5)

        # 3. Detectar qué área corresponde a la semana elegida
        area_sugerida = ""
        sem_str = semana_activa.lower()
        if "tocoginecología" in sem_str or "toco" in sem_str:
            area_sugerida = "Tocoginecología"
        elif "pediatría" in sem_str:
            area_sugerida = "Pediatría"
        elif "clínica médica" in sem_str or "clinica" in sem_str:
            area_sugerida = "Clínica Médica"
        elif "cirugía" in sem_str:
            area_sugerida = "Cirugía General"
        elif "salud pública" in sem_str:
            area_sugerida = "Salud Pública y Leyes"

        # 4. Filtrar por Área y Enfoque de Examen (AR / BR / Dual)
        df_disponible = choices_df.copy()

        if filtro_pais == "🇦🇷 Solo Argentina":
            patron_ar = "unico|único|caba|eres|argentina"
            df_disponible = df_disponible[df_disponible["examen_origen"].astype(str).str.lower().str.contains(patron_ar, na=False)]
        elif filtro_pais == "🇧🇷 Solo Brasil":
            patron_br = "revalida|enamed|inep|brasil|sus"
            df_disponible = df_disponible[df_disponible["examen_origen"].astype(str).str.lower().str.contains(patron_br, na=False)]

        if area_sugerida:
            df_semana = df_disponible[df_disponible["area"].astype(str).str.contains(area_sugerida, case=False, na=False)]
        else:
            df_semana = df_disponible

        if df_semana.empty:
            df_semana = df_disponible  # Respaldo si no hay preguntas con ese nombre exacto

        # 5. Priorización inteligente de la dosis diaria:
        # Prioridad 1: Preguntas que antes tuviste mal (errores a reforzar)
        # Prioridad 2: Preguntas no hechas todavía del tema
        choices_errores = df_semana[df_semana["id"].astype(str).isin(errores_ids)]
        choices_nuevos = df_semana[~df_semana["id"].astype(str).isin(hechas_ids)]
        choices_resto = df_semana

        lista_priorizada = pd.concat([choices_errores, choices_nuevos, choices_resto]).drop_duplicates(subset=["id"])
        choices_hoy = lista_priorizada.head(dosis_diaria).reset_index(drop=True)

        st.info(f"📚 Sesión configurada: **{len(choices_hoy)} choices seleccionados** de **{area_sugerida if area_sugerida else 'Área General'}**.")

        # 6. Mostrar las preguntas en modo examen (sin spoiler de tema)
        for idx, row in choices_hoy.iterrows():
            with st.expander(f"📌 Pregunta #{idx+1} — {row['examen_origen']} | {row['area']}"):
                st.write(f"### {row['pregunta']}")
                st.write(f"**A)** {row['opcion_a']}")
                st.write(f"**B)** {row['opcion_b']}")
                st.write(f"**C)** {row['opcion_c']}")
                st.write(f"**D)** {row['opcion_d']}")

                resp_srs = st.radio(
                    f"Tu respuesta para P#{idx+1}:",
                    ["A", "B", "C", "D"],
                    key=f"srs_opt_{row['id']}_{idx}"
                )

                if st.button("Confirmar Respuesta", key=f"srs_btn_{row['id']}_{idx}"):
                    es_corr = 1 if resp_srs == str(row['correcta']).strip().upper() else 0
                    
                    # Registrar en error_log
                    new_log = pd.DataFrame([{
                        "id": random.randint(100000, 999999),
                        "username": st.session_state.current_user,
                        "choice_id": str(row['id']),
                        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "respuesta_dada": resp_srs,
                        "es_correcta": es_corr,
                        "flag_duda": 0,
                        "motivo_error": "",
                        "regla_oro": ""
                    }])
                    save_sheet_data("error_log", pd.concat([error_df, new_log], ignore_index=True))

                    if es_corr:
                        st.success(f"🎉 ¡CORRECTO! Opción {row['correcta']}")
                    else:
                        st.error(f"❌ INCORRECTO. La respuesta oficial era: {row['correcta']}")

                    st.markdown(f"🏷️ **Tema evaluado:** *{row['tema']}*")
                    st.info(f"**Fundamento:** {row['justificacion']}")
# -------------------------------------------------------------
# 2. CRONOGRAMA SEMANAL DETALLADO CON CHECKLIST DINÁMICO
# -------------------------------------------------------------
elif menu == "📅 Cronograma Semanal Detallado":
    st.header("📅 Cronograma Interactivo de Estudio")
    st.caption("Marcá los temas a medida que los completes para registrar tu avance real.")

    # Cargar o inicializar la tabla de progresos
    progreso_df = get_sheet_data("progreso_temas")
    if progreso_df.empty or "username" not in progreso_df.columns:
        progreso_df = pd.DataFrame(columns=["username", "semana", "dia", "completado"])

    # Filtrar temas completados por el usuario activo
    user_prog = progreso_df[progreso_df["username"].astype(str) == st.session_state.current_user]
    completados_set = set(zip(user_prog["semana"].astype(str), user_prog["dia"].astype(str)))

    # Métricas globales de avance
    total_dias_plan = sum(len(dias) for dias in cronograma_activo.values())
    total_hechos_usr = len(user_prog)
    pct_global = int((total_hechos_usr / total_dias_plan) * 100) if total_dias_plan > 0 else 0

    col_p1, col_p2 = st.columns([3, 1])
    with col_p1:
        st.progress(pct_global / 100)
    with col_p2:
        st.metric("🎯 Progreso Global", f"{pct_global}%", f"{total_hechos_usr}/{total_dias_plan} temas")

    st.markdown("---")

    # Selector de Semana adaptado al plan activo
    sem_select = st.selectbox("Seleccioná la semana a visualizar:", list(cronograma_activo.keys()))
    dias_semana = cronograma_activo[sem_select]

    # Contador de la semana seleccionada
    hechos_esta_semana = sum(1 for item in dias_semana if (sem_select, item["Día"]) in completados_set)
    st.info(f"Avance de esta semana: **{hechos_esta_semana} de {len(dias_semana)} temas completados**.")

    # Lista de temas en 2 columnas equilibradas (evita que se corte el texto)
    hubo_cambios = False
    for item in dias_semana:
        dia_nombre = item["Día"]
        tema_desc = item["Tema Específico"]
        clave_tupla = (sem_select, dia_nombre)
        esta_marcado = clave_tupla in completados_set

        # Columna 1 más ancha (2.2) para que quepa "Miércoles — 📌 Tema 1" completo sin cortes
        c_check, c_desc = st.columns([1.6, 8.4])
        with c_check:
            # Formato visual con sangría si es Tema 2
            if "Tema 2" in dia_nombre:
                label_check = f"&nbsp;&nbsp;&nbsp;&nbsp;↳ **{dia_nombre.split('—')[-1].strip()}**"
            else:
                label_check = f"**{dia_nombre}**"

            nuevo_estado = st.checkbox(
                label_check,
                value=esta_marcado,
                key=f"chk_{sem_select}_{dia_nombre}"
            )
        with c_desc:
            if nuevo_estado:
                st.markdown(f"~~{tema_desc}~~ ✅ *(Completado)*")
            else:
                st.markdown(f"{tema_desc}")

        # Si el usuario cambió el estado del checkbox
        if nuevo_estado != esta_marcado:
            hubo_cambios = True
            if nuevo_estado:
                # Agregar registro
                nueva_fila = pd.DataFrame([{
                    "username": st.session_state.current_user,
                    "semana": sem_select,
                    "dia": dia_nombre,
                    "completado": 1
                }])
                progreso_df = pd.concat([progreso_df, nueva_fila], ignore_index=True)
            else:
                # Quitar registro
                progreso_df = progreso_df[~(
                    (progreso_df["username"].astype(str) == st.session_state.current_user) &
                    (progreso_df["semana"].astype(str) == sem_select) &
                    (progreso_df["dia"].astype(str) == dia_nombre)
                )]

    if hubo_cambios:
        save_sheet_data("progreso_temas", progreso_df)
        st.success("¡Progreso actualizado y guardado en Google Sheets!")
        st.rerun()
# -------------------------------------------------------------
# FUNCIONES IA CON CACHÉ (Ahorro de Cuota API)
# -------------------------------------------------------------
@st.cache_data(show_spinner=False)
def obtener_algoritmo_cached(tema: str):
    prompt = f"""
    Generá un diagrama de flujo en código Mermaid.js sobre el diagnóstico y conducta clínica de: {tema}.
    
    REGLAS DE SINTAXIS ESTRICTAS:
    1. Empezá con 'graph TD'.
    2. TODO el texto dentro de corchetes o llaves DEBE ir entre comillas dobles: A["Texto"] o B{{"Decisión"}}.
    3. Cada conexión DEBE estar en una línea separada.
    4. NO uses caracteres especiales sin comillas.
    5. Devolvé ÚNICAMENTE el bloque Mermaid, sin texto previo ni posterior.
    """
    res = model.generate_content(prompt)
    mermaid_code = res.text.replace("```mermaid", "").replace("```", "").strip()
    mermaid_clean = re.sub(r'(\})\s*([A-Za-z0-9_]+)', r'\1\n\2', mermaid_code)
    mermaid_clean = re.sub(r'(\])\s*([A-Za-z0-9_]+)', r'\1\n\2', mermaid_clean)
    return mermaid_clean

@st.cache_data(show_spinner=False)
def obtener_perlas_cached(tema: str):
    p_prompt = f"Generá 4 perlas clínicas clave y de alta incidencia sobre '{tema}' para exámenes de residencia médica. Sé directo, concreto y enumerá en viñetas con negrita."
    res = model.generate_content(p_prompt)
    return res.text

@st.cache_data(show_spinner=False)
def obtener_comparativa_cached(tema: str):
    c_prompt = (
        f"Sos un experto en exámenes médicos de Residencias en Argentina y Revalida en Brasil. "
        f"Para el tema '{tema}', presentá una tabla Markdown muy sintética comparando: "
        f"1) Guía/Conducta en Argentina, 2) Guía/Conducta en Brasil (SUS/MS), 3) Perla clave para examen. "
        f"Si el manejo es idéntico, aclaralo en 2 líneas. Sé directo, breve y sin introducciones."
    )
    config = genai.types.GenerationConfig(
        max_output_tokens=600,
        temperature=0.2
    )
    res = model.generate_content(c_prompt, generation_config=config)
    return res.text
    
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
                with st.spinner(f"Cargando algoritmo para: {tema_limpio[:50]}..."):
                    try:
                        mermaid_clean = obtener_algoritmo_cached(tema_limpio)
                        st.markdown(f"```mermaid\n{mermaid_clean}\n```")
                    except Exception as err:
                        if "429" in str(err):
                            st.warning("⏳ Límite temporal alcanzado. Esperá unos 15 segundos y reintentá.")
                        else:
                            st.error(f"Error generando algoritmo: {err}")

    with t2:
        st.subheader("⚡ Resumen High-Yield & Perlas Clave")
        if st.button("✨ Generar Puntos Clave de Examen con IA", key="btn_pearls"):
            if not model:
                st.error("API de Gemini no configurada.")
            else:
                with st.spinner("Cargando perlas clínicas..."):
                    try:
                        perlas = obtener_perlas_cached(tema_limpio)
                        st.markdown(perlas)
                    except Exception as err:
                        if "429" in str(err):
                            st.warning("⏳ Límite temporal alcanzado. Esperá unos 15 segundos y reintentá.")
                        else:
                            st.error(f"Error: {err}")

    with t3:
        st.subheader("⚖️ Diferencias Normativas Argentina vs. Brasil")
        if st.button("✨ Comparar Enfoque AR vs BR con IA", key="btn_comp"):
            if not model:
                st.error("API de Gemini no configurada.")
            else:
                with st.spinner("Cargando comparativa de consensos sanitarios..."):
                    try:
                        comparativa = obtener_comparativa_cached(tema_limpio)
                        st.markdown(comparativa)
                    except Exception as err:
                        if "429" in str(err):
                            st.warning("⏳ Límite temporal alcanzado. Esperá unos 15 segundos y reintentá.")
                        else:
                            st.error(f"Error generando comparativa: {err}")

# -------------------------------------------------------------
# 4. GENERADOR AUTOMÁTICO DE CHOICES CON IA (CON 'OTROS')
# -------------------------------------------------------------
elif menu == "✨ Generador de Choices con IA":
    st.header("✨ Generador Automático de Choices Médicos con IA")
    st.caption("Creá preguntas de opción múltiple que se guardan directamente en Google Sheets.")

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        tema_ia = st.text_input("Tema a evaluar:", value="Preeclampsia Severa y Manejo de Crisis")
        area_ia = st.selectbox(
            "Especialidad / Área:",
            [
                "Tocoginecología",
                "Pediatría",
                "Clínica Médica",
                "Cirugía General",
                "Salud Pública y Leyes",
                "Otros / Especialidades Complementarias"
            ]
        )
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
# 5. BANCO DE CHOICES & SIMULACROS (FILTRO PAÍS + MODO CIEGO)
# -------------------------------------------------------------
elif menu == "📝 Banco de Choices & Simulacros":
    st.header("📝 Banco de Choices & Simulacros")

    choices_df = get_sheet_data("choices")
    if choices_df.empty:
        st.warning("No hay choices cargados en Google Sheets. Podés generarlos con IA o cargar un CSV.")
    else:
        # 1. Filtro inteligente según el país elegido en la barra lateral
        df_activa = choices_df.copy()
        
        if filtro_pais == "🇦🇷 Solo Argentina":
            # Filtra exámenes argentinos (Examen Único, ERES, CABA, etc.)
            patron_ar = "unico|único|caba|eres|argentina"
            df_activa = df_activa[df_activa["examen_origen"].astype(str).str.lower().str.contains(patron_ar, na=False)]
        elif filtro_pais == "🇧🇷 Solo Brasil":
            # Filtra exámenes brasileños (Revalida, ENAMED, INEP, etc.)
            patron_br = "revalida|enamed|inep|brasil|sus"
            df_activa = df_activa[df_activa["examen_origen"].astype(str).str.lower().str.contains(patron_br, na=False)]

        if df_activa.empty:
            st.warning(f"No hay preguntas cargadas que coincidan con el filtro '{filtro_pais}'. Podés cambiar a 'Modo Dual' en la barra lateral.")
        else:
            modo_practica = st.radio("Modalidad de Estudio:", ["📚 Por Área Específica", "🎲 Simulacro Aleatorio"], horizontal=True)

            if modo_practica == "📚 Por Área Específica":
                areas_disponibles = sorted(list(df_activa["area"].dropna().unique()))
                area_sel = st.selectbox("Seleccioná el Área Médica:", areas_disponibles)
                filtered_df = df_activa[df_activa["area"] == area_sel].reset_index(drop=True)
            else:
                filtered_df = df_activa.sample(frac=1, random_state=42).reset_index(drop=True)

            if filtered_df.empty:
                st.warning("No hay preguntas disponibles para esta selección.")
            else:
                # Selector ciego: solo número y origen
                q_idx = st.selectbox(
                    "Seleccionar Pregunta a Resolver:",
                    range(len(filtered_df)),
                    format_func=lambda x: f"Pregunta #{x+1} — {filtered_df.iloc[x]['examen_origen']}"
                )
                q = filtered_df.iloc[q_idx]

                # Encabezado sin tema
                st.markdown(f"#### `{q['examen_origen']}` | **{q['area']}**")
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
                    es_correcta = 1 if letra_elegida == str(q['correcta']).strip().upper() else 0

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

                    # Revelación posterior del tema evaluado
                    st.markdown(f"📌 **Tema evaluado:** *{q['tema']}*")
                    st.info(f"**Fundamento Clínico:** {q['justificacion']}")

# -------------------------------------------------------------
# 6. CUADERNO DE ERRORES
# -------------------------------------------------------------
elif menu == "📕 Cuaderno de Errores":
    st.header(f"📕 Libro de Errores | {st.session_state.user_name}")

    error_df = get_sheet_data("error_log")
    choices_df = get_sheet_data("choices")

    if not error_df.empty and not choices_df.empty:
        user_errors = error_df[(error_df["username"].astype(str) == st.session_state.current_user) & ((error_df["es_correcta"] == 0) | (error_df["flag_duda"] == 1))]
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
        user_logs = error_df[error_df["username"].astype(str) == st.session_state.current_user]
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
