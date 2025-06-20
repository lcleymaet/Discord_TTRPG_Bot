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
import threading
import time
import logging

load_dotenv()
logging.basicConfig(level = logging.INFO,
                    format = '[%(levelname)s] %(asctime)s - %(message)s',
                    handlers = [logging.FileHandler("bot.log"), logging.StreamHandler()]
                   )
db_path = os.path.join(os.path.dirname(__file__),"characters.db")
#need to store maximum ID from database on initialization in a local object
max_id = 0
max_id_lock = threading.Lock()
#Ensures that max_id will iterate correctly and not allow for overwriting character entries.
def get_next_id():
  global max_id
  with max_id_lock:
    val = max_id
    max_id += 1
  return val

#Dictionary to store what hit die each class takes
class_dice = {
  "barbarian": 12,
  "fighter": 10,
  "paladin": 10,
  "ranger": 10,
  "artificer": 8,
  "bard": 8,
  "cleric": 8,
  "druid": 8,
  "monk": 8,
  "rogue": 8,
  "warlock": 8,
  "sorcerer": 6,
  "wizard": 6
}

#Create classes for caching
#DnD_Char is a class that contains a single dungeons and dragons 5e character
#User is a class that contains a User that may contain none or amny characters
class DnD_Char:
  #self is char_id from database
  #stats should be a dictionary with int, cha, wis, str, con, dex as keys
  #classes is the starting class str
  #race, name, background are strings
  __slots__ = (
  "name", "owner", "race", "background", "classes", "subclasses", "hit_dice", "xp",
  "abilities", "spell_slots", "spells", "stats", "languages", "equipment", "points",
  "feats", "hp", "ac", "ms", "exhaustion", "proficiencies", "Id"
  )
  def __init__(self, 
               owner: str,
               name: str,
               race: str,
               background: str,
               classes: dict,
               hit_dice: dict,
               stats: dict,
               hp: list,
               ac: int,
               Id: int,
               xp: int = 0,
               subclasses: dict = None,
               abilities: list = None,
               spells: dict = None,
               spell_slots: dict = None,
               points: dict = None,
               ms: int = 30,
               languages: dict = None,
               equipment: dict = None,
               feats: list = None,
               exhaustion: int = 0,
               proficiencies: dict = None):
    self.name = name
    self.owner = owner
    self.race = race
    self.background = background
    self.classes = classes 
    self.subclasses = subclasses or {}
    self.hit_dice = hit_dice
    self.xp = xp
    self.abilities = abilities or []
    self.spell_slots = spell_slots or {} #type: [current, max]
    self.spells = spells or {} #prepared or known, depending on class {"known": {level: [spells]}, "prepared": [spells]}
    self.stats = stats
    self.languages = languages or []
    self.equipment = equipment or {}
    self.points = points or {} #contains things like sorcery points etc - type: [current, max]
    self.feats = feats or []
    self.hp = hp #[current, max]
    self.ac = ac
    self.ms = ms
    self.exhaustion = exhaustion
    self.proficiencies = proficiencies or {}
    self.Id = Id #placeholder, will be overwritten with next integer for database table
  def add_lang(self, lang):
    self.languages.append(lang)
  def add_ability(self, ability):
    self.abilities.append(ability)
  def remove_ability(self, ability):
    self.abilities.remove(ability)
  def remove_lang(self, lang):
    self.languages.remove(lang)
  def update_stats(self, new):
    for key, val in new.items():
      self.stats[key] = val
  def add_equip(self, thing, amount):
    if thing not in self.equipment:
      self.equipment[thing] = amount
    else:
      self.equipment[thing] += amount
  def add_xp(self, amount):
    self.xp += amount
  def add_feat(self, feat):
    self.feats.append(feat)
  def change_ms(self, new):
    self.ms = new
  def get_modifier(self, stat_name):
    return (self.stats.get(stat_name, 10) - 10) // 2
  def add_new_subclass(self, class_to_add: str, subclass: str):
    if class_to_add in self.classes and class_to_add not in self.subclasses:
      self.subclasses[class_to_add] = subclass
  def level_up(self, new_class: str, hp_roll: int, subclass: str = None, stat_change = False, stats: dict = None, feat_add = False, feats: list = None, learn_spells = False, new_spells: dict = None):
    #stats is a dictionary of stats that are changing and an amount change
    if stat_change:
      for key, val in stats.items():
        self.stats[key] += val
    if learn_spells:
      for key, val in new_spells.items():
        if "known" not in self.spells:
          self.spells["known"] = {}
        if key not in self.spells["known"]:
          self.spells["known"][key = []
        self.spells["known"][key].extend(val)
    if feat_add:
      for feat in feats:
        self.feats.append(feat)
    if new_class in self.classes:
      self.classes[new_class] += 1
    else:
      self.classes[new_class] = 1
    if new_class.lower() in ["cleric","sorcerer","warlock"] and self.classes[new_class] >= 1 and new_class.lower() not in self.subclasses:
      self.add_new_subclass(new_class, subclass)
    elif new_class.lower() not in ["cleric","sorcerer","warlock"] and self.classes[new_class] >= 3 and new_class.lower() not in self.subclasses:
      self.add_new_subclass(new_class, subclass)
    self.hp[1] += (hp_roll + ((self.stats["con"] - 10) // 2))
  def use_points(self, type, val):
    if self.points[type][0] >= val:
      self.points[type][0] -= val
  def change_max_points(self, type, val):
    if type in self.points:
      self.points[type][1] = val
    else:
      self.points[type] = [val, val]
  def cast_spell(self, level):
    if self.spell_slots[level][0] > 0:
      self.spell_slots[level][0] -= 1
  def add_exhaustion(self, decrease = False):
    self.exhaustion = max(0, self.exhaustion - 1) if decrease else self.exhaustion + 1
  def learn_spell(self, level, spell):
    if "known" not in self.spells:
      self.spells["known"] = {}
    if level not in self.spells["known"]:
      self.spells["known"][level] = []
    if spell not in self.spells["known"][level]:
      self.spells["known"][level].append(spell)
  def long_rest(self, change_spells = False, spells = []):
    self.hp[0] = self.hp[1]
    for key, val in self.spell_slots.items():
      self.spell_slots[key][0] = val[1] #dictionary is set up with key: list[current,max]
    for key, val in self.points.items():
      self.points[key][0] = val[1]
    if change_spells:
      self.spells["prepared"] = spells
    if self.exhaustion > 0:
      self.add_exhaustion(decrease = True)
  def change_hp(self, amount):
    self.hp[0] = max(self.hp[0] + amount, 0)
    if self.hp[0] > self.hp[1]:
      self.hp[0] = self.hp[1]
  def get_level(self):
    return sum(self.classes.values())
  def proficiency_bonus(self):
    return (-(-self.get_level() // 4)) + 1
  def to_dict(self):
    #for exporting to database cleanly and for throwing to a cache
    return {
      "id": self.Id,
      "owner": self.owner,
      "name": self.name,
      "race": self.race,
      "background": self.background,
      "classes": json.dumps(self.classes),
      "subclasses": json.dumps(self.subclasses),
      "hit_dice": json.dumps(self.hit_dice),
      "stats": json.dumps(self.stats),
      "hp": json.dumps(self.hp),
      "ac": self.ac,
      "xp": self.xp,
      "abilities": json.dumps(self.abilities),
      "spells": json.dumps(self.spells),
      "spell_slots": json.dumps(self.spell_slots),
      "points": json.dumps(self.points),
      "languages": json.dumps(self.languages),
      "equipment": json.dumps(self.equipment),
      "feats": json.dumps(self.feats),
      "exhaustion": self.exhaustion,
      "proficiencies": json.dumps(self.proficiencies),
      "ms": self.ms
    }
  def to_db(self, conn):
    cursor = conn.cursor()
    main_data = self.to_dict()
    cursor.execute("""
    INSERT INTO dnd_characters (
      id, owner, name, race, background, classes, hit_dice, stats, hp, ac, xp,
      points, languages, equipment, feats, exhaustion, ms
    ) VALUES (
      :id, :owner, :name, :race, :background, :classes, :hit_dice, :stats, :hp, :ac, :xp,
      :points, :languages, :equipment, :feats, :exhaustion, :ms
    )
    ON CONFLICT(id) DO UPDATE SET
      owner = excluded.owner,
      name = excluded.name,
      race = excluded.race,
      background = excluded.background,
      classes = excluded.classes,
      hit_dice = excluded.hit_dice,
      stats = excluded.stats,
      hp = excluded.hp,
      ac = excluded.ac,
      xp = excluded.xp,
      points = excluded.points,
      languages = excluded.languages,
      equipment = excluded.equipment,
      feats = excluded.feats,
      exhaustion = excluded.exhaustion,
      ms = excluded.ms
    """, main_data)
    # Update related tables
    cursor.execute("DELETE FROM character_classes WHERE character_id = ?", (self.Id,))
    for cls, level in self.classes.items():
      subclass = self.subclasses.get(cls, "")
      hd = self.hit_dice.get(cls, "")
      cursor.execute("""
      INSERT INTO character_classes (character_id, class_name, level, subclass, hit_dice)
      VALUES (?, ?, ?, ?, ?)
      """, (self.Id, cls, level, subclass, hd))
    cursor.execute("REPLACE INTO spells (character_id, spells) VALUES (?, ?)", 
                   (self.Id, json.dumps(self.spells)))
    cursor.execute("REPLACE INTO spell_slots (character_id, slots) VALUES (?, ?)", 
                   (self.Id, json.dumps(self.spell_slots)))
    cursor.execute("REPLACE INTO proficiencies (character_id, proficiencies) VALUES (?, ?)", 
                   (self.Id, json.dumps(self.proficiencies)))
  @classmethod
  def from_db(cls, conn, character_id):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM dnd_characters WHERE id = ?", (character_id,))
    row = cursor.fetchone()
    if not row:
      raise ValueError(f"Character ID {character_id} not found")

    cursor.execute("SELECT class_name, level, subclass, hit_dice FROM character_classes WHERE character_id = ?", (character_id,))
    class_rows = cursor.fetchall()
    classes = {}
    subclasses = {}
    hit_dice = {}
    for r in class_rows:
      classes[r[0]] = r[1]
      subclasses[r[0]] = r[2]
      hit_dice[r[0]] = r[3]

    cursor.execute("SELECT spells FROM spells WHERE character_id = ?", (character_id,))
    spells_row = cursor.fetchone()
    spells = json.loads(spells_row[0]) if spells_row else {}

    cursor.execute("SELECT slots FROM spell_slots WHERE character_id = ?", (character_id,))
    slots_row = cursor.fetchone()
    spell_slots = json.loads(slots_row[0]) if slots_row else {}

    cursor.execute("SELECT proficiencies FROM proficiencies WHERE character_id = ?", (character_id,))
    prof_row = cursor.fetchone()
    proficiencies = json.loads(prof_row[0]) if prof_row else {}

    return cls(
              owner = row["owner"],
              name = row["name"],
              race = row["race"],
              background = row["background"],
              classes = classes,
              hit_dice = hit_dice,
              stats = json.loads(row["stats"]),
              hp = json.loads(row["hp"]),
              ac = row["ac"],
              Id = row["id"],
              xp = row["xp"],
              subclasses = subclasses,
              abilities = json.loads(row["abilities"] if "abilities" in row.keys() else "[]"),
              proficiencies = proficiencies,
              spells = spells,
              spell_slots = spell_slots,
              points = json.loads(row["points"] if "points" in row.keys() else "{}"),
              ms = row["ms"] if "ms" in row.keys() else 30,
              languages = json.loads(row["languages"] if "languages" in row.keys() else "[]"),
              equipment = json.loads(row["equipment"] if "equipment" in row.keys() else "{}"),
              feats = json.loads(row["feats"] if "feats" in row.keys() else "[]"),
              exhaustion = row["exhaustion"] if "exhaustion" in row.keys() else 0
              )
  def serialize_for_display(self):
    return {
      "Name": self.name,
      "Race": self.race,
      "Background": self.background,
      "Level": self.get_level(),
      "HP": f"Current - {self.hp[0]}; Max - {self.hp[1]}",
      "AC": self.ac,
      "Stats": self.stats,
      "Spells": self.spells,
      "Spell Slots": self.spell_slots,
      "Abilities": self.abilities,
      "Feats": self.feats,
      "Languages": self.languages
    }

#An object to store characters in runtime to reduce the need to query the database
#Can grow this so that it includes dnd_characters dictionary and other game dictionary in the object, but for now only DnD
class DnD_Cache:
  def __init__(self):
    self.lock = threading.Lock()
    self.characters = {} #Format {character_id (int): DnD_char instance}
  def add_char(self, character):
    with self.lock:
      self.characters[character.Id] = character
  def remove_character(self, character_id):
    with self.lock:
      if character_id in self.characters:
        del self.characters[character_id]
  def get_character(self, character_id):
    with self.lock:
      return self.characters.get(character_id)
  def all_characters(self):
    with self.lock:
      return self.characters.values()
  def clear(self):
    with self.lock:
      self.characters.clear()
  def is_empty(self):
    with self.lock:
      return len(self.characters) == 0

#pushing the dnd character cache to a database
def push_dnd_cache_to_db(cache: DnD_Cache, db: str):
  if cache.is_empty():
    logging.info("Character cache is empty. Skipping database push.")
  try:
    conn = lite.connect(db)
    conn.row_factory = lite.Row

    chars = cache.all_characters()
    logging.info(f"Starting push of {len(chars)} characters to database.")
    
    for character in chars:
      character.to_db(conn)
    conn.commit()
    logging.info(f"Pushed {len(chars)} characters to database.")
    cache.clear()
    logging.info("Cache cleared after successful push.")

  except Exception as e:
    conn.rollback()
    logging.error(f"Failed to push characters to database: {e}")
  finally:
    conn.close()

#automate cache push to database
def schedule_push(cache, db_path, interval_seconds = 7200):
  def loop():
    while True:
      push_dnd_cache_to_db(cache, db_path)
      time.sleep(interval_seconds)
  thread = threading.Thread(target = loop, daemon = True)
  thread.start()
#initialize connection to database
def init_db():
  conn = lite.connect(db_path)
  cursor = conn.cursor()
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    chars TEXT
  );
  """)
  #Not adding a foreign key on user id/owner as this data may be used to train an ML model
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS dnd_characters (
    id INTEGER PRIMARY KEY,
    owner TEXT,
    name TEXT,
    race TEXT,
    background TEXT,
    hit_dice TEXT, -- JSON {"class": "1d8",...}
    stats TEXT, -- JSON {"str": 10, "cha": 8,...}
    hp TEXT, -- JSON [current, max]
    ac INTEGER,
    xp INTEGER,
    points TEXT, -- JSON {"sorcerer points": 4, ...}
    languages TEXT, -- JSON ["common", "thieves cant",...]
    equipment TEXT, -- JSON {"gold": 500, "dagger": 2,...}
    feats TEXT, -- JSON [...]
    abilities TEXT, -- JSON ["Darkvision", ...]
    exhaustion INTEGER,
    ms INTEGER -- move speed
  );
  """)
  #For multiclass support
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS character_classes (
    character_id INTEGER,
    class_name TEXT,
    level INTEGER,
    subclass TEXT,
    hit_dice TEXT,
    PRIMARY KEY (character_id, class_name),
    FOREIGN KEY (character_id) REFERENCES dnd_characters(id) ON DELETE CASCADE
  );
  """)
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS proficiencies (
    character_id INTEGER PRIMARY KEY,
    proficiencies TEXT, -- JSON {"str": 1, "acrobatics": 2, "thieves_tools": 1,...} 1 for proficient, 2 for expertise
    FOREIGN KEY (character_id) REFERENCES dnd_characters(id) ON DELETE CASCADE
  );
  """)
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS spell_slots (
    character_id INTEGER PRIMARY KEY,
    slots TEXT, -- JSON {"level": [current, max],...}
    FOREIGN KEY (character_id) REFERENCES dnd_characters(id) ON DELETE CASCADE
  );
  """)
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS spells (
    character_id INTEGER PRIMARY KEY,
    spells TEXT, -- JSON {"known": {"cantrips": [...],...}, "prepared": [...]}
    FOREIGN KEY (character_id) REFERENCES dnd_characters(id) ON DELETE CASCADE
  );
  """)
  cursor.execute("CREATE INDEX IF NOT EXISTS idx_char_id_spells ON spells(character_id)")
  cursor.execute("CREATE INDEX IF NOT EXISTS idx_char_id_spell_slots ON spell_slots(character_id)")
  cursor.execute("CREATE INDEX IF NOT EXISTS idx_char_id_proficiencies ON proficiencies(character_id)")
  cursor.execute("CREATE INDEX IF NOT EXISTS idx_char_id_classes ON character_classes(character_id)")
  cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON dnd_characters(owner)")
  conn.commit()
  conn.close()

def update_max_id():
  global max_id
  try:
    conn = lite.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(id) FROM dnd_characters")
    result = cursor.fetchone()
    max_id = result[0] + 1 if result[0] is not None else 0
    logging.info(f"Max ID initialized to {max_id}")
  except Exception as e:
    logging.error(f"Error initializing max_id: {e}")
  finally:
    conn.close()
#Function to check tables for entries
#This is necessary to populate the ID iterator correctly in runtime cache of characters
def check_for_entries(table_name, db = db_path):
  #returns True if there are one or more entires, False otherwise
  #Arguments: table_name - name of table to be queried
  #db - file path to database
  #Return: bool: True if 1 or more entries, False otherwise
  conn = None
  try:
    conn = lite.connect(db)
    cursor = conn.cursor()
    #query to count entries
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    return count > 0
  except lite.Error as e:
    print(f"SQL error: {e}")
    return False
  finally:
    if conn:
      conn.close()

TOKEN = os.getenv("DISCORD_TOKEN")

slot_lib = ctypes.CDLL('./slot_machine.dll')

slot_lib.play_machine.argtypes = [ctypes.c_char_p]
slot_lib.play_machine.restype = ctypes.c_char_p
MACHINE_TYPES = ["basic","complex","default"]

intents = discord.Intents.default()
bot = commands.Bot(command_prefix = "!", intents = intents)
tree = app_commands.CommandTree(bot)

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
