# ============================================
# AGUWEYBOT - MULTI-USUARIO PARA STREAMLIT CLOUD
# VERSIÓN CON GITHUB - MAYO 2026
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
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
from functools import lru_cache

# Autenticación
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

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

# ============================================
# CONFIGURACIÓN DESDE SECRETS
# ============================================
MODEL_NAME = "ministral-3b-latest"
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Cargar configuración desde secrets
MISTRAL_API_KEY = st.secrets["MISTRAL_API_KEY"]
OPENROUTER_API_KEY = st.secrets.get("OPENROUTER_API_KEY", None)

# Configuración de usuarios desde secrets
USERS_CONFIG = {}
for username, user_data in st.secrets["users"].items():
    USERS_CONFIG[username] = {
        "name": user_data["name"],
        "password": user_data["password"],
        "email": user_data["email"],
        "role": user_data.get("role", "user")
    }

ADMIN_USERNAMES = st.secrets["app"].get("admin_usernames", [])

# Límites
MAX_CONVERSATIONS = int(st.secrets["limits"].get("max_conversations", 50))
MAX_FILE_SIZE_MB = int(st.secrets["limits"].get("max_file_size_mb", 50))
MAX_STORAGE_MB = int(st.secrets["limits"].get("max_storage_mb", 500))

# ============================================
# GESTIÓN DE DATOS POR USUARIO (Versión Cloud)
# ============================================
class UserDataManager:
    """Gestiona datos privados por usuario en Streamlit Cloud"""
    
    def __init__(self, username: str):
        self.username = username
        # Usar directorio persistente en Streamlit Cloud
        self.base_dir = Path(os.getenv('STREAMLIT_DATA_DIR', 'user_data'))
        self.user_dir = self.base_dir / username
        self.conversations_dir = self.user_dir / "conversaciones"
        self.files_dir = self.user_dir / "archivos"
        
        # Crear directorios del usuario
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)
    
    def get_storage_usage_mb(self) -> float:
        """Calcula el uso de almacenamiento del usuario en MB"""
        total_bytes = 0
        for filepath in self.user_dir.rglob("*"):
            if filepath.is_file():
                total_bytes += filepath.stat().st_size
        return total_bytes / (1024 * 1024)
    
    def check_storage_limit(self) -> bool:
        """Verifica si el usuario excede el límite de almacenamiento"""
        usage = self.get_storage_usage_mb()
        if usage > MAX_STORAGE_MB:
            st.warning(f"⚠️ Has alcanzado el límite de almacenamiento ({MAX_STORAGE_MB} MB). "
                      f"Por favor, elimina algunas conversaciones o archivos viejos.")
            return False
        return True
    
    def save_conversation(self, messages: List[Dict], nombre: str = None) -> Optional[str]:
        """Guarda conversación del usuario"""
        if not self.check_storage_limit():
            return None
            
        if not nombre:
            first_user_msg = next((m["content"] for m in messages if m["role"] == "user"), "Nueva conversacion")
            nombre = first_user_msg[:50].replace(" ", "_").replace("/", "_").replace("\\", "_")
            nombre = re.sub(r'[^\w\-_\.]', '', nombre)
        
        # Verificar límite de conversaciones
        existing_conversations = len(list(self.conversations_dir.glob("*.json")))
        if existing_conversations >= MAX_CONVERSATIONS:
            st.warning(f"⚠️ Has alcanzado el límite de {MAX_CONVERSATIONS} conversaciones guardadas. "
                      f"Elimina algunas para guardar nuevas.")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.conversations_dir / f"{timestamp}_{nombre}.json"
        
        data = {
            "username": self.username,
            "timestamp": timestamp,
            "nombre": nombre,
            "mensajes": messages,
            "total_mensajes": len(messages),
            "modelo": st.session_state.get(f"modelo_{self.username}", "mistral")
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return str(filename)
    
    def load_conversation(self, filename: str) -> Optional[List[Dict]]:
        """Carga conversación del usuario"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("mensajes", [])
        except Exception as e:
            st.error(f"Error al cargar conversación: {str(e)}")
            return None
    
    def list_conversations(self) -> List[Dict[str, Any]]:
        """Lista conversaciones del usuario"""
        conversaciones = []
        
        for filepath in sorted(self.conversations_dir.glob("*.json"), reverse=True):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                conversaciones.append({
                    "filename": str(filepath),
                    "nombre": data.get("nombre", "Sin nombre"),
                    "timestamp": data.get("timestamp", "Desconocido"),
                    "total_mensajes": data.get("total_mensajes", 0),
                    "modelo": data.get("modelo", "Desconocido")
                })
            except:
                continue
        
        return conversaciones
    
    def delete_conversation(self, filename: str) -> bool:
        """Elimina conversación del usuario"""
        try:
            if os.path.exists(filename):
                os.remove(filename)
                return True
        except Exception as e:
            st.error(f"Error al eliminar: {str(e)}")
        return False
    
    def save_uploaded_file(self, uploaded_file) -> Optional[str]:
        """Guarda archivo subido del usuario"""
        if uploaded_file is None:
            return None
        
        if not self.check_storage_limit():
            return None
        
        # Verificar tamaño
        uploaded_file.seek(0, os.SEEK_END)
        file_size_mb = uploaded_file.tell() / (1024 * 1024)
        uploaded_file.seek(0)
        
        if file_size_mb > MAX_FILE_SIZE_MB:
            st.error(f"❌ El archivo excede el límite de {MAX_FILE_SIZE_MB} MB")
            return None
        
        # Crear nombre único
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{uploaded_file.name}"
        filepath = self.files_dir / safe_filename
        
        with open(filepath, 'wb') as f:
            f.write(uploaded_file.getbuffer())
        
        return str(filepath)
    
    def clean_old_files(self, days_old: int = 30):
        """Limpia archivos antiguos del usuario"""
        cutoff_time = time.time() - (days_old * 86400)
        for filepath in self.files_dir.glob("*"):
            if filepath.stat().st_mtime < cutoff_time:
                try:
                    filepath.unlink()
                except:
                    pass

# ============================================
# SISTEMA DE AUTENTICACIÓN
# ============================================
def init_auth():
    """Inicializa el sistema de autenticación con hashing"""
    
    # Crear configuración para authenticator
    credentials = {"usernames": {}}
    
    for username, user_data in USERS_CONFIG.items():
        # Hashear la contraseña
        hashed_password = stauth.Hasher([user_data["password"]]).generate()[0]
        
        credentials["usernames"][username] = {
            "email": user_data["email"],
            "name": user_data["name"],
            "password": hashed_password,
            "role": user_data.get("role", "user")
        }
    
    # Configuración de la cookie
    cookie_config = {
        'name': 'aguweybot_auth',
        'key': base64.b64encode(os.urandom(32)).decode(),
        'expiry_days': 7
    }
    
    authenticator = stauth.Authenticate(
        credentials,
        cookie_config['name'],
        cookie_config['key'],
        cookie_config['expiry_days']
    )
    
    return authenticator

def login_screen():
    """Muestra pantalla de login estilizada"""
    st.markdown("""
    <style>
    .login-container {
        max-width: 450px;
        margin: 0 auto;
        padding: 2rem;
        background: rgba(30, 42, 58, 0.95);
        border-radius: 20px;
        border: 2px solid #00ffff;
        box-shadow: 0 0 30px rgba(0, 255, 255, 0.3);
        backdrop-filter: blur(10px);
    }
    .login-title {
        text-align: center;
        color: #00ffff;
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    .login-subtitle {
        text-align: center;
        color: #e0e5f0;
        margin-bottom: 2rem;
        font-size: 0.9rem;
    }
    .stButton > button {
        background: linear-gradient(145deg, #00cccc, #00ffff);
        color: black;
        font-weight: bold;
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        st.markdown('<h1 class="login-title">🤖 AguweyBot</h1>', unsafe_allow_html=True)
        st.markdown('<p class="login-subtitle">Asistente IA Multi-Usuario</p>', unsafe_allow_html=True)
        
        # Formulario de login
        with st.form("login_form"):
            username = st.text_input("👤 Usuario", placeholder="Ingresa tu usuario")
            password = st.text_input("🔒 Contraseña", type="password", placeholder="Ingresa tu contraseña")
            submit = st.form_submit_button("🚀 Iniciar Sesión", use_container_width=True)
            
            if submit:
                if username in USERS_CONFIG and USERS_CONFIG[username]["password"] == password:
                    st.session_state["authentication_status"] = True
                    st.session_state["username"] = username
                    st.session_state["user_name"] = USERS_CONFIG[username]["name"]
                    st.session_state["user_role"] = USERS_CONFIG[username].get("role", "user")
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos")
        
        st.markdown('</div>', unsafe_allow_html=True)

# ============================================
# CONSTANTES Y CONFIGURACIÓN VISUAL
# ============================================
class Config:
    PRIMARY_COLOR = "#00ffff"
    SECONDARY_COLOR = "#00cccc"
    BACKGROUND_DARK = "#0a0c10"
    CARD_BACKGROUND = "#1e2a3a"
    MAX_HISTORY_MESSAGES = 10
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
# FUNCIONES AUXILIARES (Las mismas que tenías)
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

def set_background():
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
        max-width: 1200px !important;
    }}
    </style>
    """, unsafe_allow_html=True)

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
        transition: all 0.3s ease;
        margin-left: 8px;
    }}
    
    .copy-btn:hover {{ 
        background: {Config.PRIMARY_COLOR}; 
        color: #000;
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
        font-size: 0.9rem;
    }}
    
    .fixed-footer strong {{
        color: {Config.PRIMARY_COLOR};
    }}
    
    .model-badge {{
        background: rgba(0, 255, 255, 0.1);
        border: 1px solid {Config.PRIMARY_COLOR};
        border-radius: 20px;
        padding: 2px 8px;
        font-size: 12px;
        display: inline-block;
        margin-left: 10px;
    }}
    </style>
    """, unsafe_allow_html=True)

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
        navigator.clipboard.writeText(textToCopy).then(() => {{
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
        }});
    }}
    </script>
    """
    components.html(html_code, height=40)

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
    
    return export_text

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
        return None

def leer_archivo_completo(uploaded_file, user_manager):
    """Lee archivo y lo guarda en el directorio del usuario"""
    if uploaded_file is None:
        return None, "No hay archivo para procesar"
    
    # Guardar archivo
    saved_path = user_manager.save_uploaded_file(uploaded_file)
    if not saved_path:
        return None, "Error al guardar archivo o límite de almacenamiento excedido"
    
    try:
        file_path = Path(saved_path)
        nombre = uploaded_file.name.lower()
        datos = DatosArchivo()
        datos.nombre = uploaded_file.name
        
        # Procesar según tipo de archivo
        if nombre.endswith(".pdf"):
            try:
                reader = PdfReader(file_path)
                datos.num_paginas = len(reader.pages)
                texto_completo = []
                
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        texto_completo.append(f"--- PÁGINA {i+1} ---\n{page_text}")
                
                datos.contenido_completo = "\n\n".join(texto_completo)
                datos.tipo = "pdf"
            except Exception as e:
                return None, f"Error al leer PDF: {str(e)}"
        
        elif nombre.endswith((".xlsx", ".xls")):
            try:
                df = pd.read_excel(file_path)
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
                raw_data = file_path.read_bytes()
                result = chardet.detect(raw_data)
                encoding = result['encoding'] or 'utf-8'
                df = pd.read_csv(file_path, encoding=encoding)
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
                datos.contenido_completo = file_path.read_text(encoding='utf-8')
                datos.tipo = "txt"
            except:
                try:
                    datos.contenido_completo = file_path.read_text(encoding='latin-1')
                    datos.tipo = "txt"
                except Exception as e:
                    return None, f"Error al leer TXT: {str(e)}"
        
        elif nombre.endswith(".docx"):
            try:
                doc = Document(file_path)
                texto_completo = []
                for p in doc.paragraphs:
                    if p.text.strip():
                        texto_completo.append(p.text)
                datos.contenido_completo = "\n".join(texto_completo)
                datos.tipo = "docx"
            except Exception as e:
                return None, f"Error al leer DOCX: {str(e)}"
        else:
            return None, f"Tipo de archivo no soportado"
        
        datos.num_caracteres = len(datos.contenido_completo)
        datos.resumen = datos.generar_resumen()
        
        # Limpiar archivo temporal después de procesar
        file_path.unlink()
        
        return datos, None
        
    except Exception as e:
        return None, f"Error inesperado: {str(e)}"

# ============================================
# FUNCIONES DE API (Las mismas que tenías)
# ============================================

def generar_respuesta_streaming_mistral(messages, container):
    """Genera respuesta con Mistral"""
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
        
        response_container.markdown(
            f'<div class="respuesta-aguwey">{full_response}</div>',
            unsafe_allow_html=True
        )
        
        return full_response
        
    except Exception as e:
        return f"Error: {str(e)}"

def generar_respuesta_streaming_qwen(messages, container):
    """Genera respuesta con Qwen via OpenRouter"""
    if OPENROUTER_API_KEY is None:
        return "❌ Error: OpenRouter no configurado"
    
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
                                    f'<div class="respuesta-aguwey" style="position: relative;">{full_response}▌<div style="position: absolute; bottom: 5px; right: 10px; font-size: 10px; color: #666;">Generando con Qwen... {elapsed:.1f}s</div></div>',
                                    unsafe_allow_html=True
                                )
                                time.sleep(0.002)
                    except json.JSONDecodeError:
                        continue
        
        response_container.markdown(
            f'<div class="respuesta-aguwey">{full_response}</div>',
            unsafe_allow_html=True
        )
        
        return full_response
        
    except Exception as e:
        return f"Error: {str(e)}"

def generar_respuesta_streaming_gemma(messages, container):
    """Genera respuesta con Gemma via OpenRouter"""
    if OPENROUTER_API_KEY is None:
        return "❌ Error: OpenRouter no configurado"
    
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
                                    f'<div class="respuesta-aguwey" style="position: relative;">{full_response}▌<div style="position: absolute; bottom: 5px; right: 10px; font-size: 10px; color: #666;">Generando con Gemma... {elapsed:.1f}s</div></div>',
                                    unsafe_allow_html=True
                                )
                                time.sleep(0.002)
                    except json.JSONDecodeError:
                        continue
        
        response_container.markdown(
            f'<div class="respuesta-aguwey">{full_response}</div>',
            unsafe_allow_html=True
        )
        
        return full_response
        
    except Exception as e:
        return f"Error: {str(e)}"

# ============================================
# FUNCIÓN PRINCIPAL
# ============================================
def main():
    st.set_page_config(
        page_title="AguweyBot - Multi-Usuario",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Verificar autenticación
    if "authentication_status" not in st.session_state:
        st.session_state["authentication_status"] = False
    
    if not st.session_state["authentication_status"]:
        login_screen()
        return
    
    # Usuario autenticado
    username = st.session_state["username"]
    user_name = st.session_state["user_name"]
    user_role = st.session_state["user_role"]
    user_manager = UserDataManager(username)
    
    # Inicializar session state del usuario
    session_key = f"user_{username}"
    if session_key not in st.session_state:
        st.session_state[session_key] = {
            "messages": [],
            "datos_archivo": None,
            "primer_mensaje": True,
            "audio_actual_bytes": None,
            "ultimo_audio_idx": -1,
            "modelo_seleccionado": "mistral"
        }
    
    user_state = st.session_state[session_key]
    
    # Aplicar estilos
    set_background()
    aplicar_estilos()
    
    # Sidebar
    with st.sidebar:
        # Logo (opcional)
        st.markdown("""
        <div style="text-align: center; padding: 20px 0;">
            <div style="background: linear-gradient(145deg, #00cccc, #00ffff); border-radius: 50%; width: 100px; height: 100px; margin: 0 auto; display: flex; align-items: center; justify-content: center;">
                <span style="font-size: 50px;">🤖</span>
            </div>
            <h2 style="color: #00ffff; margin-top: 15px;">AguweyBot</h2>
        </div>
        """, unsafe_allow_html=True)
        
        # Información del usuario
        st.markdown(f"""
        <div style="text-align: center; padding: 10px; background: rgba(0,255,255,0.1); border-radius: 10px; margin-bottom: 20px;">
            👤 <strong>{user_name}</strong><br>
            <span style="font-size: 12px;">@{username}</span><br>
            <span style="font-size: 10px;">🎭 {user_role}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # Mostrar almacenamiento usado
        storage_usage = user_manager.get_storage_usage_mb()
        storage_percent = min(100, (storage_usage / MAX_STORAGE_MB) * 100)
        st.progress(storage_percent / 100, text=f"💾 Almacenamiento: {storage_usage:.1f} MB / {MAX_STORAGE_MB} MB")
        
        # Botón de logout
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state["authentication_status"] = False
            st.session_state.pop(session_key, None)
            st.rerun()
        
        st.markdown("---")
        
        # Selector de modelo
        st.markdown("### 🧠 Modelo IA")
        opciones_modelo = {
            "mistral": "🤖 Mistral Ministral-3",
            "qwen": "🐉 Qwen 2.5 72B",
            "gemma": "🐐 Gemma 4 31B"
        }
        
        modelo_actual = st.radio(
            "Selecciona el modelo:",
            options=list(opciones_modelo.keys()),
            format_func=lambda x: opciones_modelo[x],
            index=0,
            key=f"modelo_selector_{username}"
        )
        
        if modelo_actual != user_state["modelo_seleccionado"]:
            user_state["modelo_seleccionado"] = modelo_actual
            st.rerun()
        
        st.markdown("---")
        
        # Estado de APIs
        st.markdown("### 🔑 Estado de APIs")
        st.success("✅ Mistral AI")
        if OPENROUTER_API_KEY:
            st.success("✅ OpenRouter")
        else:
            st.error("❌ OpenRouter no configurado")
        
        st.markdown("---")
        
        # Guardar conversación
        st.markdown("### 💾 Mis Conversaciones")
        if user_state["messages"]:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 Guardar", use_container_width=True):
                    filename = user_manager.save_conversation(user_state["messages"])
                    if filename:
                        st.success("✅ ¡Conversación guardada!")
                    st.rerun()
            with col2:
                export_text = exportar_conversacion(user_state["messages"])
                st.download_button(
                    label="📄 Exportar",
                    data=export_text,
                    file_name=f"conversacion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
        
        st.markdown("---")
        
        # Listar conversaciones guardadas
        conversaciones = user_manager.list_conversations()
        if conversaciones:
            st.markdown("**📚 Guardadas:**")
            for i, conv in enumerate(conversaciones[:5]):
                col1, col2 = st.columns([8, 1])
                with col1:
                    if st.button(f"📝 {conv['nombre'][:20]}...", key=f"load_{username}_{i}", use_container_width=True):
                        mensajes_cargados = user_manager.load_conversation(conv["filename"])
                        if mensajes_cargados:
                            user_state["messages"] = mensajes_cargados
                            st.success("✅ Conversación cargada")
                            st.rerun()
                with col2:
                    if st.button("🗑️", key=f"del_{username}_{i}"):
                        if user_manager.delete_conversation(conv["filename"]):
                            st.success("✅ Eliminada")
                            st.rerun()
        
        st.markdown("---")
        
        # Subir archivo
        st.markdown("### 📎 Subir Archivo")
        uploaded_file = st.file_uploader(
            "Elige un archivo",
            type=["pdf", "xlsx", "xls", "csv", "txt", "docx"],
            key=f"file_uploader_{username}",
            label_visibility="collapsed"
        )
        
        if uploaded_file is not None:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📖 Leer TODO", key=f"btn_leer_{username}", use_container_width=True):
                    with st.spinner("📖 Leyendo archivo..."):
                        datos, error = leer_archivo_completo(uploaded_file, user_manager)
                        if error:
                            st.error(f"❌ {error}")
                        elif datos:
                            user_state["datos_archivo"] = datos
                            st.success(f"✅ {datos.resumen}")
                            st.balloons()
            with col2:
                if st.button("🔄 Limpiar", key=f"clear_{username}", use_container_width=True):
                    user_state["datos_archivo"] = None
                    st.rerun()
        
        if user_state["datos_archivo"]:
            with st.expander("📁 Archivo activo", expanded=True):
                datos = user_state["datos_archivo"]
                st.markdown(f"""
                **Nombre:** {datos.nombre}
                **Tipo:** {datos.resumen}
                **Tamaño:** {datos.num_caracteres:,} caracteres
                """)
        
        st.markdown("---")
        
        if st.button("🔄 Nueva Conversación", key=f"new_conv_{username}", use_container_width=True):
            user_state["messages"] = []
            user_state["datos_archivo"] = None
            user_state["audio_actual_bytes"] = None
            user_state["ultimo_audio_idx"] = -1
            st.success("¡Conversación reiniciada!")
            st.rerun()
    
    # Contenido principal
    modelo_iconos = {"mistral": "🤖", "qwen": "🐉", "gemma": "🐐"}
    modelo_nombres = {"mistral": "Ministral-3", "qwen": "Qwen 2.5 72B", "gemma": "Gemma 4 31B"}
    
    current_model = user_state["modelo_seleccionado"]
    
    st.markdown(f"""
    <h1>{modelo_iconos[current_model]} AguweyBot <span class='model-badge'>{modelo_nombres[current_model]}</span></h1>
    <p class="subtitle">👋 Hola {user_name} | Asistente con análisis de documentos y audio</p>
    """, unsafe_allow_html=True)
    
    # Mostrar historial
    for i, msg in enumerate(user_state["messages"]):
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                st.markdown(f'<div class="respuesta-aguwey">{msg["content"]}</div>', unsafe_allow_html=True)
                
                col_audio, col_copy, _ = st.columns([1, 1, 4])
                with col_audio:
                    if TTS_AVAILABLE:
                        if st.button(f"🔊 Escuchar", key=f"audio_{username}_{i}"):
                            with st.spinner("Generando audio..."):
                                audio_bytes = texto_a_audio_unico(msg["content"])
                                if audio_bytes:
                                    user_state["audio_actual_bytes"] = audio_bytes
                                    user_state["ultimo_audio_idx"] = i
                                    st.rerun()
                with col_copy:
                    boton_copiar(msg["content"], f"copy_{username}_{i}")
                
                if (user_state.get('audio_actual_bytes') and 
                    user_state["ultimo_audio_idx"] == i):
                    st.audio(user_state["audio_actual_bytes"], format="audio/mpeg")
            else:
                st.markdown(f"**Tú:** {msg['content']}")
    
    # Mensaje de bienvenida
    if user_state["primer_mensaje"] and not user_state["messages"]:
        st.info(f"""
        👋 **¡Bienvenido {user_name} a AguweyBot!**
        
        **🧠 Modelos disponibles:**
        - **🤖 Mistral Ministral-3** (Default) - Rápido y eficiente
        - **🐉 Qwen 2.5 72B** - Muy potente, ideal para análisis complejos
        - **🐐 Gemma 4 31B** - Gratuito, 256K contexto
        
        **📝 Cómo usar:**
        1. Sube un archivo en el panel izquierdo
        2. Haz clic en **"Leer TODO"**
        3. Selecciona el modelo que prefieras
        4. Pregúntame sobre el contenido
        
        **🔒 Privacidad:** Cada usuario tiene sus propias conversaciones y archivos
        """)
        user_state["primer_mensaje"] = False
    
    # Input del usuario
    prompt = st.chat_input("Escribe tu pregunta aquí...")
    
    if prompt:
        user_state["messages"].append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(f"**Tú:** {prompt}")
        
        with st.chat_message("assistant"):
            try:
                messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                
                for m in user_state["messages"][-Config.MAX_HISTORY_MESSAGES:]:
                    messages.append({"role": m["role"], "content": m["content"]})
                
                if user_state["datos_archivo"]:
                    datos = user_state["datos_archivo"]
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
                
                container = st.empty()
                
                if current_model == "qwen":
                    response = generar_respuesta_streaming_qwen(messages, container)
                elif current_model == "gemma":
                    response = generar_respuesta_streaming_gemma(messages, container)
                else:
                    response = generar_respuesta_streaming_mistral(messages, container)
                
                user_state["messages"].append({"role": "assistant", "content": response})
                
                user_state["audio_actual_bytes"] = None
                user_state["ultimo_audio_idx"] = -1
                st.rerun()
                        
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    # Footer
    st.markdown(f"""
    <div class="fixed-footer">
        <strong>CC-SA</strong> Prof. Raymond Rosa Ávila • AguweyBot Multi-Usuario • {user_name} • 2026
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()