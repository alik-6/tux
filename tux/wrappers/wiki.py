from typing import Any, ClassVar
from urllib.parse import unquote, urlparse

import httpx
import pywikibot  # type: ignore
from loguru import logger
from pywikibot import Family, Site, _BaseSite, config  # type: ignore
from pywikibot.family import Family as BaseFamily

from tux.database.controllers.wiki import WikiBlockItemController, WikiController  # type: ignore


def generate_wiki_family(
    code: str,
    site: str,
    fname: str,
    article_path: str | None = None,
    script_path: str | None = None,
) -> BaseFamily:
    """
    Generate a custom Pywikibot Family subclass for a given MediaWiki site.

    This dynamically creates and returns a subclass of `BaseFamily` tailored to the
    specified MediaWiki installation. Useful for scripting against custom wikis
    using Pywikibot without creating a manual family file.

    Parameters
    ----------
    code : str
        Language or project code (e.g., 'en').
    site : str
        Full URL of the target MediaWiki site (e.g., 'https://wiki.archlinux.org').
    fname : str
        Internal family name used by Pywikibot (e.g., 'archwiki').
    article_path : str, optional
        The path pattern to articles, using `$1` as the placeholder (e.g., '/wiki/$1').
        Defaults to '/wiki/$1' if not provided.
    script_path : str, optional
        Path to the `api.php` endpoint (e.g., '/w'). Defaults to '/w' if not provided.

    Returns
    -------
    BaseFamily
        A dynamically generated subclass of `BaseFamily` configured for the specified site.

    Examples
    --------
    >>> family_class = generate_wiki_family(
    ...     code="en", site="https://wiki.archlinux.org", fname="archwiki", article_path="/title/$1", script_path="/"
    ... )
    >>> family = family_class()
    >>> family.apipath("en")
    '/api.php'
    """
    parsed_site = urlparse(site)
    hostname = parsed_site.netloc  # this gives 'wiki.archlinux.org'

    class Family(BaseFamily):
        name = fname
        langs: ClassVar[dict[str, str]] = {code: hostname}  # type: ignore[assignment]
        articlepath: ClassVar[dict[str, str]] = {code: article_path or "/wiki/$1"}

        def scriptpath(self, code: Any):
            return script_path or "/w"

        def apipath(self, code: Any) -> str:
            if script_path:
                return f"{script_path.rstrip('/')}/api.php"
            return "/w/api.php"  # Default API path for MediaWiki

    Family.__name__ = f"{fname.capitalize()}Family"
    return Family  # type: ignore[return]


def load_family(family_name: str) -> Family | None:  # type: ignore
    """
    Attempt to load a MediaWiki family by name.

    Parameters
    ----------
    family_name : str
        The name of the MediaWiki family to load.

    Returns
    -------
    Family or None
        The loaded Family object if successful, otherwise None.
    """
    try:
        return Family.load(family_name)  # type: ignore
    except Exception as e:
        logger.error(f"Failed to load family '{family_name}': {e}")
        return None


def get_preregistered_wikis() -> list[BaseFamily]:  # type: ignore
    """
    Load all configured MediaWiki families from pywikibot config.

    Returns
    -------
    list of Family
        A list of successfully loaded Family objects.
    """
    return [
        fam
        for name in config.family_files  # type: ignore
        if (fam := load_family(name)) is not None  # type: ignore
    ]


def search_wiki(site: _BaseSite, query: str) -> tuple[str, str] | None:  # type: ignore
    """
    Try to get a page from a given wiki site by exact title.
    Parameters
    ----------
    site : BaseSite
        The MediaWiki site to query.
    query : str
        The exact page title.

    Returns
    -------
    tuple of (str, str) or None
    A tuple containing the title and URL of the page if it exists,
    or None if the page does not exist or an error occurs.
    """
    try:
        page = pywikibot.Page(site, query)  # type: ignore
        if not page.exists():
            logger.info(f"Page '{query}' does not exist on '{site.family.name}'")  # type: ignore
            return None
        return page.title(), unquote(page.full_url())  # type: ignore
    except Exception as e:
        logger.error(f"Error retrieving page '{query}' on '{site.family.name}': {e}")  # type: ignore
        return None


def query_wiki(search: str, family: BaseFamily) -> tuple[str, str]:
    """
    Query a MediaWiki-compatible site for a search term.

    Parameters
    ----------
    search : str
        The term to search for.
    family : Family
        The MediaWiki family object representing the site.

    Returns
    -------
    tuple of (str, str)
        A tuple containing the title and URL of the first result,
        or fallback values if the search fails.
    """
    try:
        site = Site(code="en", fam=family)
    except Exception as e:
        logger.error(f"Site creation failed for family '{family.name}': {e}")
        return "error", "Site initialization failed."

    result = search_wiki(site, search)
    return result if result else ("No results", "N/A")


async def is_wiki(code: str, family: BaseFamily) -> bool:
    if code not in family.langs:
        logger.debug(f"Code '{code}' not in family.langs.")
        return False

    site = Site(code, family)
    api_url = f"{site.protocol()}://{site.hostname()}{site.apipath()}"  # type: ignore
    params = {"action": "query", "meta": "siteinfo", "format": "json"}

    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            response = await client.get(api_url, params=params)

        if response.status_code != 200:
            logger.warning(f"Non-200 response: {response.status_code} from {api_url}")
            return False

        data = response.json()
        generator = data.get("query", {}).get("general", {}).get("generator", "")
        return generator.startswith("MediaWiki")

    except (httpx.RequestError, ValueError) as e:
        logger.error(f"Error while checking site: {e}")
        return False


class WikiRegistry:
    def __init__(self, guild_id: int):
        self.db = WikiController(guild_id)
        self.block_db = WikiBlockItemController(guild_id)
        self.guild_id = guild_id
        self._static_families: dict[str, BaseFamily] = {
            f.name: f
            for f in get_preregistered_wikis()
            if f.name is not None  # type: ignore
        }

    async def _get_blocked_static_wikis(self) -> set[str]:
        blocks = await self.block_db.get_all_blocks()
        return {block.wiki_name for block in blocks}

    async def delete(self, name: str) -> bool:
        name = name.lower()
        if name in self._static_families:
            logger.debug(f"Blocking static wiki: {name}")
            await self.block_db.insert_blocked_wiki(name)
            return True

        guild_families = await self._get_guild_families()
        if name in guild_families:
            logger.debug(f"seleting dynamic wiki: {name}")
            return await self.db.delete_wiki_by_name(name) is not None

        logger.warning(f"Wiki '{name}' not found in registry.")
        return False

    async def register(
        self,
        name: str,
        url: str,
        article_path: str | None = None,
        script_path: str | None = None,
    ) -> bool:
        try:
            family_cls = generate_wiki_family("en", url, name, article_path, script_path)
            is_valid = await is_wiki("en", family_cls())  # type: ignore
            if is_valid:
                await self.db.insert_wiki(
                    name=name,
                    url=url,
                    article_path=article_path,
                    script_path=script_path,
                )
            return is_valid
        except Exception as e:
            logger.error(f"Failed to register wiki '{name}': {e}")
            return False

    async def _get_guild_families(self) -> dict[str, BaseFamily]:
        wikis = await self.db.get_wikis_by_guild_id()
        return {
            wiki.wiki_name: generate_wiki_family(
                code="en",
                site=wiki.wiki_url,
                fname=wiki.wiki_name,
                article_path=wiki.wiki_article_path,
                script_path=wiki.wiki_script_path,
            )()  # type: ignore
            for wiki in wikis
        }

    async def get(self, name: str) -> BaseFamily | None:
        blocked = await self._get_blocked_static_wikis()
        if name in blocked:
            return None

        guild_families = await self._get_guild_families()
        return guild_families.get(name) or self._static_families.get(name)

    async def list(self) -> list[tuple[str, BaseFamily]]:
        blocked = await self._get_blocked_static_wikis()
        guild_families = await self._get_guild_families()

        # Filter static families
        filtered_static = {name: family for name, family in self._static_families.items() if name not in blocked}

        # Merge with dynamic ones (guild_families take priority)
        merged = {**filtered_static, **guild_families}
        return list(merged.items())
