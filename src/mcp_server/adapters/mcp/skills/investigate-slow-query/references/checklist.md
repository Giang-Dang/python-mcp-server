# Evidence checklist

- Label planner rows and costs as estimates. EXPLAIN without ANALYZE supplies
  no actual timing, actual row counts, rows removed or buffer statistics.
- A sequential scan can be the correct choice. An index proposal needs evidence
  about selectivity, table size, available indexes and representative workload.
- For joins, inspect estimated input rows and repeated inner work. Metadata
  alone does not prove a foreign key or a one-to-one relationship exists.
- pg_stat_statements aggregates normalized queries over time; account for calls,
  total versus mean execution time, reset windows and potentially truncated output.
- Dead tuples, scan counters and timestamps suggest checks, not a proven cause.
- Locks are a momentary snapshot. A granted lock does not by itself prove blocking.
- Include operation ids and relevant plan properties with each observation.
- State what additional evidence could confirm or reject each hypothesis.
- Preserve P01-P13. Keep corrective SQL as an explicit proposal for review.
