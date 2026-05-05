import discord
from discord.ext import commands
from command_helpers import match_to_db
from bet_helpers import handle_bet_payouts
from model_helpers import train_models
import aiosqlite

class Record(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def record(self, ctx, rounds_to_win: int, *args):
        """
        Usage: !record <rounds_to_win> @Player1 <rounds> @Player2 <rounds> ...
        Example (1v1): !record 10 @Raf 10 @Dom 7
        Example (MP):  !record 10 @Raf 10 @Dom 7 @Jake 4
        """
        async with aiosqlite.connect("rankings.db") as db:

            # --- PARSING ---
            if len(args) < 4:
                await ctx.send(
                    "Invalid input: Need at least 2 players.\n"
                    "Usage: `!record <rounds_to_win> @Player1 <rounds> @Player2 <rounds> ...`"
                )
                return

            if len(args) % 2 != 0:
                await ctx.send("Invalid input: Every player needs a corresponding round count.")
                return

            player_rounds = []

            for i in range(0, len(args), 2):
                try:
                    member = await commands.MemberConverter().convert(ctx, args[i])
                except commands.BadArgument:
                    await ctx.send(f"Invalid input: Could not find player `{args[i]}`.")
                    return
                try:
                    rounds = int(args[i + 1])
                except ValueError:
                    await ctx.send(f"Invalid input: `{args[i + 1]}` is not a valid round count.")
                    return

                player_rounds.append((member, rounds))

            # --- VALIDATION ---
            if len(player_rounds) > 10:
                await ctx.send("Invalid input: Maximum of 10 players per match.")
                return

            player_ids = [m.id for m, _ in player_rounds]
            if len(player_ids) != len(set(player_ids)):
                await ctx.send("Invalid input: Duplicate players are not allowed.")
                return

            if rounds_to_win < 1:
                await ctx.send("Invalid input: rounds_to_win must be at least 1.")
                return

            if any(r < 0 for _, r in player_rounds):
                await ctx.send("Invalid input: Round counts cannot be negative.")
                return

            if any(r > rounds_to_win for _, r in player_rounds):
                await ctx.send(f"Invalid input: No player can have more than {rounds_to_win} rounds.")
                return

            winners = [(m, r) for m, r in player_rounds if r == rounds_to_win]
            if len(winners) == 0:
                await ctx.send(f"Invalid input: Exactly one player must have {rounds_to_win} rounds.")
                return
            if len(winners) > 1:
                await ctx.send(f"Invalid input: Only one player can have {rounds_to_win} rounds.")
                return

            # --- MODE DETECTION ---
            game_mode = '1v1' if len(player_rounds) == 2 else 'mp'

            # --- RECORD ---
            try:
                results = await match_to_db(
                    [(m.id, r) for m, r in player_rounds],
                    rounds_to_win,
                    db
                )
            except Exception as e:
                await ctx.send(f"An error occurred while recording the match: {e}")
                return

            # --- BUILD OUTPUT ---
            member_lookup = {m.id: m for m, _ in player_rounds}
            mode_label = '1v1' if game_mode == '1v1' else 'Multiplayer'

            match_lines = []
            for r in results:
                member = member_lookup[r['player_id']]
                sp_str  = f"+{r['sp_change']}"  if r['sp_change']  >= 0 else str(r['sp_change'])
                sc_str  = f"+{r['straftcoin_change']}" if r['straftcoin_change'] >= 0 else str(r['straftcoin_change'])
                elo_str = f"+{r['elo_change']:.1f}" if r['elo_change'] >= 0 else f"{r['elo_change']:.1f}"

                match_lines.append(
                    f"**#{r['placement']} {member.mention}** — {r['rounds_won']} rounds\n"
                    f"  SP: {sp_str} → {r['new_sp']} | Rank: **{r['rank']}** {r['rank_emoji']}\n"
                    f"  Straftcoin: {sc_str} → {r['new_straftcoins']} | Elo: {elo_str}"
                )

            message_content = (
                f"**Match Recorded** *({mode_label} — First to {rounds_to_win})*\n\n"
                + "\n\n".join(match_lines)
            )
            message = await ctx.send(message_content)

            # --- BET PAYOUTS ---
            match_id     = results[0]['match_id']
            winner       = results[0]
            second       = results[1]
            winner_member = member_lookup[winner['player_id']]
            total_rounds = sum(r['rounds_won'] for r in results)
            spread       = winner['rounds_won'] - second['rounds_won']

            bet_settlements_message = await handle_bet_payouts(
                match_id,
                winner_member.display_name,
                winner['player_id'],
                spread,
                total_rounds,
                db
            )

            if bet_settlements_message:
                thread = await ctx.channel.create_thread(
                    name=f"Resolved Bets — {winner_member.display_name}'s match",
                    message=message
                )
                await thread.send(f"**Spread (1st vs 2nd):** {spread}\n**Total Rounds:** {total_rounds}")
                await thread.send(bet_settlements_message)

            await train_models('spread', db)


async def setup(bot):
    await bot.add_cog(Record(bot))