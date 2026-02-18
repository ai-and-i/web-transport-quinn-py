# web-transport-py

Python bindings for [web-transport-quinn](https://docs.rs/web-transport-quinn/) (Rust WebTransport library), built with PyO3 and maturin.

## Project layout

```
web-transport-py/
├── Cargo.toml              # Rust crate config (pyo3 dependency, cdylib)
├── pyproject.toml          # Python package metadata, maturin build-backend
├── src/                    # Rust source (PyO3 bindings)
│   └── lib.rs
├── python/
│   └── web_transport/         # Python-source layout (maturin `python-source = "python"`)
│       ├── __init__.py
│       ├── _web_transport.pyi # Type stubs for the native module
│       └── py.typed        # PEP 561 marker
└── tests/                  # Python tests (pytest)
```

Maturin compiles the Rust crate into a `.so` (Linux/macOS) or `.pyd` (Windows) and places it inside `python/web_transport/`. Add `*.so`, `*.pyd`, `target/`, and `*.egg-info` to `.gitignore`.

## Build and dev commands

| Task | Command |
|---|---|
| Install dev dependencies | `uv sync` |
| Dev build (debug, in-place) | `uv run maturin develop` |
| Release build (wheel) | `uv run maturin build --release` |
| Rust build only | `cargo build` |
| Rust tests | `cargo test` |
| Python tests | `uv run pytest` |
| Lint Python | `uv run ruff check .` |
| Format Python | `uv run ruff format .` |
| Type check Python | `uv run ty check` |
| Lint Rust | `cargo clippy -- -D warnings` |
| Format Rust | `cargo fmt` |
| Full check | `uv run ruff format . && uv run ruff check . && uv run ty check && cargo fmt --check && cargo clippy -- -D warnings && cargo test && uv run maturin develop && uv run pytest` |

**Important:** Always run `uv run maturin develop` before `uv run pytest` — Python tests import the compiled native module, so a stale or missing `.so` will cause failures.

Use `uv` for all Python environment and dependency management (never raw `pip`).

## Code style and conventions

**Python**
- Formatter and linter: ruff (`uv run ruff format`, `uv run ruff check`)
- Type checker: ty (`uv run ty check`)
- Docstrings on every public function, class, and module

**Rust**
- `cargo fmt` for formatting, `cargo clippy -- -D warnings` for lints
- Every `#[pyfunction]` and `#[pymethods]` block returns `PyResult<T>`
- Keep modules small and focused — one Rust file per logical Python class/group

## Testing guidelines

- **Rust tests** (`cargo test`): test internal logic, serialization, error mapping — anything that doesn't need the Python runtime.
- **Python tests** (`pytest`): test the public API surface as users see it — constructors, methods, exceptions, async behavior.
- Run everything before committing: `uv run ruff format . && uv run ruff check . && uv run ty check && cargo test && uv run maturin develop && uv run pytest`
- Use `pytest-asyncio` for async tests.

## Type stubs

- Maintain `.pyi` stub files alongside the native module in `python/web_transport/`.
- Include a `py.typed` marker file for PEP 561 compliance.
- Use `pyo3-stub-gen` or `pyo3-stubgen` to generate initial stubs; hand-edit for clarity.
- Verify stubs pass `uv run ty check` in CI.

## Error handling across the FFI boundary

- All exported functions must return `PyResult<T>` — never a bare `T`.
- Map Rust errors to specific Python exceptions (`PyValueError`, `PyRuntimeError`, etc.) using `.map_err()` or `impl From<MyError> for PyErr`.
- Wrap any code that might panic in `std::panic::catch_unwind` and convert to `PyRuntimeError`.
- Never `.unwrap()` or `.expect()` in `#[pyfunction]`/`#[pymethods]` — a panic across FFI is undefined behavior.

## Memory safety considerations

- **GIL discipline:** Hold `Python<'py>` token only as long as needed. Release the GIL (`py.detach(|| ...)`) for long-running Rust operations.
- **Reference counting:** Use `Py<T>` for storing Python objects in Rust structs. Clone references rather than holding borrows across await points.
- **Copy over reference:** Prefer copying data across the FFI boundary instead of handing out raw references to Rust memory.
- **Async safety:** Futures stored across `.await` must be `Send`. Do not hold `Python<'py>` or `&PyAny` across `.await` — extract data before yielding.

## CI workflow expectations

1. **Lint:** `uv run ruff check .` + `cargo clippy -- -D warnings`
2. **Format check:** `uv run ruff format --check .` + `cargo fmt --check`
3. **Type check:** `uv run ty check`
4. **Rust tests:** `cargo test`
5. **Build + Python tests:** `uv run maturin develop && uv run pytest`
6. **Matrix:** multiple Python versions (3.12+) and platforms (Linux, macOS, Windows)

Use `uv` for Python environment setup in CI. Pin Rust toolchain via `rust-toolchain.toml`.

## Versioning and release

- Single version source: `pyproject.toml` (`version` field). Use `maturin`'s version integration so `Cargo.toml` stays in sync.
- Follow SemVer. Breaking API changes bump major.
- Tag-based releases: push a `vX.Y.Z` tag to trigger the release workflow.
- Publish via trusted publishing (PyPI OIDC) — no API tokens in CI secrets.

## Common PyO3 pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Panic in exported fn | SIGABRT / undefined behavior | Return `PyResult`, use `catch_unwind` |
| Holding GIL in blocking code | Python interpreter freezes | `py.allow_threads(\|\| ...)` |
| Stale `.so` after Rust change | Old behavior / import errors | Re-run `uv run maturin develop` |
| `Send` requirement for async | Compiler error on `.await` | Extract data before yielding, avoid `Py<T>` across await |
| PyO3 / rustc version mismatch | Build failure, cryptic errors | Pin `pyo3` version, match `rust-toolchain.toml` |
| Returning borrowed data | Lifetime errors | Copy or clone data at the boundary |
| Missing `#[new]` on constructor | `TypeError: cannot create instance` | Add `#[new]` to `__init__` impl |
