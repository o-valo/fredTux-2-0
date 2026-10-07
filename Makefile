.PHONY: install check test devcheck backup clean

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install --no-deps --editable .

check: test devcheck

test:
	.venv/bin/python -m compileall -q .
	.venv/bin/python -m unittest discover -s tests -v

devcheck:
	.venv/bin/python scripts/devcheck.py

backup:
	bash scripts/backup_fredtux.sh $(ARGS)

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf build dist *.egg-info
