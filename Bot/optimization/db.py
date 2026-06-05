"""
Database integration for optimization results.

This module provides functions to save and load optimization results from PostgreSQL,
including weights_sets and optuna_studies tables.
"""

import logging
import math
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from datetime import datetime
import json
import asyncpg

from .types import StudyResult, WalkForwardResult

# Structured logging
logger = logging.getLogger(__name__)


def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively sanitize an object for JSON serialization.

    Replaces infinity and NaN float values with None since JSON
    doesn't support these values.

    Args:
        obj: Object to sanitize (dict, list, or primitive)

    Returns:
        Sanitized object safe for json.dumps()
    """
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None
        return obj
    else:
        return obj


async def save_weights_set(
    db_pool: asyncpg.Pool,
    name: str,
    weights: Dict[str, float],
    optimization_score: float,
    source: str = "optuna",
    is_active: bool = False
) -> UUID:
    """
    Save indicator weights to weights_sets table.

    Args:
        db_pool: Database connection pool
        name: Name for the weights set
        weights: Indicator weights dictionary
        optimization_score: Score achieved with these weights
        source: Source of weights ("optuna" or "manual")
        is_active: Whether to activate this weights set

    Returns:
        UUID of the saved weights_set

    Raises:
        Exception: If database operation fails
    """
    weights_set_id = uuid4()

    # Convert infinite scores to None (database NUMERIC field can't hold infinity)
    if optimization_score is not None and not (-1e308 < optimization_score < 1e308):
        logger.warning(
            f"optimization_score is infinite ({optimization_score}), storing as NULL",
            extra={"optimization_score": optimization_score}
        )
        optimization_score = None

    logger.info(
        "Saving weights set to database",
        extra={
            "weights_set_id": str(weights_set_id),
            "weights_set_name": name,
            "source": source,
            "optimization_score": optimization_score,
            "is_active": is_active,
            "weights": weights
        }
    )

    async with db_pool.acquire() as conn:
        # If setting as active, deactivate all other sets first
        if is_active:
            await conn.execute("UPDATE weights_sets SET is_active = false")
            logger.debug("Deactivated all existing weights sets")

        # Insert new weights set
        await conn.execute(
            """
            INSERT INTO weights_sets (id, name, source, weights, optimization_score, is_active)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            weights_set_id,
            name,
            source,
            json.dumps(weights),
            optimization_score,
            is_active
        )

    logger.info(
        "Weights set saved successfully",
        extra={"weights_set_id": str(weights_set_id)}
    )

    return weights_set_id


async def save_study_result(
    db_pool: asyncpg.Pool,
    result: StudyResult
) -> int:
    """
    Save Optuna study result to optuna_studies table.

    Args:
        db_pool: Database connection pool
        result: StudyResult object with optimization results

    Returns:
        Database ID of the created study record

    Raises:
        Exception: If database operation fails
    """
    logger.info(
        "Saving study result to database",
        extra={
            "study_name": result.study_name,
            "n_trials": result.n_trials,
            "best_value": result.best_value,
            "weights_set_id": str(result.weights_set_id) if result.weights_set_id else None
        }
    )

    # Generate metadata and sanitize for JSON (handle -inf, inf, NaN)
    metadata = sanitize_for_json(result.to_metadata_dict())
    best_params = sanitize_for_json(result.best_params)

    # Also sanitize best_value for database storage
    best_value = result.best_value
    if best_value is not None and (math.isinf(best_value) or math.isnan(best_value)):
        logger.warning(
            f"best_value is not finite ({best_value}), storing as NULL",
            extra={"best_value": best_value}
        )
        best_value = None

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO optuna_studies (
                study_name, run_id, n_trials, best_value, best_params,
                weights_set_id, started_at, completed_at, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
            """,
            result.study_name,
            result.run_id,
            result.n_trials,
            best_value,
            json.dumps(best_params),
            result.weights_set_id,
            result.started_at,
            result.completed_at,
            json.dumps(metadata)
        )

    study_id = row["id"]
    logger.info(
        "Study result saved successfully",
        extra={"study_name": result.study_name, "study_id": study_id}
    )

    return study_id


async def get_active_weights(db_pool: asyncpg.Pool) -> Optional[Dict[str, Any]]:
    """
    Get the currently active weights set.

    Args:
        db_pool: Database connection pool

    Returns:
        Dict with id, name, weights, and score, or None if no active set

    Raises:
        Exception: If database operation fails
    """
    logger.debug("Fetching active weights set from database")

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, name, weights, optimization_score
            FROM weights_sets
            WHERE is_active = true
            ORDER BY created_at DESC
            LIMIT 1
            """
        )

        if not row:
            logger.warning("No active weights set found in database")
            return None

        weights_data = {
            "id": row["id"],
            "name": row["name"],
            "weights": json.loads(row["weights"]),
            "optimization_score": float(row["optimization_score"]) if row["optimization_score"] else None
        }

        logger.info(
            "Active weights set retrieved",
            extra={
                "weights_set_id": str(weights_data["id"]),
                "name": weights_data["name"],
                "score": weights_data["optimization_score"]
            }
        )

        return weights_data


async def list_weights_sets(
    db_pool: asyncpg.Pool,
    limit: int = 10,
    source: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    List weights sets from database.

    Args:
        db_pool: Database connection pool
        limit: Maximum number of sets to return
        source: Optional filter by source ("optuna" or "manual")

    Returns:
        List of weights set dictionaries

    Raises:
        Exception: If database operation fails
    """
    logger.debug(
        "Listing weights sets",
        extra={"limit": limit, "source": source}
    )

    async with db_pool.acquire() as conn:
        if source:
            rows = await conn.fetch(
                """
                SELECT id, name, source, weights, optimization_score, is_active, created_at
                FROM weights_sets
                WHERE source = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                source,
                limit
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, name, source, weights, optimization_score, is_active, created_at
                FROM weights_sets
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit
            )

        weights_sets = []
        for row in rows:
            weights_sets.append({
                "id": row["id"],
                "name": row["name"],
                "source": row["source"],
                "weights": json.loads(row["weights"]),
                "optimization_score": float(row["optimization_score"]) if row["optimization_score"] else None,
                "is_active": row["is_active"],
                "created_at": row["created_at"]
            })

        logger.info(
            "Weights sets retrieved",
            extra={"count": len(weights_sets)}
        )

        return weights_sets


async def get_study_by_id(
    db_pool: asyncpg.Pool,
    study_id: UUID
) -> Optional[Dict[str, Any]]:
    """
    Get optimization study by ID.

    Args:
        db_pool: Database connection pool
        study_id: UUID of the study

    Returns:
        Study dictionary or None if not found

    Raises:
        Exception: If database operation fails
    """
    logger.debug(
        "Fetching study by ID",
        extra={"study_id": str(study_id)}
    )

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, study_name, run_id, n_trials, best_value, best_params,
                   weights_set_id, started_at, completed_at, metadata, created_at
            FROM optuna_studies
            WHERE id = $1
            """,
            study_id
        )

        if not row:
            logger.warning(
                "Study not found",
                extra={"study_id": str(study_id)}
            )
            return None

        study = {
            "id": row["id"],
            "study_name": row["study_name"],
            "run_id": row["run_id"],
            "n_trials": row["n_trials"],
            "best_value": float(row["best_value"]) if row["best_value"] else None,
            "best_params": json.loads(row["best_params"]) if row["best_params"] else {},
            "weights_set_id": row["weights_set_id"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "created_at": row["created_at"]
        }

        logger.info(
            "Study retrieved",
            extra={
                "study_id": str(study_id),
                "study_name": study["study_name"],
                "best_value": study["best_value"]
            }
        )

        return study


async def get_study_by_name(
    db_pool: asyncpg.Pool,
    study_name: str
) -> Optional[Dict[str, Any]]:
    """
    Get optimization study by name.

    Args:
        db_pool: Database connection pool
        study_name: Name of the study

    Returns:
        Study dictionary or None if not found

    Raises:
        Exception: If database operation fails
    """
    logger.debug(
        "Fetching study by name",
        extra={"study_name": study_name}
    )

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, study_name, run_id, n_trials, best_value, best_params,
                   weights_set_id, started_at, completed_at, metadata, created_at
            FROM optuna_studies
            WHERE study_name = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            study_name
        )

        if not row:
            logger.warning(
                "Study not found",
                extra={"study_name": study_name}
            )
            return None

        study = {
            "id": row["id"],
            "study_name": row["study_name"],
            "run_id": row["run_id"],
            "n_trials": row["n_trials"],
            "best_value": float(row["best_value"]) if row["best_value"] else None,
            "best_params": json.loads(row["best_params"]) if row["best_params"] else {},
            "weights_set_id": row["weights_set_id"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "created_at": row["created_at"]
        }

        logger.info(
            "Study retrieved",
            extra={
                "study_name": study_name,
                "best_value": study["best_value"]
            }
        )

        return study


async def list_studies(
    db_pool: asyncpg.Pool,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    List optimization studies from database.

    Args:
        db_pool: Database connection pool
        limit: Maximum number of studies to return

    Returns:
        List of study dictionaries

    Raises:
        Exception: If database operation fails
    """
    logger.debug("Listing optimization studies", extra={"limit": limit})

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, study_name, run_id, n_trials, best_value, best_params,
                   weights_set_id, started_at, completed_at, created_at
            FROM optuna_studies
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit
        )

        studies = []
        for row in rows:
            studies.append({
                "id": row["id"],
                "study_name": row["study_name"],
                "run_id": row["run_id"],
                "n_trials": row["n_trials"],
                "best_value": float(row["best_value"]) if row["best_value"] else None,
                "best_params": json.loads(row["best_params"]) if row["best_params"] else {},
                "weights_set_id": row["weights_set_id"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "created_at": row["created_at"]
            })

        logger.info(
            "Studies retrieved",
            extra={"count": len(studies)}
        )

        return studies


async def activate_weights_set(
    db_pool: asyncpg.Pool,
    weights_set_id: UUID
) -> None:
    """
    Activate a specific weights set (deactivates all others).

    Args:
        db_pool: Database connection pool
        weights_set_id: UUID of the weights set to activate

    Raises:
        ValueError: If weights set not found
        Exception: If database operation fails
    """
    logger.info(
        "Activating weights set",
        extra={"weights_set_id": str(weights_set_id)}
    )

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            # Check if weights set exists
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM weights_sets WHERE id = $1)",
                weights_set_id
            )

            if not exists:
                raise ValueError(f"Weights set not found: {weights_set_id}")

            # Deactivate all sets
            await conn.execute("UPDATE weights_sets SET is_active = false")

            # Activate the specified set
            await conn.execute(
                "UPDATE weights_sets SET is_active = true WHERE id = $1",
                weights_set_id
            )

    logger.info(
        "Weights set activated successfully",
        extra={"weights_set_id": str(weights_set_id)}
    )
