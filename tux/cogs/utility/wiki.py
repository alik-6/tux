from typing import Any

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from tux.bot import Tux
from tux.ui.embeds import EmbedCreator
from tux.utils import checks
from tux.utils.functions import generate_usage
from tux.wrappers.wiki import WikiRegistry
from tux.wrappers.wiki import query_wiki as pwb_query_wiki


class Wiki(commands.Cog):
    def __init__(self, bot: Tux) -> None:
        self.bot = bot
        self.wiki.usage = generate_usage(self.wiki)
        self.search_wiki.usage = generate_usage(self.search_wiki)
        self.add_wiki.usage = generate_usage(self.add_wiki)

    async def cog_load(self) -> None:
        pass  # Registry setup was commented out

    async def autocomplete_wiki_names(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        registry = WikiRegistry(interaction.guild_id)  # type: ignore
        wiki_list = await registry.list()
        if not current:
            return [app_commands.Choice(name=name, value=name) for name, _ in sorted(wiki_list)][:25]
        return [app_commands.Choice(name=name, value=name) for name, _ in wiki_list if current.lower() in name.lower()][
            :25
        ]

    async def safe_send(self, ctx: commands.Context[Tux], *args: Any, **kwargs: Any) -> None:
        if ctx.interaction:
            done = ctx.interaction.response.is_done()
            logger.debug(f"[safe_send] interaction.response.is_done() = {done}")
            try:
                if not done:
                    logger.debug("[safe_send] Sending initial response")
                    await ctx.interaction.response.send_message(*args, **kwargs)
                else:
                    logger.debug("[safe_send] Sending followup response")
                    kwargs.pop("ephemeral", None)
                    await ctx.interaction.followup.send(*args, **kwargs)
            except Exception as e:
                logger.error(f"[safe_send] Failed to send message: {e!r}")
                raise
        else:
            await ctx.send(*args, **kwargs)

    def create_embed(self, result: tuple[str, str], ctx: commands.Context[Tux]) -> discord.Embed:
        assert isinstance(result, tuple) and len(result) == 2
        title, description = result

        if title == "error":
            return EmbedCreator.create_embed(
                bot=self.bot,
                embed_type=EmbedCreator.ERROR,
                user_name=ctx.author.name,
                user_display_avatar=ctx.author.display_avatar.url,
                description="No search results found.",
            )

        return EmbedCreator.create_embed(
            bot=self.bot,
            embed_type=EmbedCreator.INFO,
            user_name=ctx.author.name,
            user_display_avatar=ctx.author.display_avatar.url,
            title=title,
            description=description,
        )

    @commands.hybrid_group(name="wiki", aliases=["wk"], invoke_without_command=True)
    @commands.guild_only()
    async def wiki(self, ctx: commands.Context[Tux]) -> None:
        """Wiki-related commands."""
        await ctx.send_help("wiki")

    @wiki.command(name="list")
    async def list_wikis(self, ctx: commands.Context[Tux]) -> None:
        """List all registered wikis."""
        if ctx.interaction:
            await ctx.interaction.response.defer()
        registry = WikiRegistry(ctx.guild.id)  # type: ignore
        wiki_list = await registry.list()

        if not wiki_list:
            await self.safe_send(ctx, "❌ No wikis are currently registered.")
            return

        description = "`" + " - ".join([name for name, _ in wiki_list]) + "`"
        embed = self.create_embed(("Registered Wikis", description), ctx)
        embed.set_footer(
            text=f"{embed.footer.text}, Total: {len(wiki_list)} wikis",
            icon_url=embed.footer.icon_url,
        )
        await self.safe_send(ctx, embed=embed)

    @wiki.command(name="search")
    @app_commands.autocomplete(wiki_name=autocomplete_wiki_names)
    async def search_wiki(self, ctx: commands.Context[Tux], wiki_name: str, *, query: str) -> None:
        """Search a registered wiki."""
        if ctx.interaction:
            await ctx.interaction.response.defer()
        registry = WikiRegistry(ctx.guild.id)  # type: ignore
        family = await registry.get(wiki_name)
        if not family:
            await self.safe_send(
                ctx,
                f"❌ Wiki `{wiki_name}` is not registered. Use `!wiki list` to see available wikis.",
            )
            return
        try:
            result = pwb_query_wiki(query, family)
            embed = self.create_embed(result, ctx)
            await self.safe_send(ctx, embed=embed)
        except Exception as e:
            logger.error(f"Error querying wiki {wiki_name}: {e}")
            await self.safe_send(ctx, "❌ An error occurred while querying the wiki.")

    @wiki.command(name="add")
    @checks.has_pl(2)
    async def add_wiki(
        self,
        ctx: commands.Context[Tux],
        name: str,
        url: str,
        article_path: str | None = None,
        script_path: str | None = None,
    ) -> None:
        """Register a new wiki manually."""
        if ctx.interaction:
            await ctx.interaction.response.defer()

        registry = WikiRegistry(ctx.guild.id)  # type: ignore
        is_registerd = await registry.register(name, url, article_path, script_path)
        if is_registerd:
            await self.safe_send(ctx, f"Registered {name}")
        else:
            await self.safe_send(ctx, "❌ Couldn't Register WOMP WOMP")

    @add_wiki.error
    async def add_wiki_error(self, ctx: commands.Context[Tux], error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await self.safe_send(ctx, "❌ You do not have permission to use this command.")
        else:
            await self.safe_send(ctx, "❌ An error occurred while adding the wiki.")

    @wiki.command(name="delete")
    @checks.has_pl(2)
    async def delete_wiki(self, ctx: commands.Context[Tux], name: str) -> None:
        """Delete a registered wiki."""
        if ctx.interaction:
            await ctx.interaction.response.defer()

        registry = WikiRegistry(ctx.guild.id)  # type: ignore
        is_deleted = await registry.delete(name)
        if is_deleted:
            await self.safe_send(ctx, f"Deleted {name}")
        else:
            await self.safe_send(ctx, "❌ Couldn't Delete WOMP WOMP")

    @delete_wiki.error
    async def delete_wiki_error(self, ctx: commands.Context[Tux], error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await self.safe_send(ctx, "❌ You do not have permission to use this command.")
        else:
            await self.safe_send(ctx, "❌ An error occurred while deleting the wiki.")


async def setup(bot: Tux) -> None:
    await bot.add_cog(Wiki(bot))
