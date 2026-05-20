# ============================================
# AGUWEYBOT - VERSIÓN MINISTRAL-3 + QWEN 2.5 72B + GEMMA 4 (OpenRouter)
# CON LOGO - MAYO 2026
# ============================================

import os
import base64
import time
import streamlit as st
import streamlit.components.v1 as components
import re
import io
import json
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime

# Para documentos
from PyPDF2 import PdfReader
from docx import Document
import pandas as pd
import chardet

# Para imágenes
from PIL import Image

# ============================================
# TEXTO A VOZ
# ============================================
try:
    from gtts import gTTS
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    print("⚠️ gTTS no disponible")

# ============================================
# CONFIGURACIÓN
# ============================================
MODEL_NAME = "ministral-3b-latest"
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Verificar API keys
if "MISTRAL_API_KEY" not in st.secrets:
    st.error("❌ No se encontró la API Key de MISTRAL AI en los secrets")
    st.stop()

MISTRAL_API_KEY = st.secrets["MISTRAL_API_KEY"]

# Verificar OpenRouter key (necesaria para Qwen y Gemma 4)
OPENROUTER_API_KEY = st.secrets.get("OPENROUTER_API_KEY", None)

# Directorio para guardar conversaciones
SAVE_DIR = "conversaciones_guardadas"
os.makedirs(SAVE_DIR, exist_ok=True)

# ============================================
# CONSTANTES Y CONFIGURACIÓN VISUAL
# ============================================
class Config:
    PRIMARY_COLOR = "#00ffff"
    SECONDARY_COLOR = "#00cccc"
    BACKGROUND_DARK = "#0a0c10"
    CARD_BACKGROUND = "#1e2a3a"
    LOGO_PATH = "logo.png"
    BACKGROUND_PATH = "fondo.png"
    MAX_HISTORY_MESSAGES = 10
    MAX_FILE_SIZE_MB = 50
    MAX_CONTEXT_TOKENS = 8000

# ============================================
# SYSTEM PROMPT
# ============================================
SYSTEM_PROMPT = """
Eres AguweyBot, un asistente experto en análisis de documentos usando inteligencia artificial.

Cuando el usuario suba un archivo, DEBES:
1. Leer TODO el contenido del archivo cuidadosamente
2. Responder preguntas específicas sobre su contenido
3. Si te piden resumir, haz un resumen detallado de TODO el documento
4. Si hay datos numéricos, analízalos completamente
5. Si hay código, explícalo línea por línea

REGLAS:
- Usa TODO el contenido del archivo para responder
- No inventes información
- Si no encuentras algo en el archivo, dilo honestamente
- Usa emojis para hacer las respuestas más amigables
- Responde de manera clara, concisa y profesional
"""

# ============================================
# GESTIÓN DE CONVERSACIONES GUARDADAS
# ============================================
class ConversacionGuardada:
    @staticmethod
    def guardar_conversacion(messages: List[Dict], nombre: str = None) -> str:
        if not nombre:
            first_user_msg = next((m["content"] for m in messages if m["role"] == "user"), "Nueva conversacion")
            nombre = first_user_msg[:50].replace(" ", "_").replace("/", "_").replace("\\", "_")
            nombre = re.sub(r'[^\w\-_\.]', '', nombre)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{SAVE_DIR}/{timestamp}_{nombre}.json"
        
        modelo_usado = st.session_state.get("modelo_seleccionado", MODEL_NAME)
        
        data = {
            "timestamp": timestamp,
            "nombre": nombre,
            "mensajes": messages,
            "total_mensajes": len(messages),
            "modelo": modelo_usado
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return filename
    
    @staticmethod
    def cargar_conversacion(filename: str) -> Optional[List[Dict]]:
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("mensajes", [])
        except Exception as e:
            st.error(f"Error al cargar conversación: {str(e)}")
            return None
    
    @staticmethod
    def listar_conversaciones() -> List[Dict[str, Any]]:
        conversaciones = []
        if not os.path.exists(SAVE_DIR):
            return conversaciones
        
        for filename in os.listdir(SAVE_DIR):
            if filename.endswith('.json'):
                filepath = os.path.join(SAVE_DIR, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    conversaciones.append({
                        "filename": filepath,
                        "nombre": data.get("nombre", "Sin nombre"),
                        "timestamp": data.get("timestamp", "Desconocido"),
                        "total_mensajes": data.get("total_mensajes", 0),
                        "modelo": data.get("modelo", "Desconocido")
                    })
                except:
                    continue
        
        conversaciones.sort(key=lambda x: x["timestamp"], reverse=True)
        return conversaciones
    
    @staticmethod
    def eliminar_conversacion(filename: str) -> bool:
        try:
            if os.path.exists(filename):
                os.remove(filename)
                return True
        except Exception as e:
            st.error(f"Error al eliminar: {str(e)}")
        return False

# ============================================
# FUNCIÓN PARA TRUNCAR CONTEXTO
# ============================================
def truncar_contexto(texto: str, max_caracteres: int = 6000) -> str:
    if len(texto) <= max_caracteres:
        return texto
    
    lines = texto.split('\n')
    result = []
    current_len = 0
    
    for line in lines:
        if current_len + len(line) + 1 <= max_caracteres:
            result.append(line)
            current_len += len(line) + 1
        else:
            remaining = max_caracteres - current_len
            if remaining > 50:
                result.append(line[:remaining] + "...")
            break
    
    return '\n'.join(result)

# ============================================
# FUNCIÓN PARA FONDO
# ============================================
def set_background():
    """Aplica la imagen de fondo si existe"""
    if os.path.exists(Config.BACKGROUND_PATH):
        try:
            with open(Config.BACKGROUND_PATH, "rb") as f:
                img_data = f.read()
            encoded = base64.b64encode(img_data).decode()
            
            st.markdown(
                f"""
                <style>
                .stApp {{
                    background-image: url("data:image/png;base64,{encoded}");
                    background-size: cover;
                    background-position: center;
                    background-attachment: fixed;
                    background-repeat: no-repeat;
                }}
                .main .block-container {{
                    background-color: rgba(0, 0, 0, 0.7);
                    backdrop-filter: blur(10px);
                    border-radius: 20px;
                    padding: 2rem;
                    margin: 2rem auto;
                    border: 1px solid {Config.PRIMARY_COLOR};
                    box-shadow: 0 0 20px rgba(0, 255, 255, 0.3);
                    max-width: 1200px;
                }}
                </style>
                """,
                unsafe_allow_html=True
            )
        except:
            aplicar_fondo_gradiente()
    else:
        aplicar_fondo_gradiente()

def aplicar_fondo_gradiente():
    """Aplica un fondo con gradiente como fallback"""
    st.markdown(f"""
    <style>
    .stApp {{
        background: linear-gradient(135deg, {Config.BACKGROUND_DARK}, #1a1f2a);
    }}
    .main .block-container {{
        background-color: rgba(10, 12, 16, 0.85);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 2rem;
        margin: 1rem auto;
        border: 1px solid {Config.PRIMARY_COLOR};
        box-shadow: 0 0 30px rgba(0, 255, 255, 0.2);
        max-width: 1000px !important;
    }}
    </style>
    """, unsafe_allow_html=True)

# ============================================
# FUNCIÓN PARA MOSTRAR LOGO
# ============================================
def mostrar_logo():
    """Muestra el logo desde archivo local o un fallback estilizado"""
    if os.path.exists(Config.LOGO_PATH):
        try:
            logo = Image.open(Config.LOGO_PATH)
            st.sidebar.image(logo, use_container_width=True)
        except Exception as e:
            st.sidebar.warning(f"No se pudo cargar el logo: {str(e)}")
            mostrar_logo_fallback()
    else:
        mostrar_logo_fallback()

def mostrar_logo_fallback():
    """Muestra un logo estilizado con HTML/CSS"""
    st.sidebar.markdown("""
    <style>
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(0, 255, 255, 0.7); }
        70% { box-shadow: 0 0 0 20px rgba(0, 255, 255, 0); }
        100% { box-shadow: 0 0 0 0 rgba(0, 255, 255, 0); }
    }
    
    @keyframes float {
        0% { transform: translateY(0px); }
        50% { transform: translateY(-8px); }
        100% { transform: translateY(0px); }
    }
    
    .logo-container {
        text-align: center;
        padding: 20px 0;
        animation: float 3s ease-in-out infinite;
    }
    
    .logo-circle {
        background: linear-gradient(145deg, #00cccc, #00ffff);
        border-radius: 50%;
        width: 140px;
        height: 140px;
        margin: 0 auto;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 3px solid #00ffff;
        animation: pulse 2s infinite;
    }
    
    .logo-emoji {
        font-size: 75px;
        filter: drop-shadow(0 0 10px rgba(0, 255, 255, 0.5));
    }
    
    .logo-title {
        color: #00ffff;
        margin-top: 15px;
        font-size: 28px;
        font-weight: bold;
        text-shadow: 0 0 20px rgba(0, 255, 255, 0.5);
        letter-spacing: 2px;
    }
    
    .logo-subtitle {
        color: #e0e5f0;
        font-size: 13px;
        opacity: 0.9;
        margin-top: -5px;
    }
    </style>
    
    <div class="logo-container">
        <div class="logo-circle">
            <span class="logo-emoji">🤖</span>
        </div>
        <div class="logo-title">AGUWEYBOT</div>
        <div class="logo-subtitle">Multi-Modelo IA</div>
    </div>
    """, unsafe_allow_html=True)

# ============================================
# ESTILOS CSS
# ============================================
def aplicar_estilos():
    st.markdown(f"""
    <style>
    h1 {{
        color: {Config.PRIMARY_COLOR} !important;
        font-size: 2.5rem !important;
        text-align: center;
        text-shadow: 0 0 20px rgba(0, 255, 255, 0.5);
        margin-bottom: 0.5rem !important;
        font-weight: bold;
    }}
    
    .subtitle {{
        text-align: center;
        color: #e0e5f0;
        margin-bottom: 2rem;
        font-size: 1.1rem;
    }}
    
    h2, h3 {{
        color: {Config.PRIMARY_COLOR} !important;
    }}
    
    .respuesta-aguwey {{
        background: linear-gradient(145deg, {Config.CARD_BACKGROUND}, #15232e);
        border-left: 6px solid {Config.PRIMARY_COLOR};
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        color: white;
        font-size: 1.1rem;
        line-height: 1.6;
        box-shadow: 0 4px 15px rgba(0, 255, 255, 0.1);
    }}
    
    [data-testid="stSidebar"] {{
        background: linear-gradient(165deg, #0e1219, #0a0e14);
        border-right: 2px solid {Config.PRIMARY_COLOR};
        padding: 1rem;
    }}
    
    .stButton > button {{
        background: linear-gradient(145deg, {Config.SECONDARY_COLOR}, {Config.PRIMARY_COLOR});
        color: black !important;
        font-weight: bold;
        border: none;
        border-radius: 20px;
        padding: 0.3rem 1rem;
        transition: all 0.2s;
    }}
    
    .stButton > button:hover {{
        transform: translateY(-2px);
        box-shadow: 0 4px 15px rgba(0, 255, 255, 0.3);
    }}
    
    .copy-btn {{
        background: rgba(0, 255, 255, 0.1);
        border: 1px solid {Config.PRIMARY_COLOR};
        color: {Config.PRIMARY_COLOR};
        border-radius: 8px;
        padding: 4px 12px;
        cursor: pointer;
        font-size: 12px;
        font-family: sans-serif;
        transition: all 0.3s ease;
        margin-left: 8px;
    }}
    
    .copy-btn:hover {{ 
        background: {Config.PRIMARY_COLOR}; 
        color: #000;
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(0, 255, 255, 0.3);
    }}
    
    .fixed-footer {{
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: rgba(10, 12, 16, 0.98);
        backdrop-filter: blur(12px);
        border-top: 2px solid {Config.PRIMARY_COLOR};
        padding: 0.8rem;
        text-align: center;
        color: #e0e5f0;
        z-index: 999;
        font-size: 0.95rem;
    }}
    
    .fixed-footer strong {{
        color: {Config.PRIMARY_COLOR};
    }}
    
    .model-badge {{
        background: rgba(0, 255, 255, 0.1);
        border: 1px solid {Config.PRIMARY_COLOR};
        border-radius: 20px;
        padding: 2px 8px;
        font-size: 10px;
        display: inline-block;
        margin-left: 10px;
    }}
    
    .stChatInput input {{
        border-radius: 20px;
        border: 1px solid {Config.PRIMARY_COLOR};
        background: rgba(255, 255, 255, 0.05);
        color: white;
    }}
    </style>
    """, unsafe_allow_html=True)

# ============================================
# BOTÓN DE COPIAR
# ============================================
def boton_copiar(texto: str, id_unico: str) -> None:
    texto_escapado = (texto.replace('\\', '\\\\')
                           .replace('`', '\\`')
                           .replace('$', '\\$')
                           .replace('\n', '\\n')
                           .replace("'", "\\'")
                           .replace('"', '\\"'))
    
    html_code = f"""
    <div style="text-align: right; margin-top: 0px;">
        <button id="btn_{id_unico}" class="copy-btn" onclick="copyText_{id_unico}()">
            📋 Copiar
        </button>
    </div>
    <script>
    function copyText_{id_unico}() {{
        const textToCopy = `{texto_escapado}`;
        if (navigator.clipboard && navigator.clipboard.writeText) {{
            navigator.clipboard.writeText(textToCopy).then(() => {{
                showCopied_{id_unico}();
            }}).catch(() => {{
                fallbackCopy_{id_unico}(textToCopy);
            }});
        }} else {{
            fallbackCopy_{id_unico}(textToCopy);
        }}
    }}
    function fallbackCopy_{id_unico}(text) {{
        const tempTextArea = document.createElement('textarea');
        tempTextArea.value = text;
        tempTextArea.style.position = 'fixed';
        tempTextArea.style.opacity = '0';
        document.body.appendChild(tempTextArea);
        tempTextArea.select();
        document.execCommand('copy');
        document.body.removeChild(tempTextArea);
        showCopied_{id_unico}();
    }}
    function showCopied_{id_unico}() {{
        const btn = document.getElementById("btn_{id_unico}");
        const originalText = btn.innerText;
        btn.innerText = "✅ ¡Copiado!";
        btn.style.background = "rgba(0, 255, 0, 0.2)";
        btn.style.borderColor = "#00ff00";
        btn.style.color = "#00ff00";
        setTimeout(() => {{ 
            btn.innerText = originalText;
            btn.style.background = "rgba(0, 255, 255, 0.1)";
            btn.style.borderColor = "#00ffff";
            btn.style.color = "#00ffff";
        }}, 2000);
    }}
    </script>
    """
    components.html(html_code, height=40)

# ============================================
# CLASE DATOS ARCHIVO
# ============================================
class DatosArchivo:
    def __init__(self):
        self.nombre: str = ""
        self.contenido_completo: str = ""
        self.tipo: str = ""
        self.dataframe: Optional[pd.DataFrame] = None
        self.num_paginas: int = 0
        self.num_caracteres: int = 0
        self.resumen: str = ""
        self.fecha_carga: float = time.time()
    
    def generar_resumen(self) -> str:
        if self.tipo == "pdf":
            return f"📄 PDF con {self.num_paginas} páginas"
        elif self.tipo in ["excel", "csv"]:
            if self.dataframe is not None:
                return f"📊 Tabla con {len(self.dataframe)} filas y {len(self.dataframe.columns)} columnas"
        elif self.tipo in ["txt", "docx"]:
            palabras = len(self.contenido_completo.split())
            return f"📝 Documento con {palabras} palabras"
        return "📁 Archivo procesado"

# ============================================
# FUNCIÓN PARA LEER ARCHIVOS
# ============================================
def leer_archivo_completo(uploaded_file):
    if uploaded_file is None:
        return None, "No hay archivo para procesar"
    
    try:
        uploaded_file.seek(0)
        uploaded_file.seek(0, os.SEEK_END)
        file_size = uploaded_file.tell()
        uploaded_file.seek(0)
        
        if file_size > Config.MAX_FILE_SIZE_MB * 1024 * 1024:
            return None, f"El archivo excede el límite de {Config.MAX_FILE_SIZE_MB}MB"
        
        nombre = uploaded_file.name.lower()
        datos = DatosArchivo()
        datos.nombre = uploaded_file.name
        
        if nombre.endswith(".pdf"):
            try:
                reader = PdfReader(uploaded_file)
                datos.num_paginas = len(reader.pages)
                texto_completo = []
                
                progress_bar = st.progress(0, text="📖 Leyendo PDF...")
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        texto_completo.append(f"--- PÁGINA {i+1} ---\n{page_text}")
                    progress_bar.progress((i + 1) / datos.num_paginas)
                
                datos.contenido_completo = "\n\n".join(texto_completo)
                datos.tipo = "pdf"
                progress_bar.empty()
                
                if not datos.contenido_completo:
                    return None, "El PDF no contiene texto extraíble"
            except Exception as e:
                return None, f"Error al leer PDF: {str(e)}"
        
        elif nombre.endswith((".xlsx", ".xls")):
            try:
                df = pd.read_excel(uploaded_file)
                datos.dataframe = df
                datos.contenido_completo = f"📊 ARCHIVO EXCEL: {uploaded_file.name}\n"
                datos.contenido_completo += f"Filas: {len(df)}, Columnas: {len(df.columns)}\n"
                datos.contenido_completo += f"Columnas: {', '.join(df.columns.tolist())}\n\n"
                datos.contenido_completo += "DATOS COMPLETOS:\n"
                datos.contenido_completo += df.to_string()
                datos.tipo = "excel"
            except Exception as e:
                return None, f"Error al leer Excel: {str(e)}"
        
        elif nombre.endswith(".csv"):
            try:
                raw_data = uploaded_file.read()
                result = chardet.detect(raw_data)
                encoding = result['encoding'] or 'utf-8'
                df = pd.read_csv(io.BytesIO(raw_data), encoding=encoding)
                datos.dataframe = df
                datos.contenido_completo = f"📊 ARCHIVO CSV: {uploaded_file.name}\n"
                datos.contenido_completo += f"Filas: {len(df)}, Columnas: {len(df.columns)}\n"
                datos.contenido_completo += f"Columnas: {', '.join(df.columns.tolist())}\n\n"
                datos.contenido_completo += "DATOS COMPLETOS:\n"
                datos.contenido_completo += df.to_string()
                datos.tipo = "csv"
            except Exception as e:
                return None, f"Error al leer CSV: {str(e)}"
        
        elif nombre.endswith(".txt"):
            try:
                contenido = uploaded_file.read()
                result = chardet.detect(contenido)
                encoding = result['encoding'] or 'utf-8'
                datos.contenido_completo = contenido.decode(encoding)
                datos.tipo = "txt"
            except Exception as e:
                return None, f"Error al leer TXT: {str(e)}"
        
        elif nombre.endswith(".docx"):
            try:
                doc = Document(uploaded_file)
                texto_completo = []
                for p in doc.paragraphs:
                    if p.text.strip():
                        texto_completo.append(p.text)
                for table in doc.tables:
                    for row in table.rows:
                        row_text = [cell.text for cell in row.cells]
                        texto_completo.append(" | ".join(row_text))
                datos.contenido_completo = "\n".join(texto_completo)
                datos.tipo = "docx"
                if not datos.contenido_completo:
                    return None, "El documento no contiene texto"
            except Exception as e:
                return None, f"Error al leer DOCX: {str(e)}"
        else:
            return None, f"Tipo de archivo no soportado: {nombre.split('.')[-1]}"
        
        datos.num_caracteres = len(datos.contenido_completo)
        datos.resumen = datos.generar_resumen()
        return datos, None
        
    except Exception as e:
        return None, f"Error inesperado: {str(e)}"

# ============================================
# FUNCIÓN PARA STREAMING CON MISTRAL (API REST)
# ============================================
def generar_respuesta_streaming_mistral(messages, container):
    """Genera respuesta con streaming usando la API REST de Mistral"""
    try:
        full_response = ""
        response_container = container.empty()
        
        headers = {
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        }
        
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        data = {
            "model": MODEL_NAME,
            "messages": formatted_messages,
            "temperature": 0.2,
            "max_tokens": 2000,
            "stream": True
        }
        
        response = requests.post(
            MISTRAL_API_URL,
            headers=headers,
            json=data,
            stream=True,
            timeout=60
        )
        
        if response.status_code != 200:
            st.error(f"❌ Error de API: {response.status_code}")
            return f"Error: {response.text}"
        
        start_time = time.time()
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    line = line[6:]
                    if line.strip() == '[DONE]':
                        break
                    
                    try:
                        chunk = json.loads(line)
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            delta = chunk['choices'][0].get('delta', {})
                            content = delta.get('content', '')
                            
                            if content:
                                full_response += content
                                
                                elapsed = time.time() - start_time
                                response_container.markdown(
                                    f'<div class="respuesta-aguwey" style="position: relative;">{full_response}▌<div style="position: absolute; bottom: 5px; right: 10px; font-size: 10px; color: #666;">Generando... {elapsed:.1f}s</div></div>',
                                    unsafe_allow_html=True
                                )
                                time.sleep(0.002)
                    except json.JSONDecodeError:
                        continue
        
        elapsed = time.time() - start_time
        response_container.markdown(
            f'<div class="respuesta-aguwey" style="position: relative;">{full_response}<div style="position: absolute; bottom: 5px; right: 10px; font-size: 10px; color: #666;">Generado con Mistral en {elapsed:.1f}s</div></div>',
            unsafe_allow_html=True
        )
        
        return full_response
        
    except requests.exceptions.Timeout:
        st.error("❌ Timeout: La solicitud excedió el tiempo límite")
        return "Error: Tiempo de espera agotado"
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Error de conexión: {str(e)}")
        return f"Error de conexión: {str(e)}"
    except Exception as e:
        st.error(f"❌ Error inesperado: {str(e)}")
        return f"Error: {str(e)}"

# ============================================
# FUNCIÓN PARA STREAMING CON QWEN 2.5 72B (OpenRouter)
# ============================================
def generar_respuesta_streaming_qwen(messages, container):
    """Genera respuesta con streaming usando Qwen 2.5 72B via OpenRouter"""
    if OPENROUTER_API_KEY is None:
        return "❌ Error: No se configuró la API key de OpenRouter. Agrega OPENROUTER_API_KEY a los secrets para usar Qwen."
    
    try:
        full_response = ""
        response_container = container.empty()
        
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://aguweybot.streamlit.app",
            "X-Title": "AguweyBot"
        }
        
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        data = {
            "model": "qwen/qwen-2.5-72b-instruct",
            "messages": formatted_messages,
            "temperature": 0.2,
            "max_tokens": 2000,
            "stream": True
        }
        
        response = requests.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=data,
            stream=True,
            timeout=120
        )
        
        if response.status_code != 200:
            st.error(f"❌ Error de OpenRouter: {response.status_code}")
            return f"Error: {response.text}"
        
        start_time = time.time()
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    line = line[6:]
                    if line.strip() == '[DONE]':
                        break
                    
                    try:
                        chunk = json.loads(line)
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            delta = chunk['choices'][0].get('delta', {})
                            content = delta.get('content', '')
                            
                            if content:
                                full_response += content
                                
                                elapsed = time.time() - start_time
                                response_container.markdown(
                                    f'<div class="respuesta-aguwey" style="position: relative;">{full_response}▌<div style="position: absolute; bottom: 5px; right: 10px; font-size: 10px; color: #666;">Generando con Qwen 2.5 72B... {elapsed:.1f}s</div></div>',
                                    unsafe_allow_html=True
                                )
                                time.sleep(0.002)
                    except json.JSONDecodeError:
                        continue
        
        elapsed = time.time() - start_time
        response_container.markdown(
            f'<div class="respuesta-aguwey" style="position: relative;">{full_response}<div style="position: absolute; bottom: 5px; right: 10px; font-size: 10px; color: #666;">Generado con Qwen 2.5 72B en {elapsed:.1f}s</div></div>',
            unsafe_allow_html=True
        )
        
        return full_response
        
    except requests.exceptions.Timeout:
        st.error("❌ Timeout: La solicitud excedió el tiempo límite")
        return "Error: Tiempo de espera agotado"
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Error de conexión: {str(e)}")
        return f"Error de conexión: {str(e)}"
    except Exception as e:
        st.error(f"❌ Error inesperado: {str(e)}")
        return f"Error: {str(e)}"

# ============================================
# FUNCIÓN PARA STREAMING CON GEMMA 4 (OpenRouter)
# ============================================
def generar_respuesta_streaming_gemma(messages, container):
    """Genera respuesta con streaming usando Gemma 4 via OpenRouter"""
    if OPENROUTER_API_KEY is None:
        return "❌ Error: No se configuró la API key de OpenRouter. Agrega OPENROUTER_API_KEY a los secrets para usar Gemma 4."
    
    try:
        full_response = ""
        response_container = container.empty()
        
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://aguweybot.streamlit.app",
            "X-Title": "AguweyBot"
        }
        
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        # Usamos Gemma 4 31B versión gratuita
        data = {
            "model": "google/gemma-4-31b-it:free",
            "messages": formatted_messages,
            "temperature": 0.7,
            "max_tokens": 2000,
            "stream": True
        }
        
        response = requests.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=data,
            stream=True,
            timeout=120
        )
        
        if response.status_code != 200:
            st.error(f"❌ Error de OpenRouter (Gemma): {response.status_code}")
            return f"Error: {response.text}"
        
        start_time = time.time()
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    line = line[6:]
                    if line.strip() == '[DONE]':
                        break
                    
                    try:
                        chunk = json.loads(line)
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            delta = chunk['choices'][0].get('delta', {})
                            content = delta.get('content', '')
                            
                            if content:
                                full_response += content
                                
                                elapsed = time.time() - start_time
                                response_container.markdown(
                                    f'<div class="respuesta-aguwey" style="position: relative;">{full_response}▌<div style="position: absolute; bottom: 5px; right: 10px; font-size: 10px; color: #666;">Generando con Gemma 4... {elapsed:.1f}s</div></div>',
                                    unsafe_allow_html=True
                                )
                                time.sleep(0.002)
                    except json.JSONDecodeError:
                        continue
        
        elapsed = time.time() - start_time
        response_container.markdown(
            f'<div class="respuesta-aguwey" style="position: relative;">{full_response}<div style="position: absolute; bottom: 5px; right: 10px; font-size: 10px; color: #666;">Generado con Gemma 4 31B en {elapsed:.1f}s</div></div>',
            unsafe_allow_html=True
        )
        
        return full_response
        
    except requests.exceptions.Timeout:
        st.error("❌ Timeout: La solicitud excedió el tiempo límite")
        return "Error: Tiempo de espera agotado"
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Error de conexión: {str(e)}")
        return f"Error de conexión: {str(e)}"
    except Exception as e:
        st.error(f"❌ Error inesperado: {str(e)}")
        return f"Error: {str(e)}"

# ============================================
# FUNCIÓN PRINCIPAL DE GENERACIÓN (elige el modelo)
# ============================================
def generar_respuesta_streaming(messages, container):
    """Genera respuesta según el modelo seleccionado"""
    modelo_actual = st.session_state.get("modelo_seleccionado", "mistral")
    
    if modelo_actual == "qwen":
        return generar_respuesta_streaming_qwen(messages, container)
    elif modelo_actual == "gemma":
        return generar_respuesta_streaming_gemma(messages, container)
    else:
        return generar_respuesta_streaming_mistral(messages, container)

# ============================================
# TEXTO A VOZ
# ============================================
def texto_a_audio_unico(texto: str) -> Optional[bytes]:
    if not TTS_AVAILABLE or not texto or not texto.strip():
        return None
    
    try:
        texto_limpio = re.sub(r'[#*_`\[\]()---+"📄📊🔊🔗🔘🎯✅❌⚠️📌📚🔹💡🔧🌳🌟🤔🛠️📈🔍📍📏📝👍📐⏳🌍🏗️🌱💧📜🗣️🌡️📋]', '', texto)
        texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()
        
        if not texto_limpio:
            return None
            
        tts = gTTS(text=texto_limpio, lang='es', slow=False)
        audio_bytes_io = io.BytesIO()
        tts.write_to_fp(audio_bytes_io)
        audio_bytes_io.seek(0)
        return audio_bytes_io.getvalue()
        
    except Exception as e:
        st.warning(f"⚠️ No se pudo generar audio: {str(e)}")
        return None

# ============================================
# EXPORTAR CONVERSACIÓN
# ============================================
def exportar_conversacion(messages: List[Dict]) -> str:
    export_text = "=" * 60 + "\n"
    export_text += f"CONVERSACIÓN AGUWEYBOT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    export_text += "=" * 60 + "\n\n"
    
    for i, msg in enumerate(messages, 1):
        role = "👤 USUARIO" if msg["role"] == "user" else "🤖 AGUWEYBOT"
        export_text += f"[{i}] {role}\n"
        export_text += "-" * 40 + "\n"
        export_text += msg["content"] + "\n"
        export_text += "-" * 40 + "\n\n"
    
    export_text += "=" * 60 + "\n"
    export_text += "FIN DE LA CONVERSACIÓN\n"
    export_text += "=" * 60
    
    return export_text

# ============================================
# FUNCIÓN PRINCIPAL
# ============================================
def main():
    st.set_page_config(
        page_title="AguweyBot - Asistente con Mistral + Qwen + Gemma 4",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    set_background()
    aplicar_estilos()
    
    # Inicializar session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "datos_archivo" not in st.session_state:
        st.session_state.datos_archivo = None
    if "primer_mensaje" not in st.session_state:
        st.session_state.primer_mensaje = True
    if "audio_actual_bytes" not in st.session_state:
        st.session_state.audio_actual_bytes = None
    if "ultimo_audio_idx" not in st.session_state:
        st.session_state.ultimo_audio_idx = -1
    if "modelo_seleccionado" not in st.session_state:
        st.session_state.modelo_seleccionado = "mistral"
    
    # Sidebar
    with st.sidebar:
        # Mostrar logo
        mostrar_logo()
        
        st.markdown("---")
        
        # Selector de modelo
        st.markdown("### 🧠 Modelo IA")
        
        # Opciones de modelo
        opciones_modelo = {
            "mistral": "🤖 Mistral Ministral-3 (Default - Rápido)",
            "qwen": "🐉 Qwen 2.5 72B (Requiere OpenRouter key)",
            "gemma": "🐐 Gemma 4 31B (Gratuito - vía OpenRouter)"
        }
        
        modelo_actual = st.radio(
            "Selecciona el modelo:",
            options=list(opciones_modelo.keys()),
            format_func=lambda x: opciones_modelo[x],
            index=0 if st.session_state.modelo_seleccionado == "mistral" else (1 if st.session_state.modelo_seleccionado == "qwen" else 2),
            key="selector_modelo"
        )
        
        if modelo_actual != st.session_state.modelo_seleccionado:
            st.session_state.modelo_seleccionado = modelo_actual
            st.rerun()
        
        st.markdown("---")
        
        # Mostrar estado de los modelos
        st.markdown("### 🔑 Estado de APIs")
        
        # Mistral
        st.success("✅ Mistral AI")
        st.markdown(f"<span style='font-size:11px'>🤖 {MODEL_NAME}</span>", unsafe_allow_html=True)
        
        # OpenRouter (para Qwen y Gemma)
        if OPENROUTER_API_KEY:
            st.success("✅ OpenRouter (Qwen + Gemma)")
            st.markdown(f"<span style='font-size:11px'>🐉 Qwen 2.5 72B | 🐐 Gemma 4 31B</span>", unsafe_allow_html=True)
        else:
            st.error("❌ OpenRouter no configurado")
            st.markdown(f"<span style='font-size:10px'>⚠️ Agrega OPENROUTER_API_KEY para usar Qwen y Gemma</span>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Estado del audio
        if TTS_AVAILABLE:
            st.success("✅ Audio disponible")
        else:
            st.warning("⚠️ Audio no disponible")
        
        st.markdown("---")
        
        # Guardar conversación
        st.markdown("### 💾 Conversaciones")
        if st.session_state.messages:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 Guardar", use_container_width=True):
                    filename = ConversacionGuardada.guardar_conversacion(st.session_state.messages)
                    st.success(f"✅ ¡Conversación guardada!")
                    st.rerun()
            with col2:
                export_text = exportar_conversacion(st.session_state.messages)
                st.download_button(
                    label="📄 Exportar",
                    data=export_text,
                    file_name=f"conversacion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
        
        st.markdown("---")
        
        # Lista de conversaciones guardadas
        conversaciones = ConversacionGuardada.listar_conversaciones()
        if conversaciones:
            st.markdown("**📚 Guardadas:**")
            for i, conv in enumerate(conversaciones[:5]):
                try:
                    fecha = datetime.strptime(conv["timestamp"], "%Y%m%d_%H%M%S").strftime("%d/%m/%Y %H:%M")
                except:
                    fecha = conv["timestamp"]
                
                col1, col2 = st.columns([8, 1])
                with col1:
                    if st.button(f"📝 {conv['nombre'][:25]}...", key=f"load_{i}", use_container_width=True):
                        mensajes_cargados = ConversacionGuardada.cargar_conversacion(conv["filename"])
                        if mensajes_cargados:
                            st.session_state.messages = mensajes_cargados
                            st.success("✅ Conversación cargada")
                            st.rerun()
                with col2:
                    if st.button("🗑️", key=f"del_{conv['filename']}_{i}", help="Eliminar"):
                        if ConversacionGuardada.eliminar_conversacion(conv["filename"]):
                            st.success("✅ Eliminada")
                            st.rerun()
        else:
            st.info("📭 No hay conversaciones guardadas")
        
        st.markdown("---")
        
        # Subir archivo
        st.markdown("### 📎 Subir Archivo")
        uploaded_file = st.file_uploader(
            "Elige un archivo",
            type=["pdf", "xlsx", "xls", "csv", "txt", "docx"],
            key="file_uploader",
            label_visibility="collapsed"
        )
        
        if uploaded_file is not None:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📖 Leer TODO", key="btn_leer", use_container_width=True):
                    with st.spinner("📖 Leyendo archivo..."):
                        datos, error = leer_archivo_completo(uploaded_file)
                        if error:
                            st.error(f"❌ {error}")
                        elif datos:
                            st.session_state.datos_archivo = datos
                            st.success(f"✅ {datos.resumen}")
                            st.balloons()
            with col2:
                if st.button("🔄 Limpiar", use_container_width=True):
                    st.session_state.datos_archivo = None
                    st.rerun()
        
        if st.session_state.datos_archivo:
            with st.expander("📁 Archivo activo", expanded=True):
                datos = st.session_state.datos_archivo
                st.markdown(f"""
                **Nombre:** {datos.nombre}
                **Tipo:** {datos.resumen}
                **Tamaño:** {datos.num_caracteres:,} caracteres
                """)
        
        st.markdown("---")
        
        if st.button("🔄 Nueva Conversación", use_container_width=True):
            st.session_state.messages = []
            st.session_state.audio_actual_bytes = None
            st.session_state.ultimo_audio_idx = -1
            st.success("¡Conversación reiniciada!")
            st.rerun()
    
    # Contenido principal
    # Determinar qué modelo mostrar en el título
    if st.session_state.modelo_seleccionado == "mistral":
        modelo_mostrar = "Ministral-3"
        modelo_icono = "🤖"
    elif st.session_state.modelo_seleccionado == "qwen":
        modelo_mostrar = "Qwen 2.5 72B"
        modelo_icono = "🐉"
    else:
        modelo_mostrar = "Gemma 4 31B"
        modelo_icono = "🐐"
    
    st.markdown(f"<h1>{modelo_icono} AguweyBot <span class='model-badge'>{modelo_mostrar}</span></h1>", unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Asistente inteligente con análisis de documentos y audio | 3 modelos disponibles</p>', unsafe_allow_html=True)
    
    # Mostrar historial
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                st.markdown(f'<div class="respuesta-aguwey">{msg["content"]}</div>', unsafe_allow_html=True)
                
                col_audio, col_copy, _ = st.columns([1, 1, 4])
                with col_audio:
                    if TTS_AVAILABLE:
                        if st.button(f"🔊 Escuchar", key=f"audio_{i}"):
                            with st.spinner("Generando audio..."):
                                audio_bytes = texto_a_audio_unico(msg["content"])
                                if audio_bytes:
                                    st.session_state.audio_actual_bytes = audio_bytes
                                    st.session_state.ultimo_audio_idx = i
                                    st.rerun()
                with col_copy:
                    boton_copiar(msg["content"], f"copy_{i}")
                
                if (st.session_state.get('audio_actual_bytes') and 
                    st.session_state.ultimo_audio_idx == i):
                    st.audio(st.session_state.audio_actual_bytes, format="audio/mpeg")
            else:
                st.markdown(f"**Tú:** {msg['content']}")
    
    # Mensaje de bienvenida
    if st.session_state.primer_mensaje and not st.session_state.messages:
        st.info("""
        👋 **¡Bienvenido a AguweyBot!**
        
        **🧠 Modelos disponibles (vía OpenRouter):**
        - **🤖 Mistral Ministral-3** (Default) - Rápido y eficiente
        - **🐉 Qwen 2.5 72B** - Muy potente, ideal para análisis complejos
        - **🐐 Gemma 4 31B** - Gratuito, 256K contexto, excelente para documentos largos
        
        **📝 Cómo usar:**
        1. Sube un archivo en el panel izquierdo
        2. Haz clic en **"Leer TODO"**
        3. Selecciona el modelo que prefieras
        4. Pregúntame sobre el contenido
        
        **💾 Guarda conversaciones** para retomarlas después
        """)
        st.session_state.primer_mensaje = False
    
    # Input del usuario
    prompt = st.chat_input("Escribe tu pregunta aquí...")
    
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(f"**Tú:** {prompt}")
        
        with st.chat_message("assistant"):
            try:
                # Construir mensajes
                messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                
                # Agregar historial
                for m in st.session_state.messages[-Config.MAX_HISTORY_MESSAGES:]:
                    messages.append({"role": m["role"], "content": m["content"]})
                
                # Agregar contexto del archivo
                if st.session_state.datos_archivo:
                    datos = st.session_state.datos_archivo
                    contenido_truncado = truncar_contexto(datos.contenido_completo, Config.MAX_CONTEXT_TOKENS)
                    contexto = f"""
📁 ARCHIVO: {datos.nombre}
TIPO: {datos.resumen}

========== CONTENIDO ==========
{contenido_truncado}
========== FIN CONTENIDO ==========

PREGUNTA: {prompt}
"""
                    messages.append({"role": "user", "content": contexto})
                
                # Generar respuesta
                container = st.empty()
                response = generar_respuesta_streaming(messages, container)
                
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                # Limpiar audio después de nueva respuesta
                st.session_state.audio_actual_bytes = None
                st.session_state.ultimo_audio_idx = -1
                st.rerun()
                        
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    # Footer
    st.markdown(
        f"""
        <div class="fixed-footer">
            <strong>CC-SA</strong> Prof. Raymond Rosa Ávila • AguweyBot v7.0 • 3 Modelos: Mistral + Qwen + Gemma 4 • 2026
        </div>
        """,
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
