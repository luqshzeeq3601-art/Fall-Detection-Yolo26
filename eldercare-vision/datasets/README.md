# Datasets

Dataset binaries are outside Git (see `.gitignore`).

- Primary: UR Fall Detection Dataset (temporal benchmark).
- Secondary: UP-Fall RGB subset (robustness).
- Local UAT recordings: never committed; kept out of the repository.

`manifests/` holds dataset manifests; `derived/` holds reproducible derived cache.
Full dataset strategy is defined in the planning pack (`DATASET_PLAN.md`, ADR-004).
No datasets are downloaded in P0-001.
