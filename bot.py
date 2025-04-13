# ================================
# 🔐 Variáveis de ambiente
# ================================
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

# ================================
# 🌐 Endpoints
# ================================
STEAM_STORE_URL = "https://store.steampowered.com/api/storesearch"
STEAM_APP_DETAILS = "https://store.steampowered.com/api/appdetails"

# ================================
# 🤖 Cliente Discord
# ================================
import discord
from discord import app_commands
from discord.ui import Select, View

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
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="comandos /steam e /ficheiro"
        )
        await self.change_presence(activity=activity)
        print(f"✅ Bot conectado como {self.user}")

client = MyClient()

# ================================
# 🔍 Funções auxiliares
# ================================
import requests
from concurrent.futures import ThreadPoolExecutor

def is_dlc(appid):
    try:
        params = {'appids': appid, 'l': 'portuguese'}
        response = requests.get(STEAM_APP_DETAILS, params=params)
        data = response.json().get(str(appid), {})

        if data.get('success'):
            info = data.get('data', {})
            if info.get('type') == 'dlc':
                return True
            if any(cat.get('description') == 'DLC' for cat in info.get('categories', [])):
                return True
        return False
    except Exception as e:
        print(f"Erro ao verificar DLC {appid}: {e}")
        return False

async def search_steam_games(query, max_results=5):
    try:
        params = {
            'term': query,
            'l': 'portuguese',
            'cc': 'pt',
            'key': STEAM_API_KEY
        }
        response = requests.get(STEAM_STORE_URL, params=params)
        response.raise_for_status()
        data = response.json()

        prelim = [
            item for item in data.get('items', [])
            if all(k not in item['name'].lower() for k in ['dlc', 'pack', 'expansion', 'content'])
        ][:10]

        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            for item in prelim:
                if not is_dlc(item['id']):
                    price = "Gratuito"
                    if item.get('price'):
                        price = f"{item['price']['final'] / 100:.2f}€"
                        if item['price'].get('discount_percent', 0) > 0:
                            price += f" (🔥 -{item['price']['discount_percent']}%)"

                    results.append({
                        'name': item['name'],
                        'appid': item['id'],
                        'price': price,
                        'url': f"https://store.steampowered.com/app/{item['id']}",
                        'image': item['tiny_image']
                    })
                    if len(results) >= max_results:
                        break
        return results

    except Exception as e:
        print(f"Erro na pesquisa Steam: {e}")
        return None

# ================================
# 🎮 Selects e Embeds
# ================================
class GameSelect(Select):
    def __init__(self, games):
        options = [
            discord.SelectOption(
                label=game['name'][:100],
                value=str(idx),
                description=game['price'][:100]
            ) for idx, game in enumerate(games)
        ]
        super().__init__(placeholder="Seleciona um jogo para ver detalhes...", options=options)
        self.games = games

    async def callback(self, interaction: discord.Interaction):
        game = self.games[int(self.values[0])]
        embed = discord.Embed(title=game['name'], url=game['url'], color=0x1b2838)
        embed.add_field(name="💰 Preço", value=game['price'], inline=True)
        embed.add_field(name="🄐 AppID", value=game['appid'], inline=True)
        embed.set_thumbnail(url=game['image'])
        embed.set_footer(text="Steam Search • Resultado selecionado")
        await interaction.response.edit_message(embed=embed, view=None)

class FileSelect(Select):
    def __init__(self, games):
        options = [
            discord.SelectOption(
                label=game['name'][:100],
                value=str(idx),
                description=game['price'][:100]
            ) for idx, game in enumerate(games)
        ]
        super().__init__(placeholder="Escolhe um jogo...", options=options)
        self.games = games

    async def callback(self, interaction: discord.Interaction):
        await send_drive_link(interaction, self.games[int(self.values[0])])

# ================================
# 📁 Google Drive
# ================================
def build_drive_query(appid):
    return (
        f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and "
        f"fullText contains '{appid}' and "
        f"mimeType != 'application/vnd.google-apps.folder'"
    )

async def send_drive_link(interaction, game):
    try:
        query = build_drive_query(game['appid'])
        url = (
            "https://www.googleapis.com/drive/v3/files"
            f"?q={requests.utils.quote(query)}&key={GOOGLE_API_KEY}"
            "&fields=files(id,name,description)"
        )
        response = requests.get(url)
        files = response.json().get("files", [])

        if files:
            file = files[0]
            link = f"https://drive.google.com/file/d/{file['id']}/view"
            embed = discord.Embed(
                title=f"📂 Ficheiro: {game['name']}",
                description=f"[🔗 Abrir ficheiro]({link})",
                color=0x34a853
            )
            embed.add_field(name="🄐 AppID", value=game['appid'], inline=True)
            embed.add_field(name="💬 Descrição", value=file.get("description", "Sem descrição"), inline=True)
            embed.set_footer(text="Google Drive • Resultado encontrado")
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.edit_message(
                content=f"❌ Nenhum ficheiro encontrado para `{game['name']}`.",
                embed=None, view=None
            )
    except Exception as e:
        await interaction.response.edit_message(
            content=f"❌ Erro ao procurar ficheiro: {str(e)}",
            embed=None, view=None
        )

# ================================
# 🧩 Comandos
# ================================
@client.tree.command(name="steam", description="Pesquisa jogos na Steam (sem DLCs)")
@app_commands.describe(query="Nome do jogo", max_results="Número de resultados (1-5)")
async def steam(interaction: discord.Interaction, query: str, max_results: int = 3):
    await interaction.response.defer()
    results = await search_steam_games(query, max(1, min(5, max_results)))

    if not results:
        await interaction.followup.send("❌ Nenhum jogo encontrado.")
        return

    if len(results) == 1:
        game = results[0]
        embed = discord.Embed(title=game['name'], url=game['url'], color=0x1b2838)
        embed.add_field(name="💰 Preço", value=game['price'], inline=True)
        embed.add_field(name="🄐 AppID", value=game['appid'], inline=True)
        embed.set_thumbnail(url=game['image'])
        embed.set_footer(text="Steam Search • Resultado único")
        await interaction.followup.send(embed=embed)
    else:
        view = View()
        view.add_item(GameSelect(results))
        embed = discord.Embed(
            title=f"🔍 Resultados para: {query}",
            description="Seleciona um jogo abaixo",
            color=0x1b2838
        )
        embed.set_footer(text="Steam Search • Selecione uma opção")
        await interaction.followup.send(embed=embed, view=view)

@client.tree.command(name="ficheiro", description="Mostra ficheiro do jogo no Google Drive")
@app_commands.describe(query="Nome do jogo", max_results="Número de resultados (1-10)")
async def ficheiro(interaction: discord.Interaction, query: str, max_results: int = 5):
    await interaction.response.defer()
    results = await search_steam_games(query, max(1, min(10, max_results)))

    if not results:
        await interaction.followup.send("❌ Nenhum jogo encontrado.")
        return

    if len(results) == 1:
        await send_drive_link(interaction, results[0])
    else:
        view = View()
        view.add_item(FileSelect(results))
        embed = discord.Embed(
            title=f"📁 Resultados para: {query}",
            description="Seleciona um jogo abaixo",
            color=0x1b2838
        )
        embed.set_footer(text="Google Drive • Selecione um jogo")
        await interaction.followup.send(embed=embed, view=view)

# ================================
# 🚀 Executar bot
# ================================
if __name__ == "__main__":
    client.run(TOKEN)
