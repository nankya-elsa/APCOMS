# Scenarios

This folder holds short scripted demo video clips used by main.py for the panel demo.

Each scenario represents a single shuttle stop event (one passenger boarding, several alighting, mixed traffic, etc). When main.py starts it picks the next scenario in sequence, plays it through the pipeline, then advances on shutdown. After the last scenario the cycle wraps around to the first.

## Naming convention

Use numeric prefixes so files sort in play order:

- `01_first_boarding.mp4`
- `02_main_library.mp4`
- `03_cedat_busy.mp4`

## Why videos are gitignored

Scenario videos are large binary files. They are NEVER committed to git — each developer maintains their own copies locally. The real demo recordings will be shared via a separate channel (Drive / WhatsApp / etc) and dropped into this folder before the demo.

This README itself IS committed so the folder structure is preserved and future developers understand what belongs here.
