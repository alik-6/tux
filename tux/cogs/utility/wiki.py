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

        self.registry = WikiRegistry()

    async def cog_load(self) -> None:
        """Load the cog and log the registered wikis."""
        self.registry.register("nixos", "https://wiki.nixos.org/")
        self.registry.register(
            name="archlinux",
            site="https://wiki.archlinux.org/",
            article_path="/title/$1",
            script_path="/",
        )
        self.registry.register(name="atlwiki", site="https://atl.wiki", article_path="/$1", script_path="/")
        logger.info(f"Loaded {len(self.registry.list())} registered wikis.")

    async def autocomplete_wiki_names(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if not current:
            # Show the first 25 wikis alphabetically if user hasn't typed anything yet
            return [app_commands.Choice(name=name, value=name) for name in sorted(self.registry.list())][:25]

        # Otherwise filter by user input
        return [
            app_commands.Choice(name=name, value=name)
            for name in self.registry.list()
            if current.lower() in name.lower()
        ][:25]

    async def safe_send(self, ctx: commands.Context[Tux], *args: str, **kwargs: Any) -> None:
        if ctx.interaction:
            await ctx.interaction.followup.send(*args, **kwargs)
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
    async def wiki(self, ctx: commands.Context[Tux]) -> None:
        """Wiki-related commands."""
        await ctx.send_help("wiki")

    @wiki.command(name="list")
    async def list_wikis(self, ctx: commands.Context[Tux]) -> None:
        """List all registered wikis."""
        if not self.registry.list():
            await ctx.send("❌ No wikis are currently registered.")
            return

        description = "`" + " - ".join(self.registry.list()) + "`"
        embed = self.create_embed(("Registered Wikis", description), ctx)
        embed.set_footer(
            text=f"{embed.footer.text}, Total: {len(self.registry.list())} wikis",
            icon_url=embed.footer.icon_url,
        )
        await ctx.send(embed=embed)

    @wiki.command(name="search")
    @app_commands.autocomplete(wiki_name=autocomplete_wiki_names)
    async def search_wiki(self, ctx: commands.Context[Tux], wiki_name: str, *, query: str) -> None:
        """
        Search a registered wiki.

        Parameters
        ----------
        wiki_name : str
            The short name of the registered wiki.
        query : str
            The search query.
        """
        # defers the interaction response if it's an interaction command to prevent timeout
        if ctx.interaction:
            await ctx.interaction.response.defer()
        family = self.registry.get(wiki_name.lower())
        if not family:
            await self.safe_send(
                ctx,
                f"❌ Wiki `{wiki_name}` is not registered. Use `!wiki list` to see available wikis.",
                ephemeral=True,
            )
            return
        try:
            result = pwb_query_wiki(query, family)
            embed = self.create_embed(result, ctx)
            await self.safe_send(ctx, embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error querying wiki {wiki_name}: {e}")
            await self.safe_send(ctx, "❌ An error occurred while querying the wiki.", ephemeral=True)

    @wiki.command(name="add")
    @checks.has_pl(2)
    async def add_wiki(self, ctx: commands.Context[Tux], name: str, api_url: str) -> None:
        """
        Register a new wiki manually. (Note: Dynamic Family registration not supported here.)

        Parameters
        ----------
        name : str
            The short name for the wiki.
        api_url : str
            The full URL to the wiki API endpoint. (Not used with pywikibot Family objects.)
        """

        await ctx.send("❌ Manual wiki registration is not supported with pywikibot. *`yet`*")

    @add_wiki.error
    async def add_wiki_error(self, ctx: commands.Context[Tux], error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await self.safe_send(ctx, "❌ You do not have permission to use this command.", ephemeral=True)
        else:
            await self.safe_send(ctx, "❌ An error occurred while adding the wiki.", ephemeral=True)


async def setup(bot: Tux) -> None:
    await bot.add_cog(Wiki(bot))
