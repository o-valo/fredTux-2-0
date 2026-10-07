## Zusammenfassung
- Was wurde geändert?
- Welches Problem wird gelöst?

## Prüfungen
- [ ] `.venv/bin/python -m unittest discover -s tests -v`
- [ ] `.venv/bin/python scripts/devcheck.py --no-ollama-check`
- [ ] `.venv/bin/fredtux --help`
- [ ] Keine Secrets, `.venv`-Dateien, `*.egg-info` oder private Sitzungen enthalten
- [ ] README/Dokumentation bei Verhaltensänderungen aktualisiert

## Risiken
- Bekannte Einschränkungen:
- Rollback:
