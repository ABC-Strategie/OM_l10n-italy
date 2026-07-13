{
    "name": "ABC Date Range Fix",
    "summary": "Fix date_range imports for Odoo 19",
    "version": "19.0.1.0.0",
    "author": "Antigravity",
    "depends": ["date_range"],
    "assets": {
        "web.assets_backend": [
            ("remove", "date_range/static/src/js/condition_tree.esm.js"),
            ("remove", "date_range/static/src/js/domain_selector.esm.js"),
            "abc_date_range_fix/static/src/js/condition_tree.esm.js",
            "abc_date_range_fix/static/src/js/domain_selector.esm.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
