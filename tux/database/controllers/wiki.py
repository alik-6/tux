from typing import Any

from prisma.models import Wiki, WikiBlockItem
from tux.database.controllers.base import BaseController


class WikiController(BaseController[Wiki]):
    """
    Controller for managing Wiki entries across guilds.
    """

    def __init__(self, guild_id: int) -> None:
        """
        Initialize the WikiController with a guild context.
        """
        self.guild_id = guild_id
        super().__init__("wiki")

    async def get_wiki_by_name(self, wiki_name: str) -> Wiki | None:
        """
        Retrieve a Wiki by name (not scoped to guild).
        """
        return await self.find_unique(where={"wiki_name": wiki_name})

    async def get_wiki_by_name_and_guild(self, wiki_name: str) -> Wiki | None:
        """
        Retrieve a Wiki by name for the current guild.
        """
        return await self.find_unique(where={"wiki_name": wiki_name, "guild_id": self.guild_id})

    async def get_wiki_by_id(self, wiki_id: int) -> Wiki | None:
        """
        Retrieve a Wiki by its ID.
        """
        return await self.find_unique(where={"wiki_id": wiki_id})

    async def insert_wiki(
        self,
        name: str,
        url: str,
        script_path: str | None = None,
        article_path: str | None = None,
    ) -> Wiki:
        """
        Insert a new Wiki entry for the current guild.
        """
        return await self.create(
            data={
                "wiki_name": name,
                "wiki_url": url,
                "wiki_script_path": script_path,
                "wiki_article_path": article_path,
                "guild": self.connect_or_create_relation("guild_id", self.guild_id),
            },
            include={"guild": True},
        )

    async def delete_wiki_by_id(self, wiki_id: int) -> Wiki | None:
        """
        Delete a Wiki entry by ID.
        """
        return await self.delete(where={"wiki_id": wiki_id})

    async def delete_wiki_by_name(self, wiki_name: str) -> Wiki | None:
        """
        Delete a Wiki entry by name for the current guild.
        """
        return await self.delete(where={"wiki_name": wiki_name, "guild_id": self.guild_id})

    async def update_wiki_by_id(
        self,
        wiki_id: int,
        name: str | None = None,
        url: str | None = None,
        script_path: str | None = None,
        article_path: str | None = None,
    ) -> Wiki | None:
        """
        Update a Wiki entry by ID.
        """
        data: dict[str, Any] = {}

        if name is not None:
            data["wiki_name"] = name
        if url is not None:
            data["wiki_url"] = url
        if script_path is not None:
            data["wiki_script_path"] = script_path
        if article_path is not None:
            data["wiki_article_path"] = article_path

        return await self.update(where={"wiki_id": wiki_id}, data=data)

    async def get_wikis_by_guild_id(self, limit: int | None = None) -> list[Wiki]:
        """
        Retrieve all Wiki entries for the current guild.
        """
        return await self.find_many(
            where={"guild_id": self.guild_id},
            order={"wiki_name": "asc"},
            take=limit,
        )

    async def count_wiki_by_guild_id(self) -> int:
        """
        Count the number of Wiki entries in the current guild.
        """
        return await self.count(where={"guild_id": self.guild_id})

    async def wiki_exists(self, wiki_name: str) -> bool:
        """
        Check if a Wiki with the given name exists in the current guild.
        """
        return await self.find_unique(where={"wiki_name": wiki_name, "guild_id": self.guild_id}) is not None


class WikiBlockItemController(BaseController[WikiBlockItem]):
    """
    Controller for managing blocked Wiki entries in a guild.
    """

    def __init__(self, guild_id: int) -> None:
        """
        Initialize the WikiBlockItemController with a guild context.
        """
        self.guild_id = guild_id
        super().__init__("wikiblockitem")

    async def get_block_by_name(self, wiki_name: str) -> WikiBlockItem | None:
        """
        Retrieve a blocked Wiki entry by name for the current guild.
        """
        return await self.find_unique(where={"wiki_name": wiki_name, "guild_id": self.guild_id})

    async def get_block_by_id(self, wiki_block_id: int) -> WikiBlockItem | None:
        """
        Retrieve a blocked Wiki entry by ID.
        """
        return await self.find_unique(where={"wiki_block_id": wiki_block_id})

    async def insert_blocked_wiki(self, name: str) -> WikiBlockItem:
        """
        Insert a new blocked Wiki entry for the current guild.
        """
        return await self.create(
            data={
                "wiki_name": name,
                "guild": self.connect_or_create_relation("guild_id", self.guild_id),
            },
            include={"guild": True},
        )

    async def delete_block_by_id(self, wiki_block_id: int) -> WikiBlockItem | None:
        """
        Delete a blocked Wiki entry by ID.
        """
        return await self.delete(where={"wiki_block_id": wiki_block_id})

    async def update_block_by_id(
        self,
        wiki_block_id: int,
        name: str | None = None,
    ) -> WikiBlockItem | None:
        """
        Update a blocked Wiki entry by ID.
        """
        data: dict[str, Any] = {}
        if name is not None:
            data["wiki_name"] = name

        return await self.update(where={"wiki_block_id": wiki_block_id}, data=data)

    async def get_all_blocks(self, limit: int | None = None) -> list[WikiBlockItem]:
        """
        Retrieve all blocked Wiki entries for the current guild.
        """
        return await self.find_many(
            where={"guild_id": self.guild_id},
            order={"wiki_name": "asc"},
            take=limit,
        )

    async def count_blocks(self) -> int:
        """
        Count the number of blocked Wiki entries in the current guild.
        """
        return await self.count(where={"guild_id": self.guild_id})
