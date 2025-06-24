import discord
from discord.ext import commands
from discord import app_commands, Interaction, ui
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
    max_id += 1
    val = max_id
  return val

def init_max_id_from_db(db = db_path):
  global max_id
  try:
    conn = lite.connect(db)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(id) FROM dnd_characters")
    row = cursor.fetchone()
    max_id = (row[0] or 0) + 1
  except Exception as e:
    logging.error(f"Failed to initialize max_id from database: {e}")
  finally:
    conn.close()

#initialize cache
dnd_cache = DnD_Cache()

#These are the levels each class gets its subclass
subclass_levels = {
  "barbarian": 3,
  "fighter": 3,
  "paladin": 3,
  "ranger": 3,
  "artificer": 3,
  "bard": 3,
  "cleric": 1,
  "druid": 2,
  "monk": 3,
  "rogue": 3,
  "warlock": 1,
  "sorcerer": 1,
  "wizard": 2
}

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
  "feats", "hp", "ac", "ms", "exhaustion", "proficiencies", "Id", "notes"
  )
  def __init__(self, 
               owner: int,
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
               notes: list = None,
               spells: dict = None,
               spell_slots: dict = None,
               points: dict = None,
               ms: int = 30,
               languages: list = None,
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
    self.notes = notes or []
    self.abilities = abilities or []
    self.spell_slots = spell_slots or {} #type: [current, max]
    self.spells = spells or {} #prepared or known, depending on class {"known": {level: [spells]}, "prepared": {level: [spells]}}
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
  def __repr__(self):
    return f"<DnD_Char {self.name} (ID {self.Id}), Level {self.get_level()}>"
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
          self.spells["known"][key] = []
        self.spells["known"][key].extend(val)
    if feat_add:
      for feat in feats:
        self.feats.append(feat)
    if new_class in self.classes:
      self.classes[new_class] += 1
    else:
      self.classes[new_class] = 1
    if new_class.lower() in ["cleric","sorcerer","warlock"] and self.classes[new_class] >= 1 and new_class.lower() not in self.subclasses:
      self.add_new_subclass(new_class.lower(), subclass)
    elif new_class.lower() not in ["cleric","sorcerer","warlock"] and self.classes[new_class] >= 3 and new_class.lower() not in self.subclasses:
      self.add_new_subclass(new_class.lower(), subclass)
    hp_gain = max(1, hp_roll + ((self.stats["con"] - 10) // 2))
    self.hp[1] += hp_gain
    self.hp[0] += hp_gain
  def use_points(self, type, val):
    if self.points[type][0] >= val:
      self.points[type][0] -= val
  def change_max_points(self, type, val):
    if type in self.points:
      self.points[type][1] = val
    else:
      self.points[type] = [val, val]
  def cast_spell(self, level):
    if level in self.spell_slots and self.spell_slots[level][0] > 0:
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
      "ms": self.ms,
      "notes": json.dumps(self.notes)
    }
  def to_db(self, conn):
    cursor = conn.cursor()
    main_data = self.to_dict()
    cursor.execute("""
    INSERT INTO dnd_characters (
      id, owner, name, race, background, classes, hit_dice, stats, hp, ac, xp,
      points, languages, equipment, feats, exhaustion, ms, notes
    ) VALUES (
      :id, :owner, :name, :race, :background, :classes, :hit_dice, :stats, :hp, :ac, :xp,
      :points, :languages, :equipment, :feats, :exhaustion, :ms, :notes
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
      ms = excluded.ms,
      notes = excluded.notes
    """, main_data)
    # Update related tables
    cursor.execute("DELETE FROM character_classes WHERE character_id = ?", (self.Id,))
    for cls, level in self.classes.items():
      subclass = self.subclasses.get(cls, "")
      cursor.execute("""
      INSERT INTO character_classes (character_id, class_name, level, subclass)
      VALUES (?, ?, ?, ?)
      """, (self.Id, cls, level, subclass))
    cursor.execute("REPLACE INTO spells (character_id, spells) VALUES (?, ?)", 
                   (self.Id, json.dumps(self.spells)))
    cursor.execute("REPLACE INTO spell_slots (character_id, slots) VALUES (?, ?)", 
                   (self.Id, json.dumps(self.spell_slots)))
    cursor.execute("REPLACE INTO proficiencies (character_id, proficiencies) VALUES (?, ?)", 
                   (self.Id, json.dumps(self.proficiencies)))
    conn.commit()
  @classmethod
  def from_db(cls, conn, character_id):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM dnd_characters WHERE id = ?", (character_id,))
    row = cursor.fetchone()
    if not row:
      raise ValueError(f"Character ID {character_id} not found")

    cursor.execute("SELECT class_name, level, subclass FROM character_classes WHERE character_id = ?", (character_id,))
    class_rows = cursor.fetchall()
    classes = {}
    subclasses = {}
    for r in class_rows:
      classes[r[0]] = r[1]
      subclasses[r[0]] = r[2]

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
              hit_dice = json.loads(row["hit_dice"]) if "hit_dice" in row.keys() else {},
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
              exhaustion = row["exhaustion"] if "exhaustion" in row.keys() else 0,
              notes = json.loads(row["notes"] if "notes" in row.keys() else "[]")
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

def update_users_table(cache: DnD_Cache, conn):
    cursor = conn.cursor()
    # Group characters by owner
    user_char_map = {}
    for char in cache.all_characters():
        user_id = char.owner
        if user_id not in user_char_map:
            user_char_map[user_id] = []
        user_char_map[user_id].append(char.Id)
    #remove users from table who have no characters
    cursor.execute("SELECT user_id FROM users")
    existing_users = {row[0] for row in cursor.fetchall()}
    current_users = set(user_char_map.keys())
    stale_users = existing_users - current_users
    for user_id in stale_users:
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    # Update users table
    for user_id, char_ids in user_char_map.items():
        chars_json = json.dumps(char_ids)
        n_chars = len(char_ids)
        # This assumes username is unknown at this stage (or fetched elsewhere)
        # You can pass in a username dictionary if needed
        cursor.execute("""
        INSERT INTO users (user_id, chars, n_chars)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
          chars = excluded.chars,
          n_chars = excluded.n_chars
        """, (user_id, chars_json, n_chars))
      conn.commit()

#pushing the dnd character cache to a database
def push_dnd_cache_to_db(cache: DnD_Cache, db: str):
  if cache.is_empty():
    logging.info("Character cache is empty. Skipping database push.")
    return
  try:
    conn = lite.connect(db)
    conn.row_factory = lite.Row

    chars = list(cache.all_characters())
    logging.info(f"Starting push of {len(chars)} characters to database.")
    
    for character in chars:
      character.to_db(conn)
    #update the users table
    update_users_table(cache, conn) 
    conn.commit()
    logging.info(f"Pushed {len(chars)} characters to database.")
    cache.clear()
    logging.info("Cache cleared after successful push.")

  except Exception as e:
    if 'conn' in locals():
      conn.rollback()
    logging.error(f"Failed to push characters to database: {e}")
  finally:
    if 'conn' in locals():
      conn.close()

#automate cache push to database
def schedule_push(cache, db_path, interval_seconds = 7200):
  def loop():
    while True:
      try:
        push_dnd_cache_to_db(cache, db_path)
      except Exception as e:
        logging.error(f"Scheduled push failed: {e}")
      time.sleep(interval_seconds)
  thread = threading.Thread(target = loop, daemon = True)
  thread.start()
  logging.info(f"Started Scheduled cache push every {interval_seconds} seconds.")
  
#initialize connection to database
def init_db(db_path = db_path):
  conn = lite.connect(db_path)
  cursor = conn.cursor()
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    chars TEXT,
    n_chars INTEGER
  );
  """)
  #Not adding a foreign key on user id/owner as this data may be used to train an ML model
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS dnd_characters (
    id INTEGER PRIMARY KEY,
    owner INTEGER,
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
    ms INTEGER -- move speed,
    notes TEXT -- JSON ["Note1", ...]
    FOREIGN KEY (owner) REFERENCES users(user_id)
  );
  """)
  #For multiclass support
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS character_classes (
    character_id INTEGER,
    class_name TEXT,
    level INTEGER,
    subclass TEXT,
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
    spells TEXT, -- JSON {"known": {"cantrip": [...],...}, "prepared": {"cantrip": [...],...}}
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

#Get the highest character ID from the table
def update_max_id():
  global max_id
  conn = None
  try:
    conn = lite.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(id) FROM dnd_characters")
    result = cursor.fetchone()
    max_id = result[0] + 1 if result[0] is not None else 1
    logging.info(f"Max ID initialized to {max_id}")
  except Exception as e:
    logging.error(f"Error initializing max_id: {e}")
    max_id = 1
  finally:
    if conn:
      conn.close()
#Function to check tables for entries
#This is necessary to populate the ID iterator correctly in runtime cache of characters
def check_for_entries(table_name, db = db_path):
  #returns True if there are one or more entires, False otherwise
  #Return: bool: True if 1 or more entries, False otherwise
  conn = None
  allowed_tables = {"dnd_characters", "users", "spells", "spell_slots", "proficiencies", "character_classes"}
  if table_name not in allowed_tables:
    raise ValueError("Invalid table name")
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

#a class to handle getting multiple classes with levels as an interactive prompt in character creation
class ClassLevelModal(ui.Modal, title = "Add a Class"):
  class_name = ui.TextInput(label = "Class", placeholder = "eg. wizard", required = True)
  level = ui.TextInput(label = f"Level", placeholder = "eg. 1", required = True)
  def __init__(self, existing_classes):
    super().__init__(title = "Add a class", custom_id = "class_level_modal")
    self.existing_classes = existing_classes
    self.result = None
  async def on_submit(self, interaction: discord.Interaction):
    cls = self.class_name.value.strip().lower()
    lvl = self.level.value.strip()
    if cls not in class_dice:
      await interaction.response.send_message(f"Invalid class selection: {cls}. Supported classes: {', '.join(class_dice)}", ephemeral = True)
      return
    try:
      lvl = int(lvl)
      if lvl < 1 or lvl > 20:
        raise ValueError
    except ValueError:
      await interaction.response.send_message("Level must be a number between 1 and 20.", ephemeral = True)
      return
    if cls in self.existing_classes:
      await interaction.response.send_message(f"The class {cls} is already in your list. Each class can only be added once.", ephemeral = True)
      return
    self.result = (cls, lvl)
    await interaction.response.send_message(f"Added {cls} at level {lvl}.", ephemeral = True)

#Interactive view to loop until user done entering classes
class ClassLoopView(ui.View):
  def __init__(self, timeout = 500):
    super().__init__(timeout = timeout)
    self.class_data = {}
    self.finished = False
  @discord.ui.button(label = "Add Class", style = discord.ButtonStyle.primary)
  async def add_class(self, interaction: discord.Interaction, button: ui.Button):
    await interaction.response.send_message(f"Please add a class from the following list of classes: {", ".join(class_dice)}", ephemeral = True)
    modal = ClassLevelModal(existing_classes = self.class_data)
    await interaction.response.send_modal(modal)
    def check(i): return i.user == interaction.user and i.type.name == "modal_submit" and i.data.get("custom_id") == "class_level_modal"
    try:
      modal_interaction = await interaction.client.wait_for("interaction", check=check, timeout=300)
    except asyncio.TimeoutError:
      await interaction.followup.send("Modal timed out.", ephemeral = True)
      return
    if modal.result:
      cls, lvl = modal.result
      self.class_data[cls] = lvl
  @discord.ui.button(label = "Finish", style = discord.ButtonStyle.success)
  async def finish(self, interaction: discord.Interaction, button = ui.Button):
    if not self.class_data:
      await interaction.followup.send("Please add at least one class.", ephemeral = True)
      return
    self.finished = True
    self.stop()
    class_summary = "\n".join([f"{cls.title()} - Level {lvl}" for cls, lvl in self.class_data.items()])
    await interaction.followup.send(f"Final class breakdown:\n{class_summary}", ephemeral = True)

class SubclassModal(ui.Modal, title = "Add Subclass"):
  subclass = ui.TextInput(label = "Subclass Name", placeholder = "eg.; Circle of the Moon", required = True, max_length = 50)
  def __init__(self, view):
    super().__init__(title = "Add Subclass", timeout = 180, custom_id = "subclass_modal")
    self.view = view
    self.add_item(self.subclass)
  async def on_submit(self, interaction: discord.Interaction):
    name = self.subclass.value.strip().lower()
    if not name:
      await interaction.response.send_message("Subclass name cannot be empty.", ephemeral = True)
      return
    self.view.subclass = name
    await interaction.response.send_message(f"Added {name} as subclass.", ephemeral = True)

class SubclassView(ui.View):
  def __init__(self):
    super().__init__(timeout = 300)
    self.subclass = ""
    self.finished = False
  @discord.ui.button(label = "Add subclass", style = discord.ButtonStyle.primary)
  async def add_subclass(self, interaction: discord.Interaction, button: ui.Button):
    modal = SubclassModal(view = self)
    await interaction.response.send_modal(modal)
    def check(i): return i.user == interaction.user and i.type.name == "modal_submit" and i.data.get("custom_id") == "subclass_modal"
    try:
      await interaction.client.wait_for("interaction", check = check, timeout = 300)
    except asyncio.TimeoutError:
      await interaction.followup.send("Subclass entry timed out.", ephemeral = True)
  @discord.ui.button(label = "Finish", style = discord.ButtonStyle.success)
  async def finish(self, interaction: discord.Interaction, button: ui.Button):
    self.finished = True
    self.stop()
    if self.subclass == "":
      await interaction.response.send_message("No subclass added.\nYour class level indicates you should have a subclass.\nAdd one later.", ephemeral = True)
    else:
      await interaction.response.send_message("Subclass entry complete.", ephemeral = True)

class ProficiencyModal(ui.Modal, title = "Add Proficiency"):
  proficiency = ui.TextInput(label = "Proficiency name", placeholder = "eg.; str, athletics, thieves tools etc", required = True, max_length = 50)
  level = ui.TextInput(label = "Proficiency level (1 = Proficient, 2 = Expertise)", placeholder = "Enter 1 or 2", required = True, max_length = 1)
  def __init__(self, view):
    super().__init__(title="Add Proficiency", timeout=180, custom_id="proficiency_modal")
    self.view = view
    self.add_item(self.proficiency)
    self.add_item(self.level)
  async def on_submit(self, interaction: discord.Interaction):
    name = self.proficiency.value.strip().lower()
    level = self.level.value.strip()
    if level not in ("1", "2"):
      await interaction.response.send_message("Level must be 1 or 2. Please try again.", ephemeral = True)
      return
    if not name:
      await interaction.response.send_message("Proficiency name cannot be empty", ephemeral = True)
      return
    if name in self.view.proficiencies:
      await interaction.response.send_message(f"{name} already added.", ephemeral = True)
      return
    self.view.proficiencies[name] = int(level)
    await interaction.response.send_message(f"Added: {name} (Level {level})", ephemeral = True)

class ProficiencyView(ui.View):
  def __init__(self):
    super().__init__(timeout = 300)
    self.proficiencies = {}
    self.finished = False
  @discord.ui.button(label = "Add Proficiency", style = discord.ButtonStyle.primary)
  async def add_proficiency(self, interaction: discord.Interaction, button: ui.Button):
    modal = ProficiencyModal(view = self)
    await interaction.response.send_modal(modal)
    def check(i): return i.user == interaction.user and i.type.name == "modal_submit" and i.data.get("custom_id") == "proficiency_modal"
    try:
      await interaction.client.wait_for("interaction", check = check, timeout = 300)
    except asyncio.TimeoutError:
      await interaction.followup.send("Proficiency entry timed out.", ephemeral = True)
  @discord.ui.button(label = "Finish", style = discord.ButtonStyle.success)
  async def finish(self, interaction: discord.Interaction, button: ui.Button):
    self.finished = True
    self.stop()
    if not self.proficiencies:
      await interaction.response.send_message("No proficiencies added.", ephemeral = True)
    else:
      proficiency_summary = "\n".join([f"{prof.title()} - Level {lvl}" for prof, lvl in self.proficiencies.items()])
      await interaction.response.send_message(f"Added proficiencies:\n{proficiency_summary}", ephemeral = True)
    

class SpellsModal(ui.Modal, title = "Add Spell"):
  spell = ui.TextInput(label = "Spell Name", placeholder = "eg.; fireball", required = True, max_length = 30)
  level = ui.TextInput(label = "Spell Level (cantrip or 1-9)", placeholder = "eg.; (cantrip) or (1)", required = True, max_length = 7)
  def __init__(self, view):
    super().__init__(title = "Add Spell", timeout = 180, custom_id = "spells_modal")
    self.view = view
    self.add_item(self.spell)
    self.add_item(self.level)
  async def on_submit(self, interaction: discord.Interaction):
    name = self.spell.value.strip().lower()
    level = self.level.value.strip()
    approved = {"cantrip"} | {str(i) for i in range(1,10)}
    if level not in approved:
      await interaction.response.send_message("level must either be cantrip or a number 1-9. Please try again.", ephemeral = True)
      return
    self.view.spells[name] = level
    await interaction.response.send_message(f"Added: {name.title()} (Level {level})", ephemeral = True)

class SpellsView(ui.View):
  def __init__(self):
    super().__init__(timeout = 300)
    self.spells = {}
    self.finished = False
  @discord.ui.button(label = "Add spell", style = discord.ButtonStyle.primary)
  async def add_spell(self, interaction: discord.Interaction, button: ui.Button):
    modal = SpellsModal(view = self)
    await interaction.response.send_modal(modal)
    def check(i: discord.Interaction): return i.user == interaction.user and i.type.name == "modal_submit" and i.data.get("custom_id") == "spells_modal"
    try:
      await interaction.client.wait_for("interaction", check = check, timeout = 300)
    except asyncio.TimeoutError:
      await interaction.followup.send("Spell entry timed out.", ephemeral = True)
  @discord.ui.button(label = "Finish", style = discord.ButtonStyle.success)
  async def finish(self, interaction: discord.Interaction, button: ui.Button):
    self.finished = True
    self.stop()
    if not self.spells:
      await interaction.response.send_message("No spells added at this time.", ephemeral = True)
    else:
      spells_summary = "\n".join([f"{spell.title()} - Level {lvl}" for spell, lvl in self.spells.items()])
      await interaction.response.send_message(f"Added spells:\n{spells_summary}", ephemeral = True)

class SpellSlotsModal(ui.Modal, title = "Add spell slots array"):
  level = ui.TextInput(label = "Slot level", placeholder = "eg.; 1", required = True, max_length = 1)
  num = ui.TextInput(label = "Number of Slots for that level", placeholder = "eg.; 3", required = True, max_length = 2)
  def __init__(self, view):
    super().__init__(title = "Add spell slots array", timeout = 180, custom_id = "spellslots_modal")
    self.view = view
    self.add_item(self.level)
    self.add_item(self.num)
  async def on_submit(self, interaction: discord.Interaction):
    level = self.level.value.strip()
    try:
      num = int(self.num.value.strip())
    except ValueError:
      await interaction.response.send_message("Number of slots must be a valid integer.", ephemeral = True)
      return
    approved = {str(i) for i in range(1,10)}
    if level not in approved:
      await interaction.response.send_message("level must be a number 1-9. Please try again.", ephemeral = True)
      return
    self.view.slots[level] = num
    await interaction.response.send_message(f"Added {num} slots at level {level}", ephemeral = True)

class SpellSlotsView(ui.View):
  def __init__(self):
    super().__init__(timeout = 300)
    self.slots = {}
    self.finished = False
  @discord.ui.button(label = "Add spell slot level", style = discord.ButtonStyle.primary)
  async def add_spell_slot(self, interaction: discord.Interaction, button: ui.Button):
    modal = SpellSlotsModal(view = self)
    await interaction.response.send_modal(modal)
    def check(i): return i.user == interaction.user and i.type.name == "modal_submit" and i.data.get("custom_id") == "spellslots_modal"
    try:
      await interaction.client.wait_for("interaction", check = check, timeout = 300)
    except asyncio.TimeoutError:
      await interaction.followup.send("Spell slot entry timed out.", ephemeral = True)
  @discord.ui.button(label = "Finish", style = discord.ButtonStyle.success)
  async def finish(self, interaction: discord.Interaction, button: ui.Button):
    self.finished = True
    self.stop()
    if not self.slots:
      await interaction.response.send_message("No changes entered.", ephemeral = True)
    else:
      slots_summary = "\n".join([f"Level: {lvl} - Number: {num}" for lvl, num in sorted(self.slots.items(), key = lambda x: int(x[0]))])
      await interaction.response.send_message(f"Changes summary:\n{slots_summary}", ephemeral = True)

class FeatsModal(ui.Modal, title = "Add feats"):
  feat = ui.TextInput(label = "Feat Name", placeholder = "eg.; Sharpshooter", max_length = 50)
  def __init__(self, view):
    super().__init__(title = "Add feat", timeout = 300, custom_id = "feats_modal")
    self.view = view
    self.add_item(self.feat)
  async def on_submit(self, interaction: discord.Interaction):
    name = self.feat.value.strip()
    self.view.feats.append(name)
    await interaction.response.send_message(f"Added {name.title()} to list of feats.", ephemeral = True)

class FeatsView(ui.View):
  def __init__(self):
    super().__init(timeout = 300)
    self.feats = []
    self.finished = False
  @discord.ui.button(label = "Add a feat", style = discord.ButtonStyle.primary)
  async def add_feat(self, interaction: discord.Interaction, button: ui.Button):
    modal = FeatsModal(view = self)
    await interaction.response.send_modal(modal)
    def check(i): return i.user == interaction.user and i.type.name == "modal_submit" and i.data.get("custom_id") == "feats_modal"
    try:
      await interaction.client.wait_for("interaction", check = check, timeout = 300)
    except asyncio.TimeoutError:
      await interaction.followup.send("Feat entry timed out.", ephemeral = True)
  @discord.ui.button(label = "Finish", style = discord.ButtonStyle.success)
  async def finish(self, interaction: discord.Interaction, button: ui.Button):
    self.finished = True
    self.stop()
    if not self.feats:
      await interaction.response.send_message("No feats added at this time.", ephemeral = True)
    else:
      feats_summary = "\n".join(self.feats)
      await interaction.response.send_message(f"Feats added summary:\n{feats_summary}", ephemeral = True)

class EquipmentModal(ui.Modal, title = "Add equipment"):
  equipment = ui.TextInput(label = "Item Name", placeholder = "eg.; Gold", max_length = 50)
  num = ui.TextInput(label = "Number held", placeholder = "eg.; 500", max_length = 10)
  def __init__(self, view):
    super().__init__(title = "Add equipment", timeout = 300, custom_id = "equipment_modal")
    self.view = view
    self.add_item(self.equipment)
    self.add_item(self.num)
  async def on_submit(self, interaction: discord.Interaction):
    name = self.equipment.value.strip()
    try:
      num = int(self.num.value.strip())
    except ValueError:
      await interaction.response.send_message("Amount must be a valid integer.", ephemeral = True)
      return
    self.view.equipment[name] = num
    await interaction.response.send_message(f"Item: {name.title()} - Amount: {num}", ephemeral = True)

class EquipmentView(ui.View):
  def __init__(self):
    super().__init(timeout = 300)
    self.equipment = {}
    self.finished = False
  @discord.ui.button(label = "Add an item", style = discord.ButtonStyle.primary)
  async def add_item(self, interaction: discord.Interaction, button: ui.Button):
    modal = EquipmentModal(view = self)
    await interaction.response.send_modal(modal)
    def check(i): return i.user == interaction.user and i.type.name == "modal_submit" and i.data.get("custom_id") == "equipment_modal"
    try:
      await interaction.client.wait_for("interaction", check = check, timeout = 300)
    except asyncio.TimeoutError:
      await interaction.followup.send("Equipment entry timed out.", ephemeral = True)
  @discord.ui.button(label = "Finish", style = discord.ButtonStyle.success)
  async def finish(self, interaction: discord.Interaction, button: ui.Button):
    self.finished = True
    self.stop()
    if not self.equipment:
      await interaction.response.send_message("No items or money added at this time.", ephemeral = True)
    else:
      items_summary = "\n".join([f"Item: {item} - Amount: {num}" for item, num in self.equipment.items()])
      await interaction.response.send_message(f"Items added summary:\n{items_summary}", ephemeral = True)

class AbilitiesModal(ui.Modal, title = "Add Abilities"):
  ability = ui.TextInput(label = "Ability Name", placeholder = "eg.; Hunter's Mark", max_length = 50)
  def __init__(self, view):
    super().__init__(title = "Add Abilities", timeout = 300, custom_id = "abilities_modal")
    self.view = view
    self.add_item(self.ability)
  async def on_submit(self, interaction: discord.Interaction):
    name = self.ability.value.strip()
    self.view.abilities.append(name)
    await interaction.response.send_message(f"Added {name.title()} to list of abilities.", ephemeral = True)

class AbilitiesView(ui.View):
  def __init__(self):
    super().__init(timeout = 300)
    self.abilities = []
    self.finished = False
  @discord.ui.button(label = "Add an ability", style = discord.ButtonStyle.primary)
  async def add_ability(self, interaction: discord.Interaction, button: ui.Button):
    modal = AbilitiesModal(view = self)
    await interaction.response.send_modal(modal)
    def check(i): return i.user == interaction.user and i.type.name == "modal_submit" and i.data.get("custom_id") == "abilities_modal"
    try:
      await interaction.client.wait_for("interaction", check = check, timeout = 300)
    except asyncio.TimeoutError:
      await interaction.followup.send("Ability entry timed out.", ephemeral = True)
  @discord.ui.button(label = "Finish", style = discord.ButtonStyle.success)
  async def finish(self, interaction: discord.Interaction, button: ui.Button):
    self.finished = True
    self.stop()
    if not self.abilities:
      await interaction.response.send_message("No abilities added at this time.", ephemeral = True)
    else:
      abilities_summary = "\n".join(self.abilities)
      await interaction.response.send_message(f"Abilities added summary:\n{abilities_summary}", ephemeral = True)

class PointsModal(ui.Modal, title = "Add expendable points"):
  point = ui.TextInput(label = "Point Name", placeholder = "eg.; Sorcery Points or Bardic Inspiration", max_length = 50)
  num = ui.TextInput(label = "Maximum number", placeholder = "eg.; 5", max_length = 3)
  def __init__(self, view):
    super().__init__(title = "Add expendable points", timeout = 300, custom_id = "points_modal")
    self.view = view
    self.add_item(self.point)
    self.add_item(self.num)
  async def on_submit(self, interaction: discord.Interaction):
    name = self.point.value.strip()
    try:
      num = int(self.num.value.strip())
    except ValueError:
      await interaction.response.send_message("Number must be a valid integer.", ephemeral = True)
      return
    self.view.points[name] = num
    await interaction.response.send_message(f"Type: {name.title()} - Amount: {num}", ephemeral = True)

class PointsView(ui.View):
  def __init__(self):
    super().__init(timeout = 300)
    self.points = {}
    self.finished = False
  @discord.ui.button(label = "Add a point type", style = discord.ButtonStyle.primary)
  async def add_point(self, interaction: discord.Interaction, button: ui.Button):
    modal = PointsModal(view = self)
    await interaction.response.send_modal(modal)
    def check(i): return i.user == interaction.user and i.type.name == "modal_submit" and i.data.get("custom_id") == "points_modal"
    try:
      await interaction.client.wait_for("interaction", check = check, timeout = 300)
    except asyncio.TimeoutError:
      await interaction.followup.send("Point entry timed out.", ephemeral = True)
  @discord.ui.button(label = "Finish", style = discord.ButtonStyle.success)
  async def finish(self, interaction: discord.Interaction, button: ui.Button):
    self.finished = True
    self.stop()
    if not self.points:
      await interaction.response.send_message("No expendable points added at this time.", ephemeral = True)
    else:
      items_summary = "\n".join([f"Type: {item} - Max: {num}" for item, num in self.points.items()])
      await interaction.response.send_message(f"Points added summary:\n{items_summary}", ephemeral = True)

class LanguagesModal(ui.Modal, title = "Add Languages"):
  language = ui.TextInput(label = "Language Name", placeholder = "eg.; Common", max_length = 50)
  def __init__(self, view):
    super().__init__(title = "Add Languages", timeout = 300, custom_id = "languages_modal")
    self.view = view
    self.add_item(self.language)
  async def on_submit(self, interaction: discord.Interaction):
    name = self.language.value.strip()
    self.view.languages.append(name)
    await interaction.response.send_message(f"Added {name.title()} to list of languages.", ephemeral = True)

class LanguagesView(ui.View):
  def __init__(self):
    super().__init(timeout = 300)
    self.languages = []
    self.finished = False
  @discord.ui.button(label = "Add a language", style = discord.ButtonStyle.primary)
  async def add_language(self, interaction: discord.Interaction, button: ui.Button):
    modal = LanguagesModal(view = self)
    await interaction.response.send_modal(modal)
    def check(i): return i.user == interaction.user and i.type.name == "modal_submit" and i.data.get("custom_id") == "languages_modal"
    try:
      await interaction.client.wait_for("interaction", check = check, timeout = 300)
    except asyncio.TimeoutError:
      await interaction.followup.send("Language entry timed out.", ephemeral = True)
  @discord.ui.button(label = "Finish", style = discord.ButtonStyle.success)
  async def finish(self, interaction: discord.Interaction, button: ui.Button):
    self.finished = True
    self.stop()
    if not self.languages:
      await interaction.response.send_message("No languages added at this time.", ephemeral = True)
    else:
      summary = "\n".join(self.languages)
      await interaction.response.send_message(f"Languages added summary:\n{summary}", ephemeral = True)

class NotesModal(ui.Modal, title = "Add Notes"):
  note = ui.TextInput(label = "Note", placeholder = "eg.; The shopkeeper hates us", max_length = 500)
  def __init__(self, view):
    super().__init__(title = "Add Notes", timeout = 500, custom_id = "notes_modal")
    self.view = view
    self.add_item(self.note)
  async def on_submit(self, interaction: discord.Interaction):
    name = self.note.value.strip()
    self.view.notes.append(name)
    await interaction.response.send_message(f"Added a note.\n{name}", ephemeral = True)

class NotesView(ui.View):
  def __init__(self):
    super().__init(timeout = 300)
    self.notes = []
    self.finished = False
  @discord.ui.button(label = "Add a note", style = discord.ButtonStyle.primary)
  async def add_note(self, interaction: discord.Interaction, button: ui.Button):
    modal = NotesModal(view = self)
    await interaction.response.send_modal(modal)
    def check(i): return i.user == interaction.user and i.type.name == "modal_submit" and i.data.get("custom_id") == "notes_modal"
    try:
      await interaction.client.wait_for("interaction", check = check, timeout = 500)
    except asyncio.TimeoutError:
      await interaction.followup.send("Note entry timed out.", ephemeral = True)
  @discord.ui.button(label = "Finish", style = discord.ButtonStyle.success)
  async def finish(self, interaction: discord.Interaction, button: ui.Button):
    self.finished = True
    self.stop()
    if not self.notes:
      await interaction.response.send_message("No notes added at this time.", ephemeral = True)
    else:
      summary = "\n".join(self.notes)
      await interaction.response.send_message(f"Notes added summary:\n{summary}", ephemeral = True)

async def machine_type_autocomplete(interaction: discord.Interaction, current: str):
  return [
    app_commands.Choice(name = mt, value = mt)
    for mt in MACHINE_TYPES
    if current.lower() in mt.lower()
  ]
  
@bot.event
async def on_ready():
  await bot.tree.sync()
  await init_db()
  await init_max_id_from_db()
  print(f"Logged in as {bot.user}")

#dice roller
@bot.tree.command(name = 'roll', description = 'Roll some dice!')
@app_commands.describe(dice = "Dice roll in ndm or ndm+x or ndm-x format (ie 1d6+2)")
async def roll(interaction: discord.Interaction, dice: str = "1d6+0"):
  match = re.fullmatch(r"(\d+)d(\d+)([+-]\d+)?", dice)
  if not match:
    await interaction.response.send_message("Invalid format. Please use ndm+x like 2d6+0 or 1d20-3.", ephemeral = True)
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

  await interaction.response.send_message(f"Rolling {num}d{sides}:\nResults: {roll_text}\n**Total: {total}**")

#enter a character that is already built elsewhere to the database
@bot.tree.command(name = "add_character", description = "Add a character that you already have built to your account (Interactive)")
@app_commands.describe(name = "Character Name",
                       race = "Character race",
                       max_hp = "Maximum HP",
                       current_hp = "Current HP",
                       ac = "Armor Class",
                       ms = "Move Speed",
                       xp = "Experience Points, (default 0 if not using xp)",
                       background = "Character background",
                       str_stat = "Strength ability score",
                       dex_stat = "Dexterity ability score",
                       con_stat = "Constitution ability score",
                       int_stat = "Intelligence ability score",
                       wis_stat = "Wisdom ability score",
                       cha_stat = "Charisma ability score")
async def add_character(interaction: discord.Interaction,
                        name: str,
                        race: str,
                        max_hp: int,
                        current_hp: int,
                        ac: int,
                        ms: int,
                        xp: int = 0,
                        background: str,
                        str_stat: int,
                        dex_stat: int,
                        con_stat: int,
                        int_stat: int,
                        wis_stat: int,
                        cha_stat: int):
                          #Get the stat array into a dictionary
                          stats = {"str": str_stat,
                                  "dex": dex_stat,
                                  "con": con_stat,
                                  "int": int_stat,
                                  "wis": wis_stat,
                                  "cha": cha_stat}
                          owner = interaction.user.id
                          #set hp
                          hp = [current_hp, max_hp]
                          #for iterative interactive command prompting checks
                          def check(m):
                            return m.author.id == interaction.user.id and m.channel == interaction.channel
                          #Get the classes
                          class_view = ClassLoopView()
                          await interaction.response.send_message("Let's add your character's classes.", ephemeral = True)
                          await interaction.followup.send(view = class_view, ephemeral = True)
                          await class_view.wait()
                          subclasses = {}
                          if not class_view.class_data:
                            await interaction.followup.send("No classes entered. Character creation cancelled.")
                            return
                          if class_view.finished:
                            classes = class_view.class_data
                            hit_dice = {}
                            for cls in classes:
                              die = class_dice[cls]
                              if die not in hit_dice:
                                hit_dice[die] = [classes[cls], classes[cls]]
                              else:
                                hit_dice[die][0] += classes[cls]
                                hit_dice[die][1] += classes[cls]
                              if classes[cls] >= subclass_levels[cls]:
                                subclass_view = SubclassView()
                                await interaction.followup.send(f"Your level in {cls.title()} indicates you should have a subclass.\nAdd it now.", ephemeral = True)
                                await interaction.followup.send(view = subclass_view, ephemeral = True)
                                await subclass_view.wait()
                                if subclass_view.finished:
                                  subclasses[cls] = subclass_view.subclass
                          #add proficiencies
                          proficiencies = {}
                          prof_view = ProficiencyView()
                          await interaction.followup.send("Let's add your proficiencies, including saves, abilities, and items.", ephemeral = True)
                          await interaction.followup.send(view = prof_view, ephemeral = True)
                          await prof_view.wait()
                          if prof_view.finished:
                            proficiencies = prof_view.proficiencies
                          #add known spells
                          spells_known = {}
                          spells_view = SpellsView()
                          await interaction.followup.send("Let's add your known spells.\nIf your class knows the whole list and only prepares spells, skip this step.\nSkip if you don't cast spells.", ephemeral = True)
                          await interaction.followup.send(view = spells_view, ephemeral = True)
                          await spells_view.wait()
                          if spells_view.finished and spells_view.spells:
                            #need to flip dictionary from {spell: level} to {level: [spells]}
                            for spell, lvl in spells_view.spells.items():
                              spells_known.setdefault(lvl, []).append(spell)
                          #add prepared spells
                          spells_prepared = {}
                          prep_view = SpellsView()
                          await interaction.followup.send("Let's add your prepared spells.\nIf your class does not prepare spells, skip this step.\nSkip if you don't cast spells.", ephemeral = True)
                          await interaction.followup.send(view = prep_view, ephemeral = True)
                          await prep_view.wait()
                          if prep_view.finished:
                            if prep_view.spells:
                              for spell, lvl in prep_view.spells.items():
                                if lvl not in spells_prepared:
                                  spells_prepared[lvl] = [spell]
                                else:
                                  spells_prepared[lvl].append(spell)
                          #Add spell slots
                          spell_slots = {}
                          slots_view = SpellSlotsView()
                          await interaction.followup.send("Let's add your spell slots array.\nIf your character does not need spell slots, skip this step.", ephemeral = True)
                          await interaction.followup.send(view = slots_view, ephemeral = True)
                          await slots_view.wait()
                          if slots_view.finished and slots_view.slots:
                            for lvl, num in slots_view.slots.items():
                              spell_slots[lvl] = [num, num]
                          #add feats
                          feats = []
                          feats_view = FeatsView()
                          await interaction.followup.send("Add any feats your character has.\nIf you don't have any feats, just select Finished.", ephemeral = True)
                          await interaction.followup.send(view = feats_view, ephemeral = True)
                          await feats_view.wait()
                          if feats_view.finished and feats_view.feats:
                            feats = feats_view.feats
                          #add equipment, including gold/silver/etc
                          equipment = {}
                          equipment_view = EquipmentView()
                          await interaction.followup.send("Add any money or equipment.", ephemeral = True)
                          await interaction.followup.send(view = equipment_view, ephemeral = True)
                          await equipment_view.wait()
                          if equipment_view.finished and equipment_view.equipment:
                            equipment = equipment_view.equipment
                          #add abilities
                          abilities = []
                          abilities_view = AbilitiesView()
                          await interaction.followup.send("Add any character abilities.", ephemeral = True)
                          await interaction.followup.send(view = abilities_view, ephemeral = True)
                          await abilities_view.wait()
                          if abilities_view.finished and abilities_view.abilities:
                            abilities = abilities_view.abilities
                          #add expendable points like bardic inspiration or action surge
                          points = {}
                          points_view = PointsView()
                          await interaction.followup.send("Add expendable points.\nExamples include Sorcery Points, Action Surge, and Bardic Inspiration.", ephemeral = True)
                          await interaction.followup.send(view = points_view, ephemeral = True)
                          await points_view.wait()
                          if points_view.finished and points_view.points:
                            points = points_view.points
                          #Add languages known
                          languages = []
                          langs_view = LanguagesView()
                          await interaction.followup.send("Add languages known.", ephemeral = True)
                          await interaction.followup.send(view = langs_view, ephemeral = True)
                          await langs_view.wait()
                          if langs_view.finished and langs_view.languages:
                            languages = langs_view.languages
                          #add notes
                          notes = []
                          notes_view = NotesView()
                          await interaction.followup.send("Add campaign or character notes.", ephemeral = True)
                          await interaction.followup.send(view = notes_view, ephemeral = True)
                          await notes_view.wait()
                          if notes_view.finished and notes_view.notes:
                            notes = notes_view.notes
                          #Set exhaustion elvel to 0
                          exhaustion = 0
                          #generate character id
                          char_id = get_next_id()
                          #create dnd_character object
                          character = DnD_Char(
                            owner = owner,
                            name = name,
                            race = race,
                            background = background,
                            classes = classes,
                            hit_dice = hit_dice,
                            stats = stats,
                            hp = hp,
                            ac = ac,
                            Id = char_id,
                            xp = xp,
                            subclasses = subclasses,
                            abilities = abilities,
                            notes = notes,
                            spells = { "known": spells_known, "prepared": spells_prepared},
                            spell_slots = spell_slots,
                            points = points,
                            ms = ms,
                            languages = languages,
                            equipment = equipment,
                            feats = feats,
                            exhaustion = exhaustion,
                            proficiencies = proficiencies
                          )
                          
                          
                          
                          
#slot machine command (Needed for my campaign so I made it here)
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
