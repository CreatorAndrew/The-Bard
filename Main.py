import os
import requests
import yaml
import asyncio
import typing
import discord
from discord import app_commands
from discord.ext import commands
from Music import Music

class CursorHandler:
    def __init__(self, cursor, integer_data_type, placeholder):
        self.cursor = cursor
        self.integer_data_type = integer_data_type
        self.placeholder = placeholder

    def execute(self, statement, args=tuple()):
        self.cursor.execute(statement.replace("?", self.placeholder).replace("integer", self.integer_data_type), args)

    def fetchall(self): return self.cursor.fetchall()

    def fetchone(self): return self.cursor.fetchone()

class CommandTranslator(app_commands.Translator):
    async def translate(self, string: app_commands.locale_str, locale: discord.Locale, context: app_commands.TranslationContext) -> "str | None":
        try:
            if os.path.exists(f"{language_directory}/{locale.name}.yaml"):
                return yaml.safe_load(open(f"{language_directory}/{locale.name}.yaml", "r"))["strings"][str(string)]
            return None
        except: return None

class Main(commands.Cog):
    def __init__(self, bot, connection, cursor, data, flat_file, guilds, language_directory, lock):
        self.bot = bot
        self.connection = connection
        self.cursor = cursor
        self.data = data
        self.flat_file = flat_file
        self.language_directory = language_directory
        self.lock = lock
        self.guilds = guilds
        self.default_language = "american_english"
        self.init_guilds()
        self.set_language_options()

    def init_guilds(self):
        if self.cursor is None:
            guilds = self.data["guilds"]
            id = "id"
            language = "language"
            keep = "keep"
            repeat = "repeat"
        else:
            self.cursor.execute("select guild_id, guild_lang, keep_in_voice, repeat_queue from guilds")
            guilds = self.cursor.fetchall()
            id = 0
            language = 1
            keep = 2
            repeat = 3
        for guild in guilds:
            self.guilds[str(guild[id])] = {"language": guild[language],
                                           "strings": yaml.safe_load(open(f"{self.language_directory}/{guild[language]}.yaml", "r"))["strings"],
                                           "keep": guild[keep],
                                           "repeat": guild[repeat],
                                           "queue": [],
                                           "index": 0,
                                           "time": .0,
                                           "volume": 1.0,
                                           "connected": False}

    def set_language_options(self):
        self.language_options = []
        for language_file in sorted(os.listdir(self.language_directory)):
            if language_file.endswith(".yaml"):
                language = yaml.safe_load(open(f"{self.language_directory}/{language_file}", "r"))["name"]
                self.language_options.append(app_commands.Choice(name=language, value=language_file.replace(".yaml", "")))

    @app_commands.command(description="language_command_desc")
    async def language_command(self, context: discord.Interaction, set: str=None, add: discord.Attachment=None):
        if self.cursor is None: await self.lock.acquire()
        guild = self.guilds[str(context.guild.id)]
        current_language_file = guild["language"] + ".yaml"
        strings = guild["strings"]
        if add is not None and set is None:
            file_name = str(add)[str(add).rindex("/") + 1:str(add).index("?")]
            if file_name.endswith(".yaml"):
                if not os.path.exists(f"{self.language_directory}/{file_name}"):
                    response = requests.get(str(add))
                    content = yaml.safe_load(response.content.decode("utf-8"))
                    try:
                        if content["strings"]: pass
                    except:
                        await context.response.send_message(strings["invalid_language_file"].replace("%{language_file}", file_name),
                                                            file=discord.File(open(f"{self.language_directory}/{current_language_file}", "r"),
                                                                              filename=current_language_file),
                                                            ephemeral=True)
                        if self.cursor is None: self.lock.release()
                        return
                    for string in yaml.safe_load(open("LanguageStringNames.yaml", "r"))["names"]:
                        try:
                            if content["strings"][string]: pass
                        except:
                            await context.response.send_message(strings["invalid_language_file"].replace("%{language_file}", file_name),
                                                                file=discord.File(open(f"{self.language_directory}/{current_language_file}", "r"),
                                                                                  filename=current_language_file),
                                                                ephemeral=True)
                            if self.cursor is None: self.lock.release()
                            return
                    open(f"{self.language_directory}/{file_name}", "wb").write(response.content)
                else:
                    await context.response.send_message(strings["language_file_exists"].replace("%{language_file}", file_name))
                    if self.cursor is None: self.lock.release()
                    return
                # ensure that the attached language file is fully transferred before the language is changed to it
                while not os.path.exists(f"{self.language_directory}/{file_name}"): await asyncio.sleep(.1)

                self.set_language_options()
                language = file_name.replace(".yaml", "")
        elif add is None and set is not None:
            language = set
            if not os.path.exists(f"{self.language_directory}/{language}.yaml"):
                await context.response.send_message(strings["invalid_language"].replace("%{language}", language).replace("%{bot}", self.bot.user.mention),
                                                    file=discord.File(open(f"{self.language_directory}/{current_language_file}", "r"), filename=current_language_file),
                                                    ephemeral=True)
                if self.cursor is None: self.lock.release()
                return
        elif add is None and set is None:
            await context.response.send_message(strings["language"].replace("%{language}",
                                                                            yaml.safe_load(open(f"{self.language_directory}/{current_language_file}", "r"))["name"]),
                                                ephemeral=True)
            if self.cursor is None: self.lock.release()
            return
        else:
            await context.response.send_message(strings["invalid_command"], ephemeral=True)
            if self.cursor is None: self.lock.release()
            return
        language_data = yaml.safe_load(open(f"{self.language_directory}/{language}.yaml", "r"))
        guild["strings"] = language_data["strings"]
        guild["language"] = language
        if self.cursor is None:
            for guild_searched in self.data["guilds"]:
                if guild_searched["id"] == context.guild.id:
                    guild_searched["language"] = language
                    # modify the flat file for guilds to reflect the change of language
                    yaml.safe_dump(self.data, open(self.flat_file, "w"), indent=4)

                    break
            self.lock.release()
        else:
            self.cursor.execute("update guilds set guild_lang = ? where guild_id = ?", (language, context.guild.id))
            self.connection.commit()
        await context.response.send_message(language_data["strings"]["language_change"].replace("%{language}", language_data["name"]))

    @language_command.autocomplete("set")
    async def language_name_autocompletion(self, context: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
        language_options = []
        for language_option in self.language_options:
            if (current == "" or current.lower() in language_option.name.lower()) and len(language_options) < 25: language_options.append(language_option)
        return language_options

    # add a guild that added this bot to the database or flat file for guilds
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.lock.acquire()
        await self.add_guild(guild)
        self.lock.release()

    # remove a guild that removed this bot from the database or flat file for guilds
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        await self.lock.acquire()
        if self.cursor is None:
            ids = []
            for guild_searched in self.data["guilds"]: ids.append(guild_searched["id"])
            if guild.id in ids: self.data["guilds"].remove(self.data["guilds"][ids.index(guild.id)])
            yaml.safe_dump(self.data, open(self.flat_file, "w"), indent=4)
        else: self.remove_guild_from_database(guild.id)
        del self.guilds[str(guild.id)]
        self.lock.release()

    # add a user that joined a guild with this bot to the database or flat file for guilds
    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.lock.acquire()
        if member.id != self.bot.user.id:
            if self.cursor is None:
                for guild in self.data["guilds"]:
                    if guild["id"] == member.guild.id:
                        self.add_user(guild, member)
                        break
                yaml.safe_dump(self.data, open(self.flat_file, "w"), indent=4)
            else:
                self.add_user(member.guild, member)
                self.connection.commit()
        self.lock.release()

    # remove a user that left a guild with this bot from the database or flat file for guilds
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self.lock.acquire()
        if member.id != self.bot.user.id:
            if self.cursor is None:
                for guild in self.data["guilds"]:
                    if guild["id"] == member.guild.id:
                        ids = []
                        for user in guild["users"]: ids.append(user["id"])
                        if member.id in ids: guild["users"].remove(guild["users"][ids.index(member.id)])
                        break
                yaml.safe_dump(self.data, open(self.flat_file, "w"), indent=4)
            else:
                self.cursor.execute("delete from guild_users where user_id = ? and guild_id = ?", (member.guild.id, member.id))
                self.cursor.execute("delete from users where user_id not in (select user_id from guild_users)")
                self.connection.commit()
        self.lock.release()
    
    @commands.command()
    async def sync_guilds(self, context):
        if context.author.id == variables["master_id"]:
            await self.lock.acquire()
            if self.cursor is None: guild_count = len(self.data["guilds"])
            else:
                self.cursor.execute("select count(guild_id) from guilds")
                guild_count = cursor.fetchone()[0]
            if len(self.bot.guilds) > guild_count:
                async for guild in self.bot.fetch_guilds(): await self.add_guild(guild)
            elif len(self.bot.guilds) < guild_count:
                ids = []
                async for guild in self.bot.fetch_guilds(): ids.append(guild.id)
                if self.cursor is None:
                    index = 0
                    while index < len(self.data["guilds"]):
                        if self.data["guilds"]["id"] not in ids:
                            del self.guilds[str(self.data["guilds"]["id"])]
                            self.data["guilds"].remove(self.data["guilds"][index]) 
                            index -= 1
                        index += 1
                    yaml.safe_dump(self.data, open(flat_file, "w"), indent=4)
                else:
                    self.cursor.execute("select guild_id from guilds")
                    for id in cursor.fetchall():
                        if id[0] not in ids:
                            del self.guilds[str(id[0])]
                            self.remove_guild_from_database(id[0])
            await context.reply(f"Synced all guilds")
            self.lock.release()

    @commands.command()
    async def sync_users(self, context):
        if context.author.id == variables["master_id"]:
            await self.lock.acquire()
            async for guild in self.bot.fetch_guilds():
                if self.cursor is None:
                    for guild_searched in self.data["guilds"]:
                        if guild_searched["id"] == guild.id:
                            guild_index = self.data["guilds"].index(guild_searched)
                            user_count = len(guild_searched["users"])
                            break
                else:
                    self.cursor.execute("select count(user_id) from guild_users where guild_id = ?", (guild.id,))
                    user_count = cursor.fetchone()[0]
                # subtract 1 from the member count to exclude the bot itself
                if len(guild.members) - 1 > user_count:
                    async for user in guild.fetch_members(limit=guild.member_count):
                        if user.id != self.bot.user.id: self.add_user(self.data["guilds"][guild_index]["users"] if self.cursor is None else guild, user)
                # subtract 1 from the member count to exclude the bot itself
                elif len(guild.members) - 1 < user_count:
                    ids = []
                    async for user in guild.fetch_members(limit=guild.member_count):
                        if user.id != self.bot.user.id: ids.append(user.id)
                    if self.cursor is None:
                        index = 0
                        while index < len(self.data["guilds"][guild_index]["users"]):
                            if self.data["guilds"][guild_index]["users"][index]["id"] not in ids:
                                self.data["guilds"][guild_index]["users"].remove(self.data["guilds"][guild_index]["users"][index]) 
                                index -= 1
                            index += 1
                    else:
                        self.cursor.execute("select user_id from guild_users where guild_id = ?", (guild.id,))
                        for id in cursor.fetchall():
                            if id[0] not in ids: self.cursor.execute("delete from guild_users where guild_id = ? and user_id = ?", (guild.id, id[0]))
                        self.cursor.execute("delete from users where user_id not in (select user_id from guild_users)")
            if self.cursor is None: yaml.safe_dump(self.data, open(flat_file, "w"), indent=4)
            else: self.connection.commit()
            await context.reply(f"Synced all users")
            self.lock.release()

    async def add_guild(self, guild):
        init_guild = False
        keep = False
        repeat = False
        if self.cursor is None:
            ids = []
            for guild_searched in self.data["guilds"]: ids.append(guild_searched["id"])
            if guild.id not in ids:
                self.data["guilds"].append({"id": guild.id,
                                            "language": self.default_language,
                                            "keep": keep,
                                            "repeat": repeat,
                                            "playlists": [],
                                            "users": []})
                async for user in guild.fetch_members(limit=guild.member_count):
                    if user.id != self.bot.user.id: self.add_user(self.data["guilds"][len(self.data["guilds"]) - 1], user)
                yaml.safe_dump(self.data, open(self.flat_file, "w"), indent=4)
                init_guild = True
        else:
            try:
                self.cursor.execute("insert into guilds values(?, ?, ?, ?, ?)", (guild.id, self.default_language, None, False, False))
                async for user in guild.fetch_members(limit=guild.member_count):
                    if user.id != self.bot.user.id: self.add_user(guild, user)
                self.connection.commit()
                init_guild = True
            except: pass
        if init_guild:
            self.guilds[str(guild.id)] = {"language": self.default_language,
                                          "strings": yaml.safe_load(open(f"{self.language_directory}/{self.default_language}.yaml", "r"))["strings"],
                                          "keep": keep,
                                          "repeat": repeat,
                                          "queue": [],
                                          "index": 0,
                                          "time": .0,
                                          "volume": 1.0,
                                          "connected": False}

    def remove_guild_from_database(self, id):
        self.cursor.execute("delete from guild_users where guild_id = ?", (id,))
        self.cursor.execute("delete from users where user_id not in (select user_id from guild_users)")
        self.cursor.execute("delete from songs where pl_id in (select pl_id from playlists where guild_id = ?)", (id,))
        self.cursor.execute("delete from playlists where guild_id = ?", (id,))
        self.cursor.execute("delete from guilds where guild_id = ?", (id,))
        self.connection.commit()

    def add_user(self, guild, user):
        if self.cursor is None:
            ids = []
            for user_searched in guild["users"]: ids.append(user_searched["id"])
            if user.id not in ids: guild["users"].append({"id": user.id})
        else:
            try: self.cursor.execute("insert into users values (?)", (user.id,))
            except: pass
            try: self.cursor.execute("insert into guild_users values (?, ?)", (guild.id, user.id))
            except: pass

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="+", intents=intents)
bot.remove_command("help")

variables = yaml.safe_load(open("Variables.yaml", "r"))

if variables["storage"] == "yaml":
    connection = None
    cursor = None
    flat_file = "Guilds.yaml"
    if not os.path.exists(flat_file): yaml.safe_dump({"guilds": []}, open(flat_file, "w"), indent=4)
    data = yaml.safe_load(open(flat_file, "r"))
else:
    data = None
    flat_file = None
    if variables["storage"] == "postgresql":
        import subprocess
        import psycopg2cffi
        subprocess.run(["psql",
                        "-c",
                        f"create database \"{variables['postgresql_credentials']['database']}\"",
                        f"""user={variables["postgresql_credentials"]["user"]}
                            dbname={variables["postgresql_credentials"]["user"]}
                            password={variables["postgresql_credentials"]["password"]}"""],
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.STDOUT)
        database_exists = False
        connection = psycopg2cffi.connect(database=variables["postgresql_credentials"]["database"],
                                          user=variables["postgresql_credentials"]["user"],
                                          password=variables["postgresql_credentials"]["password"],
                                          host=variables["postgresql_credentials"]["host"],
                                          port=variables["postgresql_credentials"]["port"])
        connection.autocommit = True
        cursor = CursorHandler(connection.cursor(), "bigint", "%s")
    elif variables["storage"] == "sqlite":
        import sqlite3
        database = "Guilds.db"
        database_exists = os.path.exists(database)
        connection = sqlite3.connect(database)
        cursor = CursorHandler(connection.cursor(), "integer", "?")
    if not database_exists:
        try:
            cursor.execute("""create table guilds(guild_id integer not null,
                                                  guild_lang text not null,
                                                  working_thread_id integer null,
                                                  keep_in_voice boolean not null,
                                                  repeat_queue boolean not null,
                                                  primary key (guild_id))""")
            cursor.execute("""create table playlists(pl_id integer not null,
                                                     pl_name text not null,
                                                     guild_id integer not null,
                                                     guild_pl_id integer not null,
                                                     primary key (pl_id),
                                                     foreign key (guild_id) references guilds(guild_id))""")
            cursor.execute("""create table songs(song_id integer not null,
                                                 song_name text not null,
                                                 song_url text not null,
                                                 song_duration float not null,
                                                 pl_id integer not null,
                                                 pl_song_id integer not null,
                                                 primary key (song_id),
                                                 foreign key (pl_id) references playlists(pl_id))""")
            cursor.execute("create table users(user_id integer not null, primary key (user_id))")
            cursor.execute("""create table guild_users(guild_id integer not null,
                                                       user_id integer not null,
                                                       primary key (guild_id, user_id),
                                                       foreign key (guild_id) references guilds(guild_id),
                                                       foreign key (user_id) references users(user_id))""")
        except: pass

guilds = {}
language_directory = "Languages"
lock = asyncio.Lock()

@bot.event
async def on_ready(): print(f"Logged in as {bot.user}")

@bot.command()
async def sync_commands(context):
    if context.author.id == variables["master_id"]:
        await bot.tree.set_translator(CommandTranslator())
        synced = await bot.tree.sync()
        await context.reply(f"Synced {len(synced)} command{'' if len(synced) == 1 else 's'}")

async def main():
    async with bot:
        await bot.add_cog(Main(bot, connection, cursor, data, flat_file, guilds, language_directory, lock))
        await bot.add_cog(Music(bot, connection, cursor, data, flat_file, guilds, language_directory, lock))
        await bot.start(variables["token"])

asyncio.run(main())

connection.close()
