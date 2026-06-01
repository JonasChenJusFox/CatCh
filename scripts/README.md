# scripts/

Small project maintenance scripts.

## Fishing Catalog

`build_fish_catalog.py` is the only Hollan data script. It is the source of
truth for generating the committed 50-species fish catalog metadata:

```bash
python3 scripts/build_fish_catalog.py
```

It verifies that every `data/fish_images/<species_id>.png` exists, then writes
`data/fish_species.json`.

The AI-generated transparent PNG files are committed directly under
`data/fish_images/`. The frontend does not keep a second copy; `game-service`
serves the same files at `/fish_images/<species_id>.png`.

To add fish later:

1. Add the new fish metadata to `FISH` in `build_fish_catalog.py`.
2. Add a matching transparent PNG in `data/fish_images/`.
3. Run `python3 scripts/build_fish_catalog.py`.
4. Run `cd game-service && pipenv run pytest tests/test_fishing.py -v`.

## Coding Problem Dataset

The runtime coding problem dataset is committed directly at
`data/judgeable_problems.json`. It contains the curated 74 executable
coding-practice problems used by game-service. Raw problem-set CSV files and
intermediate cleanup artifacts are intentionally not kept in the repo.
