"""分类业务逻辑"""
from pathlib import Path

from app.repositories.comic_repo import ComicsMetadataRepo, ComicsDetailRepo, DETAIL_DIR

CATEGORY_GROUPS = [
    {"name": "角色", "subs": ["人妻", "偽娘哲學", "妹妹系", "姐姐系", "性轉換", "扶他樂園", "非人類"]},
    {"name": "服饰", "subs": ["Cosplay"]},
    {"name": "特殊play", "subs": ["NTR", "SM", "強暴", "足の恋"]},
    {"name": "猎奇", "subs": ["重口地帶", "CG雜圖"]},
    {"name": "其它", "subs": []},
]


class CategoryService:
    def __init__(
        self,
        detail_repo: ComicsDetailRepo,
        metadata_repo: ComicsMetadataRepo,
    ):
        self._detail = detail_repo
        self._metadata = metadata_repo

    async def _get_local_categories(self) -> set[str]:
        cats = set()
        folders = await self._detail.list_folders()
        for folder in folders:
            meta = self._detail.read_metadata(folder)
            if meta:
                for c in meta.get("categories", []):
                    cats.add(c)
        return cats

    def _get_remote_categories(self) -> set[str]:
        cats = set()
        comics = self._metadata.load_all()
        for c in comics:
            for cat_name in c.get("categories", []):
                cats.add(cat_name)
        return cats

    async def get_full_categories(self) -> list[dict]:
        local_cats = await self._get_local_categories()
        remote_cats = self._get_remote_categories()
        all_cats = local_cats | remote_cats

        parent_map = {}
        for g in CATEGORY_GROUPS:
            for s in g["subs"]:
                parent_map[s] = g["name"]

        groups = [{"name": g["name"], "subs": list(g["subs"])} for g in CATEGORY_GROUPS]
        other = next(g for g in groups if g["name"] == "其它")

        for c in sorted(all_cats):
            if c not in parent_map:
                other["subs"].append(c)

        return [g for g in groups if g["subs"]]
