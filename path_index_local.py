import os
import time
import sqlite3
import difflib
import re
from pathlib import Path
from typing import List, Dict, Any

# ---------- Database location ----------
def get_default_db() -> Path:
    """Store the index DB next to this script, in CentreIndex/paths.db."""
    here = Path(__file__).resolve().parent
    db_folder = here / "CentreIndex"
    db_folder.mkdir(parents=True, exist_ok=True)
    return db_folder / "paths.db"

DEFAULT_DB: Path = get_default_db()

# ---------- SQLite helpers ----------
def connect(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(db))

def ensure_schema(con: sqlite3.Connection) -> bool:
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS paths(path TEXT PRIMARY KEY);")
    has_fts = False
    try:
        cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS paths_fts USING fts5(path, content='');")
        has_fts = True
    except Exception:
        has_fts = False
    con.commit()
    return has_fts

# ---------- Index building ----------
def rebuild_index(db: Path, targets: List[str]) -> None:
    """Full rebuild of the path index for the given drive letters (e.g. ['C','E','F'])."""
    start = time.time()
    con = connect(db)
    has_fts = ensure_schema(con)
    cur = con.cursor()

    # Clear main table
    cur.execute("DELETE FROM paths;")

    # Recreate FTS table safely (contentless FTS5 cannot be DELETEd)
    if has_fts:
        try:
            cur.execute("DROP TABLE IF EXISTS paths_fts;")
            cur.execute("CREATE VIRTUAL TABLE paths_fts USING fts5(path, content='');")
        except Exception as e:
            print("[WARN] Could not recreate FTS table:", e)

    con.commit()

    total = 0

    def add_batch(batch: List[str]) -> None:
        nonlocal total
        if not batch:
            return
        cur.executemany(
            "INSERT OR IGNORE INTO paths(path) VALUES (?);",
            ((p,) for p in batch)
        )
        if has_fts:
            cur.executemany(
                "INSERT INTO paths_fts(path) VALUES (?);",
                ((p,) for p in batch)
            )
        total += len(batch)

    # Scan each target drive (e.g. 'C','E','F')
    for tgt in targets:
        drive = tgt.rstrip(":/\\").strip()
        if not drive:
            continue
        root = Path(f"{drive}:/")
        print(f"[SCAN] {root}")
        if not root.exists():
            print(f"[WARN] Drive not found: {root}")
            continue

        batch: List[str] = []
        try:
            for path in root.rglob("*"):
                try:
                    p_str = str(path)
                    batch.append(p_str)
                    if len(batch) >= 5000:
                        add_batch(batch)
                        batch = []
                except Exception:
                    continue
        except Exception:
            # rglob can fail on some protected areas; just skip
            continue

        if batch:
            add_batch(batch)
            batch = []

    con.commit()
    con.close()

    elapsed = time.time() - start
    print(f"[BUILD] Indexed ~{total:,} paths in {elapsed:.1f}s → {db}")

# Backwards-compatible wrapper for older CMC code
def quick_build(targets: List[str]) -> None:
    """Compatibility function used by /qbuild in the main script."""
    rebuild_index(DEFAULT_DB, targets)

# ---------- Query helpers ----------
def _tokenize_query(q: str) -> List[str]:
    return [t.strip().lower() for t in q.replace("\n", " ").split() if t.strip()]

_SYNONYMS: Dict[str, List[str]] = {
    "server": ["servers", "srv", "instance", "world"],
    "servers": ["server", "srv", "instance", "world"],
    "atlauncher": ["atlauncher", "launcher"],
}

def _expand_terms(terms: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
        for syn in _SYNONYMS.get(t, []):
            if syn not in seen:
                seen.add(syn)
                out.append(syn)
    return out

def _path_tokens(plow: str) -> List[str]:
    """Split a path into coarse tokens for fuzzy presence checks."""
    return [tok for tok in re.split(r"[\\/._\-\s]+", plow) if tok]

# ---------- Advanced fuzzy search ----------
def advanced_query_paths(db: Path, q: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Advanced ranked search over the path index.

    Features:
      - multi-word AND logic on the original core terms
      - fuzzy presence detection against path segments
      - synonym expansion (server/servers/srv/etc.)
      - fuzzy scoring on basename + full path
    Returns: list of {path, score}.
    """
    terms = _tokenize_query(q)
    if not terms:
        return []

    core_terms = terms[:]        # original query terms
    expanded = _expand_terms(terms)

    con = connect(db)
    cur = con.cursor()

    candidate_max = max(limit * 80, 2000)
    candidates: List[str] = []

    # 1) Primary candidate set: AND over core terms (substring LIKE)
    if core_terms:
        and_sql = " AND ".join(["LOWER(path) LIKE ?"] * len(core_terms))
        and_params = [f"%{t}%" for t in core_terms]
        try:
            cur.execute(
                f"SELECT path FROM paths WHERE {and_sql} LIMIT ?;",
                (*and_params, candidate_max)
            )
            candidates = [row[0] for row in cur.fetchall()]
        except Exception:
            candidates = []

    # 2) Fallback OR set if we didn't get enough AND matches
    if len(candidates) < limit:
        like_terms: List[str] = []
        for t in expanded:
            if t not in like_terms:
                like_terms.append(t)
            if len(t) >= 3:
                short = t[:3]
                if short not in like_terms:
                    like_terms.append(short)

        if like_terms:
            or_sql = " OR ".join(["LOWER(path) LIKE ?"] * len(like_terms))
            or_params = [f"%{t}%" for t in like_terms]
            try:
                cur.execute(
                    f"SELECT path FROM paths WHERE {or_sql} LIMIT ?;",
                    (*or_params, candidate_max)
                )
                extra = [row[0] for row in cur.fetchall()]
            except Exception:
                extra = []

            seen = set(candidates)
            for p in extra:
                if p not in seen:
                    seen.add(p)
                    candidates.append(p)

    con.close()

    # Deduplicate
    seen2 = set()
    unique_candidates: List[str] = []
    for p in candidates:
        if p not in seen2:
            seen2.add(p)
            unique_candidates.append(p)

    results: List[Dict[str, Any]] = []

    for p in unique_candidates:
        plow = p.lower()
        basename = os.path.basename(p).lower()
        tokens = _path_tokens(plow)

        # ---- multi-term presence detection against segments ----
        contains_core: List[str] = []
        for t in core_terms:
            present = False
            if t in plow:
                present = True
            else:
                for tok in tokens:
                    if difflib.SequenceMatcher(None, t, tok).ratio() * 100 >= 70:
                        present = True
                        break
            if present:
                contains_core.append(t)

        contains_all_core = len(contains_core) >= len(core_terms) if core_terms else True

        base_score = 0.0

        # Strong AND logic: heavily reward matches that satisfy all core terms,
        # and strongly penalize those that miss terms when there are multiple.
        if len(core_terms) > 1:
            if contains_all_core:
                base_score += 140.0
            else:
                missing = len(core_terms) - len(contains_core)
                base_score -= missing * 90.0
        else:
            if contains_all_core:
                base_score += 40.0

        base_score += 15.0 * len(contains_core)

        # Fuzzy scoring using both basename and full path
        fuzzy_scores: List[float] = []
        for t in expanded:
            s1 = difflib.SequenceMatcher(None, t, basename).ratio() * 100.0
            s2 = difflib.SequenceMatcher(None, t, plow).ratio() * 100.0
            fuzzy_scores.append(max(s1, s2))

        fmax = max(fuzzy_scores) if fuzzy_scores else 0.0
        favg = sum(fuzzy_scores) / len(fuzzy_scores) if fuzzy_scores else 0.0

        base_score += 0.4 * fmax + 0.2 * favg

        results.append({
            "path": p,
            "score": int(round(base_score)),
        })

    # Rank by score, then shorter path as tie-breaker
    results.sort(key=lambda r: (-r["score"], len(r["path"])))
    return results[:limit]

def super_find(q: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Main entry for CMC /find: advanced fuzzy multi-word search."""
    return advanced_query_paths(DEFAULT_DB, q, limit)
