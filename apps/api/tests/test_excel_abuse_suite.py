import pytest
import pandas as pd
from io import BytesIO
from routers.onboarding import validate_bulk_frame, BULK_TEMPLATE_COLUMNS
from services.bulk_validation import enrich_failed_rows, make_report

def create_mock_frame(columns, data):
    return pd.DataFrame(data, columns=columns)

@pytest.mark.parametrize("test_case, columns, data, expected_error_kw", [
    # 1. Renamed columns (should be caught as missing required columns)
    ("renamed_columns", ["row_type", "WrongName", "mobile_number", "daily_wages", "duty_hours", "prev"], 
     [[ "ACTUAL", "John", "123", 400, 8, 0]], "Missing required columns"),
    
    # 2. Extra columns (should be ignored, valid rows produced)
    ("extra_columns", ["row_type", "name", "mobile_number", "daily_wages", "duty_hours", "previous_attendance_details", "ExtraCol"], 
     [[ "ACTUAL", "John", "123", 400, 8, 0, "SomeValue"]], None),
    
    # 3. Missing columns
    ("missing_columns", ["row_type", "name"], 
     [[ "ACTUAL", "John"]], "Missing required columns"),
    
    # 4. Empty rows (non-ACTUAL rows should be filtered)
    ("empty_rows", ["row_type", "name", "mobile_number", "daily_wages", "duty_hours", "previous_attendance_details"], 
     [[ "ACTUAL", "John", "123", 400, 8, 0], [None, None, None, None, None, None]], None),
    
    # 5. Formula-like cells (string that looks like formula)
    ("formula_cells", ["row_type", "name", "mobile_number", "daily_wages", "duty_hours", "previous_attendance_details"], 
     [[ "ACTUAL", "John", "123", "=SUM(A1:A2)", 8, 0]], "type"),
    
    # 6. Duplicate rows (validation should pass, deduplication happens later)
    ("duplicate_rows", ["row_type", "name", "mobile_number", "daily_wages", "duty_hours", "previous_attendance_details"], 
     [[ "ACTUAL", "John", "123", 400, 8, 0], [ "ACTUAL", "John", "123", 400, 8, 0]], None),
])
def test_onboarding_abuse(test_case, columns, data, expected_error_kw):
    frame = create_mock_frame(columns, data)
    # Testing 'worker' sub_tab_type
    valid_rows, failed_rows = validate_bulk_frame(frame, "worker", sheet_name="Workers")
    
    # Convert raw failed rows to ValidationIssues
    issues = enrich_failed_rows(failed_rows, entity_type="worker")
    report = make_report(issues, len(valid_rows), len(data))
    
    if expected_error_kw:
        assert report.has_fatal, f"Test {test_case} should have fatal errors but didn't"
        found = any(expected_error_kw.lower() in issue.error.lower() for issue in report.fatal_issues)
        assert found, f"Test {test_case} missing expected error keyword {expected_error_kw}. Issues: {report.fatal_issues}"
    else:
        # For cases that should pass (like extra columns or empty rows)
        # Valid rows should be produced for the 'ACTUAL' lines
        assert len(valid_rows) > 0, f"Test {test_case} should have produced valid rows"

if __name__ == "__main__":
    pytest.main([__file__])
