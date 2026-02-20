import ast
import asyncio
import io
import json
import os
import sqlite3
import tempfile
import time
import traceback
import urllib.request
import zipfile
from datetime import datetime
from typing import Any

# ------------------------------------------------------------
# Dynamic PyLabRobot documentation/content loader
# ------------------------------------------------------------

_MAX_DOC_CHARS = int("50000")


def _load_pylabrobot_tutorial_content(section: str) -> str:
    """Load PLR tutorial/docs text from multiple sources with graceful fallback.

    Precedence:
      1) Docs from installed pylabrobot package (docs/user_guide/...)
      2) Introspect installed package (pylabrobot)
    """
    docs: list[str] = []

    # 1) Fetch from GitHub repo zip (pinned commit by default)
    repo = "PyLabRobot/pylabrobot"
    ref = "106aef9c8699ceb826d8c9c894eba304a082f24d"

    gh_docs = _collect_docs_from_github_zip(repo=repo, ref=ref, section=section)

    if gh_docs and isinstance(gh_docs[0], tuple):
        if section == "liquid":
            formatted = _format_liquid_user_guide(gh_docs)  # returns single string
            if formatted:
                docs.append(formatted)
        else:
            # Concatenate texts in stable order
            docs.append("\n\n".join(text for _, text in gh_docs if text))
    else:
        docs.extend(gh_docs)

    if not docs:
        return ""

    text = "\n\n".join([d for d in docs if d])
    if len(text) > _MAX_DOC_CHARS:
        text = text[:_MAX_DOC_CHARS]
    return text


def _collect_docs_from_github_zip(repo: str, ref: str, section: str) -> list[tuple[str, str]] | list[str]:
    """Download GitHub repo zip and extract user_guide docs for the section.

    Uses:
      - docs/user_guide/00_liquid-handling for section == "liquid"
      - docs/user_guide/01_material-handling for section == "material"
    """
    if not repo:
        return []

    # Try commit zip first if ref looks like a commit SHA, then branch, then tag
    url = f"https://github.com/{repo}/archive/{ref}.zip"

    data = None
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = resp.read()
    except Exception:
        return []

    # Restrict to specific subfolders by section
    if section == "liquid":
        # Only the Hamilton STAR(let) folder for now
        target_subdir = "docs/user_guide/00_liquid-handling/hamilton-star"
    else:
        target_subdir = "docs/user_guide/01_material-handling"
    target_subdir = target_subdir.lower()

    collected_named: list[tuple[str, str]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # Select relevant names within target_subdir
            candidate_names = []
            for name in zf.namelist():
                lower = name.lower()
                if target_subdir not in lower:
                    continue
                if lower.endswith("/"):
                    continue
                if not (
                    lower.endswith(".md")
                    or lower.endswith(".rst")
                    or lower.endswith(".txt")
                    or lower.endswith(".ipynb")
                ):
                    continue
                candidate_names.append(name)

            # Deterministic order; for liquid, ensure basic.ipynb first
            if section == "liquid":
                candidate_names.sort(key=lambda n: (0 if n.lower().endswith("basic.ipynb") else 1, n.lower()))
            else:
                candidate_names.sort(key=lambda n: n.lower())

            for name in candidate_names:
                lower = name.lower()
                try:
                    with zf.open(name) as f:
                        content_bytes = f.read()
                        if lower.endswith(".ipynb"):
                            try:
                                nb = json.loads(content_bytes.decode("utf-8"))
                            except Exception:
                                continue
                            cells = nb.get("cells") or nb.get("worksheets", [{}])[0].get("cells", [])
                            parts = []
                            for c in cells:
                                ctype = c.get("cell_type") or c.get("type")
                                src = c.get("source") or c.get("input") or []
                                if isinstance(src, list):
                                    src = "".join(src)
                                if not isinstance(src, str):
                                    continue
                                if ctype == "markdown":
                                    parts.append(src)
                                elif ctype == "code":
                                    keep_lines = []
                                    for line in src.splitlines():
                                        l = line.strip()
                                        if l.startswith("#"):
                                            continue
                                        if "pylabrobot" in l and ("import " in l or "from " in l):
                                            keep_lines.append(l)
                                    if keep_lines:
                                        parts.append("Code refs:\n" + "\n".join(keep_lines[:20]))
                                if sum(len(p) for p in parts) > 5000:
                                    break
                            text = "\n\n".join(parts)
                        else:
                            try:
                                text = content_bytes.decode("utf-8")
                            except Exception:
                                text = str(content_bytes)
                        if text:
                            collected_named.append((lower, text[:5000]))
                except Exception:
                    continue
    except Exception:
        return []

    return collected_named


def _format_liquid_user_guide(named_docs: list[tuple[str, str]]) -> str:
    """Assemble liquid-handling docs into a curated order with headings.

    named_docs: list of (filename_lower, text) from GitHub.
    Returns a single formatted string.
    """
    sections = [
        (
            "Getting started with liquid handling on a Hamilton STAR(let)",
            ["/hamilton-star/", "basic.ipynb", "basic", "getting-started"],
        ),
        ("iSWAP Module", ["iswap"]),
        ("Liquid level detection on Hamilton STAR(let)", ["liquid-level", "lld", "level_detection", "level-detection"]),
        ("Z-probing", ["z-probing", "z_probing", "z-probing", "zprobing", "z-prob"]),
        ("Foil", ["foil"]),
        ("Using the 96 head", ["96", "head", "mca", "96-head", "head-96"]),
        (
            "Using “Hamilton Liquid Classes” with Pylabrobot",
            ["liquid-classes", "liquid_classes", "hamilton-liquid-classes"],
        ),
    ]

    used: set[int] = set()
    out_parts: list[str] = []

    def pick_first(keywords: list[str]) -> str:
        for idx, (fname, text) in enumerate(named_docs):
            if idx in used:
                continue
            if any(k in fname for k in keywords):
                used.add(idx)
                return text
        return ""

    for heading, keywords in sections:
        text = pick_first(keywords)
        if text:
            out_parts.append(f"## {heading}\n\n{text}")

    # Append any remaining docs not matched, to avoid losing content
    for idx, (fname, text) in enumerate(named_docs):
        if idx not in used and text:
            # Derive a nice title from filename
            leaf = fname.rsplit("/", 1)[-1]
            title = leaf.replace("_", " ").replace("-", " ")
            title = title.rsplit(".", 1)[0].strip().title()
            out_parts.append(f"## {title}\n\n{text}")

    return "\n\n".join(out_parts)


def get_pylabrobot_documentation_liquid() -> str:
    """Get the documentation for a specific section of the PyLabRobot tutorial."""
    tutorial_content = """Notes:
- Use hamilton_96_tiprack_1000uL_filter instead of HTF (deprecated). Note the capital L in uL.
- Use Cor_96_wellplate_360ul_Fb instead of Corning_96_wellplate_360ul_Fb.
- You must name all your plates, tip racks, and carriers.
- Assign labware into carriers via slot assignment (tip_car[0] = tiprack). Assign plates to rails using lh.deck.assign_child_resource(plate_car, rails=14).
- Rails must be between -4 and 32.
- Make sure most liquid handling operations are done with async/await.
- There are some methods that are not async, including lh.summary(). Do not use await for these methods.
- When picking up tips with multiple channels, use a flat list of tips. Do not use a list of lists. """

    tutorial_content += _load_pylabrobot_tutorial_content("liquid")

    return tutorial_content


def get_pylabrobot_documentation_material() -> str:
    tutorial_content = _load_pylabrobot_tutorial_content("material")

    return tutorial_content


def test_pylabrobot_script(
    script_input: str,
    enable_tracking: bool = False,
    timeout_seconds: int = 60,
    save_test_report: bool = False,
    test_report_dir: str = None,
) -> dict[str, Any]:
    """Test a PyLabRobot script using simulation and validation.

    Uses PyLabRobot's ChatterboxBackend and tracking systems to
    validate generated scripts without requiring physical hardware.

    Args:
        script_input (str): Either the PyLabRobot script code as a string, or a file path to a .py file
        enable_tracking (bool): Enable tip and volume tracking for error detection
        timeout_seconds (int): Maximum execution time before timeout
        save_test_report (bool): Whether to save detailed test results to file
        test_report_dir (str, optional): Directory to save test reports

    Returns:
        dict: Dictionary containing:
            - success (bool): Whether the script passed all tests
            - test_results (dict): Detailed test results for each validation step
            - execution_summary (dict): Summary of operations performed
            - errors (list): List of errors encountered
            - warnings (list): List of warnings
            - test_report_path (str): Path to saved report if requested

    Example:
        >>> # Test with script content string
        >>> script = "async def main(): ..."
        >>> result = test_pylabrobot_script(script)

        >>> # Test with file path
        >>> result = test_pylabrobot_script("/path/to/script.py")

        >>> if result["success"]:
        ...     print("Test passed!")
        ... else:
        ...     print(f"Test failed: {result['errors']}")
    """
    start_time = time.time()
    test_results = {
        "syntax_valid": False,
        "imports_valid": False,
        "simulation_successful": False,
        "tracking_enabled": enable_tracking,
    }
    execution_summary = {"operations_performed": 0, "tips_used": 0, "liquid_transferred": 0.0, "execution_time": 0.0}
    errors = []
    warnings = []

    # Determine if input is a file path or script content
    script_content = ""
    try:
        # Check if input looks like a file path and exists
        if (
            script_input.endswith(".py") and os.path.isfile(script_input) and "\n" not in script_input[:100]
        ):  # Basic heuristic: file paths shouldn't have newlines
            try:
                with open(script_input, encoding="utf-8") as f:
                    script_content = f.read()
                test_results["input_type"] = "file"
                test_results["file_path"] = script_input
            except Exception as e:
                errors.append(f"Failed to read script file '{script_input}': {str(e)}")
                return _create_test_result(
                    False,
                    test_results,
                    execution_summary,
                    errors,
                    warnings,
                    start_time,
                    save_test_report,
                    test_report_dir,
                )
        else:
            # Treat as script content string
            script_content = script_input
            test_results["input_type"] = "string"

    except Exception as e:
        errors.append(f"Failed to process script input: {str(e)}")
        return _create_test_result(
            False, test_results, execution_summary, errors, warnings, start_time, save_test_report, test_report_dir
        )

    if not script_content.strip():
        errors.append("Script content is empty")
        return _create_test_result(
            False, test_results, execution_summary, errors, warnings, start_time, save_test_report, test_report_dir
        )

    try:
        # Step 1: Syntax Validation
        try:
            ast.parse(script_content)
            test_results["syntax_valid"] = True
        except SyntaxError as e:
            errors.append(f"Syntax Error: {str(e)} at line {e.lineno}")
            return _create_test_result(
                False, test_results, execution_summary, errors, warnings, start_time, save_test_report, test_report_dir
            )

        # Step 2: Import Validation
        import_results = _validate_pylabrobot_imports(script_content)
        test_results["imports_valid"] = import_results["success"]
        if not import_results["success"]:
            errors.extend(import_results["errors"])
            warnings.extend(import_results["warnings"])

        # Step 3: Replace backends with ChatterboxBackend for simulation
        modified_script = _modify_script_for_testing(script_content, enable_tracking)

        # Step 4: Execute script in controlled environment
        execution_result = _execute_script_safely(modified_script, timeout_seconds)

        test_results["simulation_successful"] = execution_result["success"]
        execution_summary.update(execution_result["summary"])

        if not execution_result["success"]:
            errors.extend(execution_result["errors"])

        warnings.extend(execution_result.get("warnings", []))

    except Exception as e:
        errors.append(f"Unexpected error during testing: {str(e)}")
        traceback.print_exc()

    overall_success = (
        test_results["syntax_valid"] and test_results["imports_valid"] and test_results["simulation_successful"]
    )

    return _create_test_result(
        overall_success,
        test_results,
        execution_summary,
        errors,
        warnings,
        start_time,
        save_test_report,
        test_report_dir,
    )


def _validate_pylabrobot_imports(script_content: str) -> dict[str, Any]:
    """Validate that all PyLabRobot imports in the script are available."""
    import_errors = []
    import_warnings = []

    try:
        # Parse the script to find import statements
        tree = ast.parse(script_content)
        pylabrobot_imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "pylabrobot" in alias.name:
                        pylabrobot_imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and "pylabrobot" in node.module:
                    for alias in node.names:
                        full_import = f"{node.module}.{alias.name}"
                        pylabrobot_imports.append(full_import)

        # Try to import each PyLabRobot module/class
        for import_name in pylabrobot_imports:
            try:
                # Handle different import patterns
                if "." in import_name:
                    parts = import_name.split(".")
                    module_parts = parts[:-1]
                    class_name = parts[-1]

                    # Import the module
                    module_name = ".".join(module_parts)
                    module = __import__(module_name, fromlist=[class_name])

                    # Check if the class/function exists
                    if not hasattr(module, class_name):
                        import_errors.append(f"Cannot find '{class_name}' in module '{module_name}'")
                else:
                    # Direct module import
                    __import__(import_name)

            except ImportError as e:
                import_errors.append(f"Failed to import '{import_name}': {str(e)}")
            except Exception as e:
                import_warnings.append(f"Warning validating import '{import_name}': {str(e)}")

    except Exception as e:
        import_errors.append(f"Error parsing imports: {str(e)}")

    return {"success": len(import_errors) == 0, "errors": import_errors, "warnings": import_warnings}


def _modify_script_for_testing(script_content: str, enable_tracking: bool) -> str:
    """Modify script to use simulation backends and enable tracking."""
    modified_script = script_content

    # Replace STARBackend with LiquidHandlerChatterboxBackend for simulation
    replacements = [("STARBackend()", "LiquidHandlerChatterboxBackend()")]

    for old, new in replacements:
        modified_script = modified_script.replace(old, new)

    lines = modified_script.split("\n")
    insert_at = 0
    for i, line in enumerate(lines):
        if line.strip().startswith(("from ", "import ", "#")):
            insert_at = i + 1
            continue
        if line.strip().startswith(("async def", "def", "class", "if __name__")):
            break
        insert_at = i + 1
    lines.insert(insert_at, "from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend")
    modified_script = "\n".join(lines)

    # Add tracking imports and setup at the beginning
    if enable_tracking:
        tracking_setup = """
# Enable PyLabRobot tracking for validation
try:
    from pylabrobot.resources import set_tip_tracking, set_volume_tracking
    set_tip_tracking(True)
    set_volume_tracking(True)
except ImportError:
    pass  # Tracking not available in this PyLabRobot version

"""
    else:
        tracking_setup = """
# Disable PyLabRobot tracking for testing
try:
    from pylabrobot.resources import set_tip_tracking, set_volume_tracking
    set_tip_tracking(False)
    set_volume_tracking(False)
except ImportError:
    pass  # Tracking not available in this PyLabRobot version

"""

    # Insert after imports but before main function
    lines = modified_script.split("\n")
    insert_index = 0
    for i, line in enumerate(lines):
        if (
            line.strip().startswith("async def")
            or line.strip().startswith("def")
            or line.strip().startswith("if __name__")
        ):
            insert_index = i
            break

    lines.insert(insert_index, tracking_setup)
    modified_script = "\n".join(lines)

    return modified_script


def _execute_script_safely(script_content: str, timeout_seconds: int) -> dict[str, Any]:
    """Execute the modified script in a safe environment."""
    errors = []
    warnings = []
    summary = {"operations_performed": 0, "tips_used": 0, "liquid_transferred": 0.0}

    try:
        # Create a temporary file for the script
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script_content)
            temp_script_path = f.name

        # Execute the script with timeout
        try:
            # Use threading for timeout control
            import threading

            result = None
            exception = None

            def target():
                nonlocal result, exception
                try:
                    result = _run_script_with_monitoring(temp_script_path)
                except Exception as e:
                    exception = e

            thread = threading.Thread(target=target)
            thread.start()
            thread.join(timeout=timeout_seconds)

            if thread.is_alive():
                errors.append(f"Script execution timed out after {timeout_seconds} seconds")
            elif exception:
                raise exception
            elif result:
                summary.update(result.get("summary", {}))
                warnings.extend(result.get("warnings", []))

                return {"success": True, "summary": summary, "errors": errors, "warnings": warnings}
            else:
                errors.append("Script execution completed but returned no result")
        except Exception as e:
            errors.append(f"Script execution failed: {str(e)}")

    except Exception as e:
        errors.append(f"Failed to prepare script execution: {str(e)}")
    finally:
        # Clean up temporary file
        try:
            os.unlink(temp_script_path)
        except OSError:
            pass

    return {"success": False, "summary": summary, "errors": errors, "warnings": warnings}


def _run_script_with_monitoring(script_path: str) -> dict[str, Any]:
    """Run the script and monitor its execution."""
    # Note: This is a simplified version. In practice, you might want to
    # use subprocess or other isolation methods for safety

    warnings = []
    summary = {"operations_performed": 0, "tips_used": 0, "liquid_transferred": 0.0}

    try:
        # Read and execute the script
        with open(script_path) as f:
            script_content = f.read()

        # Create a namespace for execution
        namespace = {
            "__name__": "__main__",
            "__file__": script_path,
        }

        # Execute the script
        exec(script_content, namespace)

        # If the script has a main function, run it
        if "main" in namespace and callable(namespace["main"]):
            if asyncio.iscoroutinefunction(namespace["main"]):
                # Run async main function using asyncio.run if not in event loop
                try:
                    asyncio.get_running_loop()
                    # We're in an event loop, create a new thread to run asyncio.run
                    import threading

                    result = None
                    exception = None

                    def run_async():
                        nonlocal result, exception
                        try:
                            asyncio.run(namespace["main"]())
                        except Exception as e:
                            exception = e

                    thread = threading.Thread(target=run_async)
                    thread.start()
                    thread.join()

                    if exception:
                        raise exception
                except RuntimeError:
                    # No event loop running, safe to use asyncio.run
                    asyncio.run(namespace["main"]())
            else:
                namespace["main"]()

        # Execution summary collection can be added here in the future once
        # PyLabRobot exposes reliable runtime statistics.
    except Exception as e:
        raise Exception(f"Script execution error: {str(e)}") from e

    return {"summary": summary, "warnings": warnings}


def _create_test_result(
    success: bool,
    test_results: dict,
    execution_summary: dict,
    errors: list,
    warnings: list,
    start_time: float,
    save_test_report: bool,
    test_report_dir: str,
) -> dict[str, Any]:
    """Create the final test result dictionary."""
    # Calculate total execution time
    total_execution_time = time.time() - start_time
    execution_summary["total_execution_time"] = total_execution_time

    result = {
        "success": success,
        "test_results": test_results,
        "execution_summary": execution_summary,
        "errors": errors,
        "warnings": warnings,
    }

    # Save test report if requested
    if save_test_report:
        try:
            if test_report_dir:
                os.makedirs(test_report_dir, exist_ok=True)
            else:
                test_report_dir = tempfile.gettempdir()

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            report_filename = f"pylabrobot_test_report_{timestamp}.json"
            report_path = os.path.join(test_report_dir, report_filename)

            with open(report_path, "w") as f:
                json.dump(result, f, indent=2)

            result["test_report_path"] = report_path

        except Exception as e:
            warnings.append(f"Failed to save test report: {str(e)}")

    return result


_WETLAB_TABLE_NAME = "wetlab_results"
_WETLAB_KEY_FIELDS = ("experiment_id", "sample_id", "assay_name", "condition", "replicate")
_WETLAB_REQUIRED_RECORD_FIELDS = (
    "experiment_id",
    "sample_id",
    "assay_name",
    "condition",
    "replicate",
    "measurement_value",
    "measurement_unit",
    "measured_at",
)
_WETLAB_UPDATABLE_FIELDS = {
    "measurement_value",
    "measurement_unit",
    "operator",
    "instrument",
    "measured_at",
    "notes",
}
_WETLAB_QUERYABLE_FIELDS = {
    "experiment_id",
    "sample_id",
    "assay_name",
    "condition",
    "replicate",
    "measurement_unit",
    "operator",
    "instrument",
}


def _connect_wetlab_db(db_path: str) -> tuple[sqlite3.Connection, str]:
    if not db_path or not str(db_path).strip():
        raise ValueError("db_path cannot be empty.")

    resolved_db_path = os.path.abspath(os.path.expanduser(str(db_path).strip()))
    db_dir = os.path.dirname(resolved_db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(resolved_db_path)
    conn.row_factory = sqlite3.Row
    return conn, resolved_db_path


def _ensure_wetlab_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_WETLAB_TABLE_NAME} (
            result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id TEXT NOT NULL,
            sample_id TEXT NOT NULL,
            assay_name TEXT NOT NULL,
            condition TEXT NOT NULL,
            replicate INTEGER NOT NULL,
            measurement_value REAL NOT NULL,
            measurement_unit TEXT NOT NULL,
            operator TEXT,
            instrument TEXT,
            measured_at TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (experiment_id, sample_id, assay_name, condition, replicate)
        )
        """
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{_WETLAB_TABLE_NAME}_experiment_id ON {_WETLAB_TABLE_NAME} (experiment_id)"
    )
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{_WETLAB_TABLE_NAME}_sample_id ON {_WETLAB_TABLE_NAME} (sample_id)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{_WETLAB_TABLE_NAME}_assay_name ON {_WETLAB_TABLE_NAME} (assay_name)")
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{_WETLAB_TABLE_NAME}_measured_at ON {_WETLAB_TABLE_NAME} (measured_at)"
    )


def _validate_wetlab_key(key: dict) -> tuple[bool, str]:
    if not isinstance(key, dict):
        return False, "key must be a dictionary."
    missing = [field for field in _WETLAB_KEY_FIELDS if field not in key]
    if missing:
        return False, "Missing key fields: " + ", ".join(missing)
    return True, ""


def _format_wetlab_rows(columns: list[str], rows: list[sqlite3.Row]) -> str:
    if not rows:
        return ""

    values = [[("" if row[col] is None else str(row[col])) for col in columns] for row in rows]
    widths = [len(col) for col in columns]
    for row_values in values:
        for idx, item in enumerate(row_values):
            widths[idx] = max(widths[idx], len(item))

    header = " | ".join(col.ljust(widths[idx]) for idx, col in enumerate(columns))
    separator = "-+-".join("-" * widths[idx] for idx in range(len(columns)))
    body = [" | ".join(item.ljust(widths[idx]) for idx, item in enumerate(row_values)) for row_values in values]
    return "\n".join([header, separator] + body)


def init_wetlab_results_table(db_path: str) -> str:
    """Initialize the wetlab_results table and indexes in a SQLite database."""
    try:
        conn, resolved_db_path = _connect_wetlab_db(db_path)
        with conn:
            _ensure_wetlab_table(conn)
        conn.close()
        return (
            "Wetlab results table initialized successfully.\n"
            f"Database: {resolved_db_path}\n"
            f"Table: {_WETLAB_TABLE_NAME}"
        )
    except Exception as e:
        return f"Error initializing wetlab results table: {str(e)}"


def upsert_wetlab_results(db_path: str, records: list[dict]) -> str:
    """Upsert multiple wetlab result rows using the table's composite unique key."""
    if not isinstance(records, list) or not records:
        return "Error: records must be a non-empty list of dictionaries."

    try:
        conn, resolved_db_path = _connect_wetlab_db(db_path)
        with conn:
            _ensure_wetlab_table(conn)

            upsert_sql = f"""
                INSERT INTO {_WETLAB_TABLE_NAME} (
                    experiment_id, sample_id, assay_name, condition, replicate,
                    measurement_value, measurement_unit, operator, instrument, measured_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(experiment_id, sample_id, assay_name, condition, replicate)
                DO UPDATE SET
                    measurement_value = excluded.measurement_value,
                    measurement_unit = excluded.measurement_unit,
                    operator = excluded.operator,
                    instrument = excluded.instrument,
                    measured_at = excluded.measured_at,
                    notes = excluded.notes,
                    updated_at = CURRENT_TIMESTAMP
            """

            success_count = 0
            error_details = []
            for idx, record in enumerate(records, start=1):
                if not isinstance(record, dict):
                    error_details.append(f"Record {idx}: not a dictionary.")
                    continue

                missing = [field for field in _WETLAB_REQUIRED_RECORD_FIELDS if field not in record]
                if missing:
                    error_details.append(f"Record {idx}: missing required fields {missing}.")
                    continue

                try:
                    values = (
                        str(record["experiment_id"]).strip(),
                        str(record["sample_id"]).strip(),
                        str(record["assay_name"]).strip(),
                        str(record["condition"]).strip(),
                        int(record["replicate"]),
                        float(record["measurement_value"]),
                        str(record["measurement_unit"]).strip(),
                        None if record.get("operator") is None else str(record.get("operator")).strip(),
                        None if record.get("instrument") is None else str(record.get("instrument")).strip(),
                        str(record["measured_at"]).strip(),
                        None if record.get("notes") is None else str(record.get("notes")),
                    )
                    conn.execute(upsert_sql, values)
                    success_count += 1
                except Exception as e:
                    error_details.append(f"Record {idx}: {str(e)}")

        conn.close()
        lines = [
            "Wetlab result UPSERT completed.",
            f"Database: {resolved_db_path}",
            f"Input records: {len(records)}",
            f"Successful upserts: {success_count}",
            f"Failed records: {len(error_details)}",
        ]
        if error_details:
            lines.append("Failure details:")
            for detail in error_details[:20]:
                lines.append(f"- {detail}")
            if len(error_details) > 20:
                lines.append(f"- ... and {len(error_details) - 20} more")
        return "\n".join(lines)
    except Exception as e:
        return f"Error upserting wetlab results: {str(e)}"


def update_wetlab_result(db_path: str, key: dict, updates: dict) -> str:
    """Update one wetlab result row selected by the composite key."""
    try:
        key_valid, key_error = _validate_wetlab_key(key)
        if not key_valid:
            return f"Error: {key_error}"
        if not isinstance(updates, dict) or not updates:
            return "Error: updates must be a non-empty dictionary."

        invalid_fields = [field for field in updates if field not in _WETLAB_UPDATABLE_FIELDS]
        if invalid_fields:
            return "Error: unsupported update fields: " + ", ".join(invalid_fields)

        conn, resolved_db_path = _connect_wetlab_db(db_path)
        with conn:
            _ensure_wetlab_table(conn)

            set_clauses = []
            values = []
            for field, value in updates.items():
                if field == "measurement_value":
                    value = float(value)
                elif field in {"measurement_unit", "operator", "instrument", "measured_at", "notes"} and value is not None:
                    value = str(value)
                set_clauses.append(f"{field} = ?")
                values.append(value)
            set_clauses.append("updated_at = ?")
            values.append(datetime.utcnow().isoformat(timespec="seconds"))

            where_clauses = [f"{field} = ?" for field in _WETLAB_KEY_FIELDS]
            key_values = [
                int(key["replicate"]) if field == "replicate" else str(key[field]).strip()
                for field in _WETLAB_KEY_FIELDS
            ]
            values.extend(key_values)

            sql = (
                f"UPDATE {_WETLAB_TABLE_NAME} "
                f"SET {', '.join(set_clauses)} "
                f"WHERE {' AND '.join(where_clauses)}"
            )
            cursor = conn.execute(sql, values)
            affected = cursor.rowcount

        conn.close()
        return (
            "Wetlab result update completed.\n"
            f"Database: {resolved_db_path}\n"
            f"Rows updated: {affected}"
        )
    except Exception as e:
        return f"Error updating wetlab result: {str(e)}"


def delete_wetlab_result(db_path: str, key: dict) -> str:
    """Delete one wetlab result row selected by the composite key."""
    try:
        key_valid, key_error = _validate_wetlab_key(key)
        if not key_valid:
            return f"Error: {key_error}"

        conn, resolved_db_path = _connect_wetlab_db(db_path)
        with conn:
            _ensure_wetlab_table(conn)
            sql = (
                f"DELETE FROM {_WETLAB_TABLE_NAME} "
                f"WHERE experiment_id = ? AND sample_id = ? AND assay_name = ? AND condition = ? AND replicate = ?"
            )
            values = (
                str(key["experiment_id"]).strip(),
                str(key["sample_id"]).strip(),
                str(key["assay_name"]).strip(),
                str(key["condition"]).strip(),
                int(key["replicate"]),
            )
            cursor = conn.execute(sql, values)
            deleted = cursor.rowcount

        conn.close()
        return (
            "Wetlab result deletion completed.\n"
            f"Database: {resolved_db_path}\n"
            f"Rows deleted: {deleted}"
        )
    except Exception as e:
        return f"Error deleting wetlab result: {str(e)}"


def query_wetlab_results(db_path: str, filters: dict | None = None, limit: int = 100) -> str:
    """Query wetlab results with whitelist-based filters and date range support."""
    try:
        if filters is None:
            filters = {}
        if not isinstance(filters, dict):
            return "Error: filters must be a dictionary."

        allowed_filter_keys = set(_WETLAB_QUERYABLE_FIELDS) | {"measured_at_from", "measured_at_to"}
        unknown_keys = [key for key in filters if key not in allowed_filter_keys]
        if unknown_keys:
            return "Error: unsupported filter fields: " + ", ".join(sorted(unknown_keys))

        limit = max(1, int(limit))
        conn, resolved_db_path = _connect_wetlab_db(db_path)
        with conn:
            _ensure_wetlab_table(conn)

            conditions = []
            values = []

            for field in _WETLAB_QUERYABLE_FIELDS:
                if field in filters and filters[field] is not None:
                    value = filters[field]
                    if field == "replicate":
                        value = int(value)
                    else:
                        value = str(value)
                    conditions.append(f"{field} = ?")
                    values.append(value)

            measured_at_from = filters.get("measured_at_from")
            measured_at_to = filters.get("measured_at_to")
            if measured_at_from is not None:
                conditions.append("measured_at >= ?")
                values.append(str(measured_at_from))
            if measured_at_to is not None:
                conditions.append("measured_at <= ?")
                values.append(str(measured_at_to))

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            count_sql = f"SELECT COUNT(*) AS total_count FROM {_WETLAB_TABLE_NAME} {where_clause}"
            total_count = conn.execute(count_sql, values).fetchone()["total_count"]

            query_sql = (
                f"SELECT * FROM {_WETLAB_TABLE_NAME} {where_clause} "
                "ORDER BY measured_at DESC, result_id DESC LIMIT ?"
            )
            query_values = values + [limit]
            rows = conn.execute(query_sql, query_values).fetchall()

        conn.close()

        lines = [
            "Wetlab result query completed.",
            f"Database: {resolved_db_path}",
            f"Total matched rows: {total_count}",
            f"Returned rows (limit={limit}): {len(rows)}",
        ]
        if not rows:
            return "\n".join(lines + ["No rows found for the provided filters."])

        columns = [
            "result_id",
            "experiment_id",
            "sample_id",
            "assay_name",
            "condition",
            "replicate",
            "measurement_value",
            "measurement_unit",
            "operator",
            "instrument",
            "measured_at",
            "notes",
            "created_at",
            "updated_at",
        ]
        table_text = _format_wetlab_rows(columns, rows)
        return "\n".join(lines + ["", table_text])
    except Exception as e:
        return f"Error querying wetlab results: {str(e)}"
