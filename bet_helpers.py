import discord
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
import math
from command_helpers import get_straftcoin, get_emoji, get_rating


# ─────────────────────────────────────────────
# ODDS UTILITIES
# ─────────────────────────────────────────────

async def percentage_to_odds(percent_odds):
    percent_odds = max(0.01, min(0.99, percent_odds))
    if percent_odds >= 0.5:
        odds = ((percent_odds * 100) / (1 - percent_odds)) * -1
    else:
        odds = (100 / percent_odds) - 100
    return round(odds)


async def odds_to_percentage(w_or_l_or_p, bet_odds, bet_amount):
    if w_or_l_or_p == 'win':
        if bet_odds < 0:
            pct = 1 - (100 / bet_odds)
        else:
            pct = 1 + (bet_odds / 100)
        return round(bet_amount * pct), 0
    elif w_or_l_or_p == 'loss':
        return 0, bet_amount
    else:
        return 0, 0


def _american_to_decimal(odds):
    if odds < 0:
        return 1 + (100 / abs(odds))
    else:
        return 1 + (odds / 100)


def _format_odds(odds):
    return f"+{odds}" if odds > 0 else str(odds)


# ─────────────────────────────────────────────
# ODDS DISPLAY IMAGE
# ─────────────────────────────────────────────

async def create_odds_display(thread, bets_info, game_mode):
    """
    Generates a sectioned vertical odds table image and sends it to the thread.
    Sections are grouped by bet type. Each row: Label | Description | Odds
    """
    BG          = '#2f3136'
    HEADER_BG   = '#4f545c'
    TEXT        = '#ffffff'
    ODDS_POS    = '#57f287'   # green for underdog/positive odds
    ODDS_NEG    = '#ed4245'   # red for favorite/negative odds

    # Section ordering and display names
    SECTION_ORDER = [
        ('spread',      '── Spread ──'),
        ('moneyline',   '── Moneyline ──'),
        ('head_to_head','── Head-to-Head ──'),
        ('podium',      '── Podium (Top 3) ──'),
        ('last_place',  '── Last Place ──'),
        ('ou_total',    '── Over/Under Total Rounds ──'),
        ('ou_player',   '── Over/Under Player Rounds ──'),
    ]

    # Group bets by type, preserving label order within each section
    sections = {}
    for lbl, meta in bets_info.items():
        t = meta['type']
        if t not in sections:
            sections[t] = []
        sections[t].append((lbl, meta))

    # Build flat row list with section headers interleaved
    rows        = []   # (label, description, odds_str, is_header)
    for type_key, section_title in SECTION_ORDER:
        if type_key not in sections:
            continue
        rows.append(('', section_title, '', True))
        for lbl, meta in sections[type_key]:
            odds_str = _format_odds(meta['odds'])
            # Append the line value to the description for relevant bet types
            description = meta['display']
            if meta['type'] in ('spread', 'ou_total', 'ou_player'):
                description = f"{description}  {meta['value']}"
            rows.append((lbl, description, odds_str, False))

    if not rows:
        return

    fig_height = max(3, len(rows) * 0.5 + 1)
    fig, ax = plt.subplots(figsize=(7, fig_height), facecolor=BG)
    ax.set_facecolor(BG)
    ax.axis('off')

    col_widths  = [0.08, 0.62, 0.30]
    col_labels  = ['', 'Bet', 'Odds']
    y_start     = 0.97
    row_h       = 1 / (len(rows) + 2)

    # Column headers
    xs = [0.01, 0.10, 0.75]
    for i, (cx, cl) in enumerate(zip(xs, col_labels)):
        ax.text(cx, y_start, cl, transform=ax.transAxes,
                color=TEXT, fontsize=9, fontweight='bold',
                va='top', ha='left')

    y_start -= row_h * 0.8

    for label, description, odds_str, is_header in rows:
        y = y_start

        if is_header:
            # Draw a filled rectangle as section header background
            rect = plt.Rectangle((0, y - row_h * 0.15), 1, row_h * 0.85,
                                  transform=ax.transAxes,
                                  color=HEADER_BG, zorder=0)
            ax.add_patch(rect)
            ax.text(0.01, y + row_h * 0.5, description,
                    transform=ax.transAxes,
                    color=TEXT, fontsize=8.5, fontweight='bold',
                    va='center', ha='left')
        else:

            ax.text(xs[0], y + row_h * 0.3, label,
                    transform=ax.transAxes,
                    color=TEXT, fontsize=8.5, va='center', ha='left')
            ax.text(xs[1], y + row_h * 0.3, description,
                    transform=ax.transAxes,
                    color=TEXT, fontsize=8.5, va='center', ha='left')
            ax.text(xs[2], y + row_h * 0.3, odds_str,
                    transform=ax.transAxes,
                    color=TEXT, fontsize=8.5,
                    fontweight='bold', va='center', ha='left')

            # Light separator line
            ax.plot([0, 1], [y, y],
                color='#40444b', linewidth=0.4,
                transform=ax.transAxes)

        y_start -= row_h

    plt.tight_layout(pad=0.3)
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight',
                dpi=150, facecolor=BG)
    buf.seek(0)
    plt.close(fig)

    await thread.send(file=__import__('discord').File(fp=buf, filename='odds.png'))


# ─────────────────────────────────────────────
# BET PLACEMENT — SINGLE BET
# ─────────────────────────────────────────────

async def handle_bet_placements(match_title, label, amount, bet_meta, thread, message, db):
    """
    Validates balance, deducts stake, inserts bet into live_bets, and commits —
    all in one operation. Returns True on success, False on failure.
    """
    user_id  = message.author.id
    emojis   = await get_emoji(['Straftcoin'])
    sc_emoji = emojis[0]

    bet_type         = bet_meta['type']
    bet_value        = bet_meta['value']
    bet_odds         = bet_meta['odds']
    player_bet_on_id = bet_meta['player_bet_on_id']
    player_b_id      = bet_meta['player_b_id']

    amount_to_win, _ = await odds_to_percentage('win', bet_odds, amount)

    cursor = await db.execute(
        "SELECT straftcoins FROM players WHERE user_id = ?", (user_id,)
    )
    result = await cursor.fetchone()

    if result:
        current_coins = result[0]
        if amount > current_coins:
            await thread.send(
                f"{message.author.mention}, insufficient Straftcoins! "
                f"You only have {current_coins}{sc_emoji}."
            )
            return False

        await db.execute(
            "UPDATE players SET straftcoins = straftcoins - ? WHERE user_id = ?",
            (amount, user_id)
        )
        new_balance = current_coins - amount

    else:
        initial = 1000
        if amount > initial:
            await thread.send(
                f"{message.author.mention}, you start with {initial}{sc_emoji} "
                f"and can't bet more than that."
            )
            return False

        await db.execute(
            "INSERT INTO players (user_id, straftcoins) VALUES (?, ?)",
            (user_id, initial - amount)
        )
        new_balance = initial - amount

    await db.execute(
        """
        INSERT INTO live_bets
            (user_id, match_title, player_bet_on_id, player_b_id,
             bet_type, bet_value, bet_odds, bet_amount, parlay_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (user_id, match_title, player_bet_on_id, player_b_id,
         bet_type, bet_value, bet_odds, amount)
    )
    await db.commit()

    await thread.send(
        f"{message.author.mention} — **{label}** bet placed!\n"
        f"- Bet: {amount}{sc_emoji} on {bet_meta['display']} "
        f"({_format_odds(bet_odds)} odds)\n"
        f"- To Win: {amount_to_win}{sc_emoji}\n"
        f"- Balance: {new_balance}{sc_emoji}"
    )

    return True


# ─────────────────────────────────────────────
# BET PLACEMENT — PARLAY
# ─────────────────────────────────────────────

async def handle_parlay_placement(match_title, leg_labels, stake, bets_info, thread, message, db):
    """
    Validates balance, calculates combined multiplier, inserts the parlay row
    and all leg rows into the DB, then deducts the stake.
    Returns True on success, False on failure.
    """
    user_id  = message.author.id
    emojis   = await get_emoji(['Straftcoin'])
    sc_emoji = emojis[0]

    # --- Balance check ---
    cursor = await db.execute(
        "SELECT straftcoins FROM players WHERE user_id = ?", (user_id,)
    )
    result = await cursor.fetchone()

    if result:
        current_coins = result[0]
    else:
        current_coins = 1000
        await db.execute(
            "INSERT INTO players (user_id, straftcoins) VALUES (?, ?)",
            (user_id, current_coins)
        )
        await db.commit()

    if stake > current_coins:
        await thread.send(
            f"{message.author.mention}, insufficient Straftcoins! "
            f"You only have {current_coins}{sc_emoji}."
        )
        return False

    # --- Combined multiplier ---
    multiplier = 1.0
    for lbl in leg_labels:
        multiplier *= _american_to_decimal(bets_info[lbl]['odds'])
    multiplier   = round(multiplier, 4)
    expected_win = round(stake * multiplier)

    # --- Insert parlay row ---
    cursor = await db.execute(
        """
        INSERT INTO parlays
            (user_id, match_title, total_stake, num_legs,
             combined_multiplier, status, payout)
        VALUES (?, ?, ?, ?, ?, 'live', 0)
        """,
        (user_id, match_title, stake, len(leg_labels), multiplier)
    )
    parlay_id = cursor.lastrowid

    # --- Insert each leg into live_bets ---
    for lbl in leg_labels:
        meta = bets_info[lbl]
        await db.execute(
            """
            INSERT INTO live_bets
                (user_id, match_title, player_bet_on_id, player_b_id,
                 bet_type, bet_value, bet_odds, bet_amount, parlay_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, match_title,
                meta['player_bet_on_id'], meta['player_b_id'],
                meta['type'], meta['value'],
                meta['odds'], stake,
                parlay_id
            )
        )

    # --- Deduct stake ---
    await db.execute(
        "UPDATE players SET straftcoins = straftcoins - ? WHERE user_id = ?",
        (stake, user_id)
    )
    await db.commit()

    # --- Confirmation message ---
    legs_summary = '\n'.join(
        f"  {lbl}: {bets_info[lbl]['display']} "
        f"({_format_odds(bets_info[lbl]['odds'])})"
        for lbl in leg_labels
    )
    await thread.send(
        f"{message.author.mention} — **Parlay placed!**\n"
        f"- Legs ({len(leg_labels)}):\n{legs_summary}\n"
        f"- Stake: {stake}{sc_emoji}\n"
        f"- Combined multiplier: {multiplier:.2f}x\n"
        f"- To Win: {expected_win}{sc_emoji}\n"
        f"- Balance: {current_coins - stake}{sc_emoji}"
    )
    return True


# ─────────────────────────────────────────────
# MATCH TITLE LOOKUP
# ─────────────────────────────────────────────

async def check_match_titles(match_title, db):
    async with db.execute(
        "SELECT * FROM live_bets WHERE match_title = ?", (match_title,)
    ) as cursor:
        bets = await cursor.fetchall()
    return bets, match_title


# ─────────────────────────────────────────────
# WIN/LOSS DETERMINATION
# ─────────────────────────────────────────────

async def win_loss_determination(bets, match_id, spread, winner_id, total_rounds, db):
    """
    Resolves all bet types against the match result.
    Queries match_participants internally for placement and per-player round data.
    """
    # Fetch placement and rounds for all participants
    async with db.execute(
        """
        SELECT player_id, placement, rounds_won
        FROM match_participants WHERE match_id = ?
        """, (match_id,)
    ) as cursor:
        participants = await cursor.fetchall()

    placements_map  = {pid: placement for pid, placement, _ in participants}
    rounds_map      = {pid: rw        for pid, _, rw       in participants}
    max_placement   = max(p for _, p, _ in participants) if participants else 1

    winning_bets = []
    losing_bets  = []
    pushed_bets  = []

    for bet in bets:
        (bet_id, user_id, match_title,
         player_bet_on_id, player_b_id,
         bet_type, bet_value, bet_odds, bet_amount,
         parlay_id) = bet

        async def resolve(outcome):
            amount_won, _ = await odds_to_percentage(outcome, bet_odds, bet_amount)
            row = (
                user_id, match_id, match_title,
                player_bet_on_id, player_b_id,
                bet_type, bet_value, bet_odds, bet_amount,
                outcome, amount_won, parlay_id
            )
            if outcome == 'win':
                winning_bets.append(row)
            elif outcome == 'loss':
                losing_bets.append(row)
            else:
                pushed_bets.append(row)

        # ── Moneyline ──────────────────────────────────────────────
        if bet_type == 'moneyline':
            await resolve('win' if player_bet_on_id == winner_id else 'loss')

        # ── Spread (1v1 only) ──────────────────────────────────────
        elif bet_type == 'spread':
            side  = bet_value[0]           # '-' or '+'
            line  = float(bet_value[1:])

            if side == '-':
                # Favorite covers if they won AND margin > line
                if player_bet_on_id == winner_id and spread > line:
                    await resolve('win')
                elif spread == line:
                    await resolve('push')
                else:
                    await resolve('loss')
            else:
                # Underdog covers if they won OR margin < line
                if player_bet_on_id != winner_id or spread < line:
                    await resolve('win')
                elif spread == line:
                    await resolve('push')
                else:
                    await resolve('loss')

        # ── Head-to-Head ───────────────────────────────────────────
        elif bet_type == 'head_to_head':
            place_a = placements_map.get(player_bet_on_id)
            place_b = placements_map.get(player_b_id)

            if place_a is None or place_b is None:
                await resolve('push')  # player not in match, push
            elif place_a < place_b:
                await resolve('win')
            elif place_a == place_b:
                await resolve('push')
            else:
                await resolve('loss')

        # ── Podium ─────────────────────────────────────────────────
        elif bet_type == 'podium':
            place = placements_map.get(player_bet_on_id)
            if place is None:
                await resolve('push')
            elif place <= 3:
                await resolve('win')
            else:
                await resolve('loss')

        # ── Last Place ─────────────────────────────────────────────
        elif bet_type == 'last_place':
            place = placements_map.get(player_bet_on_id)
            if place is None:
                await resolve('push')
            elif place == max_placement:
                await resolve('win')
            else:
                await resolve('loss')

        # ── O/U Total Rounds ───────────────────────────────────────
        elif bet_type == 'ou_total':
            side = bet_value[0]
            line = float(bet_value[1:])

            if   side == 'O' and total_rounds > line:  await resolve('win')
            elif side == 'U' and total_rounds < line:  await resolve('win')
            elif total_rounds == line:                  await resolve('push')
            else:                                       await resolve('loss')

        # ── O/U Player Rounds ──────────────────────────────────────
        elif bet_type == 'ou_player':
            side        = bet_value[0]
            line        = float(bet_value[1:])
            player_rw   = rounds_map.get(player_bet_on_id, 0)

            if   side == 'O' and player_rw > line:  await resolve('win')
            elif side == 'U' and player_rw < line:  await resolve('win')
            elif player_rw == line:                  await resolve('push')
            else:                                    await resolve('loss')

    return winning_bets + losing_bets + pushed_bets, winning_bets, pushed_bets


# ─────────────────────────────────────────────
# BET PAYOUTS
# ─────────────────────────────────────────────

async def handle_bet_payouts(match_id, match_title, winner_id, spread, total_rounds, db):
    """
    Finds live bets for a match by participant IDs, resolves all bet types,
    settles parlays, and returns a formatted settlement message.
    """
    try:
        async with db.execute(
            "SELECT COUNT(*) FROM live_bets WHERE match_title = ?", (match_title,)
        ) as cursor:
            count_row = await cursor.fetchone()

        if not count_row or count_row[0] == 0:
            return False

        # Fetch ALL live bets for this match (includes O/U total with NULL player_bet_on_id)
        async with db.execute(
            "SELECT * FROM live_bets WHERE match_title = ?", (match_title,)
        ) as cursor:
            bets = await cursor.fetchall()

        if not bets:
            return False

        all_bets, winning_bets, pushed_bets = await win_loss_determination(
            bets, match_id, spread, winner_id, total_rounds, db
        )

        # --- Move bets to past_bets ---
        await db.executemany(
            """
            INSERT INTO past_bets
                (user_id, match_id, match_title,
                 player_bet_on_id, player_b_id,
                 bet_type, bet_value, bet_odds, bet_amount,
                 result, amount_won, parlay_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            all_bets
        )

        # --- Credit winning single bets ---
        single_wins = [b for b in winning_bets if b[11] is None]  # parlay_id index
        if single_wins:
            await db.executemany(
                "UPDATE players SET straftcoins = straftcoins + ? WHERE user_id = ?",
                [(b[10], b[0]) for b in single_wins]
            )

        # --- Refund pushed single bets ---
        single_pushes = [b for b in pushed_bets if b[11] is None]
        if single_pushes:
            await db.executemany(
                "UPDATE players SET straftcoins = straftcoins + ? WHERE user_id = ?",
                [(b[8], b[0]) for b in single_pushes]   # bet_amount index
            )

        # --- Settle parlays ---
        parlay_ids = {b[11] for b in all_bets if b[11] is not None}
        for pid in parlay_ids:
            await _settle_parlay(pid, db)

        # --- Remove live bets ---
        await db.execute(
            "DELETE FROM live_bets WHERE match_title = ?", (match_title,)
        )
        await db.commit()

        # --- Build settlement message ---
        emojis   = await get_emoji(['Poggers', 'KEKW', 'Straftcoin'])
        pog, kek, sc = emojis

        message = ''
        # Show single bets first, then parlay summaries
        single_bets = [b for b in all_bets if b[11] is None]
        for b in single_bets:
            (user_id, _, _,
             _, _,
             bet_type, bet_value, bet_odds, bet_amount,
             result, amount_won, _) = b

            balance = await get_straftcoin(db, user_id)
            bettor  = f'<@{user_id}>'
            odds_str = _format_odds(bet_odds)

            if result == 'win':
                message += (
                    f"{bettor}: **Bet Won** {pog}\n"
                    f"- {bet_type} **{bet_value}** | {bet_amount}{sc} @ {odds_str}\n"
                    f"- Won: {amount_won}{sc} | Balance: {balance}{sc}\n"
                )
            elif result == 'loss':
                message += (
                    f"{bettor}: **Bet Lost** {kek}\n"
                    f"- {bet_type} **{bet_value}** | {bet_amount}{sc} @ {odds_str}\n"
                    f"- Balance: {balance}{sc}\n"
                )
            elif result == 'push':
                message += (
                    f"{bettor}: **Bet Pushed**\n"
                    f"- {bet_type} **{bet_value}** | {bet_amount}{sc} @ {odds_str}\n"
                    f"- Returned: {bet_amount}{sc} | Balance: {balance}{sc}\n"
                )

        # Parlay summaries
        for pid in parlay_ids:
            async with db.execute(
                "SELECT user_id, total_stake, combined_multiplier, status, payout "
                "FROM parlays WHERE parlay_id = ?", (pid,)
            ) as cursor:
                p = await cursor.fetchone()
            if not p:
                continue
            p_user, p_stake, p_mult, p_status, p_payout = p
            balance  = await get_straftcoin(db, p_user)
            bettor   = f'<@{p_user}>'
            if p_status == 'won':
                message += (
                    f"{bettor}: **Parlay Won!** {pog}\n"
                    f"- Stake: {p_stake}{sc} | Multiplier: {p_mult:.2f}x\n"
                    f"- Won: {p_payout}{sc} | Balance: {balance}{sc}\n"
                )
            else:
                message += (
                    f"{bettor}: **Parlay Lost** {kek}\n"
                    f"- Stake: {p_stake}{sc} | Balance: {balance}{sc}\n"
                )

        return message if message else False

    except Exception as e:
        await db.rollback()
        print(f"handle_bet_payouts error: {e}")
        return False


async def _settle_parlay(parlay_id, db):
    """
    Checks all legs of a parlay in past_bets.
    Credits payout if all won; marks lost if any lost.
    Pushes are treated as wins (leg removed from parlay effectively).
    """
    async with db.execute(
        "SELECT result FROM past_bets WHERE parlay_id = ?",
        (parlay_id,)
    ) as cursor:
        legs = await cursor.fetchall()

    if not legs:
        return

    # Any loss = parlay lost
    if any(result == 'loss' for (result,) in legs):
        await db.execute(
            "UPDATE parlays SET status = 'lost' WHERE parlay_id = ?",
            (parlay_id,)
        )
        return

    # All non-loss = parlay won
    async with db.execute(
        "SELECT user_id, total_stake, combined_multiplier FROM parlays WHERE parlay_id = ?",
        (parlay_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        return

    user_id, total_stake, multiplier = row
    payout = round(total_stake * multiplier)

    await db.execute(
        "UPDATE players SET straftcoins = straftcoins + ? WHERE user_id = ?",
        (payout, user_id)
    )
    await db.execute(
        "UPDATE parlays SET status = 'won', payout = ? WHERE parlay_id = ?",
        (payout, parlay_id)
    )


# ─────────────────────────────────────────────
# PERFORMANCE SCORING
# ─────────────────────────────────────────────

async def get_player_stats(playerid, db):
    """
    Returns overall 1v1 stats and average win/loss margin for a player.
    """
    player_cursor = await db.execute(
        """
        SELECT wins_1v1, losses_1v1, rounds_won_1v1, rounds_lost_1v1
        FROM players WHERE user_id = ?
        """, (playerid,)
    )
    player = await player_cursor.fetchone()

    # Avg winning margin: when player placed 1st in a 1v1, how far ahead were they?
    async with db.execute(
        """
        SELECT
            AVG(CASE WHEN mp1.placement = 1
                THEN mp1.rounds_won - mp2.rounds_won ELSE NULL END) AS avg_winning_margin,
            AVG(CASE WHEN mp1.placement = 2
                THEN mp2.rounds_won - mp1.rounds_won ELSE NULL END) AS avg_losing_margin
        FROM match_participants mp1
        JOIN match_participants mp2
            ON  mp1.match_id   = mp2.match_id
            AND mp2.player_id != mp1.player_id
        JOIN matches m ON mp1.match_id = m.match_id
        WHERE mp1.player_id = ? AND m.game_mode = '1v1'
        """, (playerid,)
    ) as cursor:
        player_margin = await cursor.fetchone()

    return player, player_margin


async def get_matchup_data(playerid, db):
    """
    Returns per-opponent stats for a player across all shared 1v1 matches.
    """
    async with db.execute(
        """
        SELECT
            mp2.player_id                                                           AS opponent_id,
            SUM(CASE WHEN mp1.placement < mp2.placement THEN 1 ELSE 0 END)         AS wins_against,
            SUM(CASE WHEN mp1.placement > mp2.placement THEN 1 ELSE 0 END)         AS losses_against,
            SUM(mp1.rounds_won)                                                     AS rounds_won_shared,
            SUM(mp2.rounds_won)                                                     AS rounds_lost_shared,
            AVG(CASE WHEN mp1.placement = 1 AND mp2.placement = 2
                THEN mp1.rounds_won - mp2.rounds_won ELSE NULL END)                 AS avg_winning_margin,
            AVG(CASE WHEN mp1.placement = 2 AND mp2.placement = 1
                THEN mp2.rounds_won - mp1.rounds_won ELSE NULL END)                 AS avg_losing_margin
        FROM match_participants mp1
        JOIN match_participants mp2
            ON  mp1.match_id   = mp2.match_id
            AND mp2.player_id != mp1.player_id
        JOIN matches m ON mp1.match_id = m.match_id
        WHERE mp1.player_id = ? AND m.game_mode = '1v1'
        GROUP BY mp2.player_id
        """, (playerid,)
    ) as cursor:
        rows = await cursor.fetchall()

    return rows


async def calc_performance_score(playerid, op_id, db):
    player, player_margin = await get_player_stats(playerid, db)

    if not player:
        return 10

    total_wins, total_losses, tot_rounds_won, tot_rounds_lost = player
    avg_winning_margin = player_margin[0] if player_margin and player_margin[0] else 0
    avg_losing_margin  = player_margin[1] if player_margin and player_margin[1] else 0

    if total_wins == 0 and total_losses == 0:
        return 10

    tot_matches = total_wins + total_losses
    tot_rounds  = tot_rounds_won + tot_rounds_lost

    win_ratio           = total_wins / tot_matches if tot_matches > 0 else 0
    rounds_won_ratio    = tot_rounds_won / tot_rounds if tot_rounds > 0 else 0
    winning_margin_ratio = avg_winning_margin / 10 if avg_winning_margin > 0 else 0
    losing_margin_ratio  = avg_losing_margin  / 10 if avg_losing_margin  > 0 else 0
    stabilization       = tot_matches / (tot_matches + 10)

    W1, W2, W3, W4, W5 = 50, 20, 10, 15, 5
    score = (
        W1 * win_ratio +
        W2 * winning_margin_ratio -
        W3 * losing_margin_ratio +
        W4 * rounds_won_ratio +
        W5 * stabilization
    )

    rows = await get_matchup_data(playerid, db)
    if rows:
        for row in rows:
            (opponent_id, wins, losses,
             rw, rl,
             avg_win_margin_v_op, avg_loss_margin_v_op) = row

            if opponent_id != op_id:
                continue

            tot_op      = wins + losses
            tot_op_rds  = rw + rl
            if tot_op == 0:
                continue

            win_ratio_v_op   = wins / tot_op
            rw_ratio_v_op    = rw / tot_op_rds if tot_op_rds > 0 else 0
            wm_ratio_v_op    = (avg_win_margin_v_op  or 0) / 10
            lm_ratio_v_op    = (avg_loss_margin_v_op or 0) / 10
            stab_v_op        = tot_op / (tot_op + 10)

            W6, W7, W8, W9, W10 = 50, 20, 10, 15, 5
            score += (
                W6  * win_ratio_v_op +
                W7  * wm_ratio_v_op -
                W8  * lm_ratio_v_op +
                W9  * rw_ratio_v_op +
                W10 * stab_v_op
            )

    return score


async def calculate_win_probability(score_a, score_b, scaling_factor=100):
    prob_a = round(1 / (1 + 10 ** ((score_b - score_a) / scaling_factor)), 2)
    return prob_a, round(1 - prob_a, 2)


async def calculate_mp_win_probabilities(player_ids, db):
    """
    Estimates win probability for each player in an MP lobby.
    Uses each player's 1v1 rating with softmax normalization.
    """
    ratings = {}
    for pid in player_ids:
        ratings[pid] = await get_rating(db, pid, mode='1v1')

    # Softmax over ratings scaled by Elo divisor
    exp_vals = {pid: math.exp(r / 400) for pid, r in ratings.items()}
    total    = sum(exp_vals.values())
    probs    = {pid: round(v / total, 4) for pid, v in exp_vals.items()}

    return probs