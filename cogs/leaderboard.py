import discord
from discord.ext import commands
import aiosqlite
from command_helpers import get_ranks, get_emoji, get_display_name

class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def lb(self, ctx):
        RANKS = await get_ranks()

        async with aiosqlite.connect("rankings.db") as db:
            leaderboard_data = await db.execute("""
                SELECT user_id, rank, sp FROM players ORDER BY sp DESC
            """)
            rows = await leaderboard_data.fetchall()

        # Group players by rank
        rank_groups = {rank: [] for _, rank in RANKS}  # Initialize all ranks as empty
        for user_id, rank, sp in rows:
            rank_groups[rank].append((user_id, sp))

        # Calculate SP ranges for each rank
        rank_ranges = []
        for i, (threshold, rank) in enumerate(RANKS):
            upper_limit = RANKS[i + 1][0] - 1 if i + 1 < len(RANKS) else "∞"
            rank_ranges.append((rank, threshold, upper_limit))

        leaderboard_message = await ctx.send('**Ranked Straftat Leaderboard**')

        thread = await ctx.channel.create_thread(
            name='Ranked Straftat Leaderboard',
            message=leaderboard_message
        )

        # Build leaderboard message
        leaderboard_message_body = ''
        for rank, lower_limit, upper_limit in reversed(rank_ranges):  # Reverse to start with the highest rank
            rank_emote = await get_emoji([rank])

            if lower_limit == 3000:
                leaderboard_message_body += f"**{rank_emote[0]} {rank} (SP: {lower_limit}+):**\n"
            else:
                leaderboard_message_body += f"**{rank_emote[0]} {rank} (SP: {lower_limit} - {upper_limit}):**\n"

            players = rank_groups.get(rank, [])
            if players:
                for user_id, sp in players:
                    # Try to get the user's nickname (server-specific) or username
                    username = await get_display_name(ctx, user_id)
                    leaderboard_message_body += f"- {username}: {sp} SP\n"
            else:
                leaderboard_message_body += "No players in this rank.\n"

            leaderboard_message_body += "\n"

        await thread.send(leaderboard_message_body)

async def setup(bot):
    await bot.add_cog(Leaderboard(bot))