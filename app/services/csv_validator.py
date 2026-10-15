"""CSV parser and schema validator for hospital records."""

import csv
import io
from typing import List, Optional, Tuple

from app.models.hospital import HospitalRecord
from app.models.batch import ValidationErrorItem, CsvValidationResponse


class CsvValidationException(Exception):
    """Raised when CSV validation fails before batch processing."""

    def __init__(self, message: str, errors: Optional[List[ValidationErrorItem]] = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


class CsvValidator:
    """Validates and parses hospital records from CSV uploads."""

    REQUIRED_COLUMNS = {"name", "address"}
    ALLOWED_COLUMNS = {"name", "address", "phone"}

    def __init__(self, max_rows: int = 20):
        self.max_rows = max_rows

    def validate_and_parse(self, content_bytes: bytes) -> List[HospitalRecord]:
        """Parse raw CSV bytes and return a list of validated HospitalRecords.

        Raises:
            CsvValidationException: If headers are missing, rows exceed max_rows,
                                   or required row values are missing.
        """
        response = self.check_csv(content_bytes)
        if not response.valid:
            error_summary = "; ".join(e.message for e in response.errors[:3])
            if len(response.errors) > 3:
                error_summary += f" (and {len(response.errors) - 3} more errors)"
            raise CsvValidationException(
                message=f"CSV validation failed: {error_summary}",
                errors=response.errors,
            )

        # Convert valid rows to HospitalRecord objects
        records, _ = self._extract_records(content_bytes)
        return records

    def check_csv(self, content_bytes: bytes) -> CsvValidationResponse:
        """Run complete diagnostic validation on CSV without throwing exceptions."""
        if not content_bytes or len(content_bytes.strip()) == 0:
            return CsvValidationResponse(
                valid=False,
                total_rows=0,
                errors=[ValidationErrorItem(row=None, column=None, message="CSV file is empty.")],
                message="CSV file is empty.",
            )

        # Handle UTF-8 and UTF-8-BOM
        try:
            text = content_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content_bytes.decode("latin-1")
            except Exception as exc:
                return CsvValidationResponse(
                    valid=False,
                    total_rows=0,
                    errors=[ValidationErrorItem(row=None, column=None, message=f"Failed to decode file encoding: {str(exc)}")],
                    message="Invalid file encoding. Please upload a UTF-8 encoded CSV.",
                )

        stream = io.StringIO(text)
        reader = csv.reader(stream)

        # Read Header
        try:
            header_row = next(reader)
        except StopIteration:
            return CsvValidationResponse(
                valid=False,
                total_rows=0,
                errors=[ValidationErrorItem(row=None, column=None, message="CSV file contains no data or header row.")],
                message="CSV file is empty.",
            )

        normalized_headers = [col.strip().lower() for col in header_row if col is not None]
        errors: List[ValidationErrorItem] = []

        # Validate Header Columns
        missing_columns = self.REQUIRED_COLUMNS - set(normalized_headers)
        if missing_columns:
            errors.append(
                ValidationErrorItem(
                    row=1,
                    column=None,
                    message=f"Missing required CSV column(s): {', '.join(sorted(missing_columns))}. Header must include name,address,phone.",
                )
            )

        # Create header index mapping
        header_map = {name: idx for idx, name in enumerate(normalized_headers)}

        valid_records: List[HospitalRecord] = []
        row_idx = 1  # 1-indexed, starting after header

        for raw_row in reader:
            # Skip empty lines
            if not raw_row or all(c.strip() == "" for c in raw_row):
                continue

            row_idx += 1
            has_row_error = False

            # Extract Name
            name_val = ""
            if "name" in header_map and header_map["name"] < len(raw_row):
                name_val = raw_row[header_map["name"]].strip()
            if not name_val:
                errors.append(
                    ValidationErrorItem(
                        row=row_idx,
                        column="name",
                        message=f"Row {row_idx}: 'name' is required and cannot be empty.",
                    )
                )
                has_row_error = True

            # Extract Address
            address_val = ""
            if "address" in header_map and header_map["address"] < len(raw_row):
                address_val = raw_row[header_map["address"]].strip()
            if not address_val:
                errors.append(
                    ValidationErrorItem(
                        row=row_idx,
                        column="address",
                        message=f"Row {row_idx}: 'address' is required and cannot be empty.",
                    )
                )
                has_row_error = True

            # Extract Phone (Optional)
            phone_val: Optional[str] = None
            if "phone" in header_map and header_map["phone"] < len(raw_row):
                p = raw_row[header_map["phone"]].strip()
                if p:
                    phone_val = p

            if not has_row_error:
                valid_records.append(
                    HospitalRecord(
                        row=row_idx - 1,  # 1-indexed record number relative to data rows
                        name=name_val,
                        address=address_val,
                        phone=phone_val,
                    )
                )

        total_data_rows = row_idx - 1
        if total_data_rows == 0 and not errors:
            errors.append(
                ValidationErrorItem(
                    row=None,
                    column=None,
                    message="CSV contains headers but no hospital records.",
                )
            )

        # Check maximum row constraint
        if total_data_rows > self.max_rows:
            errors.append(
                ValidationErrorItem(
                    row=None,
                    column=None,
                    message=(
                        f"CSV contains {total_data_rows} hospital rows, which exceeds the "
                        f"maximum allowed limit of {self.max_rows} hospitals per batch."
                    ),
                )
            )

        is_valid = len(errors) == 0
        status_msg = (
            f"Validation successful. {len(valid_records)} valid hospital record(s) ready for processing."
            if is_valid
            else f"Validation failed with {len(errors)} error(s)."
        )

        return CsvValidationResponse(
            valid=is_valid,
            total_rows=total_data_rows,
            errors=errors,
            message=status_msg,
        )

    def _extract_records(self, content_bytes: bytes) -> Tuple[List[HospitalRecord], int]:
        """Extract valid records assuming validation has passed."""
        text = content_bytes.decode("utf-8-sig", errors="replace")
        stream = io.StringIO(text)
        reader = csv.reader(stream)
        header_row = next(reader)
        normalized_headers = [col.strip().lower() for col in header_row]
        header_map = {name: idx for idx, name in enumerate(normalized_headers)}

        records = []
        rec_num = 1
        for raw_row in reader:
            if not raw_row or all(c.strip() == "" for c in raw_row):
                continue
            name_val = raw_row[header_map["name"]].strip()
            address_val = raw_row[header_map["address"]].strip()
            phone_val = None
            if "phone" in header_map and header_map["phone"] < len(raw_row):
                p = raw_row[header_map["phone"]].strip()
                if p:
                    phone_val = p
            records.append(
                HospitalRecord(
                    row=rec_num,
                    name=name_val,
                    address=address_val,
                    phone=phone_val,
                )
            )
            rec_num += 1

        return records, len(records)
