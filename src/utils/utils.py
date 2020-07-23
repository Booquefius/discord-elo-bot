import requests
from discord import Embed
import discord
from utils.exceptions import send_error, get_picked_player
from utils.exceptions import get_game, get_player_by_id, PassException
from datetime import datetime

def rename_attr(obj, old_name, new_name):
    if hasattr(obj, old_name):
        obj.__dict__[new_name] = obj.__dict__.pop(old_name)
        return True
    return False


def is_url_image(url):
    """Return True if the url is an existing image."""
    img_formats = ('image/png', 'image/jpeg', 'image/jpg')
    req = requests.head(url)
    return "content-type" in req.headers and req.headers["content-type"] in img_formats


def team_name(id_team):
    """Return the name of the team from its id."""
    return ('Nobody', 'Red', 'Blue')[id_team]


def list_to_int(list_str):
    """Return the list but every elem is converted to int."""
    return [int(elem) for elem in list_str]


def get_elem_from_embed(reaction):
    mb = reaction.message.embeds[0]
    footer = mb.footer.text.split()

    return {
        "current_page": int(footer[1]),
        "last_page": int(footer[3]),
        "function": mb.fields[0].value,
        "key": mb.fields[1].value,
        "mode": int(mb.fields[2].value),
        "id": int(mb.fields[3].value) if len(mb.fields) == 4 else None
    }


def get_startpage(reaction, embed):
    allowed_emojis = {"⏮️": 1, "⬅️": embed["current_page"] - 1,
                      "➡️": embed["current_page"] + 1, "⏭️": embed["last_page"]}
    return allowed_emojis[reaction.emoji]


def add_attribute(game, attr_name, value):
    """Add an attribute to every player when I manually update."""
    for mode in game.leaderboards:
        for player in game.leaderboards[mode]:
            if not hasattr(game.leaderboards[mode][player], attr_name):
                setattr(game.leaderboards[mode][player], attr_name, value)


def reset_attribute(game, attr_name, value):
    """Add an attribute to every player when I manually update."""
    for mode in game.leaderboards:
        for player in game.leaderboards[mode]:
            setattr(game.leaderboards[mode][player], attr_name, value)


def build_other_page(bot, game, reaction, user):
    reaction.emoji = str(reaction)
    if user.id == bot.user.id or not reaction.message.embeds \
            or reaction.emoji not in "⏮️⬅️➡️⏭️":
        return
    embed = get_elem_from_embed(reaction)

    if embed["function"] not in ["leaderboard", "archived", "undecided",
        "canceled", "commands", "ranks", "history", "most", "maps"]:
        return None

    startpage = get_startpage(reaction, embed)
    if embed["function"] == "leaderboard":
        return game.leaderboard(embed["mode"], embed["key"],
                               startpage)
    elif embed["function"] in ["archived", "undecided", "canceled"]:
        return getattr(game, embed["function"])(embed["mode"],
                                               startpage=startpage)
    elif embed["function"] == "history":
        return getattr(game, embed["function"])(embed["mode"],
            embed["id"], startpage=startpage)

    elif embed["function"] == "commands":
        return cmds_embed(bot, startpage)

    elif embed["function"] == "maps":
        return getattr(game, embed["function"])(startpage)

    elif embed["function"] == "most":
        order_key, with_or_vs = embed["key"].split()
        return most_stat_embed(game, embed["mode"], embed["id"], order_key, startpage, with_or_vs)
    elif embed["function"] == "ranks":
        return game.display_ranks(embed["mode"], startpage)

    return None



def check_if_premium(game, before, after):
    if len(before.roles) < len(after.roles):
        new_role = next(
            role for role in after.roles if role not in before.roles)
        role_name = new_role.name.lower().split()
        return "double" in role_name
    return False


def cmds_embed(bot, startpage=1):
    nb_pages = 1 + len(bot.commands) // 15
    nl = '\n'
    return Embed(color=0x00FF00, description=\
          '```\n' +\
         '\n'.join([f'{command.name:15}: {command.help.split(nl)[0]}'
            for command in sorted(bot.commands, key=lambda c: c.name)[15 * (startpage - 1): 15 * startpage]
            if command.help is not None and not command.hidden]) + '```')\
            .add_field(name="name", value="commands") \
            .add_field(name="-", value="-") \
            .add_field(name="-", value=0) \
            .set_footer(text=f"[ {startpage} / {nb_pages} ]")


def most_stat_embed(game, mode, player, order_key="game", startpage=1, with_or_vs="with"):
    most_played_with = build_most_played_with(game, mode, player, with_or_vs)
    len_page = 20
    nb_pages = 1 + len(most_played_with) // len_page
    cpage = len_page * (startpage - 1)
    npage = len_page * startpage
    order = ["games", "draws", "wins", "losses"].index(order_key)
    return Embed(title=f"Leaderboard of the most played games {with_or_vs} players",
        color=0x00FF00,
        description=\
        f'```\n{"name":20} {"game":7} {"draw":7} {"wins":7} {"losses":7}\n' +\
        '\n'.join([
            f"{name:20} {_with:<7} {d:<7} {w:<7} {l:<7}"
            for name, (_with, d, w, l) in sorted(most_played_with.items(),
                key=lambda x: x[1][order], reverse=True)[cpage: npage]]) +
            "```"
        ).add_field(name="name", value="most") \
        .add_field(name="key", value=f"{order_key} {with_or_vs}") \
        .add_field(name="mode", value=mode) \
        .add_field(name="id", value=player.id_user) \
        .set_footer(text=f"[ {startpage} / {nb_pages} ]")


def get_player_lb_pos(leaderboard, player, key):
    """Return the player position in the leaderboard based on the key O(n)."""
    res = 1
    for _, p in leaderboard.items():
        res += getattr(p, "elo") > getattr(player, "elo")
    return res

def build_most_played_with(game, mode, player, with_or_vs):
    most_played_with = {}
    archive = game.archive[mode]
    # player = game.leaderboards[mode][name]
    team = []
    for (queue, win, _) in archive.values():
        if player in queue:
            if with_or_vs == "with":
                team = queue.red_team if player in queue.red_team else queue.blue_team
            else:
                team = queue.red_team if player not in queue.red_team else queue.blue_team
            for p in team:
                team_players_stats(p, player, most_played_with, win, queue)
    most_played_with.pop(player.name, None)
    return most_played_with

def team_players_stats(team_player, me, most_played_with, win, queue):
    if team_player.name in most_played_with:
        most_played_with[team_player.name][0] += 1
    else:
        # nb matches with, nb draws, nb wins, nb losses
        most_played_with[team_player.name] = [1, 0, 0, 0]
    if win == 0:
        most_played_with[team_player.name][1] += 1
    elif queue.player_in_winners(win, me):
        most_played_with[team_player.name][2] += 1
    else:
        most_played_with[team_player.name][3] += 1

async def autosubmit_reactions(reaction, user, game):
    embed = get_elem_from_embed(reaction)
    if embed["function"] != "autosubmit":
        return
    mode, id, winner = embed["mode"], embed["id"], int(embed["key"])
    if id not in game.waiting_for_approval[mode]:
        return
    queue = game.waiting_for_approval[mode][id]
    if user.id not in game.leaderboards[mode] or\
        game.leaderboards[mode][user.id] not in queue:
        await reaction.message.remove_reaction(reaction.emoji, user)
        return

    if mode not in game.correctly_submitted:
        game.correctly_submitted[mode] = set()
    if id in game.correctly_submitted[mode]:
        return
    # The message got enough positive reaction (removing bot's one)
    if reaction.message.reactions[0].count - 1 >= queue.max_queue // 2 + 1:
        text, worked = game.add_archive(mode, id, winner)
        if worked:
            game.waiting_for_approval[mode].pop(id, None)
            game.correctly_submitted[mode].add(id)
        await reaction.message.channel.send(embed=Embed(color=0xFF0000 if winner == 1 else 0x0000FF,
            description=text))

        return
    if reaction.message.reactions[1].count - 1 >= queue.max_queue // 2:
        game.waiting_for_approval[mode].pop(id, None)
        await reaction.message.channel.send(embed=Embed(color=0x000000,
            description=f"The game {id} in the mode {mode} wasn't accepted.\n\
                        Please submit again"))

async def map_pick_reactions(reaction, user, game):
    embed = get_elem_from_embed(reaction)
    if embed["function"] != "lobby_maps":
        return
    mode, id = embed["mode"], embed["id"]
    queue = game.undecided_games[mode][id]
    if user.id not in game.leaderboards[mode] or\
        game.leaderboards[mode][user.id] not in queue:
        await reaction.message.remove_reaction(reaction.emoji, user)
        return
    emoji, name = "", ""
    for i, r in enumerate(reaction.message.reactions):
        if r.count - 1 >= queue.max_queue // 2 + 1:
            emoji, name = reaction.message.embeds[0].description.split('\n')[i + 1].split()

            game.add_map_to_archive(mode, id, name, emoji)
            await reaction.message.channel.send(embed=Embed(color=0x00FF00,
                description="Okay ! We got enough votes, the map is...\n"\
                    f"{emoji} {name}"
                )
            )
            break





async def add_emojis(msg, game, mode, id):
    maps = game.available_maps
    for map in game.maps_archive[mode][id]:
        await msg.add_reaction(maps[map])

async def add_scroll(message):
    """Add ⏮️ ⬅️ ➡️ ⏭️ emojis to the message."""
    for e in ['⏮️', '⬅️', '➡️', '⏭️']:
        await message.add_reaction(e)

async def set_map(ctx, game, queue, mode):
    if queue.mapmode != 0:
        msg = await ctx.send(queue.ping_everyone(),
            embed=game.lobby_maps(mode, queue.game_id))
        if queue.mapmode == 2:
            await add_emojis(msg, game, mode, queue.game_id)


async def announce_game(ctx, res, queue):
    if res != "Queue is full...":
        await discord.utils.get(ctx.guild.channels,
            name="game_announcement")\
        .send(embed=Embed(color=0x00FF00,
            description=res),
            content=queue.ping_everyone())


async def finish_the_pick(ctx, game, queue, mode, team_just_picked):
    other_team_id = 1 if team_just_picked == 2 else 2
    other_cap = queue.get_team_by_id(other_team_id)[0]
    nb_to_pick = nb_players_to_pick(queue, other_team_id)
    if len(queue.players) == 1:
        await queue.set_player_team(ctx, other_team_id, queue.players[0])
    else:
        await ctx.send(content=
            f"<@{other_cap.id_user}> have to pick **{nb_to_pick}** players.",
            embed=Embed(color=0x00FF00, description=str(queue)))
    if queue.is_finished():
        await ctx.send(embed=Embed(color=0x00FF00,
            description=str(queue)))
        await discord.utils.get(ctx.guild.channels,
            name="game_announcement")\
                .send(embed=Embed(color=0x00FF00,
                    description=str(queue)),
                    content=queue.ping_everyone())
        game.add_game_to_be_played(game.queues[mode])
        if queue.mapmode != 0:
            msg = await ctx.send(queue.ping_everyone(),
                embed=game.lobby_maps(mode, queue.game_id))
            if queue.mapmode == 2:
                await add_emojis(msg, game, mode, queue.game_id)



def nb_players_to_pick(queue, my_team_id):
    if queue.mode in (2, 3):
        return 1
    my_team = queue.get_team_by_id(my_team_id)
    other_team = queue.get_team_by_id(1 if my_team_id == 2 else 2)
    if len(queue.players) >= 3:
        return 1 if len(my_team) >= len(other_team) else 2
    return 1

async def pick_players(ctx, queue, mode, team_id, p1, p2):
    nb_p = nb_players_to_pick(queue, team_id)
    if nb_p == 2 and not p2 or nb_p == 1 and p2:
        await send_error(ctx, f"You need to pick **{nb_p}** players.")
        raise PassException()

    lst = [await get_picked_player(ctx, mode, queue, p1)]
    if nb_p > 1:
        lst.append(await get_picked_player(ctx, mode, queue, p2))
        if lst[0] == lst[1]:
            await send_error(ctx, f"You picked twice <@{lst[0].id_user}>.")
            raise PassException()
    for i in range(nb_p):
        await queue.set_player_team(ctx, team_id, lst[i])


async def join_aux(ctx, player=None):
    game = get_game(ctx)
    mode = int(ctx.channel.name.split('vs')[0])
    id = ctx.author.id
    queue = game.queues[mode]
    if player is None:
        player = await get_player_by_id(ctx, mode, id)

    setattr(player, "last_join", datetime.now())
    is_queue_now_full = queue.has_queue_been_full
    res = queue.add_player(player, game)
    # await ctx.send(embed=Embed(color=0x00FF00, description=res))
    is_queue_now_full = queue.has_queue_been_full != is_queue_now_full

    await ctx.send(content=queue.ping_everyone() if is_queue_now_full else "",
        embed=Embed(color=0x00FF00, description=res))

    if queue.is_finished():
        await ctx.send(embed=Embed(color=0x00FF00,
            description=game.add_game_to_be_played(queue)))
        await set_map(ctx, game, queue, mode)
        await announce_game(ctx, res, queue)
