"""Milvus Lite 向量库 — 漫画语义相似检索"""
import json
import hashlib
from pathlib import Path

from pymilvus import MilvusClient, DataType
from openai import OpenAI
from app.repositories.config_repo import ConfigRepo

DB_PATH = Path("comics.db")
COLLECTION_NAME = "comics"
VECTOR_DIM = 1024


def _get_embed_client() -> OpenAI:
    cfg = ConfigRepo().read()
    return OpenAI(
        api_key=cfg.get("embedding_api_key", ""),
        base_url=cfg.get("embedding_api_base", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    )


class VectorStore:
    def __init__(self, db_path: Path = DB_PATH):
        self._db = db_path
        self._client = MilvusClient(
            str(self._db),
            timeout=60,
        )
        self._ensure_collection()
        self._client.load_collection(COLLECTION_NAME)

    def _ensure_collection(self):
        if not self._client.has_collection(COLLECTION_NAME):
            self._client.create_collection(
                collection_name=COLLECTION_NAME,
                dimension=VECTOR_DIM,
                datatype=DataType.FLOAT_VECTOR,
                metric_type="COSINE",
            )

    @staticmethod
    def _folder_id(folder: str) -> int:
        return int(hashlib.md5(folder.encode()).hexdigest()[:16], 16) % (2 ** 63)

    def _embed(self, text: str) -> list[float]:
        resp = _get_embed_client().embeddings.create(
            model="text-embedding-v3",
            input=text,
        )
        return resp.data[0].embedding

    def upsert(self, folder: str, title: str, author: str,
               categories: list[str], tags: list[str],
               description: str, eps_count: int) -> int:
        """插入或更新一部漫画的向量"""
        comic_id = self._folder_id(folder)
        text = f"{title} {author} {' '.join(categories)} {' '.join(tags)} {description}"
        vector = self._embed(text)

        data = {
            "id": comic_id,
            "vector": vector,
            "folder": folder,
            "title": title,
            "author": author,
            "categories": json.dumps(categories, ensure_ascii=False),
            "tags": json.dumps(tags, ensure_ascii=False),
            "eps_count": eps_count,
        }
        result = self._client.upsert(
            collection_name=COLLECTION_NAME,
            data=[data],
        )
        return result["upsert_count"]

    def sync_from_local(self, detail_dir: Path, progress_cb=None) -> int:
        """扫描 comics_detail 目录，同步全部漫画向量"""
        if not detail_dir.exists():
            return 0
        folders = sorted(
            [d for d in detail_dir.glob("*") if d.is_dir()],
            reverse=True,
        )
        count = 0
        for i, d in enumerate(folders):
            mp = d / "metadata.json"
            if not mp.exists():
                continue
            try:
                with open(mp, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                self.upsert(
                    folder=d.name,
                    title=meta.get("title", ""),
                    author=meta.get("author", ""),
                    categories=meta.get("categories", []),
                    tags=meta.get("tags", []),
                    description=meta.get("description", ""),
                    eps_count=meta.get("epsCount", 0),
                )
                count += 1
                if progress_cb:
                    progress_cb(i + 1, len(folders), d.name)
            except Exception:
                pass
        return count

    def search_by_folder(self, folder: str, top_k: int = 10) -> list[dict]:
        """根据漫画文件夹名检索相似漫画"""
        comic_id = self._folder_id(folder)
        target = self._client.get(
            collection_name=COLLECTION_NAME,
            ids=[comic_id],
            output_fields=["vector"],
        )
        if not target or "vector" not in target[0]:
            return []

        results = self._client.search(
            collection_name=COLLECTION_NAME,
            data=[target[0]["vector"]],
            limit=top_k + 1,
            output_fields=["folder", "title", "author", "categories",
                           "tags", "eps_count"],
        )
        hits = []
        for hit in results[0]:
            if str(hit.get("entity", {}).get("folder", "")) == folder:
                continue
            entity = hit.get("entity", {})
            cats_raw = entity.get("categories", "[]")
            tags_raw = entity.get("tags", "[]")
            try:
                cats = json.loads(cats_raw)
            except (json.JSONDecodeError, TypeError):
                cats = []
            try:
                tags = json.loads(tags_raw)
            except (json.JSONDecodeError, TypeError):
                tags = []
            hits.append({
                "folder": entity.get("folder", ""),
                "title": entity.get("title", ""),
                "author": entity.get("author", ""),
                "categories": cats,
                "tags": tags,
                "eps_count": entity.get("eps_count", 0),
                "similarity": round(1.0 - hit["distance"], 4),
            })
        return hits[:top_k]

    def search_by_text(self, query: str, top_k: int = 10) -> list[dict]:
        """文本语义搜索"""
        vector = self._embed(query)
        results = self._client.search(
            collection_name=COLLECTION_NAME,
            data=[vector],
            limit=top_k,
            output_fields=["folder", "title", "author", "categories",
                           "tags", "eps_count"],
        )
        hits = []
        for hit in results[0]:
            entity = hit.get("entity", {})
            cats_raw = entity.get("categories", "[]")
            tags_raw = entity.get("tags", "[]")
            try:
                cats = json.loads(cats_raw)
            except (json.JSONDecodeError, TypeError):
                cats = []
            try:
                tags = json.loads(tags_raw)
            except (json.JSONDecodeError, TypeError):
                tags = []
            hits.append({
                "folder": entity.get("folder", ""),
                "title": entity.get("title", ""),
                "author": entity.get("author", ""),
                "categories": cats,
                "tags": tags,
                "eps_count": entity.get("eps_count", 0),
                "similarity": round(1.0 - hit["distance"], 4),
            })
        return hits

    def clear(self) -> None:
        """清空向量库全部记录"""
        try:
            self._client.delete(
                collection_name=COLLECTION_NAME,
                filter="id >= 0",
            )
        except Exception:
            pass

    def count(self) -> int:
        try:
            result = self._client.query(
                collection_name=COLLECTION_NAME,
                filter="id >= 0",
                output_fields=["count(*)"],
            )
            return result[0]["count(*)"]
        except Exception:
            return 0
        try:
            result = self._client.query(
                collection_name=COLLECTION_NAME,
                filter="id >= 0",
                output_fields=["count(*)"],
            )
            return result[0]["count(*)"]
        except Exception:
            return 0

    def delete_by_folder(self, folder: str) -> None:
        comic_id = self._folder_id(folder)
        self._client.delete(
            collection_name=COLLECTION_NAME,
            ids=[comic_id],
        )


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
