PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
APT ?= sudo apt-get

DEBIAN_PACKAGES := \
	fonts-noto-core \
	poppler-utils

.PHONY: help install local-install dev-install system-deps ensure-debian-deps run clean

help:
	@echo "Targets:"
	@echo "  make install         # Install Debian deps, then pip install this repo"
	@echo "  make local-install   # pip install this repo into the current Python environment"
	@echo "  make dev-install     # editable install into the current Python environment"
	@echo "  make system-deps     # install Debian packages used by this repo"
	@echo "  make run             # run the GUI app"
	@echo "  make clean           # remove local build artifacts"

install: system-deps local-install

local-install:
	$(PIP) install .

dev-install:
	$(PIP) install -e .

system-deps: ensure-debian-deps

ensure-debian-deps:
	@if [ -f /etc/debian_version ]; then \
		echo "Installing Debian packages: $(DEBIAN_PACKAGES)"; \
		$(APT) update; \
		$(APT) install -y $(DEBIAN_PACKAGES); \
	else \
		echo "Non-Debian system detected; install equivalent packages manually:"; \
		echo "  $(DEBIAN_PACKAGES)"; \
		exit 1; \
	fi

run:
	$(PYTHON) solar_runner.py

clean:
	rm -rf build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
