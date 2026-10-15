"""Unit tests for CSV parsing and validation logic."""

import pytest
from app.services.csv_validator import CsvValidator, CsvValidationException


def test_valid_csv_parsing(valid_5_csv_bytes):
    validator = CsvValidator(max_rows=20)
    records = validator.validate_and_parse(valid_5_csv_bytes)

    assert len(records) == 5
    assert records[0].row == 1
    assert records[0].name == "Hospital A"
    assert records[0].address == "100 Alpha St"
    assert records[0].phone == "555-0001"

    # Row 3 has empty phone
    assert records[2].row == 3
    assert records[2].name == "Hospital C"
    assert records[2].address == "300 Gamma St"
    assert records[2].phone is None


def test_max_limit_20_allowed(valid_20_csv_bytes):
    validator = CsvValidator(max_rows=20)
    records = validator.validate_and_parse(valid_20_csv_bytes)
    assert len(records) == 20


def test_exceeding_max_rows_raises_validation_exception(exceed_limit_csv_bytes):
    validator = CsvValidator(max_rows=20)
    with pytest.raises(CsvValidationException) as exc_info:
        validator.validate_and_parse(exceed_limit_csv_bytes)

    assert "exceeds the maximum allowed limit of 20 hospitals" in str(exc_info.value)
    # Verify no payload too large, it's a standard validation error
    diag = validator.check_csv(exceed_limit_csv_bytes)
    assert not diag.valid
    assert diag.total_rows == 25
    assert any("exceeds the maximum allowed limit" in err.message for err in diag.errors)


def test_missing_required_headers():
    csv_bytes = b"title,location\nSt. Jude,Memphis TN\n"
    validator = CsvValidator(max_rows=20)

    with pytest.raises(CsvValidationException) as exc_info:
        validator.validate_and_parse(csv_bytes)

    assert "Missing required CSV column" in str(exc_info.value)


def test_empty_csv():
    validator = CsvValidator(max_rows=20)
    with pytest.raises(CsvValidationException) as exc_info:
        validator.validate_and_parse(b"")

    assert "CSV file is empty" in str(exc_info.value)


def test_empty_rows_and_whitespace():
    csv_bytes = (
        b"name,address,phone\n"
        b"\n"
        b"  Mayo Clinic  ,   200 1st St SW   ,  507-284-2511  \n"
        b"\n"
    )
    validator = CsvValidator(max_rows=20)
    records = validator.validate_and_parse(csv_bytes)
    assert len(records) == 1
    assert records[0].name == "Mayo Clinic"
    assert records[0].address == "200 1st St SW"
    assert records[0].phone == "507-284-2511"


def test_utf8_bom_handling():
    csv_bytes = b"\xef\xbb\xbfname,address,phone\nHospital BOM,123 Main St,555-1111\n"
    validator = CsvValidator(max_rows=20)
    records = validator.validate_and_parse(csv_bytes)
    assert len(records) == 1
    assert records[0].name == "Hospital BOM"


def test_case_insensitive_headers():
    csv_bytes = b"NAME,ADDRESS,PHONE\nHospital Caps,123 Main St,555-2222\n"
    validator = CsvValidator(max_rows=20)
    records = validator.validate_and_parse(csv_bytes)
    assert len(records) == 1
    assert records[0].name == "Hospital Caps"
