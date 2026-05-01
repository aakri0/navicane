# Contributing to Navicane

Thanks for your interest in contributing! This guide will help you get started.

## Development Setup

1. **Clone the repo:**
   ```bash
   git clone https://github.com/aakri0/navicane.git
   cd navicane
   ```

2. **Start in development mode (Mac):**
   ```bash
   ./start.sh
   # This builds the Docker image and runs with mock hardware
   ```

3. **Edit code:** Source files in `src/` are bind-mounted in dev mode — your changes take effect on container restart.

## Code Structure

| Directory | Purpose |
|---|---|
| `src/config/settings.py` | All configuration — modify here, not in modules |
| `src/modules/` | One file per hardware component |
| `src/main.py` | Multithreaded entry point + alert arbitration |
| `scripts/` | Build, deploy, and operational scripts |
| `docs/` | Documentation and training artifacts |

## Branch Strategy

- `main` — stable, deployable code
- Feature branches: `feat/description`
- Bug fixes: `fix/description`

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes
3. Ensure all modules pass syntax check: `python3 -m py_compile src/modules/*.py src/main.py`
4. Write clear commit messages following [Conventional Commits](https://www.conventionalcommits.org/)
5. Open a PR against `main`

## Commit Message Format

```
type(scope): description

feat(imu): add accelerometer-based fall detection
fix(camera): handle missing picamera2 gracefully
docs(readme): add indoor/outdoor mode documentation
```

## Reporting Issues

Use the GitHub issue templates:

- **Bug Report:** For unexpected behavior
- **Feature Request:** For new functionality
- **Hardware Issue:** For wiring or sensor problems

## Code Style

- Python 3.11+
- Type hints on all public functions
- Docstrings on all modules and public functions
- `logging` module for all runtime messages (not `print()` in modules)
- Constants in `settings.py`, not inline

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
