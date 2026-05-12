import asyncio
import discord
from discord.ext import commands
from helpers.command_helpers import match_to_db, get_emoji
from helpers.bet_helpers import handle_bet_payouts
from helpers.model_helpers import train_models, train_mp_models
import aiosqlite

class Record(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def record(self, ctx, rounds_to_win: int, *args):
        """
        Usage : !record <rounds_to_win> @Player1 <rounds> @Player2 <rounds> ...
        1v1   : !record 10 @Raf 10 @Dom 7
        MP    : !record 10 @Raf 10 @Dom 7 @Jake 4
        """
        async with aiosqlite.connect("rankings.db") as db:

            
            # PARSING
            
            if len(args) < 4:
                await ctx.send(
                    "Invalid input: Need at least 2 players.\n"
                    "Usage: `!record <rounds_to_win> @Player1 <rounds> @Player2 <rounds> ...`"
                )
                return

            if len(args) % 2 != 0:
                await ctx.send(
                    "Invalid input: Every player needs a corresponding round count."
                )
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
                    await ctx.send(
                        f"Invalid input: `{args[i + 1]}` is not a valid round count."
                    )
                    return

                player_rounds.append((member, rounds))

            
            # VALIDATION
            
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

            if len(player_rounds) == 2 and rounds_to_win < 10:
                await ctx.send("Invalid input: 1v1 matches require at least 10 rounds to win.")
                return

            if any(r < 0 for _, r in player_rounds):
                await ctx.send("Invalid input: Round counts cannot be negative.")
                return

            if any(r > rounds_to_win for _, r in player_rounds):
                await ctx.send(
                    f"Invalid input: No player can have more than {rounds_to_win} rounds."
                )
                return

            winners = [(m, r) for m, r in player_rounds if r == rounds_to_win]
            if len(winners) == 0:
                await ctx.send(
                    f"Invalid input: Exactly one player must have {rounds_to_win} rounds."
                )
                return
            if len(winners) > 1:
                await ctx.send(
                    f"Invalid input: Only one player can have {rounds_to_win} rounds."
                )
                return

            
            # RECORD
            
            try:
                results = await match_to_db(
                    [(m.id, r) for m, r in player_rounds],
                    rounds_to_win,
                    db
                )
            except Exception as e:
                await ctx.send(f"An error occurred while recording the match: {e}")
                return

            
            # BUILD OUTPUT MESSAGE
            
            member_lookup   = {m.id: m for m, _ in player_rounds}
            game_mode       = results[0]['game_mode']
            mode_label      = '1v1' if game_mode == '1v1' else 'Multiplayer'
            straftcoin_emoji = await get_emoji(['Straftcoin']) 

            embed = discord.Embed(
                title='Match Recorded',
                description=f'*{mode_label} — First to {rounds_to_win}*',
                color=discord.Color(0x90ee90)
            )

            for r in results:
                member  = member_lookup[r['player_id']]
                sp_str  = f"+{r['sp_change']}"         if r['sp_change']         >= 0 else str(r['sp_change'])
                sc_str  = f"+{r['straftcoin_change']}" if r['straftcoin_change'] >= 0 else str(r['straftcoin_change'])
                icon    = f"#{r['placement']}"

                embed.add_field(
                    name=f"{icon} {member.display_name} — {r['rounds_won']} rounds",
                    value=(
                        f"SP: {sp_str} → **{r['new_sp']}**\n"
                        f"Rank: **{r['rank']}** {r['rank_emoji']}\n"
                        f"Straftcoins: {sc_str} → **{r['new_straftcoins']}**{straftcoin_emoji[0]}"
                    ),
                    inline=(game_mode == '1v1')
                )

            message = await ctx.send(embed=embed)

            
            # BET PAYOUTS
            
            winner       = results[0]
            second       = results[1]
            total_rounds = sum(r['rounds_won'] for r in results)
            spread       = winner['rounds_won'] - second['rounds_won']
            participant_ids = [r['player_id'] for r in results]

            bet_match_title = f"[FT{rounds_to_win}] " + " vs ".join(
                sorted(member_lookup[r['player_id']].display_name for r in results)
            )

            bet_settlements_message = await handle_bet_payouts(
                winner['match_id'],
                bet_match_title,
                winner['player_id'],
                spread,
                total_rounds,
                db
            )

            if bet_settlements_message:
                embeds, _ = bet_settlements_message
                winner_member = member_lookup[winner['player_id']]
                thread = await ctx.channel.create_thread(
                    name=f"Resolved Bets — {winner_member.display_name}'s match",
                    message=message
                )
                for embed in embeds:
                    await thread.send(embed=embed)

            if results[0]['game_mode'] == '1v1':
                asyncio.create_task(train_models('spread'))
            else:
                asyncio.create_task(train_mp_models())

    @record.error
    async def record_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send(
                "Invalid input: missing or invalid rounds to win.\n"
                "Usage: `!record <rounds_to_win> @Player1 <rounds> @Player2 <rounds> ...`\n"
                "Example: `!record 10 @Raf 10 @Dom 7`"
            )


async def setup(bot):
    await bot.add_cog(Record(bot))