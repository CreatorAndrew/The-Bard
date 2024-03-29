import sys
import os
import asyncio
import typing
import requests
import yaml
import discord
from discord import app_commands
from discord.ext import commands

class CursorHandler:
    def __init__(self, connection, cursor, integer_data_type, placeholder):
        self.connection = connection
        self.cursor = cursor
        self.integer_data_type = integer_data_type
        self.placeholder = placeholder

    async def execute(self, statement, args=tuple()):
        cursor = await self.connection.execute(statement.replace("integer", self.integer_data_type).replace("?", self.placeholder), args)
        if self.connection != self.cursor: self.cursor = cursor

    async def fetchall(self): return await self.cursor.fetchall()

    async def fetchone(self): return await self.cursor.fetchone()

class CommandTranslator(app_commands.Translator):
    async def translate(self, string: app_commands.locale_str, locale: discord.Locale, context: app_commands.TranslationContext) -> "str | None":
        try:
            if os.path.exists(f"{language_directory}/{locale.name}.yaml"):
                return yaml.safe_load(open(f"{language_directory}/{locale.name}.yaml", "r"))["strings"][str(string)]
            return None
        except: return None

class Main(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.connection = bot.connection
        self.cursor = bot.cursor
        self.data = bot.data
        self.flat_file = bot.flat_file
        self.language_directory = bot.language_directory
        self.lock = bot.lock
        self.guilds = bot.guilds_
        self.default_language = "american_english"
        self.init_guilds(bot.init_guilds)
        self.set_language_options()

    def init_guilds(self, guilds=None):
        if self.cursor is None:
            guilds = self.data["guilds"]
            id = "id"
            language = "language"
            keep = "keep"
            repeat = "repeat"
        else:
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
        await self.lock.acquire()
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
                        self.lock.release()
                        return
                    for string in yaml.safe_load(open("LanguageStringNames.yaml", "r"))["names"]:
                        try:
                            if content["strings"][string]: pass
                        except:
                            await context.response.send_message(strings["invalid_language_file"].replace("%{language_file}", file_name),
                                                                file=discord.File(open(f"{self.language_directory}/{current_language_file}", "r"),
                                                                                  filename=current_language_file),
                                                                ephemeral=True)
                            self.lock.release()
                            return
                    open(f"{self.language_directory}/{file_name}", "wb").write(response.content)
                else:
                    await context.response.send_message(strings["language_file_exists"].replace("%{language_file}", file_name))
                    self.lock.release()
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
                self.lock.release()
                return
        elif add is None and set is None:
            await context.response.send_message(strings["language"].replace("%{language}",
                                                                            yaml.safe_load(open(f"{self.language_directory}/{current_language_file}", "r"))["name"]),
                                                ephemeral=True)
            self.lock.release()
            return
        else:
            await context.response.send_message(strings["invalid_command"], ephemeral=True)
            self.lock.release()
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
        else:
            await self.cursor.execute("update guilds set guild_lang = ? where guild_id = ?", (language, context.guild.id))
            await self.connection.commit()
        await context.response.send_message(language_data["strings"]["language_change"].replace("%{language}", language_data["name"]))
        self.lock.release()

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
        else: await self.remove_guild_from_database(guild.id)
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
                        await self.add_user(guild, member)
                        break
                yaml.safe_dump(self.data, open(self.flat_file, "w"), indent=4)
            else:
                await self.add_user(member.guild, member)
                await self.connection.commit()
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
                await self.cursor.execute("delete from guild_users where user_id = ? and guild_id = ?", (member.guild.id, member.id))
                await self.cursor.execute("delete from users where user_id not in (select user_id from guild_users)")
                await self.connection.commit()
        self.lock.release()

    @commands.command()
    async def sync_guilds(self, context):
        if context.author.id == variables["master_id"]:
            await self.lock.acquire()
            if self.cursor is None: guild_count = len(self.data["guilds"])
            else:
                await self.cursor.execute("select count(guild_id) from guilds")
                guild_count = (await self.cursor.fetchone())[0]
            if len(self.bot.guilds) > guild_count:
                async for guild in self.bot.fetch_guilds(): await self.add_guild(guild)
            elif len(self.bot.guilds) < guild_count:
                ids = []
                async for guild in self.bot.fetch_guilds(): ids.append(guild.id)
                if self.cursor is None:
                    index = 0
                    while index < len(self.data["guilds"]):
                        if self.data["guilds"][index]["id"] not in ids:
                            del self.guilds[str(self.data["guilds"][index]["id"])]
                            self.data["guilds"].remove(self.data["guilds"][index])
                            index -= 1
                        index += 1
                    yaml.safe_dump(self.data, open(self.flat_file, "w"), indent=4)
                else:
                    await self.cursor.execute("select guild_id from guilds")
                    for id in await self.cursor.fetchall():
                        if id[0] not in ids:
                            del self.guilds[str(id[0])]
                            await self.remove_guild_from_database(id[0])
            await context.reply("Synced all guilds")
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
                    await self.cursor.execute("select count(user_id) from guild_users where guild_id = ?", (guild.id,))
                    user_count = (await self.cursor.fetchone())[0]
                # subtract 1 from the member count to exclude the bot itself
                if len(guild.members) - 1 > user_count:
                    async for user in guild.fetch_members(limit=guild.member_count):
                        if user.id != self.bot.user.id: await self.add_user(self.data["guilds"][guild_index]["users"] if self.cursor is None else guild, user)
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
                        await self.cursor.execute("select user_id from guild_users where guild_id = ?", (guild.id,))
                        for id in await self.cursor.fetchall():
                            if id[0] not in ids: await self.cursor.execute("delete from guild_users where guild_id = ? and user_id = ?", (guild.id, id[0]))
                        await self.cursor.execute("delete from users where user_id not in (select user_id from guild_users)")
            if self.cursor is None: yaml.safe_dump(self.data, open(self.flat_file, "w"), indent=4)
            else: await self.connection.commit()
            await context.reply("Synced all users")
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
                    if user.id != self.bot.user.id: await self.add_user(self.data["guilds"][len(self.data["guilds"]) - 1], user)
                yaml.safe_dump(self.data, open(self.flat_file, "w"), indent=4)
                init_guild = True
        else:
            try:
                await self.cursor.execute("insert into guilds values(?, ?, ?, ?, ?)", (guild.id, self.default_language, None, keep, repeat))
                async for user in guild.fetch_members(limit=guild.member_count):
                    if user.id != self.bot.user.id: await self.add_user(guild, user)
                await self.connection.commit()
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

    async def remove_guild_from_database(self, id):
        await self.cursor.execute("delete from guild_users where guild_id = ?", (id,))
        await self.cursor.execute("delete from users where user_id not in (select user_id from guild_users)")
        await self.cursor.execute("delete from pl_songs where pl_id in (select pl_id from playlists where guild_id = ?)", (id,))
        await self.cursor.execute("delete from songs where song_id not in (select song_id from pl_songs)")
        await self.cursor.execute("delete from playlists where guild_id = ?", (id,))
        await self.cursor.execute("delete from guilds where guild_id = ?", (id,))
        await self.connection.commit()

    async def add_user(self, guild, user):
        if self.cursor is None:
            ids = []
            for user_searched in guild["users"]: ids.append(user_searched["id"])
            if user.id not in ids: guild["users"].append({"id": user.id})
        else:
            try: await self.cursor.execute("insert into users values (?)", (user.id,))
            except: pass
            try: await self.cursor.execute("insert into guild_users values (?, ?)", (guild.id, user.id))
            except: pass

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="+", intents=intents)
bot.remove_command("help")

variables = yaml.safe_load(open("Variables.yaml", "r"))

language_directory = "Languages"

@bot.event
async def on_ready(): print(f"Logged in as {bot.user}")

@bot.command()
async def sync_commands(context):
    if context.author.id == variables["master_id"]:
        await bot.tree.set_translator(CommandTranslator())
        await bot.tree.sync()
        await context.reply(f"Synced {len(bot.tree.get_commands())} command{'' if len(bot.tree.get_commands()) == 1 else 's'}")

async def main():
    async with bot:
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
                import psycopg
                credentials = f"""dbname={variables["postgresql_credentials"]["user"]}
                                  user={variables["postgresql_credentials"]["user"]}
                                  password={variables["postgresql_credentials"]["password"]}
                                  {"" if variables["postgresql_credentials"]["host"] is None else f"host={variables['postgresql_credentials']['host']}"}
                                  {"" if variables["postgresql_credentials"]["port"] is None else f"port={variables['postgresql_credentials']['port']}"}"""
                subprocess.run(["psql", "-c", f"create database \"{variables['postgresql_credentials']['database']}\"", credentials],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.STDOUT)
                database_exists = False
                connection = await psycopg.AsyncConnection.connect(credentials.replace(f"dbname={variables['postgresql_credentials']['user']}",
                                                                                       f"dbname={variables['postgresql_credentials']['database']}"),
                                                                   autocommit=True)
                cursor = CursorHandler(connection.cursor(), connection.cursor(), "bigint", "%s")
            elif variables["storage"] == "sqlite":
                import aiosqlite
                database = "Guilds.db"
                database_exists = os.path.exists(database)
                connection = await aiosqlite.connect(database)
                cursor = CursorHandler(connection, None, "integer", "?")
            if not database_exists:
                try:
                    await cursor.execute("""create table guilds(guild_id integer not null,
                                                                guild_lang text not null,
                                                                working_thread_id integer null,
                                                                keep_in_voice boolean not null,
                                                                repeat_queue boolean not null,
                                                                primary key (guild_id))""")
                    await cursor.execute("""create table playlists(pl_id integer not null,
                                                                   pl_name text not null,
                                                                   guild_id integer not null,
                                                                   guild_pl_id integer not null,
                                                                   primary key (pl_id),
                                                                   foreign key (guild_id) references guilds(guild_id))""")
                    await cursor.execute("""create table songs(song_id integer not null,
                                                               song_name text not null,
                                                               song_duration float not null,
                                                               guild_id integer not null,
                                                               channel_id integer not null,
                                                               message_id integer not null,
                                                               attachment_index integer not null,
                                                               primary key (song_id))""")
                    await cursor.execute("""create table pl_songs(song_id integer not null,
                                                                  song_name text not null,
                                                                  song_url text null,
                                                                  pl_id integer not null,
                                                                  pl_song_id integer not null,
                                                                  primary key (song_id, pl_id),
                                                                  foreign key (song_id) references songs(song_id),
                                                                  foreign key (pl_id) references playlists(pl_id))""")
                    await cursor.execute("create table users(user_id integer not null, primary key (user_id))")
                    await cursor.execute("""create table guild_users(guild_id integer not null,
                                                                     user_id integer not null,
                                                                     primary key (guild_id, user_id),
                                                                     foreign key (guild_id) references guilds(guild_id),
                                                                     foreign key (user_id) references users(user_id))""")
                except: pass
        if cursor is None: init_guilds = None
        else:
            await cursor.execute("select guild_id, guild_lang, keep_in_voice, repeat_queue from guilds")
            init_guilds = await cursor.fetchall()
        bot.connection = connection
        bot.cursor = cursor
        bot.data = data
        bot.flat_file = flat_file
        bot.guilds_ = {}
        bot.init_guilds = init_guilds
        bot.language_directory = language_directory
        bot.lock = asyncio.Lock()
        await bot.add_cog(Main(bot))
        await bot.load_extension("Music")
        await bot.start(variables["token"])

if sys.platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
