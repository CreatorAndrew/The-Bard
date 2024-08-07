import sqlite3
from yaml import safe_load as load

data = load(open("Bard.yaml", "r"))

DATABASE = "Bard.db"
connection = sqlite3.connect(DATABASE)
cursor = connection.cursor()
try:
    cursor.execute(
        """
        create table guilds(
            guild_id bigint not null,
            guild_lang text not null,
            primary key (guild_id)
        )
        """
    )
    cursor.execute("create table users(user_id bigint not null, primary key (user_id))")
    cursor.execute(
        """
        create table guild_users(
            guild_id bigint not null,
            user_id bigint not null,
            primary key (guild_id, user_id),
            foreign key (guild_id) references guilds(guild_id) on delete cascade,
            foreign key (user_id) references users(user_id) on delete cascade
        )
        """
    )
except:
    pass

for guild in data["guilds"]:
    cursor.execute(
        "insert into guilds values(?, ?)",
        (
            guild["id"],
            guild["language"],
        ),
    )
    for user in guild["users"]:
        try:
            cursor.execute("insert into users values(?)", (user["id"],))
        except:
            pass
        cursor.execute(
            "insert into guild_users values(?, ?)", (guild["id"], user["id"])
        )

connection.commit()
connection.close()
