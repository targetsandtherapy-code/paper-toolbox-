"""论点 + 论文题目 → 已匹配文献（跨用户共享签名，减少重复检索与 LLM fit）"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from modules.db.store import connect, db_lock, init_db
from modules.reference.searcher.base import Paper


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _normalize_title(title: str) -> str:
    t = (title or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def claim_signature(paper_title: str, key_claim: str) -> str:
    pt = _normalize_title(paper_title)
    kc = (key_claim or "").strip()
    raw = f"{pt}\n{kc}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def paper_to_full_dict(p: Paper) -> dict[str, Any]:
    return {
        "title": p.title,
        "authors": list(p.authors or []),
        "year": p.year,
        "journal": p.journal,
        "doi": p.doi,
        "abstract": p.abstract,
        "citation_count": p.citation_count,
        "url": p.url,
        "source": p.source or "",
        "reference_type": getattr(p, "reference_type", None) or "J",
        "eb_publish_date": p.eb_publish_date,
        "access_date": p.access_date,
        "volume": p.volume,
        "issue": p.issue,
        "pages": p.pages,
    }


def paper_from_full_dict(d: dict[str, Any]) -> Paper:
    return Paper(
        title=d.get("title") or "",
        authors=list(d.get("authors") or []),
        year=d.get("year"),
        journal=d.get("journal"),
        doi=d.get("doi"),
        abstract=d.get("abstract"),
        citation_count=d.get("citation_count"),
        url=d.get("url"),
        source=d.get("source") or "",
        reference_type=d.get("reference_type") or "J",
        eb_publish_date=d.get("eb_publish_date"),
        access_date=d.get("access_date"),
        volume=d.get("volume"),
        issue=d.get("issue"),
        pages=d.get("pages"),
    )


def get_cached_paper_for_claim(paper_title: str, key_claim: str) -> Optional[Paper]:
    if not (key_claim or "").strip():
        return None
    sig = claim_signature(paper_title, key_claim)
    init_db()
    with db_lock():
        conn = connect()
        try:
            row = conn.execute(
                """
                SELECT status, paper_json FROM claim_reference_cache WHERE signature = ?
                """,
                (sig,),
            ).fetchone()
            if not row:
                return None
            if row["status"] not in ("ok", "ok_rescue"):
                return None
            conn.execute(
                "UPDATE claim_reference_cache SET hit_count = hit_count + 1, updated_at = ? WHERE signature = ?",
                (_now_iso(), sig),
            )
            conn.commit()
            return paper_from_full_dict(json.loads(row["paper_json"]))
        except Exception:
            return None
        finally:
            conn.close()


def save_cached_match(
    paper_title: str,
    key_claim: str,
    paper: Paper,
    status: str,
    claim_type: str = "",
) -> None:
    if not (key_claim or "").strip():
        return
    if status not in ("ok", "ok_rescue"):
        return
    sig = claim_signature(paper_title, key_claim)
    preview = (key_claim or "")[:400]
    pnorm = _normalize_title(paper_title)[:300]
    raw = json.dumps(paper_to_full_dict(paper), ensure_ascii=False)
    t = _now_iso()
    ct = (claim_type or "")[:80]
    init_db()
    with db_lock():
        conn = connect()
        try:
            conn.execute(
                """
                INSERT INTO claim_reference_cache
                    (signature, paper_title_norm, key_claim_preview, status, claim_type, paper_json, hit_count, created_at, updated_at)
                VALUES (?,?,?,?,?,?,0,?,?)
                ON CONFLICT(signature) DO UPDATE SET
                    status = excluded.status,
                    claim_type = excluded.claim_type,
                    paper_json = excluded.paper_json,
                    updated_at = excluded.updated_at
                """,
                (sig, pnorm, preview, status, ct, raw, t, t),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()
