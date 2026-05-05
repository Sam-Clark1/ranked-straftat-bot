import discord
from discord.ext import commands
import asyncio
import re
import aiosqlite
import random
from itertools import combinations
from model_helpers import predict_variable
from bet_helpers import (
    check_match_titles, handle_bet_placements, handle_parlay_placement,
    create_odds_display, percentage_to_odds, calc_performance_score,
    calculate_win_probability, calculate_mp_win_probabilities
)
from command_helpers import (
    handle_inputted_players, get_emoji, get_players,
    get_display_name, get_player_matches
)


def _american_to_decimal(odds):
    """Convert American odds to decimal multiplier."""
    if odds < 0:
        return 1 + (100 / abs(odds))
    else:
        return 1 + (odds / 100)


def _add_vig(vig_range=(10, 15)):
    """Return a negative American odds value with house edge applied."""
    return -100 - random.randint(*vig_range)


class Bet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def bet(self, ctx, rounds_to_win: int, *args):
        """
        Usage : !bet <rounds_to_win> @Player1 @Player2 [@Player3 ...]
        1v1   : !bet 10 @Raf @Dom
        MP    : !bet 10 @Raf @Dom @Jake @Sam
        """
        async with aiosqlite.connect('rankings.db') as db:

            # ----------------------------------------------------------------
            # PARSING
            # ----------------------------------------------------------------
            if len(args) < 2:
                await ctx.send(
                    "Invalid input: Need at least 2 players.\n"
                    "Usage: `!bet <rounds_to_win> @Player1 @Player2 ...`"
                )
                return

            if len(args) > 10:
                await ctx.send("Invalid input: Maximum of 10 players per bet.")
                return

            players = []
            for arg in args:
                try:
                    member = await commands.MemberConverter().convert(ctx, arg)
                    players.append(member)
                except commands.BadArgument:
                    await ctx.send(f"Invalid input: Could not find player `{arg}`.")
                    return

            player_ids = [p.id for p in players]
            if len(player_ids) != len(set(player_ids)):
                await ctx.send("Invalid input: Duplicate players are not allowed.")
                return

            if rounds_to_win < 1:
                await ctx.send("Invalid input: rounds_to_win must be at least 1.")
                return

            # ----------------------------------------------------------------
            # MODE + MATCH TITLE
            # ----------------------------------------------------------------
            game_mode   = '1v1' if len(players) == 2 else 'mp'
            match_title = " vs ".join(p.display_name for p in players)

            # ----------------------------------------------------------------
            # DUPLICATE BET CHECK
            # ----------------------------------------------------------------
            bets_exist, existing_title = await check_match_titles(match_title, db)
            if bets_exist:
                await ctx.send(
                    f"Bets for **{existing_title}** have already been placed. "
                    f"Wait for that match to conclude before placing new bets."
                )
                return

            await handle_inputted_players(player_ids, db)

            # ----------------------------------------------------------------
            # COUNTDOWN SETUP
            # ----------------------------------------------------------------
            seconds = 120
            minutes, secs = divmod(seconds, 60)
            bot_message = await ctx.send(
                f"Bets for **{match_title}**\n"
                f"**Time Remaining to Bet: {minutes:02}:{secs:02}**"
            )
            thread = await ctx.channel.create_thread(
                name=match_title,
                message=bot_message
            )

            # ----------------------------------------------------------------
            # WIN PROBABILITIES
            # ----------------------------------------------------------------
            if game_mode == '1v1':
                p1, p2      = players[0], players[1]
                p1_score    = await calc_performance_score(p1.id, p2.id, db)
                p2_score    = await calc_performance_score(p2.id, p1.id, db)
                p1_prob, p2_prob = await calculate_win_probability(p1_score, p2_score)
                win_probs   = {p1.id: p1_prob, p2.id: p2_prob}

                fav = p1 if p1_prob >= p2_prob else p2
                dog = p2 if fav is p1 else p1
            else:
                # calculate_mp_win_probabilities written in part 3
                win_probs = await calculate_mp_win_probabilities(player_ids, db)

            # ----------------------------------------------------------------
            # SPREAD PREDICTION (1v1 only)
            # ----------------------------------------------------------------
            predicted_spread = None
            if game_mode == '1v1':
                fav_played = await get_player_matches(db, fav.id)
                dog_played = await get_player_matches(db, dog.id)

                if fav_played and dog_played:
                    predicted_spread = await predict_variable(fav.id, dog.id, 'spread', db)
                    predicted_spread = max(1.5, min(8.5, predicted_spread))
                elif fav_played or dog_played:
                    predicted_spread = 6.5
                else:
                    predicted_spread = 4.5

            # ----------------------------------------------------------------
            # BUILD BETS_INFO
            # Each entry maps a letter label to all metadata needed for
            # display, restriction checking, and DB insertion.
            #
            # Structure:
            # {
            #   'type'              : internal bet type string
            #   'display'           : human-readable label for the odds table
            #   'value'             : the line/name (e.g. '-3.5', 'O16.5', 'Raf')
            #   'odds'              : American odds (integer)
            #   'player_bet_on_id'  : primary player ID (None for ou_total)
            #   'player_b_id'       : secondary player ID (head_to_head only)
            #   'self_bettable_ids' : set of in-game player IDs allowed to
            #                         place this bet. Empty set = blocked for
            #                         everyone in the game.
            # }
            # ----------------------------------------------------------------
            bets_info   = {}
            label_pool  = iter('ABCDEFGHIJKLMNOPQRSTUVWXYZ')

            def next_label():
                return next(label_pool)

            if game_mode == '1v1':
                # -- Odds --
                fav_ml_odds  = await percentage_to_odds(win_probs[fav.id])
                dog_ml_odds  = await percentage_to_odds(win_probs[dog.id])

                ou_total_line  = round((rounds_to_win * 2) - predicted_spread - 0.5, 1)
                ou_player_line = round(rounds_to_win - predicted_spread - 0.5, 1)

                # Spread — favorite
                bets_info[next_label()] = {
                    'type': 'spread',
                    'display': f"{fav.display_name} Spread",
                    'value': f'-{predicted_spread}',
                    'odds': _add_vig((10, 15)),
                    'player_bet_on_id': fav.id,
                    'player_b_id': None,
                    'self_bettable_ids': {fav.id},
                }
                # Spread — underdog
                bets_info[next_label()] = {
                    'type': 'spread',
                    'display': f"{dog.display_name} Spread",
                    'value': f'+{predicted_spread}',
                    'odds': _add_vig((0, 10)),
                    'player_bet_on_id': dog.id,
                    'player_b_id': None,
                    'self_bettable_ids': {dog.id},
                }
                # Moneyline — favorite
                bets_info[next_label()] = {
                    'type': 'moneyline',
                    'display': f"{fav.display_name} ML",
                    'value': fav.display_name,
                    'odds': fav_ml_odds,
                    'player_bet_on_id': fav.id,
                    'player_b_id': None,
                    'self_bettable_ids': {fav.id},
                }
                # Moneyline — underdog
                bets_info[next_label()] = {
                    'type': 'moneyline',
                    'display': f"{dog.display_name} ML",
                    'value': dog.display_name,
                    'odds': dog_ml_odds,
                    'player_bet_on_id': dog.id,
                    'player_b_id': None,
                    'self_bettable_ids': {dog.id},
                }
                # O/U total rounds — over
                bets_info[next_label()] = {
                    'type': 'ou_total',
                    'display': 'O/U Total Rounds',
                    'value': f'O{ou_total_line}',
                    'odds': _add_vig((11, 15)),
                    'player_bet_on_id': None,
                    'player_b_id': None,
                    'self_bettable_ids': set(),     # nobody in game
                }
                # O/U total rounds — under
                bets_info[next_label()] = {
                    'type': 'ou_total',
                    'display': 'O/U Total Rounds',
                    'value': f'U{ou_total_line}',
                    'odds': _add_vig((0, 10)),
                    'player_bet_on_id': None,
                    'player_b_id': None,
                    'self_bettable_ids': set(),
                }
                # O/U loser rounds — over
                # Winner always gets exactly rounds_to_win so only the
                # loser's round count is an interesting per-player market.
                bets_info[next_label()] = {
                    'type': 'ou_player',
                    'display': f"O/U {dog.display_name} Rounds",
                    'value': f'O{ou_player_line}',
                    'odds': _add_vig((5, 15)),
                    'player_bet_on_id': dog.id,
                    'player_b_id': None,
                    'self_bettable_ids': set(),     # nobody in game
                }
                # O/U loser rounds — under
                bets_info[next_label()] = {
                    'type': 'ou_player',
                    'display': f"O/U {dog.display_name} Rounds",
                    'value': f'U{ou_player_line}',
                    'odds': _add_vig((5, 15)),
                    'player_bet_on_id': dog.id,
                    'player_b_id': None,
                    'self_bettable_ids': set(),
                }

            else:
                # ---- MP ----

                # Moneyline per player
                for player in players:
                    bets_info[next_label()] = {
                        'type': 'moneyline',
                        'display': f"{player.display_name} Wins",
                        'value': player.display_name,
                        'odds': await percentage_to_odds(win_probs[player.id]),
                        'player_bet_on_id': player.id,
                        'player_b_id': None,
                        'self_bettable_ids': {player.id},
                    }

                # Head-to-head pairings
                # Cap at 6 for readability; prefer closest-odds matchups
                all_pairs = list(combinations(players, 2))
                if len(all_pairs) > 6:
                    all_pairs = sorted(
                        all_pairs,
                        key=lambda pair: abs(win_probs[pair[0].id] - win_probs[pair[1].id])
                    )[:6]

                for pa, pb in all_pairs:
                    total = win_probs[pa.id] + win_probs[pb.id]
                    prob_a = win_probs[pa.id] / total
                    prob_b = 1 - prob_a

                    bets_info[next_label()] = {
                        'type': 'head_to_head',
                        'display': f"{pa.display_name} > {pb.display_name}",
                        'value': f'{pa.display_name} beats {pb.display_name}',
                        'odds': await percentage_to_odds(prob_a),
                        'player_bet_on_id': pa.id,
                        'player_b_id': pb.id,
                        'self_bettable_ids': {pa.id},
                    }
                    bets_info[next_label()] = {
                        'type': 'head_to_head',
                        'display': f"{pb.display_name} > {pa.display_name}",
                        'value': f'{pb.display_name} beats {pa.display_name}',
                        'odds': await percentage_to_odds(prob_b),
                        'player_bet_on_id': pb.id,
                        'player_b_id': pa.id,
                        'self_bettable_ids': {pb.id},
                    }

                # Podium (top 3) — 4+ players only
                if len(players) >= 4:
                    for player in players:
                        podium_prob = min(0.92, win_probs[player.id] * 3)
                        bets_info[next_label()] = {
                            'type': 'podium',
                            'display': f"{player.display_name} Top 3",
                            'value': f'{player.display_name} top3',
                            'odds': await percentage_to_odds(podium_prob),
                            'player_bet_on_id': player.id,
                            'player_b_id': None,
                            'self_bettable_ids': {player.id},
                        }

                # Last place — 4+ players only, nobody in-game may bet this
                if len(players) >= 4:
                    for player in players:
                        last_prob = (1 - win_probs[player.id]) / (len(players) - 1)
                        bets_info[next_label()] = {
                            'type': 'last_place',
                            'display': f"{player.display_name} Last",
                            'value': f'{player.display_name} last',
                            'odds': await percentage_to_odds(last_prob),
                            'player_bet_on_id': player.id,
                            'player_b_id': None,
                            'self_bettable_ids': set(),
                        }

                # O/U total rounds
                ou_total_line = round(rounds_to_win * len(players) * 0.55, 1)
                bets_info[next_label()] = {
                    'type': 'ou_total',
                    'display': 'O/U Total Rounds',
                    'value': f'O{ou_total_line}',
                    'odds': _add_vig((10, 15)),
                    'player_bet_on_id': None,
                    'player_b_id': None,
                    'self_bettable_ids': set(),
                }
                bets_info[next_label()] = {
                    'type': 'ou_total',
                    'display': 'O/U Total Rounds',
                    'value': f'U{ou_total_line}',
                    'odds': _add_vig((0, 10)),
                    'player_bet_on_id': None,
                    'player_b_id': None,
                    'self_bettable_ids': set(),
                }

                # O/U per-player rounds — nobody in-game may bet their own
                for player in players:
                    expected = round(
                        rounds_to_win * win_probs[player.id] * len(players) * 0.6, 1
                    )
                    ou_line = round(expected - 0.5, 1)
                    bets_info[next_label()] = {
                        'type': 'ou_player',
                        'display': f"O/U {player.display_name} Rounds",
                        'value': f'O{ou_line}',
                        'odds': _add_vig((5, 15)),
                        'player_bet_on_id': player.id,
                        'player_b_id': None,
                        'self_bettable_ids': set(),
                    }
                    bets_info[next_label()] = {
                        'type': 'ou_player',
                        'display': f"O/U {player.display_name} Rounds",
                        'value': f'U{ou_line}',
                        'odds': _add_vig((5, 15)),
                        'player_bet_on_id': player.id,
                        'player_b_id': None,
                        'self_bettable_ids': set(),
                    }

            # ----------------------------------------------------------------
            # PLAYER BALANCES EMBED
            # ----------------------------------------------------------------
            available_balances = await get_players(db)
            if available_balances:
                embed = discord.Embed(
                    title="Player Balances",
                    color=discord.Colour.dark_embed()
                )
                for user_id, straftcoins in available_balances:
                    embed.add_field(
                        name=await get_display_name(ctx, user_id),
                        value=f"Straftcoins: {straftcoins}",
                        inline=True
                    )
                await thread.send(embed=embed)

            # ----------------------------------------------------------------
            # INSTRUCTIONS
            # ----------------------------------------------------------------
            straftcoin_emoji = await get_emoji(['Straftcoin'])
            await thread.send(
                f"Welcome to the betting thread for **{match_title}**!\n"
                f"- **Single bet**: `A 100` — letter is the bet, number is your stake.\n"
                f"- **Parlay**: `P A C 100` — all legs must win. Minimum 2 legs, max 6.\n"
                f"- Bets lock after 2 minutes.\n"
                f"- Players in the match can only bet on their own positive outcomes.\n"
                f"- No account? You start with 1000 {straftcoin_emoji[0]}."
            )

            # ----------------------------------------------------------------
            # ODDS DISPLAY
            # create_odds_display written in part 3
            # ----------------------------------------------------------------
            await create_odds_display(thread, bets_info, game_mode)

            # ----------------------------------------------------------------
            # COUNTDOWN
            # ----------------------------------------------------------------
            for remaining in range(seconds - 1, -1, -1):
                await asyncio.sleep(1)
                minutes, secs = divmod(remaining, 60)
                await bot_message.edit(
                    content=f"Bets for **{match_title}**\n"
                            f"**Time Remaining to Bet: {minutes:02}:{secs:02}**"
                )

            # ----------------------------------------------------------------
            # PARLAY CONFLICT CHECKER
            # ----------------------------------------------------------------
            def has_parlay_conflict(leg_labels):
                """
                Returns True if any two legs in the parlay directly
                contradict each other, making the bet free money.
                """
                moneyline_seen    = False
                last_place_seen   = False
                ou_total_sides    = set()
                h2h_pairs         = set()
                ou_player_map     = {}   # player_id -> set of sides

                for lbl in leg_labels:
                    leg = bets_info[lbl]
                    t   = leg['type']
                    pid = leg['player_bet_on_id']

                    if t == 'moneyline':
                        # Two moneylines in same parlay = conflict
                        if moneyline_seen:
                            return True
                        moneyline_seen = True

                    elif t == 'last_place':
                        # Two last-place bets = conflict
                        if last_place_seen:
                            return True
                        last_place_seen = True

                    elif t == 'ou_total':
                        side = 'O' if leg['value'].startswith('O') else 'U'
                        if side in ou_total_sides or ou_total_sides:
                            return True     # same side twice, or over+under
                        ou_total_sides.add(side)

                    elif t == 'head_to_head':
                        pair    = (pid, leg['player_b_id'])
                        reverse = (leg['player_b_id'], pid)
                        if reverse in h2h_pairs:
                            return True     # A>B and B>A
                        h2h_pairs.add(pair)

                    elif t == 'ou_player':
                        side = 'O' if leg['value'].startswith('O') else 'U'
                        if pid not in ou_player_map:
                            ou_player_map[pid] = set()
                        if side in ou_player_map[pid] or ou_player_map[pid]:
                            return True     # over+under same player
                        ou_player_map[pid].add(side)

                return False

            # ----------------------------------------------------------------
            # COLLECT AND PROCESS BETS
            # ----------------------------------------------------------------
            single_regex = re.compile(r'^([A-Za-z])\s+(\d+)$')
            parlay_regex = re.compile(r'^P(?:\s+[A-Za-z]){2,6}\s+\d+$', re.IGNORECASE)

            collected_single_bets = []

            async for message in thread.history(oldest_first=True):
                content = message.content.strip()
                author  = message.author
                in_game = author.id in player_ids

                # ---- SINGLE BET ----
                single_match = single_regex.match(content)
                if single_match:
                    label  = single_match.group(1).upper()
                    amount = int(single_match.group(2))

                    if label not in bets_info:
                        continue

                    bet_meta = bets_info[label]

                    # Restriction check
                    if in_game and author.id not in bet_meta['self_bettable_ids']:
                        allowed = [
                            lbl for lbl, b in bets_info.items()
                            if author.id in b['self_bettable_ids']
                        ]
                        allowed_str = ', '.join(allowed) if allowed else 'none'
                        await thread.send(
                            f"{author.mention}, as a player in this match you can only bet "
                            f"on your own positive outcomes. "
                            f"Your allowed bets: **{allowed_str}**. Bet not logged."
                        )
                        continue

                    # Delegate balance check + row construction to bet_helpers
                    bet_row = await handle_bet_placements(
                        match_title, label, amount,
                        bet_meta, thread, message, db
                    )
                    if bet_row is not False:
                        collected_single_bets.append(bet_row)
                    continue

                # ---- PARLAY ----
                if parlay_regex.match(content):
                    parts      = content.split()
                    leg_labels = [p.upper() for p in parts[1:-1]]
                    try:
                        stake = int(parts[-1])
                    except ValueError:
                        continue

                    # Unknown labels
                    unknown = [l for l in leg_labels if l not in bets_info]
                    if unknown:
                        await thread.send(
                            f"{author.mention}, unknown bet label(s): "
                            f"{', '.join(unknown)}. Bet not logged."
                        )
                        continue

                    # Duplicate labels
                    if len(leg_labels) != len(set(leg_labels)):
                        await thread.send(
                            f"{author.mention}, duplicate labels in parlay. Bet not logged."
                        )
                        continue

                    # Conflict check
                    if has_parlay_conflict(leg_labels):
                        await thread.send(
                            f"{author.mention}, your parlay has conflicting legs "
                            f"(e.g. two moneylines, or over + under on the same line). "
                            f"Bet not logged."
                        )
                        continue

                    # Restriction check — every leg must be self-bettable
                    if in_game:
                        blocked = [
                            l for l in leg_labels
                            if author.id not in bets_info[l]['self_bettable_ids']
                        ]
                        if blocked:
                            await thread.send(
                                f"{author.mention}, your parlay includes legs you're not "
                                f"allowed to bet as a player in this match "
                                f"(blocked: {', '.join(blocked)}). Bet not logged."
                            )
                            continue

                    # Delegate balance check + full DB insert to bet_helpers
                    # (handle_parlay_placement inserts both the parlay row
                    #  and the leg rows so it can capture the parlay_id)
                    await handle_parlay_placement(
                        match_title, leg_labels, stake,
                        bets_info, thread, message, db
                    )

            # ----------------------------------------------------------------
            # INSERT SINGLE BETS
            # ----------------------------------------------------------------
            if collected_single_bets:
                await db.executemany("""
                    INSERT INTO live_bets
                        (user_id, match_title, player_bet_on_id, player_b_id,
                         bet_type, bet_value, bet_odds, bet_amount, parlay_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """, collected_single_bets)

            await db.commit()
            await thread.send(
                f"Bets for the next **{match_title}** match have been locked in."
            )
            await thread.edit(locked=True)


async def setup(bot):
    await bot.add_cog(Bet(bot))