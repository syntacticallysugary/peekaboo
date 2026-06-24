# CI/CD Workflows

This document describes the GitHub Actions CI/CD pipeline for Peekaboo Intelligence.

## Pipeline Overview

```
┌─────────────────────────────────┐
│  On: push / pull_request        │
└─────────────┬───────────────────┘
              │
     ┌────────┴────────┬────────────┬──────────────┐
     ▼                 ▼            ▼              ▼
  Security       Backend Tests   Frontend Build  Firmware Build
  Scans          (type check)    (Vue/Vite)      (PlatformIO)
     │                 │            │              │
     └────────────────┬─────────────┴──────────────┘
                      ▼
              CI Status Check
              (pass/fail summary)
```

## Workflows

### 1. Security Scans (`security-scans.yml`)

Runs on every push and PR. Detects secrets, vulnerabilities, and code quality issues.

**Jobs:**
- **Secrets Scan** — TruffleHog (credentials, API keys, private data)
- **Python Security** — Bandit (code injection, weak crypto) + pip-audit (dependencies)
- **C++ Static Analysis** — cppcheck (firmware analysis)
- **License Compliance** — Check for GPL/AGPL (optional; can fail without blocking)

**Fails if:**
- Secrets detected in code
- High-severity vulnerabilities found
- GPL/AGPL dependencies (configurable)

### 2. Backend Tests (`test-backend.yml`)

Runs when Python code changes. Type checks and runs unit tests.

**Jobs:**
- **Command Module Type Check** — mypy on `command-module/src`
- **Command Module Tests** — pytest on `command-module/tests` (currently broken; marked `continue-on-error`)
- **Inference Service Type Check** — mypy on `inference-service/src`

**Status:**
- Type checking is required
- Unit tests are optional/broken (will be fixed in backlog)

### 3. Build Frontend (`build-frontend.yml`)

Runs when frontend code changes. Builds Vue/TypeScript dashboard.

**Jobs:**
- **Type Check** — vue-tsc (`continue-on-error`)
- **Lint** — ESLint (`continue-on-error`)
- **Build** — Vite production build (required)
- **Verify** — Confirm dist/ output exists

**Artifacts:**
- Uploads `dist/` for 5 days (viewable in Actions tab)

### 4. Build Firmware (`build-firmware.yml`)

Runs when firmware code changes. Builds ESP32 firmware without hardware.

**Jobs:**
- **Build** — PlatformIO compile for all 4 environments:
  - `esp32s3eye` (first ESP32-S3-EYE unit)
  - `esp32s3eye_02` (second ESP32-S3-EYE unit)
  - `xiao_s3_01` (XIAO ESP32-S3 Sense)
  - `xiao_s3_02` (second XIAO unit)
- **Size Check** — Verify firmware ≤ 8 MB flash (fail-fast)

**Requirements:**
- Dummy `.env` created during build (PlatformIO needs env vars, build is offline)
- No hardware needed (offline build verification only)

### 5. CI Status (`ci.yml`)

Meta-workflow that orchestrates all checks and provides pass/fail summary.

**Trigger:** Any push or PR
**Result:** GitHub checks tab shows overall status

---

## Known Gaps & Future Work

### Gaps Accepted for Public Release

1. **No hardware-in-the-loop testing** — Firmware builds are verified offline only
2. **No CVE scanner for ESP-IDF components** — esp-idf managed_components lack mature vulnerability scanners
3. **Broken pytest suite** — Tests import deleted SQL-era code; needs full rewrite for Firestore
4. **No integration tests** — No Docker compose spin-up or Jetson simulation

### Stretch Goals

- [ ] Hardware flashing simulation (esptool dry-run)
- [ ] Firmware binary size regression tracking
- [ ] Docker image build validation (command-module, inference-service)
- [ ] End-to-end integration tests (Firebase Emulator)
- [ ] clang-tidy for C++ analysis (requires compile_commands.json)

---

## Local Development

Run the same checks locally before pushing:

```bash
# Secrets scan
trufflehog filesystem . --debug

# Python security
pip install bandit pip-audit
bandit -r command-module/src inference-service/src
pip-audit

# Frontend build
cd command-module/frontend
npm ci && npm run build

# Firmware build
cd camera
pio run -e esp32s3eye
```

---

## Troubleshooting

### Build fails with "WIFI_SSID not defined"

The firmware build creates a dummy `.env` file during CI. If local build fails, ensure `camera/.env` exists:

```bash
cd camera
cp .env.example .env
# Edit .env with your real credentials
pio run -e esp32s3eye
```

### Type check fails but code runs fine

mypy is strict; ignore warnings with `# type: ignore` comments for known issues.

### Artifacts not uploaded

Check Actions tab → click workflow run → "Artifacts" section (only available if build succeeded).

---

## CI Badge

Add this to your README to show CI status:

```markdown
[![CI Pipeline](https://github.com/YOUR_ORG/peekaboo/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_ORG/peekaboo/actions)
```

---

## See Also

- `.github/workflows/` — Workflow definitions
- `README.md` — Project overview
- `docs/` — Architecture & design
