from typing import Any, Callable, TypeVar, Awaitable, cast
from functools import wraps
from discord.ext import commands
import discord

from tux.bot import Tux 

T = TypeVar("T", bound=Callable[..., Awaitable[Any]])

def loader(emoji: str = '🐍') -> Callable[[T], T]:
    """
    Decorator to add a loading reaction emoji to a Discord message
    while an asynchronous command is running.

    Parameters
    ----------
    emoji : str, optional
        The emoji to use as a loading indicator. Default is '🐍'.

    Returns
    -------
    Callable[[T], T]
        The decorated asynchronous function with loading reaction behavior.
    
    Raises
    ------
    ValueError
        If a `commands.Context` object is not found in the arguments.
    """
    def decorator(func: T) -> T:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx: commands.Context[Tux]
            for arg in args:
                if isinstance(arg, commands.Context):
                    ctx = arg  # type: ignore[assignment]
                    break
            else:
                raise ValueError("Could not find 'ctx' in args for loader decorator.")

            try:
                await ctx.message.add_reaction(emoji)
                return await func(*args, **kwargs)
            finally:
                try:
                    await ctx.message.clear_reaction(emoji)
                except (discord.Forbidden, discord.HTTPException):
                    pass
        return cast(T, wrapper)
    return decorator

def defer() -> Callable[[T], T]:
    """
    Decorator to defer an interaction response in Discord,
    indicating that the bot is processing a long-running command.

    Returns
    -------
    Callable[[T], T]
        The decorated asynchronous function with deferral behavior.

    Raises
    ------
    ValueError
        If a `commands.Context` object is not found in the arguments.
    """
    def decorator(func: T) -> T:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx: commands.Context[Tux]
            for arg in args:
                if isinstance(arg, commands.Context):
                    ctx = arg  # type: ignore[assignment]
                    break
            else:
                raise ValueError("Could not find 'ctx' in args for defer decorator.")

            if ctx and ctx.interaction:
                await ctx.interaction.response.defer()
            return await func(*args, **kwargs)

        return cast(T, wrapper)
    return decorator
