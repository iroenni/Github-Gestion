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

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==============================================
# ⚠️⚠️⚠️ CONFIGURACIÓN PRINCIPAL ⚠️⚠️⚠️
# ==============================================

# Configuración del bot (USA VARIABLES DE ENTORNO)
API_ID = os.getenv("API_ID") or 14681595
API_HASH = os.getenv("API_HASH") or "a86730aab5c59953c424abb4396d32d5"
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8534765454:AAFjZZbb35rjS594M2kF0NdFQpR5PbQX8qI"
# ⚠️ AÑADE TU TOKEN DE GITHUB AQUÍ ⚠️
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or "tu_token_de_github_aquí"

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
