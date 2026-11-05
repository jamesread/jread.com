LINT_BUILD_DIR := $(shell mktemp -u -d -t jread-lint-XXXXXX)

default:
	hugo build

screenshots:
	python3 scripts/update-screenshots.py

screenshots-force:
	python3 scripts/update-screenshots.py --force

lint: lint-projects lint-yaml lint-markdown lint-python lint-actions lint-html

lint-projects:
	python3 scripts/lint-projects.py

# Informational: compare project descriptions with GitHub (needs `gh`).
lint-projects-github:
	python3 scripts/lint-projects.py --github

lint-yaml:
	yamllint --strict .

lint-markdown:
	npx --no-install markdownlint-cli2

lint-python:
	ruff check scripts
	ruff format --check scripts

lint-actions:
	actionlint

# Builds unminified into a temp dir (so html-validate directives survive),
# failing on any Hugo warning, then validates every page.
lint-html:
	hugo build --panicOnWarning --printPathWarnings --printI18nWarnings --quiet -d $(LINT_BUILD_DIR)
	npx --no-install html-validate -c .htmlvalidate.json "$(LINT_BUILD_DIR)/**/*.html"; \
		status=$$?; \
		if grep -rn --include='*.html' 'href=""' $(LINT_BUILD_DIR); then echo "Empty href found"; status=1; fi; \
		rm -rf $(LINT_BUILD_DIR); exit $$status

.PHONY: default screenshots screenshots-force lint lint-projects lint-projects-github lint-yaml lint-markdown lint-python lint-actions lint-html
