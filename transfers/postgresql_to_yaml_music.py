from sys import path
from os.path import dirname, exists

path.insert(0, dirname(path[0]))
import psycopg
from yaml import safe_dump as dump, safe_load as load
from utils import CREDENTIALS

FLAT_FILE = "Bard.yaml"
if not exists(FLAT_FILE):
    dump({"guilds": []}, open(FLAT_FILE, "w"), indent=4)
data = load(open(FLAT_FILE, "r"))

connection = psycopg.connect(CREDENTIALS)
cursor = connection.cursor()

cursor.execute("select * from guilds_music")
for index, guild in enumerate(cursor.fetchall()):
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
    if guild[1] is not None:
        data["guilds"][index]["working_thread_id"] = guild[1]
    data["guilds"][index]["keep"] = bool(guild[2])
    data["guilds"][index]["repeat"] = bool(guild[3])
    data["guilds"][index]["playlists"] = playlists

connection.close()

dump(data, open(FLAT_FILE, "w"), indent=4)
