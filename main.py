import discord
from discord.ext import commands
from discord import app_commands
import random
import ctypes
import json
from dotenv import load_dotenv
import os
import re
import sqlite3 as lite
import sys

load_dotenv()

#initialize connection to database
def init_db():
  db_path = os.path.join(os.path.dirname(__file__),"characters.db")
  conn = lite.connect(db_path)
  cursor = conn.cursor()

  cursor.execute("""
  CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    n_chars INTEGER
  );
  """)

cursor.execute("""
CREATE TABLE IF NOT EXISTS dnd_characters (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  name TEXT,
  level INTEGER,
  xp INTEGER,
  health INTEGER,
  gold INTEGER,
  int INTEGER,
  str INTEGER,
  agi INTEGER,
  wis INTEGER,
  con INTEGER,
  cha INTEGER
);
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS equipment_catalog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  base_die TEXT
);
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS character_equipment (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  character_id INTEGER,
  equipment_id INTEGER,
  count INTEGER
);
""")

conn.commit()
conn.close()
    

TOKEN = os.getenv("DISCORD_TOKEN")

slot_lib = ctypes.CDLL('./slot_machine.dll')

slot_lib.play_machine.argtypes = [ctypes.c_char_p]
slot_lib.play_machine.restype = ctypes.c_char_p
MACHINE_TYPES = ["basic","complex","default"]

intents = discord.Intents.default()
bot = commands.Bot(command_prefix = "!", intents = intents)

async def machine_type_autocomplete(interaction: discord.Interaction, current: str):
  return [
    app_commands.Choice(name = mt, value = mt)
    for mt in MACHINE_TYPES
    if current.lower() in mt.lower()
  ]

@bot.event
async def on_ready():
  await bot.tree.sync()
  init_db()
  print(f"Logged in as {bot.user}")

@bot.command()
async def ping(ctx):
  await ctx.send("Pong!")

@bot.tree.command(name = 'roll', description = 'Roll some dice!')
@app_commands.desccribe(dice = "Dice roll in ndm format (ie 1d6)")
async def roll(interation: discord.Interaction, dice: str = "1d6"):
  match = re.fullmatch(r"(\d+)d(\d+)", dice)
  if not match:
    await interaction.response.send_message("Invalid format. Please use ndm like 2d6 or 1d20.", ephemeral = True)
    return
  num, sides = map(int, match.groups())
  if num < 1:
    await interaction.response.send_message("Invalid format. Please enter a positive integer for nubmer of dice like 1 or 2.")
    return
  if sides < 2:
    await interaction.response.send_message("Invalid format. Please enter a number of sides 2 or greater.")
    return
  if num > 50:
    await interaction.response.send_message("Too many dice! Please enter a number of dice 50 or fewer")
    return
  rolls = [random.randint(1, sides) for _ in range(num)]
  total = sum(rolls)
  roll_text = ", ".join(str(r) for r in rolls)

  await interation.response.send_message(f"Rolling {num}d{sides}:\nResults: {roll_text}\n**Total: {total}**")
  


@bot.tree.command(name = 'slot', description = "Play a slot machine")
@app_commands.describe(machine_type = "The type of machine to play", wager = "Amount to wager")
@app_commands.autocomplete(machine_type = machine_type_autocomplete)
async def slot(interaction: discord.Interaction, machine_type: str = "basic", wager: float = 1.0):
  #prep input
  input_data = {"type": machine_type, "wager": wager}
  input_json = json.dumps(input_data).encode('utf-8')

  #Call the function from the slot machine backend
  result_ptr = slot_lib.play_machine(input_json)
  result_json = ctypes.string_at(result_ptr).decode('utf-8')

  try:
    result = json.loads(result_json)
    if "error" in result:
      await interaction.response.send_message(f"ERROR: {result['error']}")
      return
    symbols = " ".join(result['symbols'])
    multiplier = result['multiplier']
    payout = result['payout']
    wager = result['wager']

    await interaction.response.send_message(f"{symbols}\nWagered: {wager}\nWinnings Multiplier: {multiplier}\nPayout: {payout:.2f}")
  except Exception as e:
    await interaction.response.send_message(f"Failed to parse result: {e}")

bot.run(TOKEN)
