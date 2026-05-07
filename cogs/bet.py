import discord
from discord.ext import commands
import asyncio
import re
import aiosqlite
import random
import string
from itertools import combinations
from model_helpers import predict_variable, predict_mp_total_rounds, predict_mp_player_rounds_all
from bet_helpers import (
    check_match_titles, handle_bet_placements, handle_parlay_placement,
    create_odds_display, percentage_to_odds, calc_performance_score,
    calculate_win_probability, calculate_mp_win_probabilities,
    calculate_mp_last_place_probs, get_mp_h2h_rate
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

_SINGLE_REGEX      = re.compile(r'^([A-Za-z]{1,2})\s+(\d+)$')
_PARLAY_REGEX      = re.compile(r'^([A-Za-z]{1,2})(?:\s+[A-Za-z]{1,2}){1,5}\s+\d+$', re.IGNORECASE)
_BET_ATTEMPT_REGEX = re.compile(r'^[A-Za-z]{1,2}(?:\s+\S+)+$')

class Bet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_bets: dict = {}  # thread_id → {'bets_info': ..., 'player_ids': ...}

    @commands.command()
    async def bet(self, ctx, rounds_to_win: int, *args):
        """
        Usage : !bet <rounds_to_win> @Player1 @Player2 [@Player3 ...]
        1v1   : !bet 10 @Raf @Dom
        MP    : !bet 10 @Raf @Dom @Jake @Sam
        """
        async with aiosqlite.connect('rankings.db') as db:

            
            # PARSING
            
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


            # MODE + MATCH TITLE

            game_mode = '1v1' if len(players) == 2 else 'mp'

            if game_mode == '1v1' and rounds_to_win < 10:
                await ctx.send("Invalid input: 1v1 bets require at least 10 rounds to win.")
                return
            match_title = f"[FT{rounds_to_win}] " + " vs ".join(
                sorted(p.display_name for p in players)
            )

            
            # DUPLICATE BET CHECK
            
            bets_exist, existing_title = await check_match_titles(match_title, db)
            if bets_exist:
                await ctx.send(
                    f"Bets for **{existing_title}** have already been placed. "
                    f"Wait for that match to conclude before placing new bets."
                )
                return

            await handle_inputted_players(player_ids, db)

            
            # COUNTDOWN SETUP
            
            seconds = 300
            minutes, secs = divmod(seconds, 60)
            bot_message = await ctx.send(
                f"Bets for **{match_title}**\n"
                f"**Time Remaining to Bet: {minutes:02}:{secs:02}**"
            )
            thread = await ctx.channel.create_thread(
                name=match_title,
                message=bot_message
            )

            
            # WIN PROBABILITIES
            
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

            
            # SPREAD PREDICTION (1v1 only)
            
            predicted_spread = None
            if game_mode == '1v1':
                fav_played = await get_player_matches(db, fav.id)
                dog_played = await get_player_matches(db, dog.id)

                if fav_played and dog_played:
                    try:
                        predicted_spread = await predict_variable(fav.id, dog.id, 'spread', db)
                        predicted_spread = max(1.5, min(8.5, predicted_spread))
                    except Exception:
                        predicted_spread = 6.5
                elif fav_played or dog_played:
                    predicted_spread = 6.5
                else:
                    predicted_spread = 4.5

            
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
            
            bets_info   = {}
            def _label_generator():
                """Yields A-Z then AA, AB, ... AZ, BA, BB, ... indefinitely."""
                letters = string.ascii_uppercase
                for c in letters:
                    yield c
                for first in letters:
                    for second in letters:
                        yield first + second

            label_gen = _label_generator()

            def next_label():
                return next(label_gen)

            if game_mode == '1v1':
                # -- Odds --
                fav_ml_odds = await percentage_to_odds(win_probs[fav.id] * 1.04)
                dog_ml_odds = await percentage_to_odds(win_probs[dog.id] * 1.04)

                ou_total_line = round((rounds_to_win * 2) - predicted_spread - 0.5, 1)

                # A: Spread — favorite
                bets_info[next_label()] = {
                    'type': 'spread',
                    'display': f"{fav.display_name} Spread",
                    'value': f'-{predicted_spread}',
                    'odds': _add_vig((10, 15)),
                    'player_bet_on_id': fav.id,
                    'player_b_id': None,
                    'self_bettable_ids': {fav.id},
                }
                # B: Moneyline — favorite
                bets_info[next_label()] = {
                    'type': 'moneyline',
                    'display': f"{fav.display_name} ML",
                    'value': fav.display_name,
                    'odds': fav_ml_odds,
                    'player_bet_on_id': fav.id,
                    'player_b_id': None,
                    'self_bettable_ids': {fav.id},
                }
                # C: O/U total rounds — over
                bets_info[next_label()] = {
                    'type': 'ou_total',
                    'display': 'O/U Total Rounds',
                    'value': f'O{ou_total_line}',
                    'odds': _add_vig((11, 15)),
                    'player_bet_on_id': None,
                    'player_b_id': None,
                    'self_bettable_ids': set(),
                }
                # D: Spread — underdog
                bets_info[next_label()] = {
                    'type': 'spread',
                    'display': f"{dog.display_name} Spread",
                    'value': f'+{predicted_spread}',
                    'odds': _add_vig((0, 10)),
                    'player_bet_on_id': dog.id,
                    'player_b_id': None,
                    'self_bettable_ids': {dog.id},
                }
                # E: Moneyline — underdog
                bets_info[next_label()] = {
                    'type': 'moneyline',
                    'display': f"{dog.display_name} ML",
                    'value': dog.display_name,
                    'odds': dog_ml_odds,
                    'player_bet_on_id': dog.id,
                    'player_b_id': None,
                    'self_bettable_ids': {dog.id},
                }
                # F: O/U total rounds — under
                bets_info[next_label()] = {
                    'type': 'ou_total',
                    'display': 'O/U Total Rounds',
                    'value': f'U{ou_total_line}',
                    'odds': _add_vig((0, 10)),
                    'player_bet_on_id': None,
                    'player_b_id': None,
                    'self_bettable_ids': set(),
                }

            else:
                # ---- MP ----

                # Derive last-place probabilities from win probs
                last_probs = calculate_mp_last_place_probs(win_probs)

                # Moneyline per player (with vig)
                for player in players:
                    bets_info[next_label()] = {
                        'type': 'moneyline',
                        'display': f"{player.display_name} Wins",
                        'value': player.display_name,
                        'odds': await percentage_to_odds(win_probs[player.id] * 1.04),
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
                    field_total = win_probs[pa.id] + win_probs[pb.id]
                    prob_a      = win_probs[pa.id] / field_total
                    prob_b      = 1 - prob_a

                    # Blend with direct MP head-to-head history if enough shared games
                    h2h_rate = await get_mp_h2h_rate(pa.id, pb.id, db)
                    if h2h_rate is not None:
                        prob_a = prob_a * 0.7 + h2h_rate * 0.3
                        prob_b = 1 - prob_a

                    bets_info[next_label()] = {
                        'type': 'head_to_head',
                        'display': f"{pa.display_name} > {pb.display_name}",
                        'value': f'{pa.display_name} beats {pb.display_name}',
                        'odds': await percentage_to_odds(prob_a * 1.04),
                        'player_bet_on_id': pa.id,
                        'player_b_id': pb.id,
                        'self_bettable_ids': {pa.id},
                    }
                    bets_info[next_label()] = {
                        'type': 'head_to_head',
                        'display': f"{pb.display_name} > {pa.display_name}",
                        'value': f'{pb.display_name} beats {pa.display_name}',
                        'odds': await percentage_to_odds(prob_b * 1.04),
                        'player_bet_on_id': pb.id,
                        'player_b_id': pa.id,
                        'self_bettable_ids': {pb.id},
                    }

                # Podium (top 3) — 4+ players only
                # Derived from last-place probability: P(top 3) = 1 - P(last) × (n - 3)
                if len(players) >= 4:
                    for player in players:
                        podium_prob = max(0.05, min(0.95,
                            1 - last_probs[player.id] * (len(players) - 3)
                        ))
                        bets_info[next_label()] = {
                            'type': 'podium',
                            'display': f"{player.display_name} Top 3",
                            'value': f'{player.display_name} top3',
                            'odds': await percentage_to_odds(podium_prob * 1.04),
                            'player_bet_on_id': player.id,
                            'player_b_id': None,
                            'self_bettable_ids': {player.id},
                        }

                # Last place — 4+ players only, nobody in-game may bet this
                if len(players) >= 4:
                    for player in players:
                        bets_info[next_label()] = {
                            'type': 'last_place',
                            'display': f"{player.display_name} Last",
                            'value': f'{player.display_name} last',
                            'odds': await percentage_to_odds(last_probs[player.id] * 1.04),
                            'player_bet_on_id': player.id,
                            'player_b_id': None,
                            'self_bettable_ids': set(),
                        }

                # O/U total rounds — in-game players may bet (no single player controls total)
                all_player_ids = {p.id for p in players}

                _ou_total_pred = await predict_mp_total_rounds(player_ids, rounds_to_win, db)
                _ou_total_raw  = _ou_total_pred if _ou_total_pred is not None else rounds_to_win * len(players) * 0.55
                ou_total_line  = round(_ou_total_raw * 2) / 2

                _ou_player_preds = await predict_mp_player_rounds_all(player_ids, rounds_to_win, db)
                bets_info[next_label()] = {
                    'type': 'ou_total',
                    'display': 'O/U Total Rounds',
                    'value': f'O{ou_total_line}',
                    'odds': _add_vig((10, 15)),
                    'player_bet_on_id': None,
                    'player_b_id': None,
                    'self_bettable_ids': all_player_ids,
                }
                bets_info[next_label()] = {
                    'type': 'ou_total',
                    'display': 'O/U Total Rounds',
                    'value': f'U{ou_total_line}',
                    'odds': _add_vig((0, 10)),
                    'player_bet_on_id': None,
                    'player_b_id': None,
                    'self_bettable_ids': all_player_ids,
                }

                # O/U per-player rounds — in-game players may NOT bet their own rounds
                for player in players:
                    if player.id in _ou_player_preds:
                        _ou_raw = _ou_player_preds[player.id]
                    else:
                        _ou_raw = rounds_to_win * win_probs[player.id] * len(players) * 0.6

                    # Clamp lines too close to the extremes so they stay meaningful
                    if _ou_raw >= rounds_to_win - 1:
                        ou_line = rounds_to_win - 1.5
                    elif _ou_raw <= 1:
                        ou_line = 1.5
                    else:
                        ou_line = round(_ou_raw * 2) / 2 - 0.5
                    others = {p.id for p in players if p.id != player.id}
                    bets_info[next_label()] = {
                        'type': 'ou_player',
                        'display': f"O/U {player.display_name} Rounds",
                        'value': f'O{ou_line}',
                        'odds': _add_vig((5, 15)),
                        'player_bet_on_id': player.id,
                        'player_b_id': None,
                        'self_bettable_ids': others,
                    }
                    bets_info[next_label()] = {
                        'type': 'ou_player',
                        'display': f"O/U {player.display_name} Rounds",
                        'value': f'U{ou_line}',
                        'odds': _add_vig((5, 15)),
                        'player_bet_on_id': player.id,
                        'player_b_id': None,
                        'self_bettable_ids': others,
                    }

            
            # PLAYER BALANCES EMBED
            
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

            
            # INSTRUCTIONS
            
            sc_emoji = (await get_emoji(['Straftcoin']))[0]
            instructions_embed = discord.Embed(
                title='Bets Are Open',
                description=f'**{match_title}**',
                color=discord.Color(0x90ee90)
            )
            instructions_embed.add_field(
                name='How to Bet',
                value=(
                    f'**Single:** `A 100` — label then stake\n'
                    f'**Parlay:** `A B 100` — labels then stake (2–6 legs, all must win)'
                ),
                inline=False
            )
            instructions_embed.add_field(
                name='Rules',
                value=(
                    f'Bets lock in 2 minutes\n'
                    f'Players may only bet on their own positive outcomes\n'
                    f'New accounts start with 1,000 {sc_emoji}'
                ),
                inline=False
            )
            await thread.send(embed=instructions_embed)

            
            # ODDS DISPLAY
            # create_odds_display written in part 3
            
            await create_odds_display(thread, bets_info, game_mode)

            # Register so on_message / on_message_edit can validate during countdown
            self.active_bets[thread.id] = {
                'bets_info': bets_info,
                'player_ids': player_ids,
            }

            
            # COUNTDOWN
            
            for remaining in range(seconds - 1, -1, -1):
                await asyncio.sleep(1)
                minutes, secs = divmod(remaining, 60)
                await bot_message.edit(
                    content=f"Bets for **{match_title}**\n"
                            f"**Time Remaining to Bet: {minutes:02}:{secs:02}**"
                )

            self.active_bets.pop(thread.id, None)

            
            # COLLECT AND PROCESS BETS
            
            async for message in thread.history(oldest_first=True):
                content = message.content.strip()
                author  = message.author
                in_game = author.id in player_ids

                if message.author.bot:
                    continue

                # ---- SINGLE BET ----
                single_match = _SINGLE_REGEX.match(content)
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
                        await thread.send(embed=discord.Embed(
                            description=(
                                f"{author.mention} — as a player in this match you can only bet "
                                f"on your own positive outcomes. "
                                f"Your allowed bets: **{allowed_str}**."
                            ),
                            color=discord.Color.red()
                        ))
                        continue

                    # Delegate balance check + DB insert to bet_helpers
                    await handle_bet_placements(
                        match_title, label, amount,
                        bet_meta, thread, message, db
                    )
                    continue

                # ---- PARLAY ----
                if _PARLAY_REGEX.match(content):
                    parts      = content.split()
                    leg_labels = [p.upper() for p in parts[:-1]]
                    try:
                        stake = int(parts[-1])
                    except ValueError:
                        continue

                    # Unknown labels
                    unknown = [l for l in leg_labels if l not in bets_info]
                    if unknown:
                        await thread.send(embed=discord.Embed(
                            description=f"{author.mention} — unknown bet label(s): {', '.join(unknown)}.",
                            color=discord.Color.red()
                        ))
                        continue

                    # Duplicate labels
                    if len(leg_labels) != len(set(leg_labels)):
                        await thread.send(embed=discord.Embed(
                            description=f"{author.mention} — duplicate labels in parlay.",
                            color=discord.Color.red()
                        ))
                        continue

                    # Conflict check
                    if self._has_parlay_conflict(leg_labels, bets_info):
                        await thread.send(embed=discord.Embed(
                            description=(
                                f"{author.mention} — parlay has conflicting legs "
                                f"(e.g. two moneylines, or over + under on the same line)."
                            ),
                            color=discord.Color.red()
                        ))
                        continue

                    # Restriction check — every leg must be self-bettable
                    if in_game:
                        blocked = [
                            l for l in leg_labels
                            if author.id not in bets_info[l]['self_bettable_ids']
                        ]
                        if blocked:
                            await thread.send(embed=discord.Embed(
                                description=(
                                    f"{author.mention} — parlay includes legs you're not "
                                    f"allowed to bet as a player in this match "
                                    f"(blocked: {', '.join(blocked)})."
                                ),
                                color=discord.Color.red()
                            ))
                            continue

                    # Delegate balance check + full DB insert to bet_helpers
                    # (handle_parlay_placement inserts both the parlay row
                    #  and the leg rows so it can capture the parlay_id)
                    await handle_parlay_placement(
                        match_title, leg_labels, stake,
                        bets_info, thread, message, db
                    )
                    continue

                # ---- MALFORMED BET HINT ----
                # Message didn't match single or parlay format but looks like a bet attempt
                if _BET_ATTEMPT_REGEX.match(content):
                    await thread.send(embed=discord.Embed(
                        description=(
                            f"{author.mention} — bet not recognized.\n"
                            f"Single: `A 100` · Parlay: `A B 100` (2–6 legs)"
                        ),
                        color=discord.Color.red()
                    ))

            await thread.send(
                f"Bets for the next **{match_title}** match have been locked in."
            )
            await thread.edit(locked=True)

    @bet.error
    async def bet_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send(
                "Invalid input: missing or invalid rounds to win.\n"
                "Usage: `!bet <rounds_to_win> @Player1 @Player2 ...`\n"
                "Example: `!bet 10 @Raf @Dom`"
            )

    # PARLAY CONFLICT CHECKER (static — shared by bet processing and validator)
    
    @staticmethod
    def _has_parlay_conflict(leg_labels, bets_info):
        moneyline_seen  = False
        last_place_seen = False
        ou_total_seen   = False
        spread_seen     = False
        h2h_pairs       = set()
        h2h_graph       = {}   # directed graph: winner_pid → [loser_pids] for cycle detection
        ou_player_seen  = set()
        ml_player       = None
        fav_spread_pid  = None
        dog_spread_pid  = None
        h2h_winner_pids = set()
        h2h_loser_pids  = set()
        podium_pids     = set()
        last_place_pids = set()

        for lbl in leg_labels:
            leg = bets_info[lbl]
            t   = leg['type']
            pid = leg['player_bet_on_id']

            if t == 'moneyline':
                if moneyline_seen:
                    return True
                moneyline_seen = True
                if (pid in podium_pids or pid in h2h_winner_pids
                        or pid in last_place_pids or pid in h2h_loser_pids):
                    return True
                if fav_spread_pid is not None:
                    return True
                if dog_spread_pid == pid:
                    return True
                ml_player = pid

            elif t == 'spread':
                if spread_seen:
                    return True
                spread_seen = True
                if leg['value'][0] == '-':
                    fav_spread_pid = pid
                    if ml_player is not None:
                        return True
                else:
                    dog_spread_pid = pid
                    if ml_player == pid:
                        return True

            elif t == 'podium':
                if pid == ml_player:
                    return True
                podium_pids.add(pid)

            elif t == 'head_to_head':
                pair    = (pid, leg['player_b_id'])
                reverse = (leg['player_b_id'], pid)
                if reverse in h2h_pairs:
                    return True
                h2h_pairs.add(pair)
                if pid == ml_player or leg['player_b_id'] == ml_player:
                    return True
                h2h_winner_pids.add(pid)
                h2h_loser_pids.add(leg['player_b_id'])
                h2h_graph.setdefault(pid, []).append(leg['player_b_id'])

            elif t == 'last_place':
                if last_place_seen:
                    return True
                last_place_seen = True
                if pid == ml_player:
                    return True
                last_place_pids.add(pid)

            elif t == 'ou_total':
                if ou_total_seen:
                    return True
                ou_total_seen = True

            elif t == 'ou_player':
                if pid in ou_player_seen:
                    return True
                ou_player_seen.add(pid)

        # Detect transitive H2H cycles (e.g. A>B, B>C, C>A is impossible)
        if Bet._h2h_has_cycle(h2h_graph):
            return True

        return False

    @staticmethod
    def _h2h_has_cycle(graph):
        visited   = set()
        rec_stack = set()

        def dfs(node):
            visited.add(node)
            rec_stack.add(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        for node in list(graph):
            if node not in visited:
                if dfs(node):
                    return True
        return False

    
    # REAL-TIME BET VALIDATOR
    
    def _validate_bet(self, content, author_id, state):
        """
        Returns (True, None) for valid, (False, reason) for invalid,
        (None, None) if the message doesn't look like a bet.
        """
        bets_info  = state['bets_info']
        player_ids = state['player_ids']
        in_game    = author_id in player_ids

        content = content.strip()
        if not _BET_ATTEMPT_REGEX.match(content):
            return None, None

        single_match = _SINGLE_REGEX.match(content)
        if single_match:
            label = single_match.group(1).upper()
            if label not in bets_info:
                return False, f"Unknown label `{label}`."
            if in_game and author_id not in bets_info[label]['self_bettable_ids']:
                allowed = [lbl for lbl, b in bets_info.items() if author_id in b['self_bettable_ids']]
                return False, f"Restricted. Allowed: {', '.join(allowed) or 'none'}."
            return True, None

        if _PARLAY_REGEX.match(content):
            parts      = content.split()
            leg_labels = [p.upper() for p in parts[:-1]]
            try:
                int(parts[-1])
            except ValueError:
                return False, "Invalid stake."
            unknown = [l for l in leg_labels if l not in bets_info]
            if unknown:
                return False, f"Unknown label(s): {', '.join(unknown)}."
            if len(leg_labels) != len(set(leg_labels)):
                return False, "Duplicate labels."
            if self._has_parlay_conflict(leg_labels, bets_info):
                return False, "Conflicting legs."
            if in_game:
                blocked = [l for l in leg_labels if author_id not in bets_info[l]['self_bettable_ids']]
                if blocked:
                    return False, f"Blocked legs: {', '.join(blocked)}."
            return True, None

        return False, "Malformed bet."

    
    # LIVE VALIDATION LISTENERS
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        state = self.active_bets.get(message.channel.id)
        if state is None:
            return
        valid, _ = self._validate_bet(message.content, message.author.id, state)
        if valid is True:
            await message.add_reaction('✅')
        elif valid is False:
            await message.add_reaction('❌')

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.author.bot:
            return
        state = self.active_bets.get(after.channel.id)
        if state is None:
            return
        me = self.bot.user
        for emoji in ('✅', '❌'):
            try:
                await after.remove_reaction(emoji, me)
            except (discord.HTTPException, discord.NotFound):
                pass
        valid, _ = self._validate_bet(after.content, after.author.id, state)
        if valid is True:
            await after.add_reaction('✅')
        elif valid is False:
            await after.add_reaction('❌')


async def setup(bot):
    await bot.add_cog(Bet(bot))