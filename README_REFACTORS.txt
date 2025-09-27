PetWellnessApp – Refactored Bundle (prioritized modules)
--------------------------------------------------------
Highlights (non-breaking):
- Standardized context-managed DB usage in data helpers
- Defensive updates (ignore empty field dicts)
- Added type hints & docstrings in core helpers
- Fixed duplicate function in reports.py (_invoice_date_expr)
- Removed duplicate QMessageBox in reports_analytics.py
- Minor UX copy fixes (Inventory adjust qty prompt)
- Cleaned mojibake apostrophes in consent_dialog.py

Notes:
- Heavier UI modules (scheduling, consent forms, analytics) were left logically unchanged to avoid regressions.
- If you want deeper consolidation (e.g., shared clinic constants, centralized export styling), say the word.
