# Quickstart

```bash
./install.sh && . .venv/bin/activate
```

Then, with the boards on USB:

```bash
luminary boards     # find, verify, register them
luminary flash      # build, flash, confirm each one answers
luminary map        # interactive; it explains itself
luminary flash      # again — now it knows each board's strip length
luminary geometry   # mapping records -> real geometry; prints an id
luminary show --lights <id> --pattern aurora
```

Preview: <http://localhost:8080/preview>

If something is wrong, `luminary boards -v` says what and why.
Limits, tuning, and the rest: [README.md](README.md).
