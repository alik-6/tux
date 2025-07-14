from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Generic, TypeVar
from urllib.parse import unquote, urlparse

import httpx
import pywikibot  # type: ignore
from loguru import logger
from pywikibot import Family, Site, config  # type: ignore
from pywikibot.family import Family as BaseFamily # type: ignore
from tux.database.controllers.wiki import WikiBlockItemController, WikiController   # type: ignore

pywikibot.config.retry_attempts = 0  # type: ignore
pywikibot.config.retry_wait = 0  # type: ignore
pywikibot.config.max_retries = 0  # type: ignore
T = TypeVar("T")


class ResultStatus(Enum):
    NOT_FOUND = 0
    ALREADY_EXISTS = 1
    DONE = 2
    EXCEPTION = 3


@dataclass
class Result(Generic[T]):
    data: T
    status: ResultStatus
    message: str


def wiki_factory(
    code: str,
    site: str,
    name: str,
    article_path: str | None = None,
    script_path: str | None = None,
) -> type[BaseFamily]:
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
    name : str
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
    ...     code="en", site="https://wiki.archlinux.org", name="archwiki", article_path="/title/$1", script_path="/"
    ... )
    >>> family = family_class()
    >>> family.apipath("en")
    '/api.php'
    """
    if not site.startswith(("http://", "https://")):
        site = f"https://{site}"
    parsed_site = urlparse(site)
    hostname = parsed_site.netloc

    fname: str = name
    class Family(BaseFamily):
        name: str | None = fname
        langs: ClassVar[dict[str, str]] = {code: hostname}  # type: ignore[assignment]
        articlepath: ClassVar[dict[str, str]] = {code: article_path or "/wiki/$1"}

        def scriptpath(self, code: Any):
            return script_path or "/w"

        def apipath(self, code: Any) -> str:   
            if script_path:
                return f"{script_path.rstrip('/')}/api.php"   # type: ignore
            return "/w/api.php"  # Default API path for MediaWiki

    Family.__name__ = f"{name.capitalize()}Family"
    return Family  


def load_family(name: str) -> Result[Family | None]: # type: ignore
    """
    Attempt to load a MediaWiki family by name.
    """
    try:
        family = Family.load(name)  # type: ignore
        return Result(data=family, status=ResultStatus.DONE, message=f"Family '{name}' loaded successfully.")   # type: ignore
    except Exception as e:
        logger.error(f"Failed to load family '{name}': {e}")
        return Result(data=None, status=ResultStatus.EXCEPTION, message=f"Failed to load family '{name}'.")   # type: ignore


def get_preregistered_wikis() -> Result[list[BaseFamily]]:  # type: ignore
    """
    Load all configured MediaWiki families from pywikibot config.
    """
    try:
        families = []
        for name in config.family_files:  # type: ignore
            family_result = load_family(name)  # type: ignore
            if family_result.status == ResultStatus.DONE and family_result.data:   # type: ignore
                families.append(family_result.data)  # type: ignore
        return Result(
            data=families,  # type: ignore
            status=ResultStatus.DONE,
            message=f"{len(families)} pre-registered wikis loaded.",  # type: ignore
        )  # type: ignore
    except Exception as e:
        logger.error(f"Error loading pre-registered wikis: {e}")
        return Result(data=[], status=ResultStatus.EXCEPTION, message="Failed to load pre-registered wikis.")


def search_wiki(site: pywikibot.Site, query: str) -> Result[tuple[str, str] | None]:  # type: ignore
    """
    Search the wiki for a page by query (first match), and return its title and URL.
    """
    try:
        search_results = site.search(query, total=1)  # type: ignore
        page = next(search_results, None)  # type: ignore

        if page is None or not page.exists(): # type: ignore
            logger.info(f"Page '{query}' does not exist on '{site.family.name}'")  # type: ignore
            return Result(data=None, status=ResultStatus.NOT_FOUND, message=f"Page '{query}' does not exist.")

        return Result(
            data=(page.title(), unquote(page.full_url())),  # type: ignore
            status=ResultStatus.DONE,
            message=unquote(page.full_url()),  # type: ignore
        )

    except Exception as e:
        logger.error(f"Error retrieving page '{query}' on '{site.family.name}': {e}")  # type: ignore
        return Result(data=None, status=ResultStatus.EXCEPTION, message=f"Error retrieving page '{query}'.")


def query_wiki(search: str, family: BaseFamily) -> Result[tuple[str, str]]:
    """
    Query a MediaWiki-compatible site for a search term.
    """
    try:
        site = Site(code="en", fam=family)
    except Exception as e:
        logger.error(f"Site creation failed for family '{family.name}': {e}")
        return Result(
            data=("error", "Site initialization failed."),
            status=ResultStatus.EXCEPTION,
            message="Site initialization failed.",
        )

    search_result = search_wiki(site, search)
    if search_result.status == ResultStatus.DONE and search_result.data:
        return Result(data=search_result.data, status=ResultStatus.DONE, message=search_result.message)
    return Result(data=("No results", "N/A"), status=search_result.status, message=search_result.message)


async def is_wiki(code: str, family: BaseFamily) -> Result[bool]:
    result = Result(False, ResultStatus.EXCEPTION, "Unhandled error.")

    if code not in family.langs:
        msg = f"Code '{code}' not in family."
        logger.debug(msg)
        return Result(False, ResultStatus.NOT_FOUND, msg)

    site = Site(code, family)
    api_url = f"{site.protocol()}://{site.hostname()}{site.apipath()}"   # type: ignore
    params = {"action": "query", "meta": "siteinfo", "format": "json"}

    try:
        transport = httpx.AsyncHTTPTransport(retries=0)
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True, transport=transport) as client:
            response = await client.get(api_url, params=params)

        if response.is_error:
            msg = "Error response from server."
            logger.error(msg)
            result = Result(False, ResultStatus.EXCEPTION, msg)

        else:
            try:
                data = response.json()
                generator = data.get("query", {}).get("general", {}).get("generator", "")
                is_mediawiki = generator.startswith("MediaWiki")
                status = ResultStatus.DONE if is_mediawiki else ResultStatus.NOT_FOUND
                msg = "Valid MediaWiki site." if is_mediawiki else "Site is not a MediaWiki installation."
                result = Result(is_mediawiki, status, msg)

            except ValueError:
                msg = f"Non-JSON response from {code}:{family.name} at {api_url}"
                logger.warning(msg)
                result = Result(False, ResultStatus.NOT_FOUND, "Non-JSON response received.")

    except httpx.HTTPStatusError as e:
        status = ResultStatus.NOT_FOUND if e.response.status_code == 404 else ResultStatus.EXCEPTION
        msg = (
            f"{e.response.status_code} error at {e.request.url}."
            if e.response.status_code == 404
            else f"HTTP error: {e}"
        )
        logger.warning(msg) if status == ResultStatus.NOT_FOUND else logger.error(msg)
        result = Result(False, status, msg)

    except httpx.RequestError as e:
        msg = f"Request error for {code}:{family.name}: {e}"
        logger.error(msg)
        result = Result(False, ResultStatus.EXCEPTION, msg)

    except httpx.InvalidURL as e:
        msg = f"Invalid URL:{api_url} {e}"
        logger.error(msg)
        result = Result(False, ResultStatus.EXCEPTION, msg)

    except Exception as e:
        msg = f"Unexpected error in is_wiki: {e}"
        logger.error(msg)
        result = Result(False, ResultStatus.EXCEPTION, "Unexpected error occurred.")

    return result


D = TypeVar("D")


class Registry(Generic[D]):
    def __init__(self, guild_id: int, controller: D):
        self.guild_id = guild_id
        self.controller = controller
        self.static_families: dict[str, BaseFamily] = {
            f.name: f 
            for f in get_preregistered_wikis().data
            if f and f.name is not None  
        }


class BlockRegistry(Registry[WikiBlockItemController]):
    def __init__(self, guild_id: int):
        super().__init__(guild_id, WikiBlockItemController(guild_id))

    async def blocked_list(self) -> list[str]:
        blocks = await self.controller.get_all_blocks()
        return [block.wiki_name for block in blocks] 

    async def list(self) -> Result[dict[str, BaseFamily]]:
        result = Result[dict[str, BaseFamily]](data={}, status=ResultStatus.EXCEPTION, message="")

        try:
            blocked = await self.blocked_list()

            filtered_static = {name: family for name, family in self.static_families.items() if name in blocked}
            result.data = filtered_static
            result.status = ResultStatus.DONE
            wiki_count: int= len(result.data)
            if  wiki_count == 0:
                result.message = "No blocked wikis found."
            else:
                result.message = f"{wiki_count} blocked wiki{"s" if wiki_count > 1  else ""} found."

        except Exception:
            result.data = {}
            result.status = ResultStatus.EXCEPTION
            result.message = "An error occurred while retrieving the list of blocked wikis."

        return result

    async def unblock(self, name: str) -> Result[None]:
        result = Result[None](data=None, status=ResultStatus.DONE, message="")
        name = name.lower()

        try:
            guild_blocked_families = await self.blocked_list()

            if name in self.static_families:
                block_exists = name in guild_blocked_families
                if not block_exists:
                    result.status = ResultStatus.NOT_FOUND
                    result.message = f"Wiki '{name}' is not blocked."
                else:
                    await self.controller.delete_block_by_name(name) 
                    result.status = ResultStatus.DONE
                    result.message = f"Wiki '{name}' has been unblocked successfully."

            else:
                result.status = ResultStatus.NOT_FOUND
                result.message = f"Wiki '{name}' does not exist."

        except Exception:
            result.status = ResultStatus.EXCEPTION
            result.message = "An unexpected error occurred while trying to unblock the wiki."

        return result

    async def block(
        self,
        name: str,
    ) -> Result[None]:
        result = Result[None](data=None, status=ResultStatus.DONE, message="")
        name = name.lower()

        try:
            guild_blocked_families = await self.blocked_list()

            if name in self.static_families:
                block_exists = name in guild_blocked_families
                if block_exists:
                    result.status = ResultStatus.ALREADY_EXISTS
                    result.message = f"Wiki '{name}' is already blocked."
                else:
                    await self.controller.insert_blocked_wiki(name)
                    result.status = ResultStatus.DONE
                    result.message = f"Wiki '{name}' has been blocked successfully."

            else:
                result.status = ResultStatus.NOT_FOUND
                result.message = f"Wiki '{name}' does not exist."

        except Exception:
            result.status = ResultStatus.EXCEPTION
            result.message = "An unexpected error occurred while trying to block the wiki."

        return result


class WikiRegistry(Registry[WikiController]):
    def __init__(self, guild_id: int):
        
        super().__init__(guild_id, controller=WikiController(guild_id))
    # async def info() -> 
    async def delete(self, name: str) -> Result[None]:
        result = Result[None](data=None, status=ResultStatus.DONE, message="")
        name = name.lower()

        try:
            guild_families = await self._get_guild_families()

            if name in guild_families:
                delete_result = await self.controller.delete_wiki_by_name(name) 
                if delete_result:
                    result.status = ResultStatus.DONE
                    result.message = f"Wiki '{name}' has been deleted."
                else:
                    result.status = ResultStatus.NOT_FOUND
                    result.message = f"Wiki '{name}' was not found."

            else:
                result.status = ResultStatus.NOT_FOUND
                result.message = f"Wiki '{name}' does not exist."

        except Exception:
            result.status = ResultStatus.EXCEPTION
            result.message = "An unexpected error occurred while trying to delete the wiki."

        return result

    async def add(
        self,
        name: str,
        url: str,
        article_path: str | None = None,
        script_path: str | None = None,
    ) -> Result[bool]:
        result = Result[bool](data=False, status=ResultStatus.EXCEPTION, message="")
        try:
            family_cls = wiki_factory("en", url, name, article_path, script_path)
            is_valid = await is_wiki(
                "en", 
                family_cls() # type: ignore
            ) 

            if is_valid.data and is_valid.status == ResultStatus.DONE:
                is_inserted = await self.controller.insert_wiki( 
                    name=name,
                    url=url,
                    article_path=article_path,
                    script_path=script_path,
                )
                if is_inserted:
                    result.status = ResultStatus.DONE
                    result.data = True
                    result.message = f"Wiki '{name}' has been registered successfully."
                else:
                    result.message = f"Wiki {name} already exists."
                    result.status = ResultStatus.ALREADY_EXISTS
                    result.data = False
                    return result
            elif is_valid.status == ResultStatus.EXCEPTION:
                return result
            else:
                result.status = ResultStatus.NOT_FOUND
                result.data = False
                result.message = f"The URL for wiki '{name}' is not valid or the wiki could not be reached."

        except Exception as e:
            logger.error(e)
            result.status = ResultStatus.EXCEPTION
            result.data = False
            result.message = "An error occurred while registering the wiki."

        return result

    async def guild_name_list(self) -> list[str]:
        wikis = await self.controller.get_wikis_by_guild_id() 
        return [wiki.wiki_name for wiki in wikis]

    async def _get_guild_families(self) -> dict[str, BaseFamily]:
        wikis = await self.controller.get_wikis_by_guild_id()
        return {
            wiki.wiki_name: wiki_factory(  # type: ignore
                code="en",
                site=wiki.wiki_url, 
                name=wiki.wiki_name, 
                article_path=wiki.wiki_article_path,
                script_path=wiki.wiki_script_path, 
            )()  
            for wiki in wikis }

    async def _blocked_name_list(self) -> list[str]:
        block_registry = BlockRegistry(self.guild_id)
        return await block_registry.blocked_list()

    async def get(self, name: str) -> Result[BaseFamily | None]:
        result = Result[BaseFamily | None](data=None, status=ResultStatus.EXCEPTION, message="")

        try:
            blocked = await self._blocked_name_list()
            if name in blocked:
                result.status = ResultStatus.NOT_FOUND
                result.data = None
                result.message = f"Wiki '{name}' is currently blocked."
                return result

            guild_families = await self._get_guild_families()
            family = guild_families.get(name) or self.static_families.get(name)

            if family:
                result.status = ResultStatus.DONE
                result.data = family
                result.message = f"Wiki '{name}' found."
            else:
                result.status = ResultStatus.NOT_FOUND
                result.data = None
                result.message = f"Wiki '{name}' was not found."

        except Exception:
            result.status = ResultStatus.EXCEPTION
            result.data = None
            result.message = "An error occurred while retrieving the wiki."

        return result

    async def list(self) -> Result[dict[str, BaseFamily]]:
        result = Result[dict[str, BaseFamily]](data={}, status=ResultStatus.EXCEPTION, message="")

        try:
            blocked = await self._blocked_name_list()
            guild_families = await self._get_guild_families()

            filtered_static = {name: family for name, family in self.static_families.items() if name not in blocked}
            result.data = {**filtered_static, **guild_families}
            result.status = ResultStatus.DONE

            if len(result.data) == 0:
                result.message = "No wikis found."
            elif len(result.data) == 1:
                result.message = "1 wiki found."
            else:
                result.message = f"{len(result.data)} wikis found."

        except Exception:
            result.data = {}
            result.status = ResultStatus.EXCEPTION
            result.message = "An error occurred while retrieving the list of wikis."

        return result
