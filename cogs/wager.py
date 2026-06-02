import discord
from discord.ext import commands
import asyncio
import re
import aiosqlite
from helpers.command_helpers import sc_fmt

_WAGER_INPUT_REGEX = re.compile(r'^wager\s+(\d+)$', re.IGNORECASE)
_WAGER_SECONDS = 30


class Wager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # thread_id → {'player_a': int, 'player_b': int}
        self.active_wager_windows: dict = {}

    @commands.command(name='wager')
    async def wager(self, ctx, player: discord.Member):
        """
        Usage: !wager @Player
        Opens a 2-minute window. Both players type 'wager <amount>' in the thread.
        Amounts can be edited until the timer ends - first message's final amount is used.
        Winner of the 1v1 takes the total pot when the match is recorded.
        """
        player_a = ctx.author
        player_b = player

        if player_a.id == player_b.id:
            await ctx.send(embed=discord.Embed(
                description="You can't wager against yourself.",
                color=discord.Color.red()
            ))
            return

        # Block if a wager window is already open for this pair
        for state in self.active_wager_windows.values():
            if {state['player_a'], state['player_b']} == {player_a.id, player_b.id}:
                await ctx.send(embed=discord.Embed(
                    description=f"A wager window is already open between you and {player_b.mention}.",
                    color=discord.Color.red()
                ))
                return

        # Block if an unresolved DB wager already exists for this pair
        async with aiosqlite.connect('rankings.db') as db:
            async with db.execute("""
                SELECT wager_id FROM wagers
                WHERE status = 'active'
                  AND (
                    (player_a_id = ? AND player_b_id = ?) OR
                    (player_a_id = ? AND player_b_id = ?)
                  )
            """, (player_a.id, player_b.id, player_b.id, player_a.id)) as cur:
                existing = await cur.fetchone()

        if existing:
            await ctx.send(embed=discord.Embed(
                description=(
                    f"An unresolved wager already exists between you and {player_b.mention}. "
                    f"It will resolve automatically when your next 1v1 is recorded."
                ),
                color=discord.Color.red()
            ))
            return

        # --- Create countdown message and thread ---
        seconds = _WAGER_SECONDS
        minutes_init, secs_init = divmod(seconds, 60)
        wager_title = f"{player_a.display_name} vs {player_b.display_name} - Wager"

        bot_message = await ctx.send(
            f"Wager: **{player_a.display_name}** vs **{player_b.display_name}**\n"
            f"**Time Remaining: {minutes_init:02}:{secs_init:02}**"
        )
        thread = await ctx.channel.create_thread(
            name=wager_title,
            message=bot_message
        )

        instructions = discord.Embed(
            title="Wager Window Open",
            description=(
                f"{player_a.mention} vs {player_b.mention}\n\n"
                f"Type **`wager <amount>`** to set your stake.\n"
                f"You can **edit your message** to change the amount before the timer ends.\n"
                f"If you send multiple messages, only your **first message** counts.\n"
                f"Window closes in **2 minutes**. Both players must submit or the wager is cancelled."
            ),
            color=discord.Color(0x90ee90)
        )
        await thread.send(embed=instructions)

        # Register window state (amounts are read from thread history at countdown end)
        self.active_wager_windows[thread.id] = {
            'player_a': player_a.id,
            'player_b': player_b.id,
        }

        # --- Countdown ---
        for remaining in range(seconds - 1, -1, -1):
            await asyncio.sleep(1)
            minutes, secs = divmod(remaining, 60)
            await bot_message.edit(
                content=(
                    f"Wager: **{player_a.display_name}** vs **{player_b.display_name}**\n"
                    f"**Time Remaining: {minutes:02}:{secs:02}**"
                )
            )

        state = self.active_wager_windows.pop(thread.id, None)
        if state is None:
            return

        # --- Scan thread history to find each player's first wager message (current content) ---
        # Discord returns messages with their current content after edits.
        # oldest_first=True ensures we pick up the first message sent, not a later one.
        player_amounts = {}  # player_id → amount from their first wager message
        async for msg in thread.history(oldest_first=True, limit=200):
            if msg.author.bot:
                continue
            if msg.author.id not in (player_a.id, player_b.id):
                continue
            if msg.author.id in player_amounts:
                continue  # already found their first message; skip any later ones
            m = _WAGER_INPUT_REGEX.match(msg.content.strip())
            if m:
                amount = int(m.group(1))
                if amount > 0:
                    player_amounts[msg.author.id] = amount

        a_amount = player_amounts.get(player_a.id)
        b_amount = player_amounts.get(player_b.id)

        # --- Cancel if either player didn't submit ---
        if a_amount is None or b_amount is None:
            missing = []
            if a_amount is None:
                missing.append(player_a.mention)
            if b_amount is None:
                missing.append(player_b.mention)
            await thread.send(embed=discord.Embed(
                description=f"❌ Wager cancelled - {', '.join(missing)} did not submit a stake.",
                color=discord.Color.red()
            ))
            await thread.edit(locked=True)
            return

        # --- Re-verify balances and finalize ---
        async with aiosqlite.connect('rankings.db') as db:
            async with db.execute(
                "SELECT straftcoins FROM players WHERE user_id = ?", (player_a.id,)
            ) as cur:
                row_a = await cur.fetchone()
            async with db.execute(
                "SELECT straftcoins FROM players WHERE user_id = ?", (player_b.id,)
            ) as cur:
                row_b = await cur.fetchone()

            balance_a = row_a[0] if row_a else 0
            balance_b = row_b[0] if row_b else 0

            errors = []
            if a_amount > balance_a:
                errors.append(
                    f"{player_a.mention} only has {sc_fmt(balance_a)} SC "
                    f"(wagered {sc_fmt(a_amount)} SC)"
                )
            if b_amount > balance_b:
                errors.append(
                    f"{player_b.mention} only has {sc_fmt(balance_b)} SC "
                    f"(wagered {sc_fmt(b_amount)} SC)"
                )

            if errors:
                await thread.send(embed=discord.Embed(
                    description="❌ Wager cancelled - insufficient funds: " + "; ".join(errors),
                    color=discord.Color.red()
                ))
                await thread.edit(locked=True)
                return

            # Deduct both stakes
            await db.execute(
                "UPDATE players SET straftcoins = straftcoins - ? WHERE user_id = ?",
                (a_amount, player_a.id)
            )
            await db.execute(
                "UPDATE players SET straftcoins = straftcoins - ? WHERE user_id = ?",
                (b_amount, player_b.id)
            )

            # Persist wager
            await db.execute("""
                INSERT INTO wagers (player_a_id, player_b_id, player_a_amount, player_b_amount, status)
                VALUES (?, ?, ?, ?, 'active')
            """, (player_a.id, player_b.id, a_amount, b_amount))

            await db.commit()

        pot = a_amount + b_amount
        confirm_embed = discord.Embed(
            title="✅ Wager Locked!",
            description=(
                f"{player_a.mention} wagered **{sc_fmt(a_amount)} SC**\n"
                f"{player_b.mention} wagered **{sc_fmt(b_amount)} SC**\n\n"
                f"🏆 Winner takes **{sc_fmt(pot)} SC** when the 1v1 is recorded."
            ),
            color=discord.Color(0x90ee90)
        )
        await thread.send(embed=confirm_embed)
        await thread.edit(locked=True)

    async def _check_wager_amount(self, author_id: int, content: str):
        """
        Parse 'wager <amount>' from content and check the author's balance.
        Returns True (valid), False (invalid/insufficient), or None (not a wager message).
        """
        m = _WAGER_INPUT_REGEX.match(content.strip())
        if not m:
            return None
        amount = int(m.group(1))
        if amount <= 0:
            return False
        async with aiosqlite.connect('rankings.db') as db:
            async with db.execute(
                "SELECT straftcoins FROM players WHERE user_id = ?", (author_id,)
            ) as cur:
                row = await cur.fetchone()
        balance = row[0] if row else 0
        return amount <= balance

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        state = self.active_wager_windows.get(message.channel.id)
        if state is None:
            return
        if message.author.id not in (state['player_a'], state['player_b']):
            return

        valid = await self._check_wager_amount(message.author.id, message.content)
        if valid is True:
            await message.add_reaction('✅')
        elif valid is False:
            await message.add_reaction('❌')

    @commands.Cog.listener()
    async def on_message_edit(self, _before, after):
        if after.author.bot:
            return
        state = self.active_wager_windows.get(after.channel.id)
        if state is None:
            return
        if after.author.id not in (state['player_a'], state['player_b']):
            return

        # Remove old reactions before adding the updated one
        me = self.bot.user
        for emoji in ('✅', '❌'):
            try:
                await after.remove_reaction(emoji, me)
            except (discord.HTTPException, discord.NotFound):
                pass

        valid = await self._check_wager_amount(after.author.id, after.content)
        if valid is True:
            await after.add_reaction('✅')
        elif valid is False:
            await after.add_reaction('❌')

    @wager.error
    async def wager_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send(
                "Usage: `!wager @Player`\n"
                "Both you and the mentioned player must type `wager <amount>` in the opened thread."
            )


async def setup(bot):
    await bot.add_cog(Wager(bot))
