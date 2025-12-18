import os
import asyncio
import shutil
import tempfile
import sys
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import aiohttp
import zipfile
import io
import json
import re
import uuid
import time
import pathlib
import mimetypes
import humanize
from typing import Optional, Tuple, Dict, Any, List
import logging
from datetime import datetime, timedelta
import stat
import hashlib
from functools import wraps
import base64

# ==============================================
# CONFIGURACIÓN DE LOGGING
# ==============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==============================================
# CONFIGURACIÓN PRINCIPAL
# ==============================================
API_ID = os.getenv("API_ID") or 14681595
API_HASH = os.getenv("API_HASH") or "a86730aab5c59953c424abb4396d32d5"
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8138537409:AAGMLe6R1nk8wHmfE2AZVSdG4_AQ8aaISSA"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or "tu_token_de_github_aquí"
ADMIN_ID = 7970466590
ADMINS = [ADMIN_ID]

logger.info(f"✅ Administrador exclusivo configurado: {ADMIN_ID}")

# ==============================================
# DECORADOR ADMIN ONLY - DEFINIDO AL PRINCIPIO
# ==============================================
def admin_only(func):
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        user_id = message.from_user.id if message.from_user else None
        
        if user_id != ADMIN_ID:
            await message.reply_text(
                "❌ **Acceso denegado**\n\n"
                "Esta función solo está disponible para el administrador del bot.",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        return await func(client, message, *args, **kwargs)
    return wrapper

# ==============================================
# VERIFICACIÓN DE CREDENCIALES
# ==============================================
if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("❌ Faltan credenciales de Telegram. Configura las variables de entorno.")
    exit(1)

if not GITHUB_TOKEN or GITHUB_TOKEN == "tu_token_de_github_aquí":
    logger.warning("⚠️ No se configuró GITHUB_TOKEN. Las funciones de gestión de GitHub no estarán disponibles.")

# ==============================================
# INICIALIZACIÓN DE LA APLICACIÓN
# ==============================================
app = Client(
    "github_manager_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ==============================================
# CONFIGURACIONES GLOBALES
# ==============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp_downloads")
os.makedirs(TEMP_DIR, exist_ok=True)

search_cache: Dict[str, Dict[str, Any]] = {}
rename_states = {}
mkdir_states = {}
search_states = {}
github_states = {}
MAX_FILE_SIZE = 50 * 1024 * 1024
SEARCH_CACHE_TIMEOUT = 1800
DOWNLOAD_TIMEOUT = 300

# ==============================================
# CLASE GITHUB MANAGER
# ==============================================
class GitHubManager:
    """Clase para gestionar operaciones de GitHub API"""
    
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-Manager-Bot'
        }
        self.base_url = "https://api.github.com"
        
    async def test_connection(self) -> Tuple[bool, str]:
        """Testear conexión a GitHub API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/user",
                    headers=self.headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return True, f"✅ Conectado como: {data.get('login', 'Desconocido')}"
                    else:
                        return False, f"❌ Error {response.status}: {await response.text()}"
        except Exception as e:
            return False, f"❌ Error de conexión: {str(e)}"
    
    async def get_user_info(self) -> Dict[str, Any]:
        """Obtener información del usuario"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/user",
                    headers=self.headers
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return {}
        except Exception as e:
            logger.error(f"Error obteniendo info usuario: {e}")
            return {}
    
    async def list_repos(self, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        """Listar repositorios del usuario"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/user/repos",
                    headers=self.headers,
                    params={'page': page, 'per_page': per_page, 'sort': 'updated'}
                ) as response:
                    if response.status == 200:
                        repos = await response.json()
                        
                        total = 0
                        if 'Link' in response.headers:
                            links = response.headers['Link']
                            match = re.search(r'page=(\d+)>; rel="last"', links)
                            if match:
                                last_page = int(match.group(1))
                                total = last_page * per_page
                        
                        return {
                            'repos': repos,
                            'page': page,
                            'per_page': per_page,
                            'total': total,
                            'has_next': len(repos) == per_page
                        }
                    return {'error': f'HTTP {response.status}'}
        except Exception as e:
            logger.error(f"Error listando repos: {e}")
            return {'error': str(e)}
    
    async def create_repo(self, name: str, description: str = "", 
                         private: bool = False, auto_init: bool = True) -> Tuple[bool, str]:
        """Crear nuevo repositorio"""
        try:
            data = {
                'name': name,
                'description': description,
                'private': private,
                'auto_init': auto_init
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/user/repos",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status == 201:
                        repo_data = await response.json()
                        return True, f"✅ Repositorio creado: {repo_data['html_url']}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error creando repo: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def delete_repo(self, owner: str, repo_name: str) -> Tuple[bool, str]:
        """Eliminar repositorio"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{self.base_url}/repos/{owner}/{repo_name}",
                    headers=self.headers
                ) as response:
                    if response.status == 204:
                        return True, f"✅ Repositorio eliminado: {owner}/{repo_name}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error eliminando repo: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def fork_repo(self, owner: str, repo_name: str) -> Tuple[bool, str]:
        """Hacer fork de un repositorio"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/repos/{owner}/{repo_name}/forks",
                    headers=self.headers
                ) as response:
                    if response.status == 202:
                        repo_data = await response.json()
                        return True, f"✅ Fork creado: {repo_data['html_url']}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error haciendo fork: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def get_repo_info(self, owner: str, repo_name: str) -> Dict[str, Any]:
        """Obtener información detallada de un repositorio"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/repos/{owner}/{repo_name}",
                    headers=self.headers
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return {'error': f'HTTP {response.status}'}
        except Exception as e:
            logger.error(f"Error obteniendo info repo: {e}")
            return {'error': str(e)}
    
    async def create_file(self, owner: str, repo_name: str, path: str, 
                         content: str, message: str = "Add file via GitHub Manager Bot") -> Tuple[bool, str]:
        """Crear o actualizar archivo en repositorio"""
        try:
            content_b64 = base64.b64encode(content.encode()).decode()
            
            data = {
                'message': message,
                'content': content_b64
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{self.base_url}/repos/{owner}/{repo_name}/contents/{path}",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status in [200, 201]:
                        return True, f"✅ Archivo creado/actualizado: {path}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error creando archivo: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def list_branches(self, owner: str, repo_name: str) -> List[str]:
        """Listar ramas de un repositorio"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/repos/{owner}/{repo_name}/branches",
                    headers=self.headers
                ) as response:
                    if response.status == 200:
                        branches = await response.json()
                        return [branch['name'] for branch in branches]
                    return []
        except Exception as e:
            logger.error(f"Error listando ramas: {e}")
            return []
    
    async def create_branch(self, owner: str, repo_name: str, 
                           branch_name: str, from_branch: str = "main") -> Tuple[bool, str]:
        """Crear nueva rama"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/repos/{owner}/{repo_name}/git/refs/heads/{from_branch}",
                    headers=self.headers
                ) as response:
                    if response.status != 200:
                        return False, f"❌ Error obteniendo SHA: {response.status}"
                    
                    ref_data = await response.json()
                    sha = ref_data['object']['sha']
                
                data = {
                    'ref': f'refs/heads/{branch_name}',
                    'sha': sha
                }
                
                async with session.post(
                    f"{self.base_url}/repos/{owner}/{repo_name}/git/refs",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status == 201:
                        return True, f"✅ Rama creada: {branch_name}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error creando rama: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def create_issue(self, owner: str, repo_name: str, 
                          title: str, body: str = "", labels: List[str] = None) -> Tuple[bool, str]:
        """Crear nuevo issue"""
        try:
            data = {
                'title': title,
                'body': body
            }
            
            if labels:
                data['labels'] = labels
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/repos/{owner}/{repo_name}/issues",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status == 201:
                        issue_data = await response.json()
                        return True, f"✅ Issue creado: {issue_data['html_url']}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error creando issue: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def list_orgs(self) -> List[Dict[str, Any]]:
        """Listar organizaciones del usuario"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/user/orgs",
                    headers=self.headers
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return []
        except Exception as e:
            logger.error(f"Error listando orgs: {e}")
            return []
    
    async def create_gist(self, description: str, files: Dict[str, Dict[str, str]], 
                         public: bool = False) -> Tuple[bool, str]:
        """Crear nuevo gist"""
        try:
            data = {
                'description': description,
                'public': public,
                'files': files
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/gists",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status == 201:
                        gist_data = await response.json()
                        return True, f"✅ Gist creado: {gist_data['html_url']}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error creando gist: {e}")
            return False, f"❌ Error: {str(e)}"

# ==============================================
# INICIALIZAR GITHUB MANAGER
# ==============================================
github_manager = GitHubManager(GITHUB_TOKEN)

# ==============================================
# CLASE FILE MANAGER
# ==============================================
class FileManager:
    """Clase para gestionar archivos y directorios"""
    
    SAFE_DIRECTORIES = [
        TEMP_DIR,
        BASE_DIR,
        os.path.join(BASE_DIR, "downloads"),
        os.path.join(BASE_DIR, "logs")
    ]
    
    RESTRICTED_PATHS = [
        "/",
        "/home",
        "/etc",
        "/var",
        "/usr",
        "/bin",
        "/sbin",
        "/root",
        os.path.expanduser("~")
    ]
    
    @staticmethod
    def is_safe_path(path: str) -> bool:
        """Verifica si una ruta está dentro de los directorios permitidos"""
        try:
            abs_path = os.path.abspath(path)
            
            for restricted in FileManager.RESTRICTED_PATHS:
                if abs_path.startswith(restricted) and restricted != BASE_DIR:
                    return False
            
            for safe_dir in FileManager.SAFE_DIRECTORIES:
                if abs_path.startswith(os.path.abspath(safe_dir)):
                    return True
            
            return False
        except Exception:
            return False
    
    @staticmethod
    def get_file_info(path: str) -> Dict[str, Any]:
        """Obtiene información detallada de un archivo o directorio"""
        try:
            abs_path = os.path.abspath(path)
            stat_info = os.stat(abs_path)
            
            info = {
                "path": abs_path,
                "name": os.path.basename(abs_path),
                "size": stat_info.st_size,
                "size_human": humanize.naturalsize(stat_info.st_size),
                "modified": datetime.fromtimestamp(stat_info.st_mtime),
                "modified_str": datetime.fromtimestamp(stat_info.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "created": datetime.fromtimestamp(stat_info.st_ctime),
                "created_str": datetime.fromtimestamp(stat_info.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
                "is_dir": os.path.isdir(abs_path),
                "is_file": os.path.isfile(abs_path),
                "permissions": stat.filemode(stat_info.st_mode),
                "owner": stat_info.st_uid,
                "group": stat_info.st_gid,
                "inode": stat_info.st_ino
            }
            
            if info["is_file"]:
                mime_type, _ = mimetypes.guess_type(abs_path)
                info["mime_type"] = mime_type or "application/octet-stream"
                info["extension"] = os.path.splitext(abs_path)[1].lower()
                
                if info["size"] < 10 * 1024 * 1024:
                    try:
                        with open(abs_path, 'rb') as f:
                            info["md5"] = hashlib.md5(f.read()).hexdigest()
                    except:
                        info["md5"] = None
                else:
                    info["md5"] = None
            
            elif info["is_dir"]:
                try:
                    items = os.listdir(abs_path)
                    files = [f for f in items if os.path.isfile(os.path.join(abs_path, f))]
                    dirs = [d for d in items if os.path.isdir(os.path.join(abs_path, d))]
                    info["file_count"] = len(files)
                    info["dir_count"] = len(dirs)
                    info["total_count"] = len(items)
                except:
                    info["file_count"] = 0
                    info["dir_count"] = 0
                    info["total_count"] = 0
            
            return info
        except Exception as e:
            logger.error(f"Error obteniendo info de archivo: {e}")
            return {}
    
    @staticmethod
    def list_directory(path: str, page: int = 1, items_per_page: int = 20) -> Dict[str, Any]:
        """Lista los contenidos de un directorio con paginación"""
        try:
            if not FileManager.is_safe_path(path):
                return {"error": "Ruta no permitida", "items": [], "total": 0}
            
            if not os.path.exists(path):
                return {"error": "La ruta no existe", "items": [], "total": 0}
            
            if not os.path.isdir(path):
                return {"error": "La ruta no es un directorio", "items": [], "total": 0}
            
            items = []
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                items.append({
                    "name": item,
                    "path": item_path,
                    "is_dir": os.path.isdir(item_path),
                    "is_file": os.path.isfile(item_path),
                    "size": os.path.getsize(item_path) if os.path.isfile(item_path) else 0,
                    "size_human": humanize.naturalsize(os.path.getsize(item_path)) if os.path.isfile(item_path) else "0B",
                    "modified": datetime.fromtimestamp(os.path.getmtime(item_path)),
                    "modified_str": datetime.fromtimestamp(os.path.getmtime(item_path)).strftime("%Y-%m-%d %H:%M:%S")
                })
            
            items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            total_items = len(items)
            
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            paginated_items = items[start_idx:end_idx]
            
            return {
                "items": paginated_items,
                "total": total_items,
                "page": page,
                "items_per_page": items_per_page,
                "total_pages": (total_items + items_per_page - 1) // items_per_page,
                "current_path": path,
                "parent_path": os.path.dirname(path) if path != BASE_DIR else None
            }
        except Exception as e:
            logger.error(f"Error listando directorio: {e}")
            return {"error": str(e), "items": [], "total": 0}
    
    @staticmethod
    def search_files(root_path: str, pattern: str, search_type: str = "all") -> List[Dict[str, Any]]:
        """Busca archivos o directorios que coincidan con un patrón"""
        results = []
        
        if not FileManager.is_safe_path(root_path):
            return results
        
        try:
            pattern_lower = pattern.lower()
            
            for root, dirs, files in os.walk(root_path):
                if search_type in ["all", "dirs"]:
                    for dir_name in dirs:
                        if pattern_lower in dir_name.lower():
                            dir_path = os.path.join(root, dir_name)
                            results.append({
                                "type": "directory",
                                "name": dir_name,
                                "path": dir_path,
                                "relative_path": os.path.relpath(dir_path, root_path)
                            })
                
                if search_type in ["all", "files"]:
                    for file_name in files:
                        if pattern_lower in file_name.lower():
                            file_path = os.path.join(root, file_name)
                            results.append({
                                "type": "file",
                                "name": file_name,
                                "path": file_path,
                                "relative_path": os.path.relpath(file_path, root_path),
                                "size": os.path.getsize(file_path),
                                "size_human": humanize.naturalsize(os.path.getsize(file_path))
                            })
        except Exception as e:
            logger.error(f"Error buscando archivos: {e}")
        
        return results
    
    @staticmethod
    def create_directory(path: str) -> Tuple[bool, str]:
        """Crea un directorio"""
        try:
            if not FileManager.is_safe_path(path):
                return False, "Ruta no permitida"
            
            if os.path.exists(path):
                return False, "El directorio ya existe"
            
            os.makedirs(path, exist_ok=True)
            return True, f"Directorio creado: {path}"
        except Exception as e:
            logger.error(f"Error creando directorio: {e}")
            return False, f"Error: {str(e)}"
    
    @staticmethod
    def delete_path(path: str) -> Tuple[bool, str]:
        """Elimina un archivo o directorio"""
        try:
            if not FileManager.is_safe_path(path):
                return False, "Ruta no permitida"
            
            if not os.path.exists(path):
                return False, "La ruta no existe"
            
            if os.path.isdir(path):
                shutil.rmtree(path)
                return True, f"Directorio eliminado: {os.path.basename(path)}"
            else:
                os.remove(path)
                return True, f"Archivo eliminado: {os.path.basename(path)}"
        except Exception as e:
            logger.error(f"Error eliminando ruta: {e}")
            return False, f"Error: {str(e)}"
    
    @staticmethod
    def rename_path(old_path: str, new_name: str) -> Tuple[bool, str]:
        """Renombra un archivo o directorio"""
        try:
            if not FileManager.is_safe_path(old_path):
                return False, "Ruta no permitida"
            
            if not os.path.exists(old_path):
                return False, "La ruta no existe"
            
            parent_dir = os.path.dirname(old_path)
            new_path = os.path.join(parent_dir, new_name)
            
            if os.path.exists(new_path):
                return False, "Ya existe un elemento con ese nombre"
            
            os.rename(old_path, new_path)
            return True, f"Renombrado a: {new_name}"
        except Exception as e:
            logger.error(f"Error renombrando ruta: {e}")
            return False, f"Error: {str(e)}"
    
    @staticmethod
    def get_disk_usage() -> Dict[str, Any]:
        """Obtiene información del uso del disco"""
        try:
            base_usage = shutil.disk_usage(BASE_DIR)
            
            temp_size = 0
            if os.path.exists(TEMP_DIR):
                for dirpath, dirnames, filenames in os.walk(TEMP_DIR):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        temp_size += os.path.getsize(fp) if os.path.isfile(fp) else 0
            
            temp_count = 0
            if os.path.exists(TEMP_DIR):
                for _, _, filenames in os.walk(TEMP_DIR):
                    temp_count += len(filenames)
            
            return {
                "total": base_usage.total,
                "used": base_usage.used,
                "free": base_usage.free,
                "total_human": humanize.naturalsize(base_usage.total),
                "used_human": humanize.naturalsize(base_usage.used),
                "free_human": humanize.naturalsize(base_usage.free),
                "percent_used": (base_usage.used / base_usage.total * 100) if base_usage.total > 0 else 0,
                "temp_size": temp_size,
                "temp_size_human": humanize.naturalsize(temp_size),
                "temp_count": temp_count,
                "timestamp": datetime.now()
            }
        except Exception as e:
            logger.error(f"Error obteniendo uso de disco: {e}")
            return {}

# ==============================================
# FUNCIONES AUXILIARES
# ==============================================
async def download_github_repo(repo_url: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Descarga un repositorio de GitHub como ZIP"""
    try:
        if not repo_url or "github.com" not in repo_url:
            return None, "URL no válida. Debe ser un repositorio de GitHub."
        
        repo_url = repo_url.strip().rstrip('/')
        
        if "/archive/" in repo_url and repo_url.endswith(".zip"):
            download_url = repo_url
        else:
            pattern = r"github\.com/([^/]+)/([^/?#]+)"
            match = re.search(pattern, repo_url)
            
            if not match:
                return None, "No se pudo extraer información del repositorio."
            
            user, repo = match.groups()
            repo = re.sub(r'\.git$', '', repo)
            
            if "/tree/" in repo_url:
                branch_match = re.search(r'/tree/([^/]+)', repo_url)
                branch = branch_match.group(1) if branch_match else "main"
            else:
                branch = "main"
            
            download_url = f"https://github.com/{user}/{repo}/archive/refs/heads/{branch}.zip"
        
        timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(download_url) as response:
                if response.status != 200:
                    if "/main.zip" in download_url:
                        alt_url = download_url.replace("/main.zip", "/master.zip")
                        async with session.get(alt_url) as response2:
                            if response2.status != 200:
                                return None, f"No se pudo descargar el repositorio. HTTP {response.status}"
                            content = await response2.read()
                    else:
                        return None, f"Error HTTP {response.status}: No se pudo descargar."
                else:
                    content = await response.read()
        
        if len(content) > MAX_FILE_SIZE:
            return None, f"El archivo es demasiado grande ({len(content)/1024/1024:.1f}MB). Límite: 50MB."
        
        return content, None
        
    except asyncio.TimeoutError:
        return None, "Tiempo de espera agotado al descargar el repositorio."
    except aiohttp.ClientError as e:
        return None, f"Error de conexión: {str(e)}"
    except Exception as e:
        logger.error(f"Error en download_github_repo: {e}")
        return None, f"Error interno: {str(e)}"

def get_repo_info_from_url(repo_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Extrae información del repositorio de la URL"""
    try:
        pattern = r"github\.com/([^/]+)/([^/?#]+)"
        match = re.search(pattern, repo_url)
        
        if match:
            username = match.group(1)
            repo_name = match.group(2)
            repo_name = re.sub(r'\.git$', '', repo_name)
            if '/tree/' in repo_url:
                repo_name = repo_name.split('/')[0]
            return username, repo_name
        return None, None
    except Exception as e:
        logger.error(f"Error en get_repo_info_from_url: {e}")
        return None, None

async def search_github_repos(query: str, page: int = 1, per_page: int = 5) -> Tuple[Optional[Dict], Optional[str]]:
    """Busca repositorios en GitHub usando la API"""
    try:
        if not query or len(query.strip()) < 2:
            return None, "La búsqueda debe tener al menos 2 caracteres."
        
        query = query.strip()
        encoded_query = aiohttp.helpers.quote(query, safe='')
        url = f"https://api.github.com/search/repositories?q={encoded_query}&sort=stars&order=desc&page={page}&per_page={per_page}"
        
        headers = {
            'User-Agent': 'GitHubDownloaderBot/2.0',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 403:
                    return None, "Límite de la API de GitHub alcanzado. Intenta más tarde."
                elif response.status == 422:
                    return None, "Consulta de búsqueda no válida."
                elif response.status != 200:
                    return None, f"Error en la API: {response.status}"
                
                data = await response.json()
                
                if "items" not in data:
                    return None, "No se encontraron resultados."
                
                repos = []
                for item in data["items"]:
                    repo_info = {
                        "name": item.get("name", "Desconocido"),
                        "full_name": item.get("full_name", "Desconocido"),
                        "description": item.get("description") or "Sin descripción",
                        "url": item.get("html_url", ""),
                        "stars": item.get("stargazers_count", 0),
                        "forks": item.get("forks_count", 0),
                        "language": item.get("language") or "N/A",
                        "updated_at": item.get("updated_at", ""),
                        "owner": item.get("owner", {}).get("login", "Desconocido")
                    }
                    repos.append(repo_info)
                
                total_count = data.get("total_count", 0)
                return {
                    "repos": repos,
                    "total_count": total_count,
                    "page": page,
                    "query": query,
                    "has_next": len(repos) == per_page and (page * per_page) < total_count,
                    "has_prev": page > 1
                }, None
        
    except aiohttp.ClientError as e:
        logger.error(f"Error de conexión en search_github_repos: {e}")
        return None, "Error de conexión con GitHub."
    except Exception as e:
        logger.error(f"Error en search_github_repos: {e}")
        return None, f"Error interno: {str(e)}"

def format_repo_search_results(results: Dict) -> str:
    """Formatea los resultados de búsqueda para mostrar al usuario"""
    repos = results["repos"]
    total_count = results["total_count"]
    page = results["page"]
    query = results.get("query", "")
    
    text = f"🔍 **Resultados para: `{query}`**\n\n"
    text += f"📊 **Encontrados:** {total_count} repositorios\n"
    text += f"📄 **Página:** {page}\n\n"
    
    for i, repo in enumerate(repos, 1):
        idx = (page - 1) * 5 + i
        text += f"**{idx}. {repo['full_name']}**\n"
        text += f"   ⭐ {repo['stars']} | 🍴 {repo['forks']} | 💻 {repo['language']}\n"
        text += f"   📝 {repo['description'][:100]}{'...' if len(repo['description']) > 100 else ''}\n"
        text += f"   👤 {repo['owner']}\n\n"
    
    text += "💡 **Selecciona un repositorio con los botones**"
    return text

# ==============================================
# COMANDOS PRINCIPALES
# ==============================================
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user = message.from_user
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Buscar repos", callback_data="search"),
         InlineKeyboardButton("📚 Ayuda", callback_data="help")],
        [InlineKeyboardButton("📥 Descargar", callback_data="download_menu"),
         InlineKeyboardButton("🚀 GitHub Manager", callback_data="github")],
        [InlineKeyboardButton("🌐 GitHub API", url="https://docs.github.com/rest")]
    ])
    
    await message.reply_text(
        f"👋 ¡Hola {user.first_name}!\n\n"
        "🤖 **GitHub Manager Bot**\n\n"
        "📥 **Puedo descargar repositorios de GitHub**\n"
        "🚀 **Y gestionar TU cuenta de GitHub**\n\n"
        "🔍 **Características:**\n"
        "• Sistema de búsqueda de repositorios\n"
        "• Descarga de repos completos\n"
        "• 🆕 Gestión COMPLETA de tu cuenta GitHub\n"
        "• Crear/eliminar repositorios\n"
        "• Hacer forks y crear archivos\n"
        "• Gestionar issues y ramas\n"
        "• Interfaz intuitiva con botones\n\n"
        "**Comandos principales:**\n"
        "`/search <término>` - Buscar repositorios\n"
        "`/download <url>` - Descargar repositorio\n"
        "`/github` - Panel de gestión GitHub 🆕\n"
        "`/help` - Mostrar ayuda completa\n\n"
        "¡Prueba el nuevo panel GitHub Manager!",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    help_text = """
🤖 **GitHub Manager Bot - Ayuda**

📥 **¿Qué puedo hacer?**
• 🔍 **Buscar repositorios** en GitHub
• 📥 Descargar repositorios completos
• 🚀 **Gestionar TU cuenta de GitHub** 🆕
• 📁 Enviarlos como archivo ZIP
• 🌿 Soporte para ramas específicas
• 📊 Información detallada del repositorio

🆕 **GESTIÓN GITHUB (Solo Admin):**
`/github` - Panel de control completo
`/ghrepos` - Listar tus repositorios
`/ghcreate <nombre>` - Crear nuevo repo
`/ghfork <owner/repo>` - Hacer fork
`/ghdelete <owner/repo>` - Eliminar repo
`/ghfile <owner/repo> <ruta> <contenido>` - Crear archivo
`/ghissue <owner/repo> <título> <desc>` - Crear issue
`/ghgist <desc> <contenido>` - Crear gist
`/ghtoken <token>` - Configurar token

🛠️ **Comandos normales:**
`/start` - Iniciar el bot
`/search <término>` - Buscar repositorios
`/download <url>` - Descargar repositorio
`/help` - Mostrar esta ayuda
`/example` - Ver ejemplos de uso
`/info` - Información del bot

🔍 **Sistema de búsqueda:**
• Busca en todos los repos públicos de GitHub
• Ordena por popularidad (estrellas)
• Muestra descripción, lenguaje y estadísticas
• Navegación por páginas

⚠️ **Limitaciones:**
• Máximo 50MB por archivo (límite de Telegram)
• Solo repositorios públicos para búsqueda
• Límites de API de GitHub
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 GitHub Manager", callback_data="github"),
         InlineKeyboardButton("🔍 Probar búsqueda", callback_data="search_example")],
        [InlineKeyboardButton("📥 Ejemplo rápido", callback_data="quick_download"),
         InlineKeyboardButton("🌐 GitHub API", url="https://docs.github.com/rest")]
    ])
    
    await message.reply_text(help_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("search"))
async def search_command(client: Client, message: Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "🔍 **Sistema de Búsqueda de Repositorios**\n\n"
            "📝 **Uso:** `/search <término de búsqueda>`\n\n"
            "**Ejemplos:**\n"
            "• `/search python bot`\n"
            "• `/search machine learning`\n"
            "• `/search user:microsoft windows`\n\n"
            "💡 **Consejos:**\n"
            "• Usa palabras clave específicas\n"
            "• Busca por lenguaje: `language:python`\n"
            "• Busca por usuario: `user:nombre`\n"
            "• Máximo 5 resultados por página",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    query = args[1]
    
    if len(query) < 2:
        await message.reply_text("❌ La búsqueda debe tener al menos 2 caracteres.")
        return
    
    processing_msg = await message.reply_text(f"🔍 **Buscando:** `{query}`...")
    
    results, error = await search_github_repos(query)
    
    if error:
        await processing_msg.edit_text(f"❌ **Error:** {error}")
        return
    
    search_id = str(uuid.uuid4())[:8]
    search_cache[search_id] = {
        "results": results,
        "query": query,
        "user_id": message.from_user.id,
        "timestamp": datetime.now().timestamp()
    }
    
    keyboard_buttons = []
    for i, repo in enumerate(results["repos"], 1):
        callback_data = f"select_{search_id}_{i-1}"
        button_text = f"{i}. {repo['name'][:15]}{'...' if len(repo['name']) > 15 else ''}"
        keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    nav_buttons = []
    if results["has_prev"]:
        nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"prev_{search_id}_{results['page']}"))
    
    if results["has_next"]:
        nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"next_{search_id}_{results['page']}"))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    keyboard_buttons.append([
        InlineKeyboardButton("🔄 Nueva búsqueda", callback_data="search"),
        InlineKeyboardButton("📋 Ayuda", callback_data="help")
    ])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await processing_msg.edit_text(
        format_repo_search_results(results),
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("download"))
async def download_command(client: Client, message: Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "📥 **Descargar Repositorio**\n\n"
            "📝 **Uso:** `/download <URL del repositorio>`\n\n"
            "**Ejemplos:**\n"
            "• `/download https://github.com/usuario/repo`\n"
            "• `/download https://github.com/usuario/repo/tree/main`\n"
            "• `/download https://github.com/usuario/repo.git`\n\n"
            "💡 **También puedes usar:**\n"
            "`/search <término>` para buscar repositorios\n\n"
            "⚠️ **Límite:** 50MB por archivo",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    repo_url = args[1].strip()
    
    if not re.match(r'^https?://github\.com/[^/]+/[^/]+', repo_url):
        await message.reply_text(
            "❌ **URL no válida**\n\n"
            "Por favor, envía una URL de GitHub válida.\n"
            "**Formato:** `https://github.com/usuario/repositorio`\n\n"
            "💡 Usa `/search` para encontrar repositorios",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    processing_msg = await message.reply_text("⏳ **Descargando repositorio...**")
    
    zip_content, error = await download_github_repo(repo_url)
    
    if error:
        await processing_msg.edit_text(f"❌ **Error:** {error}")
        return
    
    username, repo_name = get_repo_info_from_url(repo_url)
    filename = f"{repo_name or 'repositorio'}.zip"
    file_size_mb = len(zip_content) / 1024 / 1024
    
    await processing_msg.edit_text(f"✅ **Descarga completada!**\n📦 Tamaño: {file_size_mb:.1f}MB\n📤 Enviando...")
    
    try:
        await message.reply_document(
            document=io.BytesIO(zip_content),
            file_name=filename,
            caption=(
                f"📦 **{repo_name or 'Repositorio'}**\n"
                f"🔗 {repo_url}\n"
                f"📊 Tamaño: {file_size_mb:.1f}MB\n"
                f"👤 Usuario: {username or 'Desconocido'}\n\n"
                f"✅ Descargado por @{client.me.username}"
            ),
            parse_mode=enums.ParseMode.MARKDOWN
        )
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error enviando documento: {e}")
        await processing_msg.edit_text(f"❌ **Error al enviar:** {str(e)[:100]}")

@app.on_message(filters.command("example"))
async def example_command(client: Client, message: Message):
    examples = """
📚 **Ejemplos de uso:**

🔍 **Búsquedas:**
`/search python bot telegram`
`/search machine learning tensorflow`
`/search language:javascript game`
`/search user:microsoft windows`

📥 **Descargas:**
`/download https://github.com/octocat/Spoon-Knife`
`/download https://github.com/python/cpython`
`/download https://github.com/torvalds/linux/tree/master`

🚀 **Gestión GitHub (Admin):**
`/ghrepos` - Ver tus repositorios
`/ghcreate mi-proyecto` - Crear nuevo repo
`/ghfork microsoft/vscode` - Hacer fork
`/ghfile usuario/repo README.md "# Titulo"` - Crear archivo

🔥 **Búsquedas populares:**
• `/search python`
• `/search javascript framework`
• `/search open source`
• `/search ai machine learning`
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Buscar 'python bot'", callback_data="search_python"),
         InlineKeyboardButton("🚀 GitHub Manager", callback_data="github")],
        [InlineKeyboardButton("❓ Ayuda", callback_data="help"),
         InlineKeyboardButton("🏠 Inicio", callback_data="start")]
    ])
    
    await message.reply_text(examples, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("info"))
async def info_command(client: Client, message: Message):
    info_text = f"""
🤖 **GitHub Manager Bot v2.0**

**Desarrollador:** Administrador Exclusivo
**Username:** @{client.me.username}
**ID:** {client.me.id}
**Versión:** 2.0
**Admin ID:** {ADMIN_ID}

**✨ Características:**
• 🔍 Sistema de búsqueda de repositorios
• 📥 Descarga de repos completos
• 🚀 Gestión COMPLETA de GitHub
• 📊 Estadísticas en tiempo real
• 🔄 Navegación por páginas
• 📋 Vista detallada de repos
• 🛠️ Panel de administración exclusivo

**🆕 Funciones GitHub:**
• Crear/eliminar repositorios
• Hacer forks de otros repos
• Crear archivos y issues
• Gestionar ramas y gists
• Ver organizaciones

**Comandos principales:**
`/search <término>` - Buscar repos
`/download <url>` - Descargar repo
`/github` - Panel GitHub Manager
`/help` - Ayuda completa
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 GitHub Manager", callback_data="github"),
         InlineKeyboardButton("🔍 Probar búsqueda", callback_data="search_example")],
        [InlineKeyboardButton("📚 Ver ayuda", callback_data="help")]
    ])
    
    await message.reply_text(info_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

# ==============================================
# COMANDOS DE ADMINISTRACIÓN (ROOT)
# ==============================================
@app.on_message(filters.command("root") & filters.private)
@admin_only
async def root_command(client: Client, message: Message):
    """Menú principal de administración - Solo para ti"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Ver directorio actual", callback_data="root_list_current")],
        [InlineKeyboardButton("🔍 Buscar archivos", callback_data="root_search_menu"),
         InlineKeyboardButton("📊 Uso de disco", callback_data="root_disk_usage")],
        [InlineKeyboardButton("🧹 Limpiar temp", callback_data="root_cleanup_temp"),
         InlineKeyboardButton("📝 Ver logs", callback_data="root_view_logs")],
        [InlineKeyboardButton("🏠 Inicio", callback_data="start")]
    ])
    
    await message.reply_text(
        "🔧 **Panel de Administración Root - EXCLUSIVO**\n\n"
        "**Opciones disponibles:**\n"
        "• 📁 **Explorar directorios** - Navegar por el sistema de archivos\n"
        "• 🔍 **Buscar archivos** - Buscar archivos por nombre\n"
        "• 📊 **Uso de disco** - Ver espacio disponible y utilizado\n"
        "• 🧹 **Limpiar temporal** - Eliminar archivos temporales\n"
        "• 📝 **Ver logs** - Consultar registros del bot\n\n"
        f"**Directorio base:** `{BASE_DIR}`\n"
        f"**Directorio temp:** `{TEMP_DIR}`\n"
        f"**Admin ID:** {ADMIN_ID}\n"
        f"**Estado:** 🔐 **ACCESO EXCLUSIVO**",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("ls") & filters.private)
@admin_only
async def ls_command(client: Client, message: Message):
    """Listar contenido de directorio - Solo para ti"""
    args = message.text.split(maxsplit=1)
    
    if len(args) > 1:
        path = args[1].strip()
    else:
        path = BASE_DIR
    
    await list_directory_command(client, message, path)

async def list_directory_command(client: Client, message: Message, path: str, page: int = 1):
    """Comando para listar directorio"""
    if not FileManager.is_safe_path(path):
        await message.reply_text(
            "❌ **Ruta no permitida**\n\n"
            "Solo puedes acceder a directorios dentro del área del bot.",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    if not os.path.exists(path):
        await message.reply_text(
            f"❌ **La ruta no existe**\n\n`{path}`",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    if not os.path.isdir(path):
        file_info = FileManager.get_file_info(path)
        
        if not file_info:
            await message.reply_text("❌ No se pudo obtener información del archivo")
            return
        
        text = f"📄 **Información del archivo**\n\n"
        text += f"**Nombre:** `{file_info['name']}`\n"
        text += f"**Ruta:** `{file_info['path']}`\n"
        text += f"**Tamaño:** {file_info['size_human']}\n"
        text += f"**Modificado:** {file_info['modified_str']}\n"
        text += f"**Creado:** {file_info['created_str']}\n"
        text += f"**Permisos:** {file_info['permissions']}\n"
        
        if 'mime_type' in file_info:
            text += f"**Tipo MIME:** {file_info['mime_type']}\n"
        
        if file_info['size'] < 5 * 1024 * 1024:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Enviar archivo", callback_data=f"root_send_{path}")],
                [InlineKeyboardButton("📝 Renombrar", callback_data=f"root_rename_{path}"),
                 InlineKeyboardButton("🗑️ Eliminar", callback_data=f"root_delete_{path}")],
                [InlineKeyboardButton("📁 Directorio padre", callback_data=f"root_list_{os.path.dirname(path)}"),
                 InlineKeyboardButton("🔙 Volver", callback_data="root")]
            ])
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Renombrar", callback_data=f"root_rename_{path}"),
                 InlineKeyboardButton("🗑️ Eliminar", callback_data=f"root_delete_{path}")],
                [InlineKeyboardButton("📁 Directorio padre", callback_data=f"root_list_{os.path.dirname(path)}"),
                 InlineKeyboardButton("🔙 Volver", callback_data="root")]
            ])
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
        return
    
    result = FileManager.list_directory(path, page)
    
    if "error" in result:
        await message.reply_text(f"❌ **Error:** {result['error']}")
        return
    
    text = f"📁 **Directorio:** `{result['current_path']}`\n\n"
    text += f"📊 **Total de items:** {result['total']}\n"
    text += f"📄 **Página {result['page']} de {result['total_pages']}**\n\n"
    
    if not result["items"]:
        text += "📭 **El directorio está vacío**\n"
    else:
        for i, item in enumerate(result["items"], 1):
            idx = (page - 1) * result["items_per_page"] + i
            icon = "📁" if item["is_dir"] else "📄"
            size = f" ({item['size_human']})" if item["is_file"] else ""
            text += f"{icon} **{idx}.** `{item['name']}`{size}\n"
    
    keyboard_buttons = []
    
    nav_buttons = []
    if result["page"] > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"root_list_{path}_{result['page']-1}"))
    
    if result["page"] < result["total_pages"]:
        nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"root_list_{path}_{result['page']+1}"))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    action_buttons = []
    if result["parent_path"]:
        action_buttons.append(InlineKeyboardButton("📁 Subir", callback_data=f"root_list_{result['parent_path']}"))
    
    action_buttons.append(InlineKeyboardButton("➕ Nueva carpeta", callback_data=f"root_mkdir_{path}"))
    keyboard_buttons.append(action_buttons)
    
    for item in result["items"][:5]:
        btn_text = f"📁 {item['name']}" if item["is_dir"] else f"📄 {item['name']}"
        if len(btn_text) > 20:
            btn_text = btn_text[:17] + "..."
        
        callback_data = f"root_list_{item['path']}" if item["is_dir"] else f"root_info_{item['path']}"
        keyboard_buttons.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])
    
    keyboard_buttons.append([
        InlineKeyboardButton("🔍 Buscar aquí", callback_data=f"root_search_{path}"),
        InlineKeyboardButton("🏠 Inicio", callback_data="root")
    ])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await message.reply_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("disk") & filters.private)
@admin_only
async def disk_command(client: Client, message: Message):
    """Mostrar uso del disco - Solo para ti"""
    disk_info = FileManager.get_disk_usage()
    
    if not disk_info:
        await message.reply_text("❌ No se pudo obtener información del disco")
        return
    
    percent = disk_info["percent_used"]
    bar_length = 20
    filled_length = int(bar_length * percent / 100)
    bar = "█" * filled_length + "░" * (bar_length - filled_length)
    
    text = "💾 **Información del Disco**\n\n"
    text += f"**Espacio total:** {disk_info['total_human']}\n"
    text += f"**Espacio usado:** {disk_info['used_human']}\n"
    text += f"**Espacio libre:** {disk_info['free_human']}\n"
    text += f"**Porcentaje usado:** {percent:.1f}%\n\n"
    text += f"`[{bar}] {percent:.1f}%`\n\n"
    text += f"**Directorio temporal:**\n"
    text += f"• Tamaño: {disk_info['temp_size_human']}\n"
    text += f"• Archivos: {disk_info['temp_count']}\n\n"
    text += f"**Actualizado:** {disk_info['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧹 Limpiar temporal", callback_data="root_cleanup_temp")],
        [InlineKeyboardButton("📊 Detalles completos", callback_data="root_disk_details"),
         InlineKeyboardButton("🔙 Volver", callback_data="root")]
    ])
    
    await message.reply_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("clean") & filters.private)
@admin_only
async def clean_command(client: Client, message: Message):
    """Limpiar archivos temporales - Solo para ti"""
    try:
        if os.path.exists(TEMP_DIR):
            file_count = 0
            total_size = 0
            
            for dirpath, dirnames, filenames in os.walk(TEMP_DIR):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp) if os.path.isfile(fp) else 0
                    file_count += 1
            
            shutil.rmtree(TEMP_DIR)
            os.makedirs(TEMP_DIR, exist_ok=True)
            
            await message.reply_text(
                f"✅ **Limpieza completada**\n\n"
                f"**Archivos eliminados:** {file_count}\n"
                f"**Espacio liberado:** {humanize.naturalsize(total_size)}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        else:
            await message.reply_text("✅ El directorio temporal ya está vacío")
    except Exception as e:
        logger.error(f"Error limpiando temporal: {e}")
        await message.reply_text(f"❌ Error: {str(e)}")

@app.on_message(filters.command("find") & filters.private)
@admin_only
async def find_command(client: Client, message: Message):
    """Buscar archivos - Solo para ti"""
    args = message.text.split(maxsplit=2)
    
    if len(args) < 2:
        await message.reply_text(
            "🔍 **Buscar Archivos**\n\n"
            "**Uso:** `/find <patrón> [ruta]`\n\n"
            "**Ejemplos:**\n"
            "• `/find .py` - Buscar archivos .py\n"
            "• `/find config /app` - Buscar 'config' en /app\n"
            "• `/find log --type=dir` - Buscar directorios\n\n"
            "**Opciones:**\n"
            "• `--type=file` - Solo archivos\n"
            "• `--type=dir` - Solo directorios\n"
            "• `--type=all` - Ambos (predeterminado)",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    pattern = args[1]
    search_path = BASE_DIR
    search_type = "all"
    
    if len(args) > 2:
        remaining = args[2]
        if remaining.startswith("--type="):
            search_type = remaining.split("=")[1]
        else:
            search_path = remaining
    
    if not FileManager.is_safe_path(search_path):
        await message.reply_text("❌ Ruta no permitida")
        return
    
    processing_msg = await message.reply_text(f"🔍 Buscando `{pattern}` en `{search_path}`...")
    
    results = FileManager.search_files(search_path, pattern, search_type)
    
    if not results:
        await processing_msg.edit_text(f"❌ No se encontraron resultados para `{pattern}`")
        return
    
    text = f"🔍 **Resultados de búsqueda**\n\n"
    text += f"**Patrón:** `{pattern}`\n"
    text += f"**Ruta:** `{search_path}`\n"
    text += f"**Tipo:** `{search_type}`\n"
    text += f"**Encontrados:** {len(results)} items\n\n"
    
    for i, result in enumerate(results[:10], 1):
        icon = "📁" if result["type"] == "directory" else "📄"
        size = f" ({result['size_human']})" if result["type"] == "file" else ""
        text += f"{icon} **{i}.** `{result['relative_path']}`{size}\n"
    
    if len(results) > 10:
        text += f"\n... y {len(results) - 10} más\n"
    
    keyboard_buttons = []
    for i, result in enumerate(results[:5], 1):
        btn_text = f"{i}. {os.path.basename(result['path'])}"
        if len(btn_text) > 20:
            btn_text = btn_text[:17] + "..."
        
        callback_data = f"root_list_{result['path']}" if result["type"] == "directory" else f"root_info_{result['path']}"
        keyboard_buttons.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])
    
    keyboard_buttons.append([
        InlineKeyboardButton("🔍 Nueva búsqueda", callback_data="root_search_menu"),
        InlineKeyboardButton("🔙 Volver", callback_data="root")
    ])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await processing_msg.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("tree") & filters.private)
@admin_only
async def tree_command(client: Client, message: Message):
    """Mostrar estructura de directorios en formato árbol - Solo para ti"""
    args = message.text.split(maxsplit=1)
    path = args[1] if len(args) > 1 else BASE_DIR
    depth = 3
    
    if not FileManager.is_safe_path(path):
        await message.reply_text("❌ Ruta no permitida")
        return
    
    if not os.path.isdir(path):
        await message.reply_text("❌ La ruta no es un directorio")
        return
    
    async def build_tree(dir_path, current_depth=0, max_depth=3, prefix=""):
        if current_depth >= max_depth:
            return ""
        
        try:
            items = os.listdir(dir_path)
            items.sort(key=lambda x: (not os.path.isdir(os.path.join(dir_path, x)), x.lower()))
            
            tree_str = ""
            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                item_path = os.path.join(dir_path, item)
                is_dir = os.path.isdir(item_path)
                
                connector = "└── " if is_last else "├── "
                icon = "📁" if is_dir else "📄"
                
                tree_str += f"{prefix}{connector}{icon} {item}\n"
                
                if is_dir and current_depth < max_depth - 1:
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    tree_str += await build_tree(item_path, current_depth + 1, max_depth, new_prefix)
            
            return tree_str
        except PermissionError:
            return f"{prefix}└── 🔒 [Acceso denegado]\n"
        except Exception:
            return f"{prefix}└── ❌ [Error]\n"
    
    processing_msg = await message.reply_text("🌳 Generando árbol de directorios...")
    
    tree_output = f"🌳 **Estructura de directorios**\n\n"
    tree_output += f"**Ruta:** `{path}`\n"
    tree_output += f"**Profundidad:** {depth} niveles\n\n"
    tree_output += "```\n"
    tree_output += os.path.basename(path.rstrip('/')) + "/\n"
    tree_output += await build_tree(path, 0, depth)
    tree_output += "```"
    
    if len(tree_output) > 4000:
        tree_output = tree_output[:4000] + "\n\n... (truncado por tamaño)"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Explorar", callback_data=f"root_list_{path}")],
        [InlineKeyboardButton("🔍 Buscar aquí", callback_data=f"root_search_{path}"),
         InlineKeyboardButton("🔙 Volver", callback_data="root")]
    ])
    
    await processing_msg.edit_text(tree_output, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("stats") & filters.private)
@admin_only
async def stats_command(client: Client, message: Message):
    """Estadísticas del bot y sistema - Solo para ti"""
    disk_info = FileManager.get_disk_usage()
    
    temp_stats = {"files": 0, "size": 0}
    if os.path.exists(TEMP_DIR):
        for dirpath, dirnames, filenames in os.walk(TEMP_DIR):
            temp_stats["files"] += len(filenames)
            for f in filenames:
                fp = os.path.join(dirpath, f)
                temp_stats["size"] += os.path.getsize(fp) if os.path.isfile(fp) else 0
    
    bot_info = await client.get_me()
    cache_size = len(search_cache)
    
    try:
        import psutil
        process = psutil.Process()
        mem_info = process.memory_info()
        mem_rss = humanize.naturalsize(mem_info.rss)
        mem_vms = humanize.naturalsize(mem_info.vms)
    except:
        mem_rss = "No disponible"
        mem_vms = "No disponible"
    
    text = "📊 **Estadísticas del Sistema - EXCLUSIVO**\n\n"
    
    text += "🤖 **Información del Bot:**\n"
    text += f"• **Nombre:** @{bot_info.username}\n"
    text += f"• **ID:** {bot_info.id}\n"
    text += f"• **Admin ID:** {ADMIN_ID}\n"
    text += f"• **Caché de búsqueda:** {cache_size} entradas\n\n"
    
    text += "💾 **Uso de Disco:**\n"
    if disk_info:
        text += f"• **Total:** {disk_info['total_human']}\n"
        text += f"• **Usado:** {disk_info['used_human']} ({disk_info['percent_used']:.1f}%)\n"
        text += f"• **Libre:** {disk_info['free_human']}\n"
        text += f"• **Temp:** {humanize.naturalsize(temp_stats['size'])} ({temp_stats['files']} archivos)\n\n"
    
    text += "🧠 **Uso de Memoria:**\n"
    text += f"• **RSS:** {mem_rss}\n"
    text += f"• **VMS:** {mem_vms}\n\n"
    
    text += "📁 **Directorios:**\n"
    text += f"• **Base:** `{BASE_DIR}`\n"
    text += f"• **Temp:** `{TEMP_DIR}`\n"
    text += f"• **Seguros:** {len(FileManager.SAFE_DIRECTORIES)} directorios\n\n"
    
    text += f"🕐 **Actualizado:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 Uso de disco", callback_data="root_disk_usage"),
         InlineKeyboardButton("🧹 Limpiar", callback_data="root_cleanup_temp")],
        [InlineKeyboardButton("📁 Explorar", callback_data="root_list_current"),
         InlineKeyboardButton("🔙 Panel", callback_data="root")]
    ])
    
    await message.reply_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

# ==============================================
# COMANDOS DE GESTIÓN GITHUB
# ==============================================
@app.on_message(filters.command("github") & filters.private)
@admin_only
async def github_command(client: Client, message: Message):
    """Menú principal de gestión de GitHub"""
    
    if not GITHUB_TOKEN or GITHUB_TOKEN == "tu_token_de_github_aquí":
        await message.reply_text(
            "❌ **Token de GitHub no configurado**\n\n"
            "Configura tu token en la variable `GITHUB_TOKEN`\n\n"
            "**Obtén tu token en:**\n"
            "https://github.com/settings/tokens\n\n"
            "**Permisos necesarios:**\n"
            "• repo (completo)\n"
            "• delete_repo\n"
            "• gist\n"
            "• user",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    success, msg = await github_manager.test_connection()
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Mis repositorios", callback_data="github_list_repos"),
         InlineKeyboardButton("➕ Nuevo repo", callback_data="github_create_repo")],
        [InlineKeyboardButton("🔍 Buscar repos", callback_data="search"),
         InlineKeyboardButton("🍴 Fork repo", callback_data="github_fork_repo")],
        [InlineKeyboardButton("🗑️ Eliminar repo", callback_data="github_delete_repo"),
         InlineKeyboardButton("📝 Crear archivo", callback_data="github_create_file")],
        [InlineKeyboardButton("🌿 Gestionar ramas", callback_data="github_branches"),
         InlineKeyboardButton("⚠️ Crear issue", callback_data="github_create_issue")],
        [InlineKeyboardButton("💾 Crear gist", callback_data="github_create_gist"),
         InlineKeyboardButton("🏢 Mis organizaciones", callback_data="github_list_orgs")],
        [InlineKeyboardButton("🔄 Test conexión", callback_data="github_test"),
         InlineKeyboardButton("🔙 Inicio", callback_data="start")]
    ])
    
    await message.reply_text(
        f"🚀 **GitHub Manager - Panel de Control**\n\n"
        f"{msg}\n\n"
        "**Operaciones disponibles:**\n"
        "• 📂 **Listar repositorios** - Ver todos tus repos\n"
        "• ➕ **Crear repositorio** - Nuevo repo público/privado\n"
        "• 🍴 **Fork repositorio** - Clonar repos de otros\n"
        "• 🗑️ **Eliminar repositorio** - Borrar repos existentes\n"
        "• 📝 **Crear archivos** - Añadir archivos a repos\n"
        "• 🌿 **Gestionar ramas** - Crear/listar ramas\n"
        "• ⚠️ **Crear issues** - Reportar problemas\n"
        "• 💾 **Crear gists** - Compartir código rápido\n"
        "• 🏢 **Organizaciones** - Ver tus organizaciones\n\n"
        "**Comandos rápidos:**\n"
        "`/ghrepos` - Listar repos\n"
        "`/ghcreate <nombre>` - Crear repo\n"
        "`/ghfork <owner/repo>` - Hacer fork\n"
        "`/ghdelete <owner/repo>` - Eliminar repo",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("ghrepos") & filters.private)
@admin_only
async def list_github_repos_command(client: Client, message: Message):
    """Listar repositorios del usuario"""
    args = message.text.split()
    page = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
    
    processing_msg = await message.reply_text(f"📂 Obteniendo repositorios (página {page})...")
    
    result = await github_manager.list_repos(page=page)
    
    if 'error' in result:
        await processing_msg.edit_text(f"❌ Error: {result['error']}")
        return
    
    repos = result['repos']
    
    if not repos:
        await processing_msg.edit_text("📭 No tienes repositorios")
        return
    
    text = f"📂 **Tus Repositorios** (Página {page})\n\n"
    
    for i, repo in enumerate(repos, 1):
        idx = (page - 1) * 10 + i
        private = "🔒" if repo['private'] else "🌐"
        text += f"**{idx}. {private} {repo['name']}**\n"
        text += f"   ⭐ {repo['stargazers_count']} | 🍴 {repo['forks_count']}\n"
        text += f"   📝 {repo['description'][:80] if repo['description'] else 'Sin descripción'}\n"
        text += f"   🔗 {repo['html_url']}\n\n"
    
    keyboard_buttons = []
    
    for i, repo in enumerate(repos[:5], 1):
        idx = (page - 1) * 10 + i
        btn_text = f"{idx}. {repo['name'][:15]}"
        if len(btn_text) > 20:
            btn_text = btn_text[:17] + "..."
        
        keyboard_buttons.append([
            InlineKeyboardButton(
                btn_text,
                callback_data=f"gh_repo_info_{repo['owner']['login']}_{repo['name']}"
            )
        ])
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"gh_repos_{page-1}"))
    
    if result.get('has_next'):
        nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"gh_repos_{page+1}"))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    keyboard_buttons.append([
        InlineKeyboardButton("➕ Crear repo", callback_data="github_create_repo"),
        InlineKeyboardButton("🔙 GitHub", callback_data="github")
    ])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await processing_msg.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("ghcreate") & filters.private)
@admin_only
async def create_github_repo_command(client: Client, message: Message):
    """Crear nuevo repositorio"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "➕ **Crear Repositorio GitHub**\n\n"
            "**Uso:** `/ghcreate <nombre> [descripción]`\n\n"
            "**Ejemplos:**\n"
            "• `/ghcreate mi-proyecto`\n"
            "• `/ghcreate api-rest \"Mi API REST en Python\"`\n\n"
            "**Opciones adicionales (por interfaz):**\n"
            "• Público/Privado\n"
            "• Inicializar con README\n"
            "• Añadir .gitignore\n"
            "• Añadir licencia",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    params = args[1].strip()
    parts = params.split('"')
    
    if len(parts) >= 3:
        name = parts[0].strip()
        description = parts[1].strip()
    else:
        name = params
        description = ""
    
    processing_msg = await message.reply_text(f"🛠️ Creando repositorio `{name}`...")
    
    success, result = await github_manager.create_repo(name, description)
    
    await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("ghfork") & filters.private)
@admin_only
async def fork_github_repo_command(client: Client, message: Message):
    """Hacer fork de un repositorio"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "🍴 **Fork Repositorio**\n\n"
            "**Uso:** `/ghfork <owner/repo>`\n\n"
            "**Ejemplos:**\n"
            "• `/ghfork octocat/Spoon-Knife`\n"
            "• `/ghfork microsoft/vscode`\n\n"
            "**Nota:** El fork se creará en tu cuenta",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    repo_path = args[1].strip()
    
    if '/' not in repo_path:
        await message.reply_text("❌ Formato incorrecto. Usa: `owner/repo`")
        return
    
    owner, repo_name = repo_path.split('/', 1)
    
    processing_msg = await message.reply_text(f"🍴 Haciendo fork de `{owner}/{repo_name}`...")
    
    success, result = await github_manager.fork_repo(owner, repo_name)
    
    await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("ghdelete") & filters.private)
@admin_only
async def delete_github_repo_command(client: Client, message: Message):
    """Eliminar repositorio"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "🗑️ **Eliminar Repositorio**\n\n"
            "⚠️ **ADVERTENCIA:** Esta acción es irreversible\n\n"
            "**Uso:** `/ghdelete <owner/repo>`\n\n"
            "**Ejemplos:**\n"
            "• `/ghdelete tuusuario/mi-repo`\n"
            "• `/ghdelete tuorg/proyecto`\n\n"
            "**Confirmación requerida**",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    repo_path = args[1].strip()
    
    if '/' not in repo_path:
        await message.reply_text("❌ Formato incorrecto. Usa: `owner/repo`")
        return
    
    owner, repo_name = repo_path.split('/', 1)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Sí, eliminar", callback_data=f"gh_confirm_delete_{owner}_{repo_name}"),
         InlineKeyboardButton("❌ Cancelar", callback_data="github")]
    ])
    
    await message.reply_text(
        f"⚠️ **Confirmar eliminación**\n\n"
        f"¿Eliminar el repositorio **{owner}/{repo_name}**?\n\n"
        f"**Esta acción:**\n"
        f"• ❌ Es IRREVERSIBLE\n"
        f"• 📝 Elimina TODO el código\n"
        f"• 🔥 Borra issues, stars, forks\n"
        f"• 🕐 No se puede recuperar\n\n"
        f"**¿Continuar?**",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("ghfile") & filters.private)
@admin_only
async def create_file_command(client: Client, message: Message):
    """Crear archivo en repositorio"""
    args = message.text.split(maxsplit=3)
    
    if len(args) < 4:
        await message.reply_text(
            "📝 **Crear Archivo en Repositorio**\n\n"
            "**Uso:** `/ghfile <owner/repo> <ruta> <contenido>`\n\n"
            "**Ejemplos:**\n"
            "• `/ghfile tuusuario/repo README.md \"# Mi Proyecto\"`\n"
            "• `/ghfile org/proj src/main.py \"print('Hola')\"`\n\n"
            "**Nota:** Usa comillas para contenido con espacios",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    repo_path = args[1]
    file_path = args[2]
    content = args[3]
    
    if '/' not in repo_path:
        await message.reply_text("❌ Formato incorrecto. Usa: `owner/repo`")
        return
    
    owner, repo_name = repo_path.split('/', 1)
    
    processing_msg = await message.reply_text(f"📝 Creando archivo `{file_path}`...")
    
    success, result = await github_manager.create_file(owner, repo_name, file_path, content)
    
    await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("ghissue") & filters.private)
@admin_only
async def create_issue_command(client: Client, message: Message):
    """Crear issue en repositorio"""
    args = message.text.split(maxsplit=3)
    
    if len(args) < 4:
        await message.reply_text(
            "⚠️ **Crear Issue**\n\n"
            "**Uso:** `/ghissue <owner/repo> <título> <descripción>`\n\n"
            "**Ejemplos:**\n"
            "• `/ghissue tuusuario/repo \"Bug fix\" \"Error en línea 42\"`\n"
            "• `/ghissue org/proj \"Nueva feature\" \"Añadir login social\"`\n\n"
            "**Nota:** Usa comillas para texto con espacios",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    repo_path = args[1]
    title = args[2]
    body = args[3] if len(args) > 3 else ""
    
    if '/' not in repo_path:
        await message.reply_text("❌ Formato incorrecto. Usa: `owner/repo`")
        return
    
    owner, repo_name = repo_path.split('/', 1)
    
    processing_msg = await message.reply_text(f"⚠️ Creando issue en `{owner}/{repo_name}`...")
    
    success, result = await github_manager.create_issue(owner, repo_name, title, body)
    
    await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("ghgist") & filters.private)
@admin_only
async def create_gist_command(client: Client, message: Message):
    """Crear gist"""
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        await message.reply_text(
            "💾 **Crear Gist**\n\n"
            "**Uso:** `/ghgist <descripción> <contenido>`\n\n"
            "**Ejemplos:**\n"
            "• `/ghgist \"Mi código\" \"print('Hello')\"`\n"
            "• `/ghgist \"Config\" \"API_KEY=123456\"`\n\n"
            "**Archivo por defecto:** `file1.txt`\n"
            "Usa la interfaz para múltiples archivos",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    description = args[1]
    content = args[2]
    
    files = {
        "file1.txt": {
            "content": content
        }
    }
    
    processing_msg = await message.reply_text(f"💾 Creando gist...")
    
    success, result = await github_manager.create_gist(description, files, public=False)
    
    await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("ghtoken") & filters.private)
@admin_only
async def set_github_token_command(client: Client, message: Message):
    """Establecer o actualizar token de GitHub"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "🔑 **Configurar Token de GitHub**\n\n"
            "**Uso:** `/ghtoken <tu_token>`\n\n"
            "**Obtén tu token en:**\n"
            "https://github.com/settings/tokens\n\n"
            "**Permisos necesarios:**\n"
            "• `repo` (completo)\n"
            "• `delete_repo`\n"
            "• `gist`\n"
            "• `user`\n\n"
            "**Nota:** El token se guarda en memoria durante esta sesión",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    new_token = args[1].strip()
    
    global github_manager
    github_manager = GitHubManager(new_token)
    
    global GITHUB_TOKEN
    GITHUB_TOKEN = new_token
    
    success, msg = await github_manager.test_connection()
    
    if success:
        await message.reply_text(
            f"✅ **Token actualizado correctamente**\n\n{msg}\n\n"
            f"**Nota:** Este cambio es temporal. Para hacerlo permanente, "
            f"actualiza la variable `GITHUB_TOKEN` en tu archivo `.env` o configuración.",
            parse_mode=enums.ParseMode.MARKDOWN
        )
    else:
        await message.reply_text(f"❌ **Token inválido**\n\n{msg}", parse_mode=enums.ParseMode.MARKDOWN)

# ==============================================
# HANDLERS DE CALLBACKS
# ==============================================
@app.on_callback_query()
async def handle_all_callbacks(client: Client, callback_query: CallbackQuery):
    """Manejador de todos los callbacks"""
    data = callback_query.data
    user_id = callback_query.from_user.id
    message = callback_query.message
    
    try:
        # Limpiar caché expirada
        current_time = datetime.now().timestamp()
        expired_keys = [
            key for key, value in search_cache.items()
            if current_time - value.get("timestamp", 0) > SEARCH_CACHE_TIMEOUT
        ]
        for key in expired_keys:
            del search_cache[key]
        
        # Callbacks para búsqueda de repositorios
        if data == "help":
            await help_command(client, message)
            await callback_query.answer()
        
        elif data == "start":
            await start_command(client, message)
            await callback_query.answer()
        
        elif data == "search":
            await callback_query.message.reply_text(
                "🔍 **Nueva búsqueda**\n\n"
                "Envía tu término de búsqueda:\n\n"
                "**Ejemplos:**\n"
                "`python telegram bot`\n"
                "`machine learning`\n"
                "`web development`\n\n"
                "O usa: `/search <término>`",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            await callback_query.answer()
        
        elif data == "search_example":
            processing_msg = await callback_query.message.reply_text("🔍 **Ejemplo:** Buscando `python bot`...")
            results, error = await search_github_repos("python bot")
            
            if error:
                await processing_msg.edit_text(f"❌ Error: {error}")
            else:
                search_id = str(uuid.uuid4())[:8]
                search_cache[search_id] = {
                    "results": results,
                    "query": "python bot",
                    "user_id": user_id,
                    "timestamp": current_time
                }
                
                keyboard_buttons = []
                for i, repo in enumerate(results["repos"], 1):
                    callback_data = f"select_{search_id}_{i-1}"
                    button_text = f"{i}. {repo['name'][:15]}"
                    keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
                
                keyboard_buttons.append([InlineKeyboardButton("🔄 Buscar algo diferente", callback_data="search")])
                keyboard = InlineKeyboardMarkup(keyboard_buttons)
                
                await processing_msg.edit_text(
                    format_repo_search_results(results),
                    reply_markup=keyboard,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
            await callback_query.answer()
        
        elif data.startswith(("prev_", "next_")):
            parts = data.split("_")
            action = parts[0]
            search_id = parts[1]
            current_page = int(parts[2])
            
            if search_id not in search_cache:
                await callback_query.answer("❌ La búsqueda ha expirado")
                return
            
            search_data = search_cache[search_id]
            
            if search_data["user_id"] != user_id:
                await callback_query.answer("❌ Esta búsqueda no es tuya")
                return
            
            new_page = current_page - 1 if action == "prev" else current_page + 1
            query = search_data["query"]
            
            results, error = await search_github_repos(query, new_page)
            
            if error:
                await callback_query.answer(f"Error: {error}")
                return
            
            search_cache[search_id]["results"] = results
            search_cache[search_id]["timestamp"] = current_time
            
            keyboard_buttons = []
            for i, repo in enumerate(results["repos"], 1):
                callback_data = f"select_{search_id}_{i-1}"
                button_text = f"{i}. {repo['name'][:15]}"
                keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            nav_buttons = []
            if results["has_prev"]:
                nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"prev_{search_id}_{results['page']}"))
            
            if results["has_next"]:
                nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"next_{search_id}_{results['page']}"))
            
            if nav_buttons:
                keyboard_buttons.append(nav_buttons)
            
            keyboard_buttons.append([InlineKeyboardButton("🔄 Nueva búsqueda", callback_data="search")])
            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            
            await message.edit_text(
                format_repo_search_results(results),
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.MARKDOWN
            )
            await callback_query.answer(f"Página {new_page}")
        
        elif data.startswith("select_"):
            parts = data.split("_")
            search_id = parts[1]
            repo_index = int(parts[2])
            
            if search_id not in search_cache:
                await callback_query.answer("❌ La búsqueda ha expirado")
                return
            
            search_data = search_cache[search_id]
            
            if search_data["user_id"] != user_id:
                await callback_query.answer("❌ Esta búsqueda no es tuya")
                return
            
            repos = search_data["results"]["repos"]
            
            if repo_index >= len(repos):
                await callback_query.answer("❌ Repositorio no encontrado")
                return
            
            repo = repos[repo_index]
            
            details_text = f"""
📦 **{repo['full_name']}**

📝 **Descripción:** {repo['description']}

📊 **Estadísticas:**
⭐ Estrellas: {repo['stars']}
🍴 Forks: {repo['forks']}
💻 Lenguaje: {repo['language']}
👤 Propietario: {repo['owner']}
🕐 Actualizado: {repo['updated_at'][:10]}

🔗 **URL:** {repo['url']}
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Descargar", callback_data=f"dl_{repo['url']}"),
                 InlineKeyboardButton("🌐 Ver en GitHub", url=repo['url'])],
                [InlineKeyboardButton("🔙 Volver a resultados", callback_data=f"back_{search_id}"),
                 InlineKeyboardButton("🔄 Nueva búsqueda", callback_data="search")]
            ])
            
            await message.edit_text(details_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
            await callback_query.answer(f"Seleccionado: {repo['name']}")
        
        elif data.startswith("back_"):
            search_id = data.split("_")[1]
            
            if search_id not in search_cache:
                await callback_query.answer("❌ La búsqueda ha expirado")
                return
            
            search_data = search_cache[search_id]
            results = search_data["results"]
            
            keyboard_buttons = []
            for i, repo in enumerate(results["repos"], 1):
                callback_data = f"select_{search_id}_{i-1}"
                button_text = f"{i}. {repo['name'][:15]}"
                keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            nav_buttons = []
            if results["has_prev"]:
                nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"prev_{search_id}_{results['page']}"))
            
            if results["has_next"]:
                nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"next_{search_id}_{results['page']}"))
            
            if nav_buttons:
                keyboard_buttons.append(nav_buttons)
            
            keyboard_buttons.append([InlineKeyboardButton("🔄 Nueva búsqueda", callback_data="search")])
            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            
            await message.edit_text(
                format_repo_search_results(results),
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.MARKDOWN
            )
            await callback_query.answer("Volviendo a resultados...")
        
        elif data.startswith("dl_"):
            repo_url = data[3:]
            
            processing_msg = await callback_query.message.reply_text("⏳ Descargando...")
            
            zip_content, error = await download_github_repo(repo_url)
            
            if error:
                await processing_msg.edit_text(f"❌ Error: {error}")
            else:
                username, repo_name = get_repo_info_from_url(repo_url)
                filename = f"{repo_name or 'repo'}.zip"
                file_size_mb = len(zip_content) / 1024 / 1024
                
                await callback_query.message.reply_document(
                    document=io.BytesIO(zip_content),
                    file_name=filename,
                    caption=(
                        f"📦 **{repo_name or 'Repositorio'}**\n"
                        f"🔗 {repo_url}\n"
                        f"📊 Tamaño: {file_size_mb:.1f}MB\n"
                        f"👤 Usuario: {username or 'Desconocido'}\n\n"
                        f"✅ Descargado por @{client.me.username}"
                    ),
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                await processing_msg.delete()
            
            await callback_query.answer("✅ Descarga completada")
        
        elif data == "quick_download":
            example_url = "https://github.com/octocat/Spoon-Knife"
            
            msg = await callback_query.message.reply_text("⏳ Descargando ejemplo...")
            zip_content, error = await download_github_repo(example_url)
            
            if error:
                await msg.edit_text(f"❌ Error: {error}")
            else:
                await callback_query.message.reply_document(
                    document=io.BytesIO(zip_content),
                    file_name="Spoon-Knife.zip",
                    caption="🍴 **Spoon-Knife**\nRepositorio de prueba de GitHub\nDescargado por GitHub Downloader Bot",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                await msg.delete()
            
            await callback_query.answer()
        
        # Callbacks para administración root
        elif data.startswith("root_"):
            if user_id != ADMIN_ID:
                await callback_query.answer("❌ Acceso exclusivo del administrador", show_alert=True)
                return
            
            if data == "root":
                await root_command(client, message)
            
            elif data == "root_list_current":
                await list_directory_command(client, message, BASE_DIR)
            
            elif data.startswith("root_list_"):
                parts = data[10:].split("_", 2)
                path = parts[0] if len(parts) > 0 else BASE_DIR
                
                if len(parts) == 2 and parts[1].isdigit():
                    page = int(parts[1])
                    await list_directory_command(client, message, path, page)
                else:
                    await list_directory_command(client, message, path)
            
            elif data.startswith("root_info_"):
                path = data[10:]
                await list_directory_command(client, message, path)
            
            elif data == "root_disk_usage":
                await disk_command(client, message)
            
            elif data == "root_disk_details":
                disk_info = FileManager.get_disk_usage()
                
                if disk_info:
                    text = "💾 **Detalles del Disco**\n\n"
                    text += f"**Total bytes:** {disk_info['total']:,}\n"
                    text += f"**Usado bytes:** {disk_info['used']:,}\n"
                    text += f"**Libre bytes:** {disk_info['free']:,}\n"
                    text += f"**Porcentaje:** {disk_info['percent_used']:.2f}%\n"
                    text += f"**Temp bytes:** {disk_info['temp_size']:,}\n"
                    text += f"**Archivos temp:** {disk_info['temp_count']}\n\n"
                    text += f"**Timestamp:** {disk_info['timestamp']}"
                    
                    await message.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
                else:
                    await message.edit_text("❌ Error obteniendo detalles del disco")
            
            elif data == "root_cleanup_temp":
                await clean_command(client, message)
            
            elif data.startswith("root_send_"):
                path = data[10:]
                
                if not FileManager.is_safe_path(path):
                    await callback_query.answer("❌ Ruta no permitida", show_alert=True)
                    return
                
                if not os.path.isfile(path):
                    await callback_query.answer("❌ No es un archivo válido", show_alert=True)
                    return
                
                file_size = os.path.getsize(path)
                
                if file_size > MAX_FILE_SIZE:
                    await callback_query.answer(
                        f"❌ Archivo demasiado grande ({humanize.naturalsize(file_size)})",
                        show_alert=True
                    )
                    return
                
                await callback_query.answer("📤 Enviando archivo...")
                
                try:
                    await message.reply_document(
                        document=path,
                        caption=f"📄 **Archivo del sistema**\n`{os.path.basename(path)}`\n\n"
                               f"**Ruta:** `{path}`\n"
                               f"**Tamaño:** {humanize.naturalsize(file_size)}",
                        parse_mode=enums.ParseMode.MARKDOWN
                    )
                except Exception as e:
                    await message.reply_text(f"❌ Error enviando archivo: {str(e)}")
            
            elif data.startswith("root_delete_"):
                path = data[12:]
                
                if not FileManager.is_safe_path(path):
                    await callback_query.answer("❌ Ruta no permitida", show_alert=True)
                    return
                
                if not os.path.exists(path):
                    await callback_query.answer("❌ La ruta no existe", show_alert=True)
                    return
                
                item_name = os.path.basename(path)
                is_dir = os.path.isdir(path)
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Sí, eliminar", callback_data=f"root_confirm_delete_{path}"),
                     InlineKeyboardButton("❌ Cancelar", callback_data=f"root_list_{os.path.dirname(path)}")]
                ])
                
                confirm_text = f"⚠️ **Confirmar eliminación**\n\n"
                if is_dir:
                    confirm_text += f"¿Eliminar el directorio **{item_name}** y todo su contenido?\n\n"
                    confirm_text += "**Esta acción no se puede deshacer.**"
                else:
                    confirm_text += f"¿Eliminar el archivo **{item_name}**?\n\n"
                    confirm_text += "**Esta acción no se puede deshacer.**"
                
                await message.edit_text(confirm_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
                await callback_query.answer()
            
            elif data.startswith("root_confirm_delete_"):
                path = data[20:]
                
                success, message_text = FileManager.delete_path(path)
                
                if success:
                    parent_dir = os.path.dirname(path)
                    await list_directory_command(client, message, parent_dir)
                    await callback_query.answer("✅ Eliminado correctamente")
                else:
                    await message.edit_text(f"❌ {message_text}")
                    await callback_query.answer("❌ Error")
            
            elif data.startswith("root_rename_"):
                path = data[12:]
                
                if not FileManager.is_safe_path(path):
                    await callback_query.answer("❌ Ruta no permitida", show_alert=True)
                    return
                
                if not os.path.exists(path):
                    await callback_query.answer("❌ La ruta no existe", show_alert=True)
                    return
                
                item_name = os.path.basename(path)
                
                rename_states[user_id] = path
                
                await callback_query.answer("📝 Ingresa el nuevo nombre")
                
                await message.reply_text(
                    f"🔄 **Renombrar**\n\n"
                    f"**Actual:** `{item_name}`\n\n"
                    f"Por favor, envía el nuevo nombre:",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
            
            elif data.startswith("root_mkdir_"):
                parent_path = data[11:]
                
                if not FileManager.is_safe_path(parent_path):
                    await callback_query.answer("❌ Ruta no permitida", show_alert=True)
                    return
                
                mkdir_states[user_id] = parent_path
                await callback_query.answer("📁 Ingresa el nombre de la carpeta")
                
                await message.reply_text(
                    f"➕ **Crear nueva carpeta**\n\n"
                    f"**Ubicación:** `{parent_path}`\n\n"
                    f"Por favor, envía el nombre de la nueva carpeta:",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
            
            elif data == "root_search_menu":
                await message.edit_text(
                    "🔍 **Buscar Archivos**\n\n"
                    "Envía el patrón de búsqueda:\n\n"
                    "**Ejemplos:**\n"
                    "• `.py` - Archivos Python\n"
                    "• `config` - Archivos de configuración\n"
                    "• `log` - Archivos de log\n\n"
                    "**O usa:** `/find <patrón> [ruta]`",
                    parse_mode=enums.ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔍 Buscar en base", callback_data=f"root_search_{BASE_DIR}"),
                         InlineKeyboardButton("🔍 Buscar en temp", callback_data=f"root_search_{TEMP_DIR}")],
                        [InlineKeyboardButton("🔙 Volver", callback_data="root")]
                    ])
                )
            
            elif data.startswith("root_search_"):
                path = data[12:]
                
                if not FileManager.is_safe_path(path):
                    await callback_query.answer("❌ Ruta no permitida", show_alert=True)
                    return
                
                search_states[user_id] = path
                await callback_query.answer("🔍 Ingresa el patrón de búsqueda")
                
                await message.reply_text(
                    f"🔍 **Buscar en directorio**\n\n"
                    f"**Ruta:** `{path}`\n\n"
                    f"Envía el patrón a buscar:",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
            
            elif data == "root_view_logs":
                log_file = os.path.join(BASE_DIR, "bot.log")
                
                if os.path.exists(log_file):
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                        
                        if lines:
                            last_lines = lines[-50:]
                            log_text = "".join(last_lines)
                            
                            if len(log_text) > 4000:
                                log_text = "...\n" + log_text[-4000:]
                            
                            text = f"📝 **Últimas líneas del log**\n\n"
                            text += f"**Archivo:** `{log_file}`\n"
                            text += f"**Total líneas:** {len(lines)}\n\n"
                            text += "```\n"
                            text += log_text
                            text += "\n```"
                            
                            keyboard = InlineKeyboardMarkup([
                                [InlineKeyboardButton("📤 Descargar log completo", callback_data="root_download_log")],
                                [InlineKeyboardButton("🗑️ Limpiar logs", callback_data="root_clear_logs"),
                                 InlineKeyboardButton("🔙 Volver", callback_data="root")]
                            ])
                            
                            await message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
                        else:
                            await message.edit_text("📭 El archivo de log está vacío")
                    except Exception as e:
                        await message.edit_text(f"❌ Error leyendo log: {str(e)}")
                else:
                    await message.edit_text("📭 No se encontró archivo de log")
            
            elif data == "root_download_log":
                log_file = os.path.join(BASE_DIR, "bot.log")
                
                if os.path.exists(log_file):
                    file_size = os.path.getsize(log_file)
                    
                    if file_size > MAX_FILE_SIZE:
                        await callback_query.answer(
                            f"❌ Log demasiado grande ({humanize.naturalsize(file_size)})",
                            show_alert=True
                        )
                        return
                    
                    await callback_query.answer("📤 Enviando archivo de log...")
                    
                    try:
                        await message.reply_document(
                            document=log_file,
                            caption="📝 **Archivo de log completo**",
                            parse_mode=enums.ParseMode.MARKDOWN
                        )
                    except Exception as e:
                        await message.reply_text(f"❌ Error enviando log: {str(e)}")
                else:
                    await callback_query.answer("❌ No se encontró archivo de log", show_alert=True)
            
            elif data == "root_clear_logs":
                log_file = os.path.join(BASE_DIR, "bot.log")
                
                if os.path.exists(log_file):
                    try:
                        backup_file = f"{log_file}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        shutil.copy2(log_file, backup_file)
                        
                        with open(log_file, 'w') as f:
                            f.write(f"=== Log limpiado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                        
                        await message.edit_text(
                            f"✅ **Log limpiado**\n\n"
                            f"Se creó un backup: `{os.path.basename(backup_file)}`",
                            parse_mode=enums.ParseMode.MARKDOWN
                        )
                    except Exception as e:
                        await message.edit_text(f"❌ Error limpiando log: {str(e)}")
                else:
                    await message.edit_text("📭 No se encontró archivo de log")
        
        # Callbacks para GitHub Manager
        elif data.startswith("github_") or data.startswith("gh_"):
            if user_id != ADMIN_ID:
                await callback_query.answer("❌ Acceso exclusivo del administrador", show_alert=True)
                return
            
            if data == "github":
                await github_command(client, message)
            
            elif data == "github_list_repos":
                await list_github_repos_command(client, message)
            
            elif data.startswith("gh_repos_"):
                page = int(data.split("_")[2])
                await list_github_repos_command(client, message)
            
            elif data.startswith("gh_repo_info_"):
                parts = data.split("_")
                owner = parts[3]
                repo_name = parts[4]
                
                repo_info = await github_manager.get_repo_info(owner, repo_name)
                
                if 'error' in repo_info:
                    text = f"❌ Error: {repo_info['error']}"
                else:
                    text = f"📦 **{repo_info['full_name']}**\n\n"
                    text += f"📝 **Descripción:** {repo_info['description'] or 'Sin descripción'}\n"
                    text += f"🌐 **Visibilidad:** {'🔒 Privado' if repo_info['private'] else '🌐 Público'}\n"
                    text += f"⭐ **Estrellas:** {repo_info['stargazers_count']}\n"
                    text += f"🍴 **Forks:** {repo_info['forks_count']}\n"
                    text += f"👁️ **Watchers:** {repo_info['watchers_count']}\n"
                    text += f"📊 **Tamaño:** {repo_info['size']} KB\n"
                    text += f"💻 **Lenguaje:** {repo_info['language'] or 'N/A'}\n"
                    text += f"📅 **Creado:** {repo_info['created_at'][:10]}\n"
                    text += f"🔄 **Actualizado:** {repo_info['updated_at'][:10]}\n"
                    text += f"🔗 **URL:** {repo_info['html_url']}\n"
                    text += f"🌿 **Rama por defecto:** {repo_info['default_branch']}\n\n"
                    
                    if repo_info['license']:
                        text += f"📄 **Licencia:** {repo_info['license']['name']}\n"
                    
                    text += f"🏠 **Página:** {repo_info['homepage'] or 'N/A'}\n"
                    text += f"⚠️ **Issues abiertos:** {repo_info['open_issues_count']}"
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📂 Listar archivos", callback_data=f"gh_list_files_{owner}_{repo_name}"),
                     InlineKeyboardButton("🌿 Ver ramas", callback_data=f"gh_list_branches_{owner}_{repo_name}")],
                    [InlineKeyboardButton("📝 Crear archivo", callback_data=f"gh_create_file_{owner}_{repo_name}"),
                     InlineKeyboardButton("⚠️ Crear issue", callback_data=f"gh_create_issue_{owner}_{repo_name}")],
                    [InlineKeyboardButton("🗑️ Eliminar repo", callback_data=f"gh_confirm_delete_{owner}_{repo_name}"),
                     InlineKeyboardButton("🔙 Volver", callback_data="github_list_repos")]
                ])
                
                await message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
            
            elif data == "github_create_repo":
                await message.edit_text(
                    "➕ **Crear Nuevo Repositorio**\n\n"
                    "Envía el nombre del nuevo repositorio:\n\n"
                    "**Ejemplos:**\n"
                    "`mi-proyecto`\n"
                    "`api-rest`\n"
                    "`blog-personal`\n\n"
                    "Luego podrás añadir descripción y configurar opciones.",
                    parse_mode=enums.ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                    ])
                )
                github_states[user_id] = {"operation": "create_repo_name"}
            
            elif data == "github_fork_repo":
                await message.edit_text(
                    "🍴 **Hacer Fork de Repositorio**\n\n"
                    "Envía el repositorio en formato `owner/repo`:\n\n"
                    "**Ejemplos:**\n"
                    "`octocat/Spoon-Knife`\n"
                    "`microsoft/vscode`\n"
                    "`facebook/react`\n\n"
                    "El fork se creará en tu cuenta.",
                    parse_mode=enums.ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                    ])
                )
                github_states[user_id] = {"operation": "fork_repo"}
            
            elif data == "github_delete_repo":
                await message.edit_text(
                    "🗑️ **Eliminar Repositorio**\n\n"
                    "Envía el repositorio en formato `owner/repo`:\n\n"
                    "**Ejemplos:**\n"
                    "`tuusuario/repo-viejo`\n"
                    "`mi-org/proyecto-test`\n\n"
                    "⚠️ **ADVERTENCIA:** Esta acción es irreversible.",
                    parse_mode=enums.ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                    ])
                )
                github_states[user_id] = {"operation": "delete_repo"}
            
            elif data.startswith("gh_confirm_delete_"):
                parts = data.split("_")
                owner = parts[3]
                repo_name = parts[4]
                
                processing_msg = await message.reply_text(f"🗑️ Eliminando `{owner}/{repo_name}`...")
                
                success, result = await github_manager.delete_repo(owner, repo_name)
                
                await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)
                
                await list_github_repos_command(client, message)
            
            elif data == "github_create_file":
                await message.edit_text(
                    "📝 **Crear Archivo en Repositorio**\n\n"
                    "Envía los datos en este formato:\n\n"
                    "`owner/repo ruta/archivo.ext \"contenido\"`\n\n"
                    "**Ejemplo:**\n"
                    "`tuusuario/mi-repo README.md \"# Mi Proyecto\\n\\nDescripción aquí\"`",
                    parse_mode=enums.ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                    ])
                )
            
            elif data == "github_branches":
                await message.edit_text(
                    "🌿 **Gestionar Ramas**\n\n"
                    "Envía el repositorio en formato `owner/repo`:\n\n"
                    "**Ejemplos:**\n"
                    "`tuusuario/mi-repo`\n"
                    "`org/proyecto`\n\n"
                    "Podrás ver y crear nuevas ramas.",
                    parse_mode=enums.ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                    ])
                )
            
            elif data.startswith("gh_list_branches_"):
                parts = data.split("_")
                owner = parts[3]
                repo_name = parts[4]
                
                branches = await github_manager.list_branches(owner, repo_name)
                
                if not branches:
                    text = f"🌿 **Ramas de {owner}/{repo_name}**\n\n📭 No hay ramas disponibles"
                else:
                    text = f"🌿 **Ramas de {owner}/{repo_name}**\n\n"
                    for i, branch in enumerate(branches, 1):
                        text += f"**{i}. {branch}**\n"
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Nueva rama", callback_data=f"gh_create_branch_{owner}_{repo_name}"),
                     InlineKeyboardButton("🔙 Repositorio", callback_data=f"gh_repo_info_{owner}_{repo_name}")]
                ])
                
                await message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
            
            elif data.startswith("gh_create_branch_"):
                parts = data.split("_")
                owner = parts[3]
                repo_name = parts[4]
                
                await message.edit_text(
                    f"🌿 **Crear Nueva Rama en {owner}/{repo_name}**\n\n"
                    "Envía el nombre de la nueva rama:\n\n"
                    "**Ejemplos:**\n"
                    "`feature/login`\n"
                    "`bugfix/issue-42`\n"
                    "`release/v2.0`\n\n"
                    "Se creará desde la rama `main` por defecto.",
                    parse_mode=enums.ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Ramas", callback_data=f"gh_list_branches_{owner}_{repo_name}")]
                    ])
                )
                github_states[user_id] = {
                    "operation": "create_branch",
                    "owner": owner,
                    "repo_name": repo_name
                }
            
            elif data == "github_create_issue":
                await message.edit_text(
                    "⚠️ **Crear Issue**\n\n"
                    "Envía los datos en este formato:\n\n"
                    "`owner/repo \"Título del issue\" \"Descripción detallada\"`\n\n"
                    "**Ejemplo:**\n"
                    "`tuusuario/repo \"Bug en login\" \"El botón de login no funciona en móviles\"`",
                    parse_mode=enums.ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                    ])
                )
            
            elif data == "github_create_gist":
                await message.edit_text(
                    "💾 **Crear Gist**\n\n"
                    "Envía los datos en este formato:\n\n"
                    "`\"Descripción del gist\" \"contenido del archivo\"`\n\n"
                    "**Ejemplo:**\n"
                    "`\"Configuración API\" \"API_KEY=abc123\\nDEBUG=True\"`",
                    parse_mode=enums.ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                    ])
                )
            
            elif data == "github_list_orgs":
                orgs = await github_manager.list_orgs()
                
                if not orgs:
                    text = "🏢 **Tus Organizaciones**\n\n📭 No perteneces a ninguna organización"
                else:
                    text = "🏢 **Tus Organizaciones**\n\n"
                    for org in orgs:
                        text += f"• **{org['login']}** - {org['description'] or 'Sin descripción'}\n"
                        text += f"  👥 {org['members_url'].split('{')[0]}\n\n"
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 GitHub", callback_data="github")]
                ])
                
                await message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
            
            elif data == "github_test":
                success, msg = await github_manager.test_connection()
                await callback_query.answer(msg, show_alert=True)
            
            elif data.startswith("gh_repo_vis_"):
                parts = data.split("_")
                visibility = parts[3]
                name = parts[4]
                description = "_".join(parts[5:])
                description = description.replace("_", " ")
                
                processing_msg = await callback_query.message.reply_text(
                    f"🛠️ Creando repositorio `{name}` ({'🌐 Público' if visibility == 'public' else '🔒 Privado'})..."
                )
                
                success, result = await github_manager.create_repo(
                    name, 
                    description, 
                    private=(visibility == "private")
                )
                
                await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)
                await callback_query.answer()
        
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error en callback: {e}")
        await callback_query.answer(f"❌ Error: {str(e)[:50]}", show_alert=True)

# ==============================================
# HANDLER DE MENSAJES DE TEXTO
# ==============================================
@app.on_message(filters.private & filters.text & ~filters.command([
    "start", "search", "download", "help", "example", "info", 
    "root", "ls", "disk", "clean", "find", "tree", "stats",
    "github", "ghrepos", "ghcreate", "ghfork", "ghdelete", 
    "ghfile", "ghissue", "ghgist", "ghtoken"
]))
async def handle_text_messages(client: Client, message: Message):
    """Maneja mensajes de texto para operaciones root y GitHub"""
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        return
    
    text = message.text.strip()
    
    # Verificar si estamos esperando un nombre para renombrar
    if user_id in rename_states:
        old_path = rename_states[user_id]
        parent_dir = os.path.dirname(old_path)
        new_path = os.path.join(parent_dir, text)
        
        success, msg = FileManager.rename_path(old_path, text)
        
        if success:
            await message.reply_text(f"✅ {msg}")
            await list_directory_command(client, message, parent_dir)
        else:
            await message.reply_text(f"❌ {msg}")
        
        del rename_states[user_id]
        return
    
    # Verificar si estamos esperando un nombre para nueva carpeta
    elif user_id in mkdir_states:
        parent_path = mkdir_states[user_id]
        new_dir = os.path.join(parent_path, text)
        
        success, msg = FileManager.create_directory(new_dir)
        
        if success:
            await message.reply_text(f"✅ {msg}")
            await list_directory_command(client, message, parent_path)
        else:
            await message.reply_text(f"❌ {msg}")
        
        del mkdir_states[user_id]
        return
    
    # Verificar si estamos esperando un patrón de búsqueda
    elif user_id in search_states:
        search_path = search_states[user_id]
        
        results = FileManager.search_files(search_path, text)
        
        if not results:
            await message.reply_text(f"❌ No se encontraron resultados para `{text}`")
        else:
            response = f"🔍 **Resultados para `{text}` en `{search_path}`**\n\n"
            response += f"**Encontrados:** {len(results)} items\n\n"
            
            for i, result in enumerate(results[:10], 1):
                icon = "📁" if result["type"] == "directory" else "📄"
                size = f" ({result['size_human']})" if result["type"] == "file" else ""
                response += f"{icon} **{i}.** `{result['relative_path']}`{size}\n"
            
            if len(results) > 10:
                response += f"\n... y {len(results) - 10} más"
            
            await message.reply_text(response, parse_mode=enums.ParseMode.MARKDOWN)
        
        del search_states[user_id]
        return
    
    # Verificar si estamos en un estado de GitHub
    elif user_id in github_states:
        state = github_states[user_id]
        operation = state.get("operation")
        
        try:
            if operation == "create_repo_name":
                github_states[user_id] = {
                    "operation": "create_repo_desc",
                    "name": text
                }
                
                await message.reply_text(
                    f"📝 **Nombre guardado:** `{text}`\n\n"
                    "Ahora envía la descripción (opcional):\n\n"
                    "**Ejemplos:**\n"
                    "`Un proyecto para gestionar tareas`\n"
                    "`API REST en FastAPI`\n\n"
                    "O envía `skip` para saltar.",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                
            elif operation == "create_repo_desc":
                name = state["name"]
                description = text if text.lower() != "skip" else ""
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🌐 Público", callback_data=f"gh_repo_vis_public_{name}_{description}"),
                     InlineKeyboardButton("🔒 Privado", callback_data=f"gh_repo_vis_private_{name}_{description}")]
                ])
                
                await message.reply_text(
                    f"🛠️ **Configurar Repositorio**\n\n"
                    f"**Nombre:** `{name}`\n"
                    f"**Descripción:** `{description or 'Sin descripción'}`\n\n"
                    f"Selecciona la visibilidad:",
                    reply_markup=keyboard,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                
                del github_states[user_id]
                
            elif operation == "fork_repo":
                if '/' not in text:
                    await message.reply_text("❌ Formato incorrecto. Usa: `owner/repo`")
                    del github_states[user_id]
                    return
                
                owner, repo_name = text.split('/', 1)
                
                processing_msg = await message.reply_text(f"🍴 Haciendo fork de `{owner}/{repo_name}`...")
                
                success, result = await github_manager.fork_repo(owner, repo_name)
                
                await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)
                
                del github_states[user_id]
                
            elif operation == "delete_repo":
                if '/' not in text:
                    await message.reply_text("❌ Formato incorrecto. Usa: `owner/repo`")
                    del github_states[user_id]
                    return
                
                owner, repo_name = text.split('/', 1)
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Sí, eliminar", callback_data=f"gh_confirm_delete_{owner}_{repo_name}"),
                     InlineKeyboardButton("❌ Cancelar", callback_data="github")]
                ])
                
                await message.reply_text(
                    f"⚠️ **Confirmar eliminación**\n\n"
                    f"¿Eliminar el repositorio **{owner}/{repo_name}**?\n\n"
                    f"**Esta acción es IRREVERSIBLE.**",
                    reply_markup=keyboard,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                
                del github_states[user_id]
                
            elif operation == "create_branch":
                owner = state["owner"]
                repo_name = state["repo_name"]
                
                processing_msg = await message.reply_text(f"🌿 Creando rama `{text}` en `{owner}/{repo_name}`...")
                
                success, result = await github_manager.create_branch(owner, repo_name, text)
                
                await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)
                
                del github_states[user_id]
                
        except Exception as e:
            logger.error(f"Error procesando estado GitHub: {e}")
            await message.reply_text(f"❌ Error: {str(e)}")
            if user_id in github_states:
                del github_states[user_id]

# ==============================================
# DETECCIÓN AUTOMÁTICA DE URLS GITHUB
# ==============================================
@app.on_message(filters.regex(r'https?://github\.com/[^\s]+'))
async def handle_github_url(client: Client, message: Message):
    """Detecta automáticamente URLs de GitHub en mensajes"""
    urls = re.findall(r'https?://github\.com/[^\s]+', message.text)
    
    if urls:
        repo_url = urls[0]
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Descargar ZIP", callback_data=f"dl_{repo_url}"),
             InlineKeyboardButton("🔍 Ver detalles", callback_data=f"info_{repo_url}")],
            [InlineKeyboardButton("🌐 Abrir en GitHub", url=repo_url)]
        ])
        
        username, repo_name = get_repo_info_from_url(repo_url)
        
        await message.reply_text(
            f"🔍 **Repositorio detectado:**\n\n"
            f"**Nombre:** {repo_name or 'Desconocido'}\n"
            f"**Usuario:** {username or 'Desconocido'}\n"
            f"**URL:** {repo_url}\n\n"
            "¿Qué quieres hacer?",
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )

# ==============================================
# FUNCIÓN PRINCIPAL
# ==============================================
async def main():
    try:
        logger.info("🚀 Iniciando GitHub Manager Bot...")
        
        os.makedirs(TEMP_DIR, exist_ok=True)
        logs_dir = os.path.join(BASE_DIR, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        
        log_file = os.path.join(BASE_DIR, "bot.log")
        if not os.path.exists(log_file):
            with open(log_file, 'w') as f:
                f.write(f"=== Bot iniciado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                f.write(f"=== Admin ID: {ADMIN_ID} ===\n")
        
        mimetypes.init()
        
        if GITHUB_TOKEN and GITHUB_TOKEN != "tu_token_de_github_aquí":
            success, msg = await github_manager.test_connection()
            logger.info(f"GitHub: {msg}")
        else:
            logger.warning("⚠️ GITHUB_TOKEN no configurado. Funciones de gestión deshabilitadas.")
        
        await app.start()
        
        me = await app.get_me()
        logger.info(f"✅ Bot iniciado como: @{me.username}")
        logger.info(f"✅ ID del bot: {me.id}")
        logger.info(f"✅ Administrador EXCLUSIVO: {ADMIN_ID}")
        
        logger.info("✅ Bot en ejecución. Presiona Ctrl+C para detener.")
        await asyncio.Event().wait()
        
    except KeyboardInterrupt:
        logger.info("🛑 Bot detenido por el usuario")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await app.stop()
        logger.info("👋 Bot detenido")

if __name__ == "__main__":
    try:
        import psutil
    except ImportError:
        logger.warning("⚠️ Instalando psutil...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "psutil"])
        import psutil
    
    try:
        import humanize
    except ImportError:
        logger.warning("⚠️ Instalando humanize...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "humanize"])
        import humanize
    
    app.run()# Configuración del bot (USA VARIABLES DE ENTORNO)
API_ID = os.getenv("API_ID") or 14681595
API_HASH = os.getenv("API_HASH") or "a86730aab5c59953c424abb4396d32d5"
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8534765454:AAFjZZbb35rjS594M2kF0NdFQpR5PbQX8qI"
# ⚠️ AÑADE TU TOKEN DE GITHUB AQUÍ ⚠️
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or "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"

# ✅ TU ID DE ADMINISTRADOR EXCLUSIVO
ADMIN_ID = 7970466590  # Tu ID exclusivo
ADMINS = [ADMIN_ID]  # Solo tú eres administrador

logger.info(f"✅ Administrador exclusivo configurado: {ADMIN_ID}")

# Verificar credenciales
if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("❌ Faltan credenciales de Telegram. Configura las variables de entorno.")
    exit(1)

if not GITHUB_TOKEN or GITHUB_TOKEN == "tu_token_de_github_aquí":
    logger.warning("⚠️ No se configuró GITHUB_TOKEN. Las funciones de gestión de GitHub no estarán disponibles.")

app = Client(
    "github_manager_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Directorio base del bot
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp_downloads")
os.makedirs(TEMP_DIR, exist_ok=True)

# ==============================================
# 🚀 CLASE PARA GESTIÓN DE GITHUB API
# ==============================================

class GitHubManager:
    """Clase para gestionar operaciones de GitHub API"""
    
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-Manager-Bot'
        }
        self.base_url = "https://api.github.com"
        
    async def test_connection(self) -> Tuple[bool, str]:
        """Testear conexión a GitHub API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/user",
                    headers=self.headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return True, f"✅ Conectado como: {data.get('login', 'Desconocido')}"
                    else:
                        return False, f"❌ Error {response.status}: {await response.text()}"
        except Exception as e:
            return False, f"❌ Error de conexión: {str(e)}"
    
    async def get_user_info(self) -> Dict[str, Any]:
        """Obtener información del usuario"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/user",
                    headers=self.headers
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return {}
        except Exception as e:
            logger.error(f"Error obteniendo info usuario: {e}")
            return {}
    
    async def list_repos(self, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        """Listar repositorios del usuario"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/user/repos",
                    headers=self.headers,
                    params={'page': page, 'per_page': per_page, 'sort': 'updated'}
                ) as response:
                    if response.status == 200:
                        repos = await response.json()
                        
                        # Obtener total de repos
                        total = 0
                        if 'Link' in response.headers:
                            links = response.headers['Link']
                            match = re.search(r'page=(\d+)>; rel="last"', links)
                            if match:
                                last_page = int(match.group(1))
                                total = last_page * per_page
                        
                        return {
                            'repos': repos,
                            'page': page,
                            'per_page': per_page,
                            'total': total,
                            'has_next': len(repos) == per_page
                        }
                    return {'error': f'HTTP {response.status}'}
        except Exception as e:
            logger.error(f"Error listando repos: {e}")
            return {'error': str(e)}
    
    async def create_repo(self, name: str, description: str = "", 
                         private: bool = False, auto_init: bool = True) -> Tuple[bool, str]:
        """Crear nuevo repositorio"""
        try:
            data = {
                'name': name,
                'description': description,
                'private': private,
                'auto_init': auto_init
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/user/repos",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status == 201:
                        repo_data = await response.json()
                        return True, f"✅ Repositorio creado: {repo_data['html_url']}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error creando repo: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def delete_repo(self, owner: str, repo_name: str) -> Tuple[bool, str]:
        """Eliminar repositorio"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{self.base_url}/repos/{owner}/{repo_name}",
                    headers=self.headers
                ) as response:
                    if response.status == 204:
                        return True, f"✅ Repositorio eliminado: {owner}/{repo_name}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error eliminando repo: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def fork_repo(self, owner: str, repo_name: str) -> Tuple[bool, str]:
        """Hacer fork de un repositorio"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/repos/{owner}/{repo_name}/forks",
                    headers=self.headers
                ) as response:
                    if response.status == 202:
                        repo_data = await response.json()
                        return True, f"✅ Fork creado: {repo_data['html_url']}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error haciendo fork: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def get_repo_info(self, owner: str, repo_name: str) -> Dict[str, Any]:
        """Obtener información detallada de un repositorio"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/repos/{owner}/{repo_name}",
                    headers=self.headers
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return {'error': f'HTTP {response.status}'}
        except Exception as e:
            logger.error(f"Error obteniendo info repo: {e}")
            return {'error': str(e)}
    
    async def create_file(self, owner: str, repo_name: str, path: str, 
                         content: str, message: str = "Add file via GitHub Manager Bot") -> Tuple[bool, str]:
        """Crear o actualizar archivo en repositorio"""
        try:
            # Codificar contenido en base64
            content_b64 = base64.b64encode(content.encode()).decode()
            
            data = {
                'message': message,
                'content': content_b64
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{self.base_url}/repos/{owner}/{repo_name}/contents/{path}",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status in [200, 201]:
                        return True, f"✅ Archivo creado/actualizado: {path}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error creando archivo: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def list_branches(self, owner: str, repo_name: str) -> List[str]:
        """Listar ramas de un repositorio"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/repos/{owner}/{repo_name}/branches",
                    headers=self.headers
                ) as response:
                    if response.status == 200:
                        branches = await response.json()
                        return [branch['name'] for branch in branches]
                    return []
        except Exception as e:
            logger.error(f"Error listando ramas: {e}")
            return []
    
    async def create_branch(self, owner: str, repo_name: str, 
                           branch_name: str, from_branch: str = "main") -> Tuple[bool, str]:
        """Crear nueva rama"""
        try:
            # Primero obtener SHA de la rama base
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/repos/{owner}/{repo_name}/git/refs/heads/{from_branch}",
                    headers=self.headers
                ) as response:
                    if response.status != 200:
                        return False, f"❌ Error obteniendo SHA: {response.status}"
                    
                    ref_data = await response.json()
                    sha = ref_data['object']['sha']
                
                # Crear nueva rama
                data = {
                    'ref': f'refs/heads/{branch_name}',
                    'sha': sha
                }
                
                async with session.post(
                    f"{self.base_url}/repos/{owner}/{repo_name}/git/refs",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status == 201:
                        return True, f"✅ Rama creada: {branch_name}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error creando rama: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def create_issue(self, owner: str, repo_name: str, 
                          title: str, body: str = "", labels: List[str] = None) -> Tuple[bool, str]:
        """Crear nuevo issue"""
        try:
            data = {
                'title': title,
                'body': body
            }
            
            if labels:
                data['labels'] = labels
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/repos/{owner}/{repo_name}/issues",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status == 201:
                        issue_data = await response.json()
                        return True, f"✅ Issue creado: {issue_data['html_url']}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error creando issue: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def list_orgs(self) -> List[Dict[str, Any]]:
        """Listar organizaciones del usuario"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/user/orgs",
                    headers=self.headers
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return []
        except Exception as e:
            logger.error(f"Error listando orgs: {e}")
            return []
    
    async def create_gist(self, description: str, files: Dict[str, Dict[str, str]], 
                         public: bool = False) -> Tuple[bool, str]:
        """Crear nuevo gist"""
        try:
            data = {
                'description': description,
                'public': public,
                'files': files
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/gists",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status == 201:
                        gist_data = await response.json()
                        return True, f"✅ Gist creado: {gist_data['html_url']}"
                    else:
                        error_msg = await response.text()
                        return False, f"❌ Error {response.status}: {error_msg}"
        except Exception as e:
            logger.error(f"Error creando gist: {e}")
            return False, f"❌ Error: {str(e)}"

# Inicializar GitHub Manager
github_manager = GitHubManager(GITHUB_TOKEN)

# ==============================================
# FUNCIONES AUXILIARES EXISTENTES
# (Mantener todas las funciones originales del código anterior)
# ==============================================

# [TODAS LAS FUNCIONES ORIGINALES PERMANECEN AQUÍ...]
# FileManager, download_github_repo, search_github_repos, etc.

# ==============================================
# 🆕 COMANDOS DE GESTIÓN GITHUB
# ==============================================

@app.on_message(filters.command("github") & filters.private)
@admin_only
async def github_command(client: Client, message: Message):
    """Menú principal de gestión de GitHub"""
    
    # Verificar token
    if not GITHUB_TOKEN or GITHUB_TOKEN == "tu_token_de_github_aquí":
        await message.reply_text(
            "❌ **Token de GitHub no configurado**\n\n"
            "Configura tu token en la variable `GITHUB_TOKEN`\n\n"
            "**Obtén tu token en:**\n"
            "https://github.com/settings/tokens\n\n"
            "**Permisos necesarios:**\n"
            "• repo (completo)\n"
            "• delete_repo\n"
            "• gist\n"
            "• user",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    # Testear conexión
    success, msg = await github_manager.test_connection()
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Mis repositorios", callback_data="github_list_repos"),
         InlineKeyboardButton("➕ Nuevo repo", callback_data="github_create_repo")],
        [InlineKeyboardButton("🔍 Buscar repos", callback_data="search"),
         InlineKeyboardButton("🍴 Fork repo", callback_data="github_fork_repo")],
        [InlineKeyboardButton("🗑️ Eliminar repo", callback_data="github_delete_repo"),
         InlineKeyboardButton("📝 Crear archivo", callback_data="github_create_file")],
        [InlineKeyboardButton("🌿 Gestionar ramas", callback_data="github_branches"),
         InlineKeyboardButton("⚠️ Crear issue", callback_data="github_create_issue")],
        [InlineKeyboardButton("💾 Crear gist", callback_data="github_create_gist"),
         InlineKeyboardButton("🏢 Mis organizaciones", callback_data="github_list_orgs")],
        [InlineKeyboardButton("🔄 Test conexión", callback_data="github_test"),
         InlineKeyboardButton("🔙 Inicio", callback_data="start")]
    ])
    
    await message.reply_text(
        f"🚀 **GitHub Manager - Panel de Control**\n\n"
        f"{msg}\n\n"
        "**Operaciones disponibles:**\n"
        "• 📂 **Listar repositorios** - Ver todos tus repos\n"
        "• ➕ **Crear repositorio** - Nuevo repo público/privado\n"
        "• 🍴 **Fork repositorio** - Clonar repos de otros\n"
        "• 🗑️ **Eliminar repositorio** - Borrar repos existentes\n"
        "• 📝 **Crear archivos** - Añadir archivos a repos\n"
        "• 🌿 **Gestionar ramas** - Crear/listar ramas\n"
        "• ⚠️ **Crear issues** - Reportar problemas\n"
        "• 💾 **Crear gists** - Compartir código rápido\n"
        "• 🏢 **Organizaciones** - Ver tus organizaciones\n\n"
        "**Comandos rápidos:**\n"
        "`/ghrepos` - Listar repos\n"
        "`/ghcreate <nombre>` - Crear repo\n"
        "`/ghfork <owner/repo>` - Hacer fork\n"
        "`/ghdelete <owner/repo>` - Eliminar repo",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("ghrepos") & filters.private)
@admin_only
async def list_github_repos_command(client: Client, message: Message):
    """Listar repositorios del usuario"""
    args = message.text.split()
    page = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
    
    processing_msg = await message.reply_text(f"📂 Obteniendo repositorios (página {page})...")
    
    result = await github_manager.list_repos(page=page)
    
    if 'error' in result:
        await processing_msg.edit_text(f"❌ Error: {result['error']}")
        return
    
    repos = result['repos']
    
    if not repos:
        await processing_msg.edit_text("📭 No tienes repositorios")
        return
    
    text = f"📂 **Tus Repositorios** (Página {page})\n\n"
    
    for i, repo in enumerate(repos, 1):
        idx = (page - 1) * 10 + i
        private = "🔒" if repo['private'] else "🌐"
        text += f"**{idx}. {private} {repo['name']}**\n"
        text += f"   ⭐ {repo['stargazers_count']} | 🍴 {repo['forks_count']}\n"
        text += f"   📝 {repo['description'][:80] if repo['description'] else 'Sin descripción'}\n"
        text += f"   🔗 {repo['html_url']}\n\n"
    
    # Botones de navegación
    keyboard_buttons = []
    
    # Botones de repositorios (máximo 5)
    for i, repo in enumerate(repos[:5], 1):
        idx = (page - 1) * 10 + i
        btn_text = f"{idx}. {repo['name'][:15]}"
        if len(btn_text) > 20:
            btn_text = btn_text[:17] + "..."
        
        keyboard_buttons.append([
            InlineKeyboardButton(
                btn_text,
                callback_data=f"gh_repo_info_{repo['owner']['login']}_{repo['name']}"
            )
        ])
    
    # Botones de navegación de página
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"gh_repos_{page-1}"))
    
    if result.get('has_next'):
        nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"gh_repos_{page+1}"))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    keyboard_buttons.append([
        InlineKeyboardButton("➕ Crear repo", callback_data="github_create_repo"),
        InlineKeyboardButton("🔙 GitHub", callback_data="github")
    ])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await processing_msg.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("ghcreate") & filters.private)
@admin_only
async def create_github_repo_command(client: Client, message: Message):
    """Crear nuevo repositorio"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "➕ **Crear Repositorio GitHub**\n\n"
            "**Uso:** `/ghcreate <nombre> [descripción]`\n\n"
            "**Ejemplos:**\n"
            "• `/ghcreate mi-proyecto`\n"
            "• `/ghcreate api-rest \"Mi API REST en Python\"`\n\n"
            "**Opciones adicionales (por interfaz):**\n"
            "• Público/Privado\n"
            "• Inicializar con README\n"
            "• Añadir .gitignore\n"
            "• Añadir licencia",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    params = args[1].strip()
    parts = params.split('"')
    
    if len(parts) >= 3:
        # Tiene descripción entre comillas
        name = parts[0].strip()
        description = parts[1].strip()
    else:
        # Sin comillas, tomar todo como nombre
        name = params
        description = ""
    
    processing_msg = await message.reply_text(f"🛠️ Creando repositorio `{name}`...")
    
    success, result = await github_manager.create_repo(name, description)
    
    await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("ghfork") & filters.private)
@admin_only
async def fork_github_repo_command(client: Client, message: Message):
    """Hacer fork de un repositorio"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "🍴 **Fork Repositorio**\n\n"
            "**Uso:** `/ghfork <owner/repo>`\n\n"
            "**Ejemplos:**\n"
            "• `/ghfork octocat/Spoon-Knife`\n"
            "• `/ghfork microsoft/vscode`\n\n"
            "**Nota:** El fork se creará en tu cuenta",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    repo_path = args[1].strip()
    
    if '/' not in repo_path:
        await message.reply_text("❌ Formato incorrecto. Usa: `owner/repo`")
        return
    
    owner, repo_name = repo_path.split('/', 1)
    
    processing_msg = await message.reply_text(f"🍴 Haciendo fork de `{owner}/{repo_name}`...")
    
    success, result = await github_manager.fork_repo(owner, repo_name)
    
    await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("ghdelete") & filters.private)
@admin_only
async def delete_github_repo_command(client: Client, message: Message):
    """Eliminar repositorio"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "🗑️ **Eliminar Repositorio**\n\n"
            "⚠️ **ADVERTENCIA:** Esta acción es irreversible\n\n"
            "**Uso:** `/ghdelete <owner/repo>`\n\n"
            "**Ejemplos:**\n"
            "• `/ghdelete tuusuario/mi-repo`\n"
            "• `/ghdelete tuorg/proyecto`\n\n"
            "**Confirmación requerida**",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    repo_path = args[1].strip()
    
    if '/' not in repo_path:
        await message.reply_text("❌ Formato incorrecto. Usa: `owner/repo`")
        return
    
    owner, repo_name = repo_path.split('/', 1)
    
    # Pedir confirmación
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Sí, eliminar", callback_data=f"gh_confirm_delete_{owner}_{repo_name}"),
         InlineKeyboardButton("❌ Cancelar", callback_data="github")]
    ])
    
    await message.reply_text(
        f"⚠️ **Confirmar eliminación**\n\n"
        f"¿Eliminar el repositorio **{owner}/{repo_name}**?\n\n"
        f"**Esta acción:**\n"
        f"• ❌ Es IRREVERSIBLE\n"
        f"• 📝 Elimina TODO el código\n"
        f"• 🔥 Borra issues, stars, forks\n"
        f"• 🕐 No se puede recuperar\n\n"
        f"**¿Continuar?**",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("ghfile") & filters.private)
@admin_only
async def create_file_command(client: Client, message: Message):
    """Crear archivo en repositorio"""
    args = message.text.split(maxsplit=3)
    
    if len(args) < 4:
        await message.reply_text(
            "📝 **Crear Archivo en Repositorio**\n\n"
            "**Uso:** `/ghfile <owner/repo> <ruta> <contenido>`\n\n"
            "**Ejemplos:**\n"
            "• `/ghfile tuusuario/repo README.md \"# Mi Proyecto\"`\n"
            "• `/ghfile org/proj src/main.py \"print('Hola')\"`\n\n"
            "**Nota:** Usa comillas para contenido con espacios",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    repo_path = args[1]
    file_path = args[2]
    content = args[3]
    
    if '/' not in repo_path:
        await message.reply_text("❌ Formato incorrecto. Usa: `owner/repo`")
        return
    
    owner, repo_name = repo_path.split('/', 1)
    
    processing_msg = await message.reply_text(f"📝 Creando archivo `{file_path}`...")
    
    success, result = await github_manager.create_file(owner, repo_name, file_path, content)
    
    await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("ghissue") & filters.private)
@admin_only
async def create_issue_command(client: Client, message: Message):
    """Crear issue en repositorio"""
    args = message.text.split(maxsplit=3)
    
    if len(args) < 4:
        await message.reply_text(
            "⚠️ **Crear Issue**\n\n"
            "**Uso:** `/ghissue <owner/repo> <título> <descripción>`\n\n"
            "**Ejemplos:**\n"
            "• `/ghissue tuusuario/repo \"Bug fix\" \"Error en línea 42\"`\n"
            "• `/ghissue org/proj \"Nueva feature\" \"Añadir login social\"`\n\n"
            "**Nota:** Usa comillas para texto con espacios",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    repo_path = args[1]
    title = args[2]
    body = args[3] if len(args) > 3 else ""
    
    if '/' not in repo_path:
        await message.reply_text("❌ Formato incorrecto. Usa: `owner/repo`")
        return
    
    owner, repo_name = repo_path.split('/', 1)
    
    processing_msg = await message.reply_text(f"⚠️ Creando issue en `{owner}/{repo_name}`...")
    
    success, result = await github_manager.create_issue(owner, repo_name, title, body)
    
    await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("ghgist") & filters.private)
@admin_only
async def create_gist_command(client: Client, message: Message):
    """Crear gist"""
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        await message.reply_text(
            "💾 **Crear Gist**\n\n"
            "**Uso:** `/ghgist <descripción> <contenido>`\n\n"
            "**Ejemplos:**\n"
            "• `/ghgist \"Mi código\" \"print('Hello')\"`\n"
            "• `/ghgist \"Config\" \"API_KEY=123456\"`\n\n"
            "**Archivo por defecto:** `file1.txt`\n"
            "Usa la interfaz para múltiples archivos",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    description = args[1]
    content = args[2]
    
    files = {
        "file1.txt": {
            "content": content
        }
    }
    
    processing_msg = await message.reply_text(f"💾 Creando gist...")
    
    success, result = await github_manager.create_gist(description, files, public=False)
    
    await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("ghtoken") & filters.private)
@admin_only
async def set_github_token_command(client: Client, message: Message):
    """Establecer o actualizar token de GitHub"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "🔑 **Configurar Token de GitHub**\n\n"
            "**Uso:** `/ghtoken <tu_token>`\n\n"
            "**Obtén tu token en:**\n"
            "https://github.com/settings/tokens\n\n"
            "**Permisos necesarios:**\n"
            "• `repo` (completo)\n"
            "• `delete_repo`\n"
            "• `gist`\n"
            "• `user`\n\n"
            "**Nota:** El token se guarda en memoria durante esta sesión",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    new_token = args[1].strip()
    
    # Actualizar el manager con nuevo token
    global github_manager
    github_manager = GitHubManager(new_token)
    
    # Testear la conexión
    success, msg = await github_manager.test_connection()
    
    if success:
        # También actualizar la variable global (para esta sesión)
        global GITHUB_TOKEN
        GITHUB_TOKEN = new_token
        
        await message.reply_text(
            f"✅ **Token actualizado correctamente**\n\n{msg}\n\n"
            f"**Nota:** Este cambio es temporal. Para hacerlo permanente, "
            f"actualiza la variable `GITHUB_TOKEN` en tu archivo `.env` o configuración.",
            parse_mode=enums.ParseMode.MARKDOWN
        )
    else:
        await message.reply_text(f"❌ **Token inválido**\n\n{msg}", parse_mode=enums.ParseMode.MARKDOWN)

# ==============================================
# HANDLERS DE CALLBACK PARA GITHUB
# ==============================================

@app.on_callback_query(filters.regex(r"^github_"))
async def handle_github_callbacks(client: Client, callback_query: CallbackQuery):
    """Manejador de callbacks de GitHub"""
    data = callback_query.data
    user_id = callback_query.from_user.id
    message = callback_query.message
    
    if user_id != ADMIN_ID:
        await callback_query.answer("❌ Acceso exclusivo del administrador", show_alert=True)
        return
    
    try:
        if data == "github":
            await github_command(client, message)
            
        elif data == "github_list_repos":
            await list_github_repos_command(client, message)
            
        elif data.startswith("gh_repos_"):
            page = int(data.split("_")[2])
            await list_github_repos_command(client, message)
            # Nota: Necesitaríamos modificar la función para aceptar parámetro de página
            
        elif data.startswith("gh_repo_info_"):
            parts = data.split("_")
            owner = parts[3]
            repo_name = parts[4]
            
            repo_info = await github_manager.get_repo_info(owner, repo_name)
            
            if 'error' in repo_info:
                text = f"❌ Error: {repo_info['error']}"
            else:
                text = f"📦 **{repo_info['full_name']}**\n\n"
                text += f"📝 **Descripción:** {repo_info['description'] or 'Sin descripción'}\n"
                text += f"🌐 **Visibilidad:** {'🔒 Privado' if repo_info['private'] else '🌐 Público'}\n"
                text += f"⭐ **Estrellas:** {repo_info['stargazers_count']}\n"
                text += f"🍴 **Forks:** {repo_info['forks_count']}\n"
                text += f"👁️ **Watchers:** {repo_info['watchers_count']}\n"
                text += f"📊 **Tamaño:** {repo_info['size']} KB\n"
                text += f"💻 **Lenguaje:** {repo_info['language'] or 'N/A'}\n"
                text += f"📅 **Creado:** {repo_info['created_at'][:10]}\n"
                text += f"🔄 **Actualizado:** {repo_info['updated_at'][:10]}\n"
                text += f"🔗 **URL:** {repo_info['html_url']}\n"
                text += f"🌿 **Rama por defecto:** {repo_info['default_branch']}\n\n"
                
                if repo_info['license']:
                    text += f"📄 **Licencia:** {repo_info['license']['name']}\n"
                
                text += f"🏠 **Página:** {repo_info['homepage'] or 'N/A'}\n"
                text += f"⚠️ **Issues abiertos:** {repo_info['open_issues_count']}"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📂 Listar archivos", callback_data=f"gh_list_files_{owner}_{repo_name}"),
                 InlineKeyboardButton("🌿 Ver ramas", callback_data=f"gh_list_branches_{owner}_{repo_name}")],
                [InlineKeyboardButton("📝 Crear archivo", callback_data=f"gh_create_file_{owner}_{repo_name}"),
                 InlineKeyboardButton("⚠️ Crear issue", callback_data=f"gh_create_issue_{owner}_{repo_name}")],
                [InlineKeyboardButton("🗑️ Eliminar repo", callback_data=f"gh_confirm_delete_{owner}_{repo_name}"),
                 InlineKeyboardButton("🔙 Volver", callback_data="github_list_repos")]
            ])
            
            await message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
            
        elif data == "github_create_repo":
            await message.edit_text(
                "➕ **Crear Nuevo Repositorio**\n\n"
                "Envía el nombre del nuevo repositorio:\n\n"
                "**Ejemplos:**\n"
                "`mi-proyecto`\n"
                "`api-rest`\n"
                "`blog-personal`\n\n"
                "Luego podrás añadir descripción y configurar opciones.",
                parse_mode=enums.ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                ])
            )
            # Aquí deberías implementar un estado para capturar el nombre
            
        elif data == "github_fork_repo":
            await message.edit_text(
                "🍴 **Hacer Fork de Repositorio**\n\n"
                "Envía el repositorio en formato `owner/repo`:\n\n"
                "**Ejemplos:**\n"
                "`octocat/Spoon-Knife`\n"
                "`microsoft/vscode`\n"
                "`facebook/react`\n\n"
                "El fork se creará en tu cuenta.",
                parse_mode=enums.ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                ])
            )
            
        elif data == "github_delete_repo":
            await message.edit_text(
                "🗑️ **Eliminar Repositorio**\n\n"
                "Envía el repositorio en formato `owner/repo`:\n\n"
                "**Ejemplos:**\n"
                "`tuusuario/repo-viejo`\n"
                "`mi-org/proyecto-test`\n\n"
                "⚠️ **ADVERTENCIA:** Esta acción es irreversible.",
                parse_mode=enums.ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                ])
            )
            
        elif data.startswith("gh_confirm_delete_"):
            parts = data.split("_")
            owner = parts[3]
            repo_name = parts[4]
            
            processing_msg = await message.reply_text(f"🗑️ Eliminando `{owner}/{repo_name}`...")
            
            success, result = await github_manager.delete_repo(owner, repo_name)
            
            await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)
            
            # Volver a la lista de repos
            await list_github_repos_command(client, message)
            
        elif data == "github_create_file":
            await message.edit_text(
                "📝 **Crear Archivo en Repositorio**\n\n"
                "Envía los datos en este formato:\n\n"
                "`owner/repo ruta/archivo.ext \"contenido\"`\n\n"
                "**Ejemplo:**\n"
                "`tuusuario/mi-repo README.md \"# Mi Proyecto\\n\\nDescripción aquí\"`",
                parse_mode=enums.ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                ])
            )
            
        elif data == "github_branches":
            await message.edit_text(
                "🌿 **Gestionar Ramas**\n\n"
                "Envía el repositorio en formato `owner/repo`:\n\n"
                "**Ejemplos:**\n"
                "`tuusuario/mi-repo`\n"
                "`org/proyecto`\n\n"
                "Podrás ver y crear nuevas ramas.",
                parse_mode=enums.ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                ])
            )
            
        elif data.startswith("gh_list_branches_"):
            parts = data.split("_")
            owner = parts[3]
            repo_name = parts[4]
            
            branches = await github_manager.list_branches(owner, repo_name)
            
            if not branches:
                text = f"🌿 **Ramas de {owner}/{repo_name}**\n\n📭 No hay ramas disponibles"
            else:
                text = f"🌿 **Ramas de {owner}/{repo_name}**\n\n"
                for i, branch in enumerate(branches, 1):
                    text += f"**{i}. {branch}**\n"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Nueva rama", callback_data=f"gh_create_branch_{owner}_{repo_name}"),
                 InlineKeyboardButton("🔙 Repositorio", callback_data=f"gh_repo_info_{owner}_{repo_name}")]
            ])
            
            await message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
            
        elif data.startswith("gh_create_branch_"):
            parts = data.split("_")
            owner = parts[3]
            repo_name = parts[4]
            
            await message.edit_text(
                f"🌿 **Crear Nueva Rama en {owner}/{repo_name}**\n\n"
                "Envía el nombre de la nueva rama:\n\n"
                "**Ejemplos:**\n"
                "`feature/login`\n"
                "`bugfix/issue-42`\n"
                "`release/v2.0`\n\n"
                "Se creará desde la rama `main` por defecto.",
                parse_mode=enums.ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Ramas", callback_data=f"gh_list_branches_{owner}_{repo_name}")]
                ])
            )
            
        elif data == "github_create_issue":
            await message.edit_text(
                "⚠️ **Crear Issue**\n\n"
                "Envía los datos en este formato:\n\n"
                "`owner/repo \"Título del issue\" \"Descripción detallada\"`\n\n"
                "**Ejemplo:**\n"
                "`tuusuario/repo \"Bug en login\" \"El botón de login no funciona en móviles\"`",
                parse_mode=enums.ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                ])
            )
            
        elif data == "github_create_gist":
            await message.edit_text(
                "💾 **Crear Gist**\n\n"
                "Envía los datos en este formato:\n\n"
                "`\"Descripción del gist\" \"contenido del archivo\"`\n\n"
                "**Ejemplo:**\n"
                "`\"Configuración API\" \"API_KEY=abc123\\nDEBUG=True\"`",
                parse_mode=enums.ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Cancelar", callback_data="github")]
                ])
            )
            
        elif data == "github_list_orgs":
            orgs = await github_manager.list_orgs()
            
            if not orgs:
                text = "🏢 **Tus Organizaciones**\n\n📭 No perteneces a ninguna organización"
            else:
                text = "🏢 **Tus Organizaciones**\n\n"
                for org in orgs:
                    text += f"• **{org['login']}** - {org['description'] or 'Sin descripción'}\n"
                    text += f"  👥 {org['members_url'].split('{')[0]}\n\n"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 GitHub", callback_data="github")]
            ])
            
            await message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
            
        elif data == "github_test":
            success, msg = await github_manager.test_connection()
            
            await callback_query.answer(msg, show_alert=True)
            
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error en callback GitHub: {e}")
        await callback_query.answer(f"❌ Error: {str(e)[:50]}", show_alert=True)

# ==============================================
# MANEJADOR DE MENSAJES PARA ESTADOS GITHUB
# ==============================================

# Estados para operaciones de GitHub
github_states = {}

@app.on_message(filters.private & filters.text & ~filters.command())
async def handle_github_states(client: Client, message: Message):
    """Manejar estados para operaciones de GitHub"""
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        return
    
    text = message.text.strip()
    
    # Verificar si estamos en un estado de GitHub
    if user_id in github_states:
        state = github_states[user_id]
        operation = state.get("operation")
        
        try:
            if operation == "create_repo_name":
                # Guardar nombre y pedir descripción
                github_states[user_id] = {
                    "operation": "create_repo_desc",
                    "name": text
                }
                
                await message.reply_text(
                    f"📝 **Nombre guardado:** `{text}`\n\n"
                    "Ahora envía la descripción (opcional):\n\n"
                    "**Ejemplos:**\n"
                    "`Un proyecto para gestionar tareas`\n"
                    "`API REST en FastAPI`\n\n"
                    "O envía `skip` para saltar.",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                
            elif operation == "create_repo_desc":
                name = state["name"]
                description = text if text.lower() != "skip" else ""
                
                # Preguntar visibilidad
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🌐 Público", callback_data=f"gh_repo_vis_public_{name}_{description}"),
                     InlineKeyboardButton("🔒 Privado", callback_data=f"gh_repo_vis_private_{name}_{description}")]
                ])
                
                await message.reply_text(
                    f"🛠️ **Configurar Repositorio**\n\n"
                    f"**Nombre:** `{name}`\n"
                    f"**Descripción:** `{description or 'Sin descripción'}`\n\n"
                    f"Selecciona la visibilidad:",
                    reply_markup=keyboard,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                
                del github_states[user_id]
                
            elif operation == "fork_repo":
                if '/' not in text:
                    await message.reply_text("❌ Formato incorrecto. Usa: `owner/repo`")
                    return
                
                owner, repo_name = text.split('/', 1)
                
                processing_msg = await message.reply_text(f"🍴 Haciendo fork de `{owner}/{repo_name}`...")
                
                success, result = await github_manager.fork_repo(owner, repo_name)
                
                await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)
                
                del github_states[user_id]
                
            elif operation == "delete_repo":
                if '/' not in text:
                    await message.reply_text("❌ Formato incorrecto. Usa: `owner/repo`")
                    return
                
                owner, repo_name = text.split('/', 1)
                
                # Pedir confirmación
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Sí, eliminar", callback_data=f"gh_confirm_delete_{owner}_{repo_name}"),
                     InlineKeyboardButton("❌ Cancelar", callback_data="github")]
                ])
                
                await message.reply_text(
                    f"⚠️ **Confirmar eliminación**\n\n"
                    f"¿Eliminar el repositorio **{owner}/{repo_name}**?\n\n"
                    f"**Esta acción es IRREVERSIBLE.**",
                    reply_markup=keyboard,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                
                del github_states[user_id]
                
        except Exception as e:
            logger.error(f"Error procesando estado GitHub: {e}")
            await message.reply_text(f"❌ Error: {str(e)}")
            if user_id in github_states:
                del github_states[user_id]

# ==============================================
# CALLBACKS ADICIONALES PARA CREACIÓN DE REPO
# ==============================================

@app.on_callback_query(filters.regex(r"^gh_repo_vis_"))
async def handle_repo_visibility(client: Client, callback_query: CallbackQuery):
    """Manejador para visibilidad de repositorio"""
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if user_id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    try:
        parts = data.split("_")
        visibility = parts[3]  # public or private
        name = parts[4]
        description = "_".join(parts[5:])  # Recuperar descripción
        
        # Reemplazar marcadores de espacio
        description = description.replace("_", " ")
        
        processing_msg = await callback_query.message.reply_text(
            f"🛠️ Creando repositorio `{name}` ({'🌐 Público' if visibility == 'public' else '🔒 Privado'})..."
        )
        
        success, result = await github_manager.create_repo(
            name, 
            description, 
            private=(visibility == "private")
        )
        
        await processing_msg.edit_text(result, parse_mode=enums.ParseMode.MARKDOWN)
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error creando repo desde callback: {e}")
        await callback_query.answer(f"❌ Error: {str(e)[:50]}", show_alert=True)

# ==============================================
# ACTUALIZAR EL HANDLER DE CALLBACKS PRINCIPAL
# ==============================================

# Reemplazar la función handle_all_callbacks existente para incluir GitHub
# (El código original tiene muchos callbacks, así que solo mostramos cómo integrar)

# En tu función handle_all_callbacks existente, AÑADE esto al inicio:

"""
if data.startswith("github_") or data.startswith("gh_"):
    await handle_github_callbacks(client, callback_query)
    return
"""

# ==============================================
# ACTUALIZAR EL COMANDO /start PARA INCLUIR GITHUB
# ==============================================

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user = message.from_user

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Buscar repos", callback_data="search"),
         InlineKeyboardButton("📚 Ayuda", callback_data="help")],
        [InlineKeyboardButton("📥 Descargar", callback_data="download_menu"),
         InlineKeyboardButton("🚀 GitHub Manager", callback_data="github")],
        [InlineKeyboardButton("🌐 GitHub API", url="https://docs.github.com/rest")]
    ])

    await message.reply_text(
        f"👋 ¡Hola {user.first_name}!\n\n"
        "🤖 **GitHub Manager Bot**\n\n"
        "📥 **Puedo descargar repositorios de GitHub**\n"
        "🚀 **Y gestionar TU cuenta de GitHub**\n\n"
        "🔍 **Características:**\n"
        "• Sistema de búsqueda de repositorios\n"
        "• Descarga de repos completos\n"
        "• 🆕 Gestión COMPLETA de tu cuenta GitHub\n"
        "• Crear/eliminar repositorios\n"
        "• Hacer forks y crear archivos\n"
        "• Gestionar issues y ramas\n"
        "• Interfaz intuitiva con botones\n\n"
        "**Comandos principales:**\n"
        "`/search <término>` - Buscar repositorios\n"
        "`/download <url>` - Descargar repositorio\n"
        "`/github` - Panel de gestión GitHub 🆕\n"
        "`/help` - Mostrar ayuda completa\n\n"
        "¡Prueba el nuevo panel GitHub Manager!",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

# ==============================================
# ACTUALIZAR EL COMANDO /help PARA INCLUIR GITHUB
# ==============================================

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    help_text = """
🤖 **GitHub Manager Bot - Ayuda**

📥 **¿Qué puedo hacer?**
• 🔍 **Buscar repositorios** en GitHub
• 📥 Descargar repositorios completos
• 🚀 **Gestionar TU cuenta de GitHub** 🆕
• 📁 Enviarlos como archivo ZIP
• 🌿 Soporte para ramas específicas
• 📊 Información detallada del repositorio

🆕 **GESTIÓN GITHUB (Solo Admin):**
`/github` - Panel de control completo
`/ghrepos` - Listar tus repositorios
`/ghcreate <nombre>` - Crear nuevo repo
`/ghfork <owner/repo>` - Hacer fork
`/ghdelete <owner/repo>` - Eliminar repo
`/ghfile <owner/repo> <ruta> <contenido>` - Crear archivo
`/ghissue <owner/repo> <título> <desc>` - Crear issue
`/ghgist <desc> <contenido>` - Crear gist
`/ghtoken <token>` - Configurar token

🛠️ **Comandos normales:**
`/start` - Iniciar el bot
`/search <término>` - Buscar repositorios
`/download <url>` - Descargar repositorio
`/help` - Mostrar esta ayuda
`/example` - Ver ejemplos de uso
`/info` - Información del bot

🔍 **Sistema de búsqueda:**
• Busca en todos los repos públicos de GitHub
• Ordena por popularidad (estrellas)
• Muestra descripción, lenguaje y estadísticas
• Navegación por páginas

⚠️ **Limitaciones:**
• Máximo 50MB por archivo (límite de Telegram)
• Solo repositorios públicos para búsqueda
• Límites de API de GitHub
"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 GitHub Manager", callback_data="github"),
         InlineKeyboardButton("🔍 Probar búsqueda", callback_data="search_example")],
        [InlineKeyboardButton("📥 Ejemplo rápido", callback_data="quick_download"),
         InlineKeyboardButton("🌐 GitHub API", url="https://docs.github.com/rest")]
    ])

    await message.reply_text(help_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

# ==============================================
# FUNCIÓN MAIN ACTUALIZADA
# ==============================================

async def main():
    try:
        logger.info("🚀 Iniciando GitHub Manager Bot...")
        
        # Crear directorios necesarios
        os.makedirs(TEMP_DIR, exist_ok=True)
        
        # Configurar mimetypes
        mimetypes.init()
        
        # Testear conexión a GitHub si hay token
        if GITHUB_TOKEN and GITHUB_TOKEN != "tu_token_de_github_aquí":
            success, msg = await github_manager.test_connection()
            logger.info(f"GitHub: {msg}")
        else:
            logger.warning("⚠️ GITHUB_TOKEN no configurado. Funciones de gestión deshabilitadas.")
        
        # Iniciar el bot
        await app.start()
        
        # Obtener información del bot
        me = await app.get_me()
        logger.info(f"✅ Bot iniciado como: @{me.username}")
        logger.info(f"✅ ID del bot: {me.id}")
        logger.info(f"✅ Administrador EXCLUSIVO: {ADMIN_ID}")
        
        # Mantener el bot en ejecución
        logger.info("✅ Bot en ejecución. Presiona Ctrl+C para detener.")
        await asyncio.Event().wait()
        
    except KeyboardInterrupt:
        logger.info("🛑 Bot detenido por el usuario")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await app.stop()
        logger.info("👋 Bot detenido")

if __name__ == "__main__":
    # Instalar dependencias si faltan
    try:
        import psutil
    except ImportError:
        logger.warning("⚠️ Instalando psutil...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "psutil"])
        import psutil
    
    try:
        import humanize
    except ImportError:
        logger.warning("⚠️ Instalando humanize...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "humanize"])
        import humanize
    
    # Ejecutar el bot
    app.run()
