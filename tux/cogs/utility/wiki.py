from typing import Any, cast

import discord
from discord import Guild, app_commands
from discord.ext import commands
from loguru import logger

from tux.bot import Tux
from tux.ui.embeds import EmbedCreator
from tux.utils import checks
from tux.utils.functions import generate_usage
from tux.utils.decorators import defer, loader
from tux.wrappers.wiki import BlockRegistry, Result, ResultStatus, WikiRegistry
from tux.wrappers.wiki import query_wiki as pwb_query_wiki


class Wiki(commands.Cog):
    """
    A Cog for handling wiki-related commands within a Discord server.

    Parameters
    ----------
    bot : Tux
        The bot instance that this cog is attached to.
    """
    def __init__(self, bot: Tux) -> None:
        self.bot = bot
        self.wiki.usage = generate_usage(self.wiki)
        self.search_wiki.usage = generate_usage(self.search_wiki)
        self.add_wiki.usage = generate_usage(self.add_wiki)
        self.delete_wiki.usage = generate_usage(self.delete_wiki)
        self.list_wikis.usage = generate_usage(self.list_wikis)
        self.add_block.usage = generate_usage(self.add_block)
        self.remove_block.usage = generate_usage(self.remove_block)
        self.list_blocks.usage = generate_usage(self.list_blocks)

    async def cog_load(self) -> None:
        """
        Called when the cog is loaded.
        """
        pass

    async def autocomplete_wiki_name(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """
        Autocomplete handler for registered wiki names.

        Parameters
        ----------
        interaction : discord.Interaction
            The interaction that triggered the autocomplete.
        current : str
            The current input from the user.

        Returns
        -------
        list of app_commands.Choice[str]
            List of autocomplete choices.
        """
        registry = WikiRegistry(cast(int, interaction.guild_id))  
        result = await registry.list()
        result = Result(list(result.data.keys()), status=result.status, message=result.message)
        return await self.autocomplete_from_result(result=result, current=current)

    async def autocomplete_static_wiki_name(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """
        Autocomplete handler for static wiki names.

        Parameters
        ----------
        interaction : discord.Interaction
            The interaction object.
        current : str
            The user's current input.

        Returns
        -------
        list of app_commands.Choice[str]
            Matching choices.
        """
        registry = WikiRegistry(cast(int,interaction.guild_id))
        result = Result(list(registry.static_families), status=ResultStatus.DONE, message="")
        return await self.autocomplete_from_result(result=result, current=current)

    async def autocomplete_dynamic_wiki_name(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """
        Autocomplete handler for dynamically added wiki names.

        Parameters
        ----------
        interaction : discord.Interaction
            The interaction object.
        current : str
            The user's current input.

        Returns
        -------
        list of app_commands.Choice[str]
            Matching choices.
        """
        registry = WikiRegistry(cast(int,interaction.guild_id)) 
        result = Result(await registry.guild_name_list(), status=ResultStatus.DONE, message="")
        return await self.autocomplete_from_result(result=result, current=current)

    async def autocomplete_blocked_wiki_name(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """
        Autocomplete handler for blocked wiki names.

        Parameters
        ----------
        interaction : discord.Interaction
            The interaction object.
        current : str
            The user's current input.

        Returns
        -------
        list of app_commands.Choice[str]
            Matching choices.
        """
        registry = BlockRegistry(cast(int, interaction.guild_id))
        result = await registry.list()
        result = Result(list(result.data.keys()), status=result.status, message=result.message)
        return await self.autocomplete_from_result(result=result, current=current)

    async def autocomplete_from_result(self, result: Result[list[str]], current: str) -> list[app_commands.Choice[str]]:
        """
        Converts a Result object into a list of autocomplete choices.

        Parameters
        ----------
        result : Result[list[str]]
            The result object containing possible choices.
        current : str
            The current input to match against.

        Returns
        -------
        list of app_commands.Choice[str]
            Matching choices.
        """
        if result.status == ResultStatus.EXCEPTION:
            return []

        if result.status == ResultStatus.DONE:
            if not current:
                return [app_commands.Choice(name=name, value=name) for name in sorted(result.data)][:25]

            return [
                app_commands.Choice(name=name, value=name) for name in result.data if current.lower() in name.lower()
            ][:25]

        return []

    async def safe_send(self, ctx: commands.Context[Tux], *args: Any, **kwargs: Any) -> None:
        """
        Safely sends a message whether in interaction or traditional command context.

        Parameters
        ----------
        ctx : commands.Context[Tux]
            The command context.
        *args : Any
            Positional arguments to pass to the send method.
        **kwargs : Any
            Keyword arguments to pass to the send method.
        """
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

    def create_embed(
        self,
        result: Result[Any],
        ctx: commands.Context[Tux],
    ) -> discord.Embed:
        """
        Create a styled embed message based on the result status.

        Parameters
        ----------
        result : Result[Any]
            Result object to extract message and status.
        ctx : commands.Context[Tux]
            Context for user information.

        Returns
        -------
        discord.Embed
            An embed appropriate for the result.
        """
        embed_type = EmbedCreator.INFO
        description = result.message or ""

        if result.status == ResultStatus.EXCEPTION:
            embed_type = EmbedCreator.ERROR
            description = result.message or "An error occurred."

        elif result.status == ResultStatus.NOT_FOUND:
            embed_type = EmbedCreator.WARNING if hasattr(EmbedCreator, "WARNING") else EmbedCreator.INFO
            description = result.message or "Not found."

        elif result.status == ResultStatus.ALREADY_EXISTS:
            embed_type = EmbedCreator.INFO
            description = result.message or "Already exists."

        elif result.status == ResultStatus.DONE:
            embed_type = EmbedCreator.INFO
            description = result.message or "Success."

        return EmbedCreator.create_embed(
            bot=self.bot,
            embed_type=embed_type,
            user_name=ctx.author.name,
            user_display_avatar=ctx.author.display_avatar.url,
            description=description,
        )




    @commands.hybrid_group(
        name="wiki",
        aliases=["wk"],
    )
    @commands.guild_only()
    @loader()
    @defer()
    async def wiki(self, ctx: commands.Context[Tux]) -> None:
        """Wiki-related commands."""
        await ctx.send_help("wiki")
    
    @wiki.command(name="list")
    @loader()
    @defer()
    async def list_wikis(self, ctx: commands.Context[Tux]) -> None:
        """List all registered wikis."""
        if ctx.interaction:
            await ctx.interaction.response.defer()
        registry = WikiRegistry( ctx.guild.id) # type: ignore  
        wiki_list = await registry.list()

        if wiki_list.status == ResultStatus.DONE and wiki_list.data:
            description = " - ".join(wiki_list.data)
            embed = self.create_embed(wiki_list, ctx)
            embed.description = description
            embed.set_footer(
                text=f"Total: {len(wiki_list.data)} wikis",
                icon_url=embed.footer.icon_url if embed.footer else None,
            )
            await self.safe_send(ctx, embed=embed)
            return

        embed = self.create_embed(wiki_list, ctx)
        await self.safe_send(ctx, embed=embed)

    @wiki.command(name="search")
    @app_commands.autocomplete(name=autocomplete_wiki_name)
    @loader()
    @defer()
    async def search_wiki(self, ctx: commands.Context[Tux], name: str, *, query: str) -> None:
        """Search a registered wiki."""
        registry = WikiRegistry(cast(Guild,ctx.guild).id)  
        result = await registry.get(name)

        if result.status == ResultStatus.DONE and result.data is not None:
            try:
                query_result = pwb_query_wiki(query, result.data)
                embed = self.create_embed(query_result, ctx)
                logger.info(embed.title)
                if query_result.status == ResultStatus.DONE:
                    embed.title = query_result.data[0]
                await self.safe_send(ctx, embed=embed)
            except Exception as e:
                logger.error(f"Error querying wiki {name}: {e!r}")
                await self.safe_send(ctx, "❌ An error occurred while querying the wiki.")
        else:
            embed = self.create_embed(result, ctx)
            await self.safe_send(ctx, embed=embed)
        
    @wiki.command(name="info")
    @loader()
    @defer()
    async def info_wiki(self, ctx: commands.Context[Tux]) -> None:
        pass
    
    @wiki.command(name="add")
    @checks.has_pl(2)
    @loader()
    @defer()
    async def add_wiki(
        self,
        ctx: commands.Context[Tux],
        name: str,
        url: str,
        article_path: str | None = None,
        script_path: str | None = None,
    ) -> None:
        """Register a new wiki."""
        registry = WikiRegistry(ctx.guild.id)  # type: ignore
        result = await registry.add(name, url, article_path, script_path)
        embed = self.create_embed(result, ctx)
        await self.safe_send(ctx, embed=embed)

    @wiki.command(name="delete")
    @checks.has_pl(2)
    @loader()
    @defer()
    @app_commands.autocomplete(name=autocomplete_dynamic_wiki_name)
    async def delete_wiki(self, ctx: commands.Context[Tux], name: str) -> None:
        """Delete a registered wiki."""

        registry = WikiRegistry(guild_id=ctx.guild.id)  # type: ignore
        result = await registry.delete(name)
        embed = self.create_embed(result, ctx)
        await self.safe_send(ctx, embed=embed)

    @wiki.command(name="add_block")
    @app_commands.autocomplete(name=autocomplete_static_wiki_name)
    @loader()
    @defer()
    async def add_block(self, ctx: commands.Context[Tux], name: str):
        """Block's a wiki."""
        registry = BlockRegistry(ctx.guild.id)  # type: ignore
        result = await registry.block(name)
        embed = self.create_embed(result, ctx)
        await self.safe_send(ctx, embed=embed)

    @wiki.command(name="remove_block")
    @app_commands.autocomplete(name=autocomplete_blocked_wiki_name)
    @loader()
    @defer()
    async def remove_block(self, ctx: commands.Context[Tux], name: str):
        """Unblock's a wiki."""
        registry = BlockRegistry(ctx.guild.id)  # type: ignore
        result = await registry.unblock(name)
        embed = self.create_embed(result, ctx)
        await self.safe_send(ctx, embed=embed)

    @wiki.command(name="list_blocks")
    @loader()
    @defer()
    async def list_blocks(self, ctx: commands.Context[Tux]) -> None:
        """List all blocked wikis."""
        registry = BlockRegistry(ctx.guild.id)  # type: ignore
        wiki_list = await registry.list()

        if wiki_list.status == ResultStatus.DONE and wiki_list.data:
            description = " - ".join(wiki_list.data)
            embed = self.create_embed(wiki_list, ctx)
            embed.description = description
            embed.set_footer(
                text=f"Total: {len(wiki_list.data)} blocked wikis",
                icon_url=embed.footer.icon_url if embed.footer else None,
            )
            await self.safe_send(ctx, embed=embed)
            return

        embed = self.create_embed(wiki_list, ctx)
        await self.safe_send(ctx, embed=embed)



async def setup(bot: Tux) -> None:
    await bot.add_cog(Wiki(bot))
