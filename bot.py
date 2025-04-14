import discord
from discord import app_commands
from discord.ui import View, Select
from dotenv import load_dotenv
import os
import requests

# ================================
# 🔐 Variáveis de ambiente
# ================================
load_dotenv()

TOKEN = os.getenv("TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
DISCORD_USER_ID = os.getenv("DISCORD_USER_ID")  # ID do utilizador para pedidos

# ================================
# 📦 Imports
# ================================
import discord
from discord import app_commands

# ================================
# 🤖 Cliente Discord
# ================================
class MyClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Comandos sincronizados")

    async def on_ready(self):
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="comandos /steam, /ficheiro e /list"
        ))
        print(f'✅ Bot conectado como {self.user}')


client = MyClient()

# ================================
# 🔍 Funções de pesquisa (sem concorrência)
# ================================
def is_dlc(appid):
    try:
        response = requests.get("https://store.steampowered.com/api/appdetails", params={
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
        response = requests.get("https://store.steampowered.com/api/storesearch", params={
            'term': query,
            'l': 'portuguese',
            'cc': 'pt',
            'key': STEAM_API_KEY
        })
        response.raise_for_status()  # Verifica se há erro na resposta
        data = response.json()

        preliminares = [item for item in data.get('items', []) if all(k not in item['name'].lower() for k in ['dlc', 'pack', 'expansion', 'content'])][:10]

        resultados = []
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
        query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and fullText contains '{jogo['appid']}' and mimeType != 'application/vnd.google-apps.folder'"
        url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&key={GOOGLE_API_KEY}&fields=files(id,name,description)"
        response = requests.get(url)
        files = response.json().get("files", [])

        if files:
            f = files[0]
            link = f"https://drive.google.com/file/d/{f['id']}/view"
            mensagem = f"<:GDrive:123456789012345678> [{f['name']}]({link}) - {f.get('description', 'Sem descrição')}"
            await interaction.response.edit_message(content=mensagem, embed=None, view=None, suppress_embeds=True)
        else:
            await interaction.response.edit_message(content=f"❌ Nenhum ficheiro encontrado para `{jogo['name']}`. Quer pedir?", embed=None, view=RequestFileView(jogo, interaction))
    except Exception as e:
        await interaction.response.edit_message(content=f"❌ Erro: {e}", embed=None, view=None)


# ================================
# 📋 Componente de seleção (Jogos Steam)
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
        embed.add_field(name="🄐 AppID", value=jogo['appid'], inline=True)
        embed.set_thumbnail(url=jogo['image'])
        embed.set_footer(text="Steam Search • Resultado selecionado")
        await interaction.response.edit_message(embed=embed, view=None)


# ================================
# 👥 Pedir ficheiro
# ================================
class RequestFileView(View):
    def __init__(self, jogo, interaction):
        super().__init__(timeout=30)
        self.jogo = jogo
        self.interaction = interaction

    @discord.ui.button(label="Sim, pedir!", style=discord.ButtonStyle.green)
    async def request_file(self, button: discord.ui.Button, interaction: discord.Interaction):
        user = await client.fetch_user(DISCORD_USER_ID)  # Enviar mensagem direta ao utilizador
        await user.send(f"📩 O utilizador {interaction.user.name} pediu o ficheiro para o jogo {self.jogo['name']} (AppID: {self.jogo['appid']}).")
        await interaction.response.edit_message(content=f"✅ Pedido enviado ao administrador para o jogo `{self.jogo['name']}`.", embed=None, view=None)

    @discord.ui.button(label="Não, obrigado", style=discord.ButtonStyle.red)
    async def decline_request(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.edit_message(content="❌ Pedido cancelado.", embed=None, view=None)


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
        embed.add_field(name="🄐 AppID", value=jogo['appid'], inline=True)
        embed.set_thumbnail(url=jogo['image'])
        embed.set_footer(text="Steam Search • Resultado único")
        await interaction.followup.send(embed=embed)
    else:
        view = View()
        view.add_item(GameSelect(resultados))
        embed = discord.Embed(title=f"🔍 Resultados para: {query}", description="Seleciona um jogo abaixo", color=0x1b2838)
        embed.set_footer(text="Steam Search • Selecione uma opção")
        await interaction.followup.send(embed=embed, view=view)


@client.tree.command(name="ficheiro", description="Pesquisa um jogo e mostra ficheiro do Google Drive")
@app_commands.describe(query="Nome do jogo", max_results="Resultados (1-10)")
async def ficheiro(interaction, query: str, max_results: int = 5):
    await interaction.response.defer()
    max_results = max(1, min(10, max_results))
    resultados = await search_steam_games(query, max_results)
    if not resultados:
        await interaction.followup.send("❌ Nenhum jogo encontrado.")
        return

    if len(resultados) == 1:
        await send_drive_link_for_game(interaction, resultados[0])
    else:
        view = View()
        view.add_item(GameSelect(resultados))
        embed = discord.Embed(title=f"📁 Resultados para: {query}", description="Seleciona um jogo", color=0x1b2838)
        embed.set_footer(text="Google Drive • Selecione uma opção")
        await interaction.followup.send(embed=embed, view=view)


# ================================
# 🧳 Comando list: Mostrar ficheiros do Google Drive
# ================================
@client.tree.command(name="list", description="Mostra todos os ficheiros encontrados na pasta da Google Drive")
async def list(interaction):
    await interaction.response.defer()

    try:
        # Query para buscar os ficheiros na pasta do Google Drive
        query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and mimeType != 'application/vnd.google-apps.folder'"
        url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&key={GOOGLE_API_KEY}&fields=files(id,name)"
        response = requests.get(url)
        files = response.json().get("files", [])

        if not files:
            await interaction.followup.send("❌ Nenhum ficheiro encontrado na Google Drive.")
            return

        # Mostra os ficheiros encontrados de forma simples, sem embed
        mensagem += f"<:GDrive:123456789012345678> [{f['name']}]({link}) - {f.get('description', 'Sem descrição')}\n"
        
        await interaction.followup.send(f"📂 Ficheiros encontrados na Google Drive:\n{file_list}")

    except Exception as e:
        await interaction.followup.send(f"❌ Erro ao obter ficheiros: {e}")



# ================================
# ▶️ Executar bot
# ================================
if __name__ == "__main__":
    client.run(TOKEN)
