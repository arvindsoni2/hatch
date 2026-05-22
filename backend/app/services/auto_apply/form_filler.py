"""Maps candidate profile fields to detected form fields and fills them via Playwright."""
from __future__ import annotations

import logging
from typing import Any

from .form_detector import FormField

logger = logging.getLogger(__name__)


class FormFiller:
    """Maps candidate profile fields to form fields and fills them.

    Uses a keyword-based mapping from common label text / HTML name patterns
    to paths within the candidate profile JSON structure.
    """

    # ------------------------------------------------------------------ #
    # Mapping: normalised label/name keywords → dot-path into profile dict
    # ------------------------------------------------------------------ #
    # Keys are lowercase substrings that may appear in a field's label or
    # name attribute.  Checked in order — first match wins.
    # ------------------------------------------------------------------ #
    FIELD_MAPPING: dict[str, str] = {
        # Personal — name
        "first name": "personal.first_name",
        "firstname": "personal.first_name",
        "given name": "personal.first_name",
        "last name": "personal.last_name",
        "lastname": "personal.last_name",
        "surname": "personal.last_name",
        "family name": "personal.last_name",
        "full name": "personal.full_name",
        "fullname": "personal.full_name",
        # Contact
        "email": "personal.email",
        "e-mail": "personal.email",
        "phone": "personal.phone",
        "telephone": "personal.phone",
        "mobile": "personal.phone",
        "contact number": "personal.phone",
        # Location
        "city": "personal.city",
        "town": "personal.city",
        "location": "personal.city",
        "postcode": "personal.postcode",
        "post code": "personal.postcode",
        "zip": "personal.postcode",
        "address": "personal.address",
        "country": "personal.country",
        # Online profiles
        "linkedin": "personal.linkedin",
        "github": "personal.github",
        "website": "personal.website",
        "portfolio": "personal.website",
        # Application documents
        "cover letter": "documents.cover_letter_text",
        "covering letter": "documents.cover_letter_text",
        "personal statement": "documents.cover_letter_text",
        "cv": "documents.cv_path",
        "resume": "documents.cv_path",
        "curriculum vitae": "documents.cv_path",
        # Right to work / eligibility
        "right to work": "eligibility.right_to_work",
        "eligible to work": "eligibility.right_to_work",
        "work authorisation": "eligibility.right_to_work",
        "require sponsorship": "eligibility.requires_sponsorship",
        "visa": "eligibility.visa_type",
        # Employment terms
        "notice period": "employment.notice_period",
        "availability": "employment.availability",
        "start date": "employment.availability",
        "earliest start": "employment.availability",
        # Compensation
        "salary": "compensation.expected_salary",
        "desired salary": "compensation.expected_salary",
        "expected salary": "compensation.expected_salary",
        "rate": "compensation.expected_rate",
        "day rate": "compensation.expected_rate",
        "hourly rate": "compensation.expected_rate",
        "expected rate": "compensation.expected_rate",
        # Diversity / EEO (optional — skip if not in profile)
        "gender": "diversity.gender",
        "ethnicity": "diversity.ethnicity",
        "disability": "diversity.disability",
        "veteran": "diversity.veteran_status",
    }

    async def fill_form(
        self,
        page: object,
        fields: list[FormField],
        profile: dict[str, Any],
        custom_answers: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Fill each detected form field using the candidate profile.

        For fields that can be auto-mapped from the profile, the value is
        typed/selected/checked directly via Playwright. For file-type fields
        (CV / cover letter) the path is set via set_input_files. Any field
        whose label matches a key in custom_answers is filled from there.

        Args:
            page: Playwright async Page object.
            fields: List of FormField objects from FormDetector.
            profile: Candidate profile dict loaded from candidate_profile.json.
            custom_answers: dict of question text → answer string (from QuestionAnswerer).

        Returns:
            List of dicts with keys: label, value, field_type, filled (bool).
        """
        results: list[dict[str, Any]] = []

        for form_field in fields:
            label_lower = form_field.label.lower()
            name_lower = form_field.name.lower()

            # 1. Check custom_answers (Claude-generated) first
            value = self._lookup_custom(label_lower, custom_answers)

            # 2. Fall back to profile mapping
            if value is None:
                value = self._lookup_profile(label_lower, name_lower, profile)

            filled = False
            if value is not None:
                try:
                    filled = await self._fill_field(page, form_field, value)
                except Exception as exc:
                    logger.warning(
                        "Failed to fill field '%s' (%s): %s",
                        form_field.label,
                        form_field.selector,
                        exc,
                    )

            results.append(
                {
                    "label": form_field.label,
                    "value": value,
                    "field_type": form_field.field_type,
                    "filled": filled,
                }
            )

        filled_count = sum(1 for r in results if r["filled"])
        logger.info("FormFiller: filled %d / %d fields", filled_count, len(results))
        return results

    # ---------------------------------------------------------------------- #
    # Private helpers
    # ---------------------------------------------------------------------- #

    def _lookup_custom(self, label_lower: str, custom_answers: dict[str, str]) -> str | None:
        """Find a matching answer in custom_answers by substring match.

        Args:
            label_lower: Lowercase field label.
            custom_answers: Question → answer mapping.

        Returns:
            Answer string or None.
        """
        for question, answer in custom_answers.items():
            if label_lower in question.lower() or question.lower() in label_lower:
                return answer
        return None

    def _lookup_profile(
        self, label_lower: str, name_lower: str, profile: dict[str, Any]
    ) -> str | None:
        """Resolve a profile value for the field via FIELD_MAPPING.

        Checks the label first, then the HTML name attribute, against all
        mapping keys. Returns None if no match or the profile path is missing.

        Args:
            label_lower: Lowercase label text.
            name_lower: Lowercase HTML name attribute.
            profile: Candidate profile dict.

        Returns:
            Resolved string value or None.
        """
        dot_path = None
        for keyword, path in self.FIELD_MAPPING.items():
            if keyword in label_lower or keyword in name_lower:
                dot_path = path
                break

        if dot_path is None:
            return None

        return self._get_nested(profile, dot_path)

    def _get_nested(self, data: dict[str, Any], dot_path: str) -> str | None:
        """Walk a dot-separated path into a nested dict.

        Args:
            data: Nested dict.
            dot_path: E.g. "personal.first_name".

        Returns:
            String value or None if any key is missing.
        """
        parts = dot_path.split(".")
        current: Any = data
        for part in parts:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
            if current is None:
                return None
        return str(current) if current is not None else None

    async def _fill_field(self, page: object, form_field: FormField, value: str) -> bool:
        """Write a value into a single form field via the appropriate Playwright API.

        Args:
            page: Playwright Page.
            form_field: The field descriptor.
            value: String value to fill (path for file fields).

        Returns:
            True if fill succeeded, False otherwise.
        """
        selector = form_field.selector

        if form_field.field_type == "file":
            await page.set_input_files(selector, value)
            return True

        if form_field.field_type == "select":
            try:
                await page.select_option(selector, label=value)
            except Exception:
                # Fallback: try selecting by value string
                await page.select_option(selector, value=value)
            return True

        if form_field.field_type == "checkbox":
            # Interpret truthy strings as checked
            truthy = value.lower() in ("yes", "true", "1", "on")
            is_checked = await page.is_checked(selector)
            if truthy != is_checked:
                await page.click(selector)
            return True

        if form_field.field_type == "radio":
            # For radio groups use click on the specific option
            radio_selector = f"input[type='radio'][value='{value}']"
            try:
                await page.click(radio_selector)
            except Exception:
                # Fallback: try filling the enclosing form element
                await page.fill(selector, value)
            return True

        # Default: text, email, tel, textarea
        await page.fill(selector, value)
        return True
