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
DISCORD_USER_ID = int(os.getenv("DISCORD_USER_ID"))
emoji_str = "<:GDrive:1360019114848026684>"

# ================================
# 📦 Imports
# ================================
import requests
import discord
from discord import app_commands
from discord.ui import Select, View, Button
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
            name="/cmds para mais info"
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
# 📋 Componentes de seleção
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
        embed.add_field(name="🏠 AppID", value=jogo['appid'], inline=True)
        embed.set_thumbnail(url=jogo['image'])
        embed.set_footer(text="Steam Search • Resultado selecionado")
        await interaction.response.edit_message(embed=embed, view=None)

class FileSelect(GameSelect):
    async def callback(self, interaction):
        jogo = self.jogos[int(self.values[0])]
        await send_drive_link_for_game(interaction, jogo)

# ================================
# 📁 Google Drive + Pedido ao Admin
# ================================
class ConfirmarPedidoView(View):
    def __init__(self, jogo, interaction_user):
        super().__init__(timeout=30)
        self.jogo = jogo
        self.interaction_user = interaction_user
        self.valor_confirmado = False

    @discord.ui.button(label="📩 Pedir jogo", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.interaction_user:
            await interaction.response.send_message("⚠️ Este botão não é para ti.", ephemeral=True)
            return

        admin_user = await client.fetch_user(DISCORD_USER_ID)
        await admin_user.send(
            f"📩 Pedido de jogo: `{self.jogo['name']}` (AppID: `{self.jogo['appid']}`) solicitado por `{interaction.user}`.\n"
            f"Steam: {self.jogo['url']}"
        )

        await interaction.response.edit_message(
            content="✅ Pedido enviado ao admin com sucesso.",
            view=None
        )
        self.valor_confirmado = True

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.red)
    async def cancelar(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.interaction_user:
            await interaction.response.send_message("⚠️ Este botão não é para ti.", ephemeral=True)
            return

        await interaction.response.edit_message(
            content="❌ Pedido cancelado.",
            view=None
        )
        self.valor_confirmado = False

async def send_drive_link_for_game(interaction, jogo):
    try:
        query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and fullText contains '{jogo['appid']}' and mimeType != 'application/vnd.google-apps.folder'"
        url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&key={GOOGLE_API_KEY}&fields=files(id,name,description)"
        response = requests.get(url)
        files = response.json().get("files", [])

        if files:
            f = files[0]
            link = f"https://drive.google.com/file/d/{f['id']}/view"
            nome_sem_extensao = os.path.splitext(f['name'])[0]
            mensagem = f"{emoji_str} [{nome_sem_extensao}]({link})"
            await interaction.response.edit_message(content=mensagem, embed=None, view=None, suppress_embeds=True)
        else:
            view = ConfirmarPedidoView(jogo, interaction.user)
            await interaction.response.edit_message(
                content=f"❌ Nenhum ficheiro encontrado para `{jogo['name']}`.\nQueres pedir ao admin que o adicione?",
                embed=None,
                view=view
            )

    except Exception as e:
        await interaction.response.edit_message(content=f"❌ Erro: {e}", embed=None, view=None)

# ================================
# ▶️ Executar bot
# ================================
if __name__ == "__main__":
    client.run(TOKEN)