from os.path import exists
import psycopg
from yaml import safe_dump as dump, safe_load as load
from utils import variables

credentials = f"""
    dbname={variables["postgresql_credentials"]["user"]}
    user={variables["postgresql_credentials"]["user"]}
    password={variables["postgresql_credentials"]["password"]}
    {"" if variables["postgresql_credentials"]["host"] is None else f"host={variables['postgresql_credentials']['host']}"}
    {"" if variables["postgresql_credentials"]["port"] is None else f"port={variables['postgresql_credentials']['port']}"}
"""

FLAT_FILE = "Bard.yaml"
if not exists(FLAT_FILE):
    dump({"guilds": []}, open(FLAT_FILE, "w"), indent=4)
data = load(open(FLAT_FILE, "r"))

CONNECTION = psycopg.connect(
    credentials.replace(
        f"dbname={variables['postgresql_credentials']['user']}",
        f"dbname={variables['postgresql_credentials']['database']}",
    )
)
cursor = CONNECTION.cursor()

cursor.execute("select * from guilds")
guilds = cursor.fetchall()
cursor.execute("select * from guilds_music")
guilds_music = cursor.fetchall()
for index, guild in enumerate(guilds):
    playlists = []
    cursor.execute(
        "select guild_pl_id, pl_name from playlists where guild_id = %s order by guild_pl_id",
        (guild[0],),
    )
    for playlist in cursor.fetchall():
        songs = []
        cursor.execute(
            """
            select pl_songs.song_name, song_url, song_duration, songs.guild_id, channel_id, message_id, attachment_index from pl_songs
            left outer join songs on songs.song_id = pl_songs.song_id
            left outer join playlists on playlists.pl_id = pl_songs.pl_id
            where playlists.guild_id = %s and guild_pl_id = %s
            order by pl_song_id
            """,
            (guild[0], playlist[0]),
        )
        for song in cursor.fetchall():
            songs.append(
                {
                    "name": song[0],
                    "file": song[1],
                    "duration": song[2],
                    "guild_id": song[3],
                    "channel_id": song[4],
                    "message_id": song[5],
                    "attachment_index": song[6],
                }
            )
        playlists.append({"name": playlist[1], "songs": songs})
    users = []
    cursor.execute("select user_id from guild_users where guild_id = %s", (guild[0],))
    for user in cursor.fetchall():
        users.append({"id": user[1]})
    data["guilds"].append(
        {
            "id": guild[0],
            "language": guild[1],
            "keep": bool(guilds_music[index][1]),
            "repeat": bool(guilds_music[index][2]),
            "playlists": playlists,
            "users": users,
        }
    )
    if guild[2] is not None:
        data["guilds"][len(data["guilds"]) - 1]["working_thread_id"] = guild[2]

CONNECTION.close()

dump(data, open(FLAT_FILE, "w"), indent=4)
