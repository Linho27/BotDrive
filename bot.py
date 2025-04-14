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
# 📦 Imports
# ================================
import requests
import discord
from discord import app_commands
from discord.ui import Select, View
from concurrent.futures import ThreadPoolExecutor

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
# 🔍 Funções de pesquisa
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
# 📋 Componente de seleção
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


class FileSelect(GameSelect):
    async def callback(self, interaction):
        jogo = self.jogos[int(self.values[0])]
        await send_drive_link_for_game(interaction, jogo)


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
            embed = discord.Embed(
                title=f"📂 Ficheiro para: {jogo['name']}",
                description=f"[🔗 Abrir ficheiro]({link})",
                color=0x34a853
            )
            embed.add_field(name="🄐 AppID", value=jogo['appid'], inline=True)
            embed.add_field(name="💬 Descrição", value=f.get("description", "Sem descrição"), inline=True)
            embed.set_footer(text="Google Drive • Resultado encontrado")
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.edit_message(content=f"❌ Nenhum ficheiro encontrado para `{jogo['name']}`.", embed=None, view=None)
    except Exception as e:
        await interaction.response.edit_message(content=f"❌ Erro: {e}", embed=None, view=None)

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
        view.add_item(FileSelect(resultados))
        embed = discord.Embed(title=f"📁 Resultados para: {query}", description="Seleciona um jogo", color=0x1b2838)
        embed.set_footer(text="Google Drive • Selecione uma opção")
        await interaction.followup.send(embed=embed, view=view)


@client.tree.command(name="list", description="Lista os ficheiros da pasta Google Drive")
async def list_files(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    url = f"https://www.googleapis.com/drive/v3/files?q=\"{GOOGLE_DRIVE_FOLDER_ID}\" in parents and mimeType != 'application/vnd.google-apps.folder'&key={GOOGLE_API_KEY}&fields=files(id,name,description)"

    try:
        response = requests.get(url)
        files = response.json().get("files", [])

        if not files:
            await interaction.channel.send("❌ Não foram encontrados ficheiros na pasta.", delete_after=10)
            return

        # Emoji personalizado do bot
        emoji_str = "<:GDrive:1360019114848026684>"

        mensagem = "**Ficheiros encontrados:**\n"
        for f in files:
            link = f"https://drive.google.com/file/d/{f['id']}/view"
            mensagem += f"{emoji_str} [{f['name']}]({link}) - {f.get('description', 'Sem descrição')}\n"

        partes = dividir_mensagem(mensagem)
        for parte in partes:
            await interaction.channel.send(parte, suppress_embeds=True)

        await interaction.channel.send("✅ Lista enviada.", delete_after=2)

    except Exception as e:
        await interaction.channel.send(f"❌ Erro ao obter os ficheiros: {e}", delete_after=10)



# ================================
# ▶️ Executar bot
# ================================
if __name__ == "__main__":
    client.run(TOKEN)