# ================================
# 🔐 Variáveis de ambiente
# ================================
import os
from dotenv import load_dotenv

load_dotenv()

required_env_vars = ["TOKEN", "STEAM_API_KEY", "GOOGLE_API_KEY", "GOOGLE_DRIVE_FOLDER_ID", "DISCORD_USER_ID"]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]

if missing_vars:
    raise EnvironmentError(f"Variáveis de ambiente ausentes: {', '.join(missing_vars)}")

TOKEN = os.getenv("TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
DISCORD_USER_ID = os.getenv("DISCORD_USER_ID")
emoji_str = "<:GDrive:1360019114848026684>"

# ================================
# 📦 Imports
# ================================
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import discord
from discord import app_commands
from discord.ui import Select, View, Button
from concurrent.futures import ThreadPoolExecutor
import time

# ================================
# 🌐 Sessão HTTP
# ================================
session = requests.Session()
retry = Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=[500, 502, 503, 504]
)
adapter = HTTPAdapter(max_retries=retry)
session.mount("http://", adapter)
session.mount("https://", adapter)

# ================================
# 🤖 Cliente Discord
# ================================
class MyClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.start_time = time.time()

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Comandos sincronizados")

    async def on_ready(self):
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="/cmds para mais info"
        ))
        print(f'✅ Bot conectado como {self.user}')

client = MyClient()

# ================================
# 🔍 Funções de pesquisa
# ================================
def is_dlc(appid):
    try:
        response = session.get("https://store.steampowered.com/api/appdetails", params={
            'appids': appid,
            'l': 'portuguese'
        }, timeout=10)
        data = response.json().get(str(appid), {})
        if data.get('success'):
            app_data = data.get('data', {})
            if app_data.get('type') == 'dlc' or any(cat.get('description') == 'DLC' for cat in app_data.get('categories', [])):
                return True
        return False
    except Exception as e:
        print(f"Erro ao verificar DLC {appid}: {e}")
        return False

async def search_steam_games(query, max_results=5):
    try:
        response = session.get("https://store.steampowered.com/api/storesearch", params={
            'term': query,
            'l': 'portuguese',
            'cc': 'pt',
            'key': STEAM_API_KEY
        }, timeout=10)
        response.raise_for_status()
        data = response.json()

        preliminares = [item for item in data.get('items', []) if all(k not in item['name'].lower() for k in ['dlc', 'pack', 'expansion', 'content'])][:10]

        resultados = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            for item in preliminares:
                if not is_dlc(item['id']):
                    preco = "Gratuito"
                    if item.get('price'):
                        preco = f"{item['price']['final'] / 100:.2f}€"
                        if item['price'].get('discount_percent', 0) > 0:
                            preco += f" (🔥 -{item['price']['discount_percent']}%)"
                    resultados.append({
                        'name': item['name'],
                        'appid': item['id'],
                        'price': preco,
                        'url': f"https://store.steampowered.com/app/{item['id']}",
                        'image': item['tiny_image']
                    })
                    if len(resultados) >= max_results:
                        break
        return resultados
    except Exception as e:
        print(f"Erro na pesquisa Steam: {e}")
        return None

# ================================
# 📁 Google Drive
# ================================
async def send_drive_link_for_game(interaction, jogo):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True)

        query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and fullText contains '{jogo['appid']}' and mimeType != 'application/vnd.google-apps.folder'"
        url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&key={GOOGLE_API_KEY}&fields=files(id,name,description)"

        response = session.get(url, timeout=10)
        if not response.ok:
            print(f"Erro HTTP {response.status_code}: {response.text}")
        response.raise_for_status()

        files = response.json().get("files", [])

        if files:
            f = files[0]
            link = f"https://drive.google.com/file/d/{f['id']}/view"
            nome_sem_extensao = os.path.splitext(f['name'])[0]
            mensagem = f"{emoji_str} [{nome_sem_extensao}]({link})"
            await interaction.followup.send(content=mensagem, embed=None, view=None, suppress_embeds=True)
        else:
            view = View()
            view.add_item(PedirButton(jogo['name'], jogo['appid']))

            embed = discord.Embed(
                title="❌ Ficheiro não encontrado",
                description=f"Não encontrei o jogo `{jogo['name']}` na Drive.\nDeseja pedir que seja adicionado?",
                color=0xff0000
            )
            embed.set_footer(text="Clique no botão abaixo para fazer o pedido")

            await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        print(f"Erro em send_drive_link_for_game: {e}")
        await interaction.followup.send(content=f"❌ Erro: {e}", embed=None, view=None)

# ================================
# 🎮 Dropdown de jogos
# ================================
class GameSelect(Select):
    def __init__(self, jogos):
        options = [discord.SelectOption(label=jogo['name'], description=jogo['price'], value=str(i)) for i, jogo in enumerate(jogos)]
        super().__init__(placeholder="Escolhe um jogo", min_values=1, max_values=1, options=options)
        self.jogos = jogos

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        jogo_selecionado = self.jogos[index]
        await send_drive_link_for_game(interaction, jogo_selecionado)

class GameSelectView(View):
    def __init__(self, jogos):
        super().__init__(timeout=60)
        self.add_item(GameSelect(jogos))

# ================================
# 📤 Botão de pedido
# ================================
class PedirButton(Button):
    def __init__(self, nome, appid):
        super().__init__(label="Pedir jogo", style=discord.ButtonStyle.blurple)
        self.nome = nome
        self.appid = appid

    async def callback(self, interaction: discord.Interaction):
        user = await client.fetch_user(int(DISCORD_USER_ID))
        await user.send(f"📥 Pedido: `{self.nome}` (AppID: `{self.appid}`)")
        await interaction.response.edit_message(content="📨 Pedido enviado!", embed=None, view=None)

# ================================
# ⌨️ Comandos
# ================================
@client.tree.command(name="jogo", description="Procura um jogo e tenta encontrar o ficheiro no Google Drive.")
@app_commands.describe(nome="Nome do jogo que queres procurar")
async def jogo_command(interaction: discord.Interaction, nome: str):
    await interaction.response.defer(thinking=True)
    jogos = await search_steam_games(nome)

    if not jogos:
        await interaction.followup.send("❌ Não encontrei jogos com esse nome.")
        return

    view = GameSelectView(jogos)
    await interaction.followup.send("🎮 Seleciona um jogo:", view=view)

@client.tree.command(name="cmds", description="Mostra os comandos disponíveis.")
async def cmds_command(interaction: discord.Interaction):
    comandos = (
        "**Comandos disponíveis:**\n"
        "`/jogo <nome>` - Pesquisa um jogo e tenta encontrar na Drive\n"
        "`/cmds` - Mostra esta lista de comandos"
    )
    await interaction.response.send_message(comandos)

# ================================
# 🚀 Iniciar o bot
# ================================
client.run(TOKEN)
