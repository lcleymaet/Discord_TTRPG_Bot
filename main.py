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
db_path = os.path.join(os.path.dirname(__file__),"characters.db")
#need to store maximum ID from database on initialization in a local object

#Create classes for caching
#DnD_Char is a class that contains a single dungeons and dragons 5e character
#User is a class that contains a User that may contain none or amny characters
class DnD_Char:
  #self is char_id from database
  #stats should be a dictionary with int, cha, wis, str, con, dex as keys
  #classes is the starting class str
  #race, name, background are strings
  def __init__(self, owner, name, race, background, classes, hit_dice, stats, hp, xp = 0, spells = {}, spell_slots = {}, current_points = {}, ac, ms = 30, id, languages = {}, equipment = {}, feats = [], exhaustion = 0):
    self.name = name
    self.owner = owner
    self.race = race
    self.background = background
    self.classes = classes
    self.hit_dice = hit_dice
    self.xp = xp
    self.spell_slots = spell_slots #type: [current, max]
    self.spells = spells #prepared or known, depending on class
    self.stats = stats
    self.languages = []
    self.equipment = {}
    self.points = current_points #contains things like sorcery points etc - type: [current, max]
    self.feats = []
    self.hp = hp #[current, max]
    self.ac = ac
    self.ms = ms
    self.exhaustion = exhaustion
    self.id = id #placeholder, will be overwritten with next integer for database table
  def add_lang(lang):
    self.languages.append(lang)
  def remove_lang(lang):
    self.languages.remove(lang)
  def update_stats(new):
    for key, val in new.items():
      self.stats[key] = val
  def add_equip(thing, amount):
    if thing not in self.equipment:
      self.equipment[thing] = amount
    else:
      self.equipment[thing] += amount
  def add_xp(amount):
    self.xp += amount
  def add_feat(feat):
    self.feats.append(feat)
  def change_ms(new):
    self.ms = new
  def level_up(new_class, hp_roll, stat_change = False, stats = {}, feat_add = False, feats = []):
    #stats is a dictionary of stats that are changing and an amount change
    if stat_change:
      for key, val in stats.items():
        self.stats[key][0] += val
    if feat_add:
      for feat in feats:
        self.feats.append(feat)
    if new_class in self.classes:
      self.classes[new_class] += 1
    else:
      self.classes[new_class] = 1
    self.max_hp += (hp_roll + ((self.stats["con"] - 10) // 2))
  def use_points(type, val):
    if self.points[type][0] >= val:
      self.points[type][0] -= val
  def change_max_points(type, val)
    self.max_points[type] = val
  def cast_spell(level):
    if self.spell_slots[level][0] > 0:
      self.spell_slots[level][0] -= 1
  def add_exhaustion(decrease = False):
    if decrease:
      self.exhaustion -= 1
    else:
      self.exhaustion += 1
  def long_rest(change_spells = False, spells = []):
    self.hp[0] = self.hp[1]
    for key, val in self.spell_slots.items():
      self.spell_slots[key][0] = val[1] #dictionary is set up with key: list[current,max]
    for key, val in self.points.items():
      self.points[key][0] = val[1]
    if change_spells:
      self.spells = spells
    if self.exhaustion > 0:
      self.exhaustion -= 1
  
class User:
  

#initialize connection to database
def init_db():
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
    id INTEGER PRIMARY KEY,
    user_id TEXT,
    name TEXT,
    race TEXT,
    move_speed INTEGER,
    level INTEGER,
    languages TEXT,
    background TEXT,
    feats TEXT,
    xp INTEGER,
    hp INTEGER,
    ac INTEGER,
    int INTEGER,
    str INTEGER,
    agi INTEGER,
    wis INTEGER,
    con INTEGER,
    cha INTEGER,
    other_proficiencies TEXT,
    skills TEXT,
    exhaustion INTEGER
  );
  """)

  #Stores 0 for no proficiency, 1 for proficiency, 2 for expertise
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS proficiencies (
    character_id INTEGER,
    str_save INTEGER,
    dex_save INTEGER,
    con_save INTEGER,
    int_save INTEGER,
    wis_save INTEGER,
    cha_save INTEGER,
    acrobatics INTEGER,
    animal_handling INTEGER,
    arcana INTEGER,
    athletics INTEGER,
    deception INTEGER,
    history INTEGER,
    insight INTEGER,
    intimidation INTEGER,
    investigation INTEGER,
    medicine INTEGER,
    nature INTEGER,
    perception INTEGER,
    performance INTEGER,
    persuasion INTEGER,
    religion INTEGER,
    sleight_of_hand INTEGER,
    stealth INTEGER,
    survival INTEGER
  );
  """)

  cursor.execute("""
  CREATE TABLE IF NOT EXISTS spellcasting (
    character_id INTEGER,
    spell_save_dc INTEGER,
    spell_attack_mod INTEGER,
    lvl_1 INTEGER,
    lvl_2 INTEGER,
    lvl_3 INTEGER,
    lvl_4 INTEGER,
    lvl_5 INTEGER,
    lvl_6 INTEGER,
    lvl_7 INTEGER,
    lvl_8 INTEGER,
    lvl_9 INTEGER
  );
  """)

  #Add table of spells. Each will be a comma separated list for parsing in a function
  #A separate table as not all classes have spells known, but instead are martial or prepare spells
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS spells (
    character_id INTEGER,
    cantrips TEXT,
    lvl_1 TEXT,
    lvl_2 TEXT,
    lvl_3 TEXT,
    lvl_4 TEXT,
    lvl_5 TEXT,
    lvl_6 TEXT,
    lvl_7 TEXT,
    lvl_8 TEXT,
    lvl_9 TEXT
  );
  """)

  #0 indicates not that class, other numbers indicate lvl in that class to support multiclassing
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS classes (
    character_id INTEGER,
    barbarian INTEGER,
    bard INTEGER,
    cleric INTEGER,
    druid INTEGER,
    fighter INTEGER,
    monk INTEGER,
    paladin INTEGER,
    ranger INTEGER,
    rogue INTEGER,
    sorcerer INTEGER,
    warlock INTEGER,
    wizard INTEGER,
    artificer INTEGER
  );
  """)

  #Addsorcery points tracking for sorcerers, plus sub-class
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS sorcerer (
    character_id INTEGER,
    hit_dice TEXT,
    sub_class TEXT,
    dragon_type TEXT,
    metamagic TEXT,
    max_points INTEGER,
    current_points INTEGER
  );
  """)

  #Add ki points tracking for monks
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS monk (
    character_id INTEGER,
    hit_dice TEXT,
    sub_class TEXT,
    max_ki INTEGER,
    current_ki INTEGER,
    elemental_disciplines TEXT,
  );
  """)

  #Add tracking for fighters
  #fighting styles will be a comma separated list for support for champion martial archetype
  #superiority dice are listed a NdM
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS fighter (
    character_id INTEGER,
    hit_dice TEXT,
    sub_class TEXT,
    fighting_styles TEXT, 
    superiority_dice TEXT,
    action_surge INTEGER,
    second_wind INTEGER
  );
  """)

  #tracking for barbarians
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS barbarian (
    character_id INTEGER,
    hit_dice TEXT,
    sub_class TEXT,
    max_rage INTEGER,
    rage INTEGER,
    totem TEXT
  );
  """)

  #add bard resource tracking
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS bard (
    character_id INTEGER,
    hit_dice TEXT,
    sub_class TEXT,
    inspiration INTEGER
  );
  """)
    
  #add cleric resource tracking
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS cleric (
    character_id INTEGER,
    hit_dice TEXT,
    sub_class TEXT,
    prepared_spells TEXT
  );
  """)

  #add druid tracking
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS druid (
    character_id INTEGER,
    hit_dice TEXT,
    sub_class TEXT,
    wild_shape INTEGER,
    prepared_spells TEXT
  );
  """)
      
  #add paladin tracking
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS paladin (
    character_id INTEGER,
    hit_dice TEXT,
    sub_class TEXT,
    divine_sense INTEGER,
    lay_on_hands INTEGER,
    fighting_styles TEXT,
    prepared_spells TEXT
  );
  """)

  #add ranger tracking
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS ranger (
    character_id INTEGER,
    hit_dice TEXT,
    sub_class TEXT,
    favored_enemies TEXT,
    favored terrains TEXT,
    fighting_styles TEXT,
    hunters_prey TEXT,
    defensive_tactics TEXT,
    multiattack TEXT,
    companion TEXT
  );
  """)

  #add rogue tracking
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS rogue (
    character_id INTEGER,
    hit_dice TEXT,
    sub_class TEXT
  );
  """)
  
  #add warlock tracking
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS warlock (
    character_id INTEGER,
    hit_dice TEXT,
    sub_class TEXT,
    pact_boon TEXT,
    arcanum TEXT
  );
  """)

  #add wizard tracking
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS wizard (
    character_id INTEGER,
    hit_dice TEXT,
    sub_class TEXT,
    signature_spells TEXT,
    prepared_spells TEXT
  );
  """)

  #add artificer tracking
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS artificer (
    character_id INTEGER,
    hit_dice TEXT,
    sub_class TEXT,
    prepared_spells TEXT,
    infusions TEXT,
    genius_max INTEGER,
    genius INTEGER
  );
  """)
  
  #Catalog of weapons and equipment
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS equipment_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    base_die TEXT
  );
  """)

  #character equipment table
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
@app_commands.desccribe(dice = "Dice roll in ndm+x format (ie 1d6+2)")
async def roll(interaction: discord.Interaction, dice: str = "1d6+0"):
  match = re.fullmatch(r"(\d+)d(\d+)+(\d+)", dice)
  if not match:
    await interaction.response.send_message("Invalid format. Please use ndm+x like 2d6+0 or 1d20+3.", ephemeral = True)
    return
  num, sides, mod = map(int, match.groups())
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
  total = sum(rolls) + mod
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
