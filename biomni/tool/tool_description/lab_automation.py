description = [
    {
        "description": "Test a PyLabRobot script based on the script content.",
        "name": "test_pylabrobot_script",
        "optional_parameters": [
            {
                "default": False,
                "description": "If True, enable tracking of the script execution",
                "name": "enable_tracking",
                "type": "bool",
            },
            {
                "default": 60,
                "description": "Timeout in seconds for the script execution",
                "name": "timeout_seconds",
                "type": "int",
            },
            {
                "default": False,
                "description": "If True, save the test results as a .json file",
                "name": "save_test_report",
                "type": "bool",
            },
            {
                "default": None,
                "description": "Directory to save the test results. If provided, the test results will be saved as a .json file in this directory",
                "name": "test_report_dir",
                "type": "str",
            },
        ],
        "required_parameters": [
            {
                "default": None,
                "description": "Script content to test",
                "name": "script_input",
                "type": "str",
            }
        ],
    },
    {
        "description": "Get the documentation for the liquid handling section of the PyLabRobot tutorial.",
        "name": "get_pylabrobot_documentation_liquid",
        "optional_parameters": [],
        "required_parameters": [],
    },
    {
        "description": "Get the documentation for the material handling section of the PyLabRobot tutorial.",
        "name": "get_pylabrobot_documentation_material",
        "optional_parameters": [],
        "required_parameters": [],
    },
    {
        "description": "Initialize the wetlab_results SQLite table and required indexes.",
        "name": "init_wetlab_results_table",
        "optional_parameters": [],
        "required_parameters": [
            {
                "default": None,
                "description": "Path to the SQLite database file",
                "name": "db_path",
                "type": "str",
            }
        ],
    },
    {
        "description": "Batch UPSERT wetlab result rows into wetlab_results using the composite key.",
        "name": "upsert_wetlab_results",
        "optional_parameters": [],
        "required_parameters": [
            {
                "default": None,
                "description": "Path to the SQLite database file",
                "name": "db_path",
                "type": "str",
            },
            {
                "default": None,
                "description": "List of record dictionaries to insert/update",
                "name": "records",
                "type": "list[dict]",
            },
        ],
    },
    {
        "description": "Update one wetlab result row identified by the composite key.",
        "name": "update_wetlab_result",
        "optional_parameters": [],
        "required_parameters": [
            {
                "default": None,
                "description": "Path to the SQLite database file",
                "name": "db_path",
                "type": "str",
            },
            {
                "default": None,
                "description": "Composite key dictionary with experiment_id/sample_id/assay_name/condition/replicate",
                "name": "key",
                "type": "dict",
            },
            {
                "default": None,
                "description": "Field-value dictionary to update (whitelisted fields only)",
                "name": "updates",
                "type": "dict",
            },
        ],
    },
    {
        "description": "Delete one wetlab result row identified by the composite key.",
        "name": "delete_wetlab_result",
        "optional_parameters": [],
        "required_parameters": [
            {
                "default": None,
                "description": "Path to the SQLite database file",
                "name": "db_path",
                "type": "str",
            },
            {
                "default": None,
                "description": "Composite key dictionary with experiment_id/sample_id/assay_name/condition/replicate",
                "name": "key",
                "type": "dict",
            },
        ],
    },
    {
        "description": "Query wetlab result rows with field filters and measured_at date range filters.",
        "name": "query_wetlab_results",
        "optional_parameters": [
            {
                "default": 100,
                "description": "Maximum rows to return",
                "name": "limit",
                "type": "int",
            },
        ],
        "required_parameters": [
            {
                "default": None,
                "description": "Path to the SQLite database file",
                "name": "db_path",
                "type": "str",
            },
            {
                "default": None,
                "description": "Filter dictionary (supports measured_at_from/measured_at_to)",
                "name": "filters",
                "type": "dict",
            },
        ],
    },
]
