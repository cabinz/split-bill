# Makefile for SplitBill
# A bill splitting tool for group trips

# Variables
PYTHON := python3
UV := uv
PIP := pip
PACKAGE_NAME := split-bill
MODULE_NAME := splitbill

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# Default target
.DEFAULT_GOAL := help

# Check if uv is available
HAS_UV := $(shell command -v uv 2> /dev/null)

# Check if we're in a virtual environment
VENV_ACTIVE := $(VIRTUAL_ENV)

# === Installation Commands ===

## install: Build and install package to current Python environment
.PHONY: install
install:
	@echo "$(BLUE)Building and installing $(PACKAGE_NAME)...$(NC)"
ifdef HAS_UV
	@echo "$(GREEN)Using uv for installation$(NC)"
	@uv build
	@uv pip install --system dist/*.whl
else
	@echo "$(YELLOW)uv not found, using pip$(NC)"
	@$(PYTHON) -m build 2>/dev/null || $(PIP) install build && $(PYTHON) -m build
	@$(PIP) install dist/*.whl
endif
	@echo "$(GREEN)✓ $(PACKAGE_NAME) installed successfully!$(NC)"
	@echo "$(GREEN)✓ Command 'splitbill' is now available$(NC)"

## install-dev: Setup complete development environment
.PHONY: install-dev
install-dev:
	@echo "$(BLUE)Setting up development environment...$(NC)"
ifndef HAS_UV
	@echo "$(RED)Error: uv is required for development setup$(NC)"
	@echo "$(YELLOW)Install uv with: curl -LsSf https://astral.sh/uv/install.sh | sh$(NC)"
	@exit 1
endif
	@echo "$(GREEN)Step 1/3: Creating virtual environment...$(NC)"
	@test -d .venv || uv venv
	@echo "$(GREEN)Step 2/3: Installing dependencies...$(NC)"
	@uv sync
	@echo "$(GREEN)Step 3/3: Installing package in editable mode...$(NC)"
	@uv pip install -e .
	@echo "$(GREEN)✓ Development environment ready!$(NC)"
	@echo "$(YELLOW)Activate with: source .venv/bin/activate$(NC)"

## uninstall: Uninstall the package
.PHONY: uninstall
uninstall:
	@echo "$(BLUE)Uninstalling $(PACKAGE_NAME)...$(NC)"
ifdef HAS_UV
	@uv pip uninstall $(PACKAGE_NAME) -y 2>/dev/null || true
else
	@$(PIP) uninstall $(PACKAGE_NAME) -y 2>/dev/null || true
endif
	@echo "$(GREEN)✓ $(PACKAGE_NAME) uninstalled$(NC)"

# === Development Commands ===

## test: Run all tests
.PHONY: test
test:
	@echo "$(BLUE)Running tests...$(NC)"
ifdef HAS_UV
	@uv run pytest $(TEST_ARGS)
else
	@echo "$(YELLOW)uv not found, using pytest directly$(NC)"
	@pytest $(TEST_ARGS)
endif

# === Web interface ===

WEBUI_SRC := webui
WEBUI_OUT := $(MODULE_NAME)/render/webui
HAS_NPM := $(shell command -v npm 2> /dev/null)

## webui: Build the web interface into splitbill/render/webui/
.PHONY: webui
webui:
ifndef HAS_NPM
	@echo "$(RED)Error: npm is required to build the web interface$(NC)"
	@echo "$(YELLOW)The built interface is committed, so this is only needed after"
	@echo "changing anything under webui/src/.$(NC)"
	@exit 1
endif
	@echo "$(BLUE)Building the web interface...$(NC)"
	@cd $(WEBUI_SRC) && npm install --silent && npm run build
	@echo "$(GREEN)✓ Built into $(WEBUI_OUT)$(NC)"
	@echo "$(YELLOW)The output is committed on purpose: it is what makes"
	@echo "'pip install splitbill && splitbill serve' work without node.$(NC)"
	@echo "$(YELLOW)Commit it alongside the source change that caused it.$(NC)"

## webui-dev: Start only Vite (needs `make serve` alongside)
.PHONY: webui-dev
webui-dev:
	@echo "$(BLUE)Starting Vite on :5173, proxying /api to :8765$(NC)"
	@echo "$(YELLOW)Run 'make serve' in another terminal for the API.$(NC)"
	@cd $(WEBUI_SRC) && npm run dev

## develop: Start frontend HMR and backend auto-reload together
.PHONY: develop
develop:
	@uv run splitbill serve --develop

## webui-test: Unit-test the shared presentation layer (no browser needed)
.PHONY: webui-test
webui-test:
ifndef HAS_NPM
	@echo "$(RED)Error: npm is required$(NC)"
	@exit 1
endif
	@echo "$(BLUE)Testing the shared presentation layer...$(NC)"
	@cd $(WEBUI_SRC) && npm install --silent && npm test

## webui-check: Build the interface and drive it in a real browser
.PHONY: webui-check
webui-check: webui webui-test
	@echo "$(BLUE)Starting the service and checking the page...$(NC)"
	@cd $(WEBUI_SRC) && npx playwright install chromium --with-deps 2>/dev/null \
		|| npx playwright install chromium
	@( uv run splitbill serve --port 8765 --no-browser & echo $$! > /tmp/sb.pid ) \
		&& sleep 3 \
		&& ( cd $(WEBUI_SRC) && node e2e/smoke.mjs --port 8765 \
		     && node e2e/print.mjs --port 8765 \
		     && node e2e/edge.mjs --port 8765 \
		     && node e2e/i18n.mjs --port 8765 ); \
		status=$$?; kill `cat /tmp/sb.pid` 2>/dev/null; rm -f /tmp/sb.pid; \
		exit $$status

## webui-shots: Screenshots and a PDF into /tmp/splitbill-shots, for looking at
.PHONY: webui-shots
webui-shots:
	@( uv run splitbill serve --port 8765 --no-browser & echo $$! > /tmp/sb.pid ) \
		&& sleep 3 \
		&& ( cd $(WEBUI_SRC) && node e2e/shots.mjs --port 8765 ); \
		status=$$?; kill `cat /tmp/sb.pid` 2>/dev/null; rm -f /tmp/sb.pid; \
		echo "$(YELLOW)pdftoppm -r 80 -png /tmp/splitbill-shots/report.pdf pg$(NC)"; \
		exit $$status

## serve: Start the local web service
.PHONY: serve
serve:
	@uv run splitbill serve

# === Build Commands ===

## build: Build distribution packages (wheel and sdist)
.PHONY: build
build: clean
	@echo "$(BLUE)Building distribution packages...$(NC)"
	@test -f $(WEBUI_OUT)/index.html \
		|| echo "$(YELLOW)⚠ No web interface in $(WEBUI_OUT) — run 'make webui'$(NC)"
ifdef HAS_UV
	@uv build
else
	@$(PYTHON) -m build 2>/dev/null || ($(PIP) install build && $(PYTHON) -m build)
endif
	@echo "$(GREEN)✓ Built packages in dist/$(NC)"
	@ls -lh dist/

## clean: Remove build artifacts and cache files
.PHONY: clean
clean:
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	@rm -rf dist/ build/ *.egg-info src/*.egg-info
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@rm -rf .pytest_cache/
	@rm -rf .ruff_cache/
	@echo "$(GREEN)✓ Cleaned$(NC)"

## publish: Publish package to PyPI
.PHONY: publish
publish: build
	@echo "$(BLUE)Publishing to PyPI...$(NC)"
ifdef HAS_UV
	@uv publish
else
	@echo "$(YELLOW)Installing twine...$(NC)"
	@$(PIP) install twine
	@twine upload dist/*
endif
	@echo "$(GREEN)✓ Published to PyPI$(NC)"

# === Helper Commands ===

## help: Show this help message
.PHONY: help
help:
	@echo "$(BLUE)SplitBill Makefile$(NC)"
	@echo ""
	@echo "$(YELLOW)Available commands:$(NC)"
	@echo ""
	@grep -E '^## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ": "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}' | sed 's/## //'
	@echo ""
	@echo "$(YELLOW)Examples:$(NC)"
	@echo "  make install         # Install for users"
	@echo "  make install-dev     # Setup development environment"
	@echo "  make serve           # Start the web interface"
	@echo "  make develop         # Start frontend and backend with hot reload"
	@echo "  make test            # Run all tests"
	@echo "  make test TEST_ARGS='-v tests/test_auto_detect.py'  # Run specific test"
	@echo "  make webui           # Rebuild the web interface after editing webui/src"
	@echo "  make webui-test      # Unit-test the shared presentation layer"
	@echo ""
ifdef HAS_UV
	@echo "$(GREEN)✓ uv detected$(NC)"
else
	@echo "$(YELLOW)⚠ uv not found - some features limited$(NC)"
endif
ifdef VENV_ACTIVE
	@echo "$(GREEN)✓ Virtual environment active$(NC)"
endif

# Declare all targets as phony to ensure they always run
.PHONY: install install-dev uninstall test build clean publish help \
	webui webui-dev webui-test webui-check webui-shots serve develop
