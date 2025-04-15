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
    total=3,
    backoff_factor=1,
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
        })
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
        })
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
# 📋 Componentes de UI
# ================================
class GameSelect(Select):
    def __init__(self, jogos):
        super().__init__(
            placeholder="Seleciona um jogo...",
            options=[discord.SelectOption(label=j['name'][:100], value=str(i), description=j['price'][:100]) for i, j in enumerate(jogos)]
        )
        self.jogos = jogos

    async def callback(self, interaction):
        jogo = self.jogos[int(self.values[0])]
        embed = discord.Embed(title=jogo['name'], url=jogo['url'], color=0x1b2838)
        embed.add_field(name="💰 Preço", value=jogo['price'], inline=True)
        embed.add_field(name="AppID", value=jogo['appid'], inline=True)
        embed.set_thumbnail(url=jogo['image'])
        embed.set_footer(text="Steam Search • Resultado selecionado")
        await interaction.response.edit_message(embed=embed, view=None)

class FileSelect(GameSelect):
    async def callback(self, interaction):
        jogo = self.jogos[int(self.values[0])]
        await send_drive_link_for_game(interaction, jogo)

class PedirButton(Button):
    def __init__(self, nome_jogo: str, appid: int):
        super().__init__(
            label="Pedir Jogo",
            style=discord.ButtonStyle.green,
            emoji="📨"
        )
        self.nome_jogo = nome_jogo
        self.appid = appid

    async def callback(self, interaction: discord.Interaction):
        try:
            target_user = await interaction.client.fetch_user(int(DISCORD_USER_ID))

            if target_user:
                embed = discord.Embed(
                    title="📨 NOVO PEDIDO DE JOGO",
                    description=f"**Jogo:** {self.nome_jogo}\n**AppID:** {self.appid}",
                    color=0x00ff00
                )
                embed.add_field(
                    name="👤 Usuário Solicitante", 
                    value=f"{interaction.user.mention} ({interaction.user.id})",
                    inline=False
                )
                embed.add_field(
                    name="📅 Data", 
                    value=discord.utils.format_dt(discord.utils.utcnow(), "F"),
                    inline=False
                )

                await target_user.send(embed=embed)

                await interaction.response.send_message(
                    "✅ Seu pedido foi enviado diretamente ao Linho!",
                    ephemeral=True
                )

                embed = discord.Embed(
                    title="✅ Pedido enviado",
                    description=f"Seu pedido para {self.nome_jogo} foi enviado ao Linho!",
                    color=0x00ff00
                )
                await interaction.message.edit(embed=embed, view=None)
            else:
                await interaction.response.send_message(
                    "❌ Não foi possível encontrar o Linho. Por favor, reporte este erro.",
                    ephemeral=True
                )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ O bot não tem permissão para enviar mensagens ao Linho.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "❌ Ocorreu um erro ao enviar seu pedido. Tente novamente mais tarde.",
                ephemeral=True
            )
            print(f"Erro ao enviar pedido: {e}")

# ================================
# 📁 Google Drive
# ================================
async def send_drive_link_for_game(interaction, jogo):
    try:
        # Consulta à API do Google Drive para encontrar o ficheiro correspondente
        query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and fullText contains '{jogo['appid']}' and mimeType != 'application/vnd.google-apps.folder'"
        url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&key={GOOGLE_API_KEY}&fields=files(id,name,description)"
        response = session.get(url)
        files = response.json().get("files", [])

        # Preparar a mensagem que será enviada
        if files:
            # Recuperar o ficheiro encontrado
            f = files[0]
            link = f"https://drive.google.com/file/d/{f['id']}/view"
            nome_sem_extensao = os.path.splitext(f['name'])[0]
            mensagem = f"{emoji_str} [{nome_sem_extensao}]({link})"  # Link do arquivo

            # Criar o embed para a mensagem
            embed = discord.Embed(
                title=f"Link para o jogo {jogo['name']}",
                description=mensagem,
                color=0x1b2838  # Cor do embed
            )
            embed.set_footer(text="Google Drive • Ficheiro Encontrado")

            # Se a resposta original não tiver sido já enviada, envia a mensagem com embed
            if interaction.response.is_done():
                await interaction.followup.send(content=mensagem, embed=embed, suppress_embeds=True)
            else:
                await interaction.response.send_message(content=mensagem, embed=embed, suppress_embeds=True)

        else:
            # Se não encontrar o ficheiro, envia uma mensagem com embed dizendo que não encontrou
            view = View()
            view.add_item(PedirButton(jogo['name'], jogo['appid']))
            embed = discord.Embed(
                title="❌ Ficheiro não encontrado",
                description=f"Não encontrei o jogo {jogo['name']} na Drive.\nDesejas pedir que seja adicionado?",
                color=0xff0000
            )
            embed.set_footer(text="Clique no botão abaixo para fazer o pedido")

            # Enviar tudo numa única mensagem
            if interaction.response.is_done():
                await interaction.followup.send(content=mensagem, embed=embed, view=view, suppress_embeds=True)
            else:
                await interaction.response.send_message(content=mensagem, embed=embed, view=view, suppress_embeds=True)

    except Exception as e:
        # Caso ocorra um erro ao tentar procurar ou enviar a mensagem
        erro_msg = f"❌ Erro: {e}"
        try:
            # Enviar uma mensagem de erro visível para todos
            if interaction.response.is_done():
                await interaction.followup.send(content=erro_msg)
            else:
                await interaction.response.send_message(content=erro_msg)
        except Exception as e2:
            print(f"[ERRO FATAL] A enviar mensagem de erro: {e2}")

# ================================
# 🔧 Utilitários
# ================================
def dividir_mensagem(msg, limite=1900):
    linhas = msg.split('\n')
    partes, atual = [], ""
    for linha in linhas:
        if len(atual + linha + '\n') > limite:
            partes.append(atual)
            atual = ""
        atual += linha + '\n'
    if atual:
        partes.append(atual)
    return partes

# ================================
# 🧠 Comandos
# ================================
@client.tree.command(name="steam", description="Pesquisa jogos na Steam")
@app_commands.describe(query="Nome do jogo", max_results="Resultados (1-5)")
async def steam(interaction, query: str, max_results: int = 3):
    await interaction.response.defer()
    max_results = max(1, min(5, max_results))
    resultados = await search_steam_games(query, max_results)
    if not resultados:
        await interaction.followup.send("❌ Nenhum jogo encontrado.")
        return

    if len(resultados) == 1:
        jogo = resultados[0]
        embed = discord.Embed(title=jogo['name'], url=jogo['url'], color=0x1b2838)
        embed.add_field(name="💰 Preço", value=jogo['price'], inline=True)
        embed.add_field(name="AppID", value=jogo['appid'], inline=True)
        embed.set_thumbnail(url=jogo['image'])
        embed.set_footer(text="Steam Search • Resultado único")
        await interaction.followup.send(embed=embed)
    else:
        view = View()
        view.add_item(GameSelect(resultados))
        embed = discord.Embed(title=f"🔍 Resultados para: {query}", description="Seleciona um jogo abaixo", color=0x1b2838)
        embed.set_footer(text="Steam Search • Selecione uma opção")
        await interaction.followup.send(embed=embed, view=view)

@client.tree.command(name="search", description="Pesquisa um jogo e mostra ficheiro do Google Drive")
@app_commands.describe(query="Nome do jogo", max_results="Resultados (1-10)")
async def search(interaction: discord.Interaction, query: str, max_results: int = 5):
    await interaction.response.defer()
    max_results = max(1, min(10, max_results))
    resultados = await search_steam_games(query, max_results)
    if not resultados:
        await interaction.followup.send("❌ Nenhum jogo encontrado.")
        return

    if len(resultados) == 1:
        jogo = resultados[0]
        try:
            # Consulta à API do Google Drive para encontrar o ficheiro correspondente
            query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and fullText contains '{jogo['appid']}' and mimeType != 'application/vnd.google-apps.folder'"
            url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&key={GOOGLE_API_KEY}&fields=files(id,name,description)"
            response = session.get(url)
            files = response.json().get("files", [])

            if files:
                # Recuperar o ficheiro encontrado
                f = files[0]
                link = f"https://drive.google.com/file/d/{f['id']}/view"
                nome_sem_extensao = os.path.splitext(f['name'])[0]
                
                # Criar embed com todas as informações
                embed = discord.Embed(
                    title=f"🔍 {jogo['name']}",
                    color=0x1b2838
                )
                embed.add_field(name="💰 Preço Steam", value=jogo['price'], inline=True)
                embed.add_field(name="🆔 AppID", value=jogo['appid'], inline=True)
                embed.add_field(name="📁 Ficheiro Google Drive", value=f"[{nome_sem_extensao}]({link})", inline=False)
                embed.set_thumbnail(url=jogo['image'])
                embed.set_footer(text="Resultado da pesquisa")
                
                await interaction.followup.send(embed=embed)
            else:
                view = View()
                view.add_item(PedirButton(jogo['name'], jogo['appid']))
                embed = discord.Embed(
                    title=f"🔍 {jogo['name']}",
                    description=f"Não encontrei o jogo na Drive.\nDesejas pedir que seja adicionado?",
                    color=0xff0000
                )
                embed.add_field(name="💰 Preço Steam", value=jogo['price'], inline=True)
                embed.add_field(name="🆔 AppID", value=jogo['appid'], inline=True)
                embed.set_thumbnail(url=jogo['image'])
                embed.set_footer(text="Clique no botão abaixo para fazer o pedido")
                
                await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            await interaction.followup.send(f"❌ Erro ao pesquisar: {e}")
    else:
        view = View()
        view.add_item(FileSelect(resultados))
        embed = discord.Embed(
            title=f"📁 Resultados para: {query}",
            description="Seleciona um jogo para ver o link do Google Drive",
            color=0x1b2838
        )
        for i, jogo in enumerate(resultados):
            embed.add_field(
                name=f"{i+1}. {jogo['name']}",
                value=f"💰 {jogo['price']} | 🆔 {jogo['appid']}",
                inline=False
            )
        embed.set_footer(text="Google Drive • Selecione uma opção")
        await interaction.followup.send(embed=embed, view=view)

@client.tree.command(name="list", description="Lista os ficheiros da pasta Google Drive")
async def list_files(interaction: discord.Interaction):
    url = f"https://www.googleapis.com/drive/v3/files?q=\"{GOOGLE_DRIVE_FOLDER_ID}\" in parents and mimeType != 'application/vnd.google-apps.folder'&key={GOOGLE_API_KEY}&fields=files(id,name,description)"

    try:
        response = session.get(url)
        files = response.json().get("files", [])

        if not files:
            await interaction.response.send_message("❌ Não foram encontrados ficheiros na pasta.", ephemeral=True, delete_after=10)
            return

        mensagem = "**Ficheiros encontrados:**\n"
        for f in files:
            link = f"https://drive.google.com/file/d/{f['id']}/view"
            nome_sem_extensao = os.path.splitext(f['name'])[0]
            mensagem += f"{emoji_str} [{nome_sem_extensao}]({link})\n"

        await interaction.response.send_message("A carregar lista...", ephemeral=True, delete_after=0.1)

        partes = dividir_mensagem(mensagem)
        for parte in partes:
            await interaction.channel.send(parte, suppress_embeds=True)

    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao obter os ficheiros: {e}", ephemeral=True, delete_after=10)

@client.tree.command(name="cmds", description="Mostra todos os comandos disponíveis do bot")
async def cmds(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 Comandos disponíveis",
        description="Aqui estão os comandos que podes usar:",
        color=0x5865F2
    )

    embed.add_field(name="/steam", value="🔍 Pesquisa jogos na Steam", inline=False)
    embed.add_field(name="/search", value="📁 Pesquisa jogo e mostra ficheiro do Google Drive", inline=False)
    embed.add_field(name="/list", value="🗂️ Lista todos os ficheiros disponíveis no Google Drive", inline=False)
    embed.add_field(name="/cmds", value="📜 Mostra esta lista de comandos", inline=False)

    embed.set_footer(text="Bot de Utilidades Steam + Google Drive")
    await interaction.response.send_message(embed=embed)

# ================================
# ▶️ Executar bot
# ================================
if __name__ == "__main__":
    client.run(TOKEN)