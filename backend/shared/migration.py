"""
QueueSense - DynamoDB GSI1 Migration & Backfill Engine
Provides safe, idempotent backfill of GSI1PK and GSI1SK attributes into legacy DynamoDB records.

Guarantees:
1. Sparse indexing compliance: only writes GSI keys to LOCATION and REPORT entities.
2. Idempotent execution: conditional expression attribute_not_exists(GSI1PK) ensures safe replays.
3. Batching & Pagination: bounded scans with ExclusiveStartKey support interrupted migration resumption.
4. Dry-run mode: non-destructive inspection of records requiring migration.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("queuesense.migration")


def backfill_gsi1_records(
    table: Any,
    batch_size: int = 50,
    max_items: Optional[int] = None,
    dry_run: bool = False,
    exclusive_start_key: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Scans DynamoDB table for legacy items lacking GSI1PK and populates GSI1 keys.
    Returns migration statistics dictionary.
    """
    try:
        from boto3.dynamodb.conditions import Attr  # type: ignore
    except Exception:
        class Attr:  # type: ignore
            def __init__(self, name):
                self.name = name

            def not_exists(self):
                return self

    stats = {
        "scanned_count": 0,
        "migrated_locations": 0,
        "migrated_reports": 0,
        "skipped": 0,
        "conditional_check_failed": 0,
        "errors": 0,
        "last_evaluated_key": None,
        "is_complete": False,
    }

    last_evaluated_key = exclusive_start_key
    total_processed = 0

    while True:
        scan_kwargs: Dict[str, Any] = {
            "FilterExpression": Attr("GSI1PK").not_exists(),
            "Limit": batch_size,
        }
        if last_evaluated_key:
            scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

        try:
            resp = table.scan(**scan_kwargs)
        except Exception as e:
            logger.error("Migration scan failed: %s", str(e))
            stats["errors"] += 1
            break

        items = resp.get("Items", [])
        stats["scanned_count"] += len(items)

        for item in items:
            pk = str(item.get("PK", ""))
            sk = str(item.get("SK", ""))
            entity_type = item.get("entityType")

            gsi1_pk = None
            gsi1_sk = None

            if entity_type == "LOCATION" or (pk.startswith("LOCATION#") and sk == "METADATA"):
                loc_id = item.get("id") or pk.replace("LOCATION#", "")
                gsi1_pk = "ENTITY#LOCATION"
                gsi1_sk = loc_id
                target_type = "LOCATION"
            elif entity_type == "REPORT" or (pk.startswith("LOCATION#") and sk.startswith("REPORT#")):
                ts = item.get("timestamp", "")
                r_id = item.get("reportId", "")
                gsi1_pk = "ENTITY#REPORT"
                gsi1_sk = f"REPORT#{ts}#{r_id}"
                target_type = "REPORT"
            else:
                stats["skipped"] += 1
                continue

            if not dry_run and gsi1_pk and gsi1_sk:
                try:
                    table.update_item(
                        Key={"PK": pk, "SK": sk},
                        UpdateExpression="SET GSI1PK = :gpk, GSI1SK = :gsk",
                        ConditionExpression="attribute_not_exists(GSI1PK)",
                        ExpressionAttributeValues={
                            ":gpk": gsi1_pk,
                            ":gsk": gsi1_sk,
                        },
                    )
                    if target_type == "LOCATION":
                        stats["migrated_locations"] += 1
                    else:
                        stats["migrated_reports"] += 1
                except Exception as update_err:
                    err_code = getattr(update_err, "response", {}).get("Error", {}).get("Code", "")
                    if err_code == "ConditionalCheckFailedException":
                        # Record already received GSI1PK concurrently; safe idempotent skip
                        stats["conditional_check_failed"] += 1
                    else:
                        logger.error("Failed to update item %s/%s: %s", pk, sk, str(update_err))
                        stats["errors"] += 1
            else:
                # Dry run
                if target_type == "LOCATION":
                    stats["migrated_locations"] += 1
                else:
                    stats["migrated_reports"] += 1

            total_processed += 1
            if max_items and total_processed >= max_items:
                break

        last_evaluated_key = resp.get("LastEvaluatedKey")
        stats["last_evaluated_key"] = last_evaluated_key

        if not last_evaluated_key or (max_items and total_processed >= max_items):
            stats["is_complete"] = last_evaluated_key is None
            break

    return stats
