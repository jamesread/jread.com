default:
	hugo build

screenshots:
	python3 scripts/update-screenshots.py

screenshots-force:
	python3 scripts/update-screenshots.py --force

.PHONY: default screenshots screenshots-force
