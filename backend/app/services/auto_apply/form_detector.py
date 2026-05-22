"""Form field detection using Playwright."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Mapping from input type attribute to our normalised field_type
_INPUT_TYPE_MAP: dict[str, str] = {
    "text": "text",
    "email": "email",
    "tel": "tel",
    "number": "text",
    "url": "text",
    "password": "text",
    "hidden": "hidden",
    "file": "file",
    "checkbox": "checkbox",
    "radio": "radio",
    "submit": "submit",
    "button": "submit",
}


@dataclass
class FormField:
    """Represents a single detected form field.

    Attributes:
        field_type: Normalised type: 'text'|'email'|'tel'|'select'|'checkbox'|'file'|'textarea'.
        label: Human-readable label text extracted from the page.
        name: The HTML name or id attribute value.
        required: Whether the field is marked as required.
        options: List of option values/text for select fields.
        selector: CSS selector that uniquely locates this field on the page.
    """

    field_type: str
    label: str
    name: str
    required: bool = False
    options: list[str] = field(default_factory=list)
    selector: str = ""


class FormDetector:
    """Detects and describes all interactive form fields on the current page."""

    async def detect_fields(self, page: object) -> list[FormField]:
        """Scan the current Playwright page for form fields.

        Queries all input, select, and textarea elements. For each element,
        attempts to resolve an associated label via the for/id relationship,
        aria-label, placeholder, or nearby text. Skips submit/button/hidden
        input types from the returned list (they are not user-fillable).

        Args:
            page: A Playwright async Page object.

        Returns:
            List of FormField describing each fillable field found.
        """
        fields: list[FormField] = []

        # ------------------------------------------------------------------ #
        # 1. textarea elements
        # ------------------------------------------------------------------ #
        textarea_handles = await page.query_selector_all("textarea")
        for idx, handle in enumerate(textarea_handles):
            name = (await handle.get_attribute("name") or
                    await handle.get_attribute("id") or
                    f"textarea_{idx}")
            selector = f"textarea[name='{name}']" if await handle.get_attribute("name") else (
                f"textarea[id='{await handle.get_attribute('id')}']"
                if await handle.get_attribute("id")
                else f"textarea:nth-of-type({idx + 1})"
            )
            label = await self._resolve_label(page, handle, name)
            required = await handle.get_attribute("required") is not None
            fields.append(
                FormField(
                    field_type="textarea",
                    label=label,
                    name=name,
                    required=required,
                    selector=selector,
                )
            )

        # ------------------------------------------------------------------ #
        # 2. select elements
        # ------------------------------------------------------------------ #
        select_handles = await page.query_selector_all("select")
        for idx, handle in enumerate(select_handles):
            name = (await handle.get_attribute("name") or
                    await handle.get_attribute("id") or
                    f"select_{idx}")
            selector = f"select[name='{name}']" if await handle.get_attribute("name") else (
                f"select[id='{await handle.get_attribute('id')}']"
                if await handle.get_attribute("id")
                else f"select:nth-of-type({idx + 1})"
            )
            label = await self._resolve_label(page, handle, name)
            required = await handle.get_attribute("required") is not None

            # Collect option texts
            option_handles = await handle.query_selector_all("option")
            options: list[str] = []
            for opt in option_handles:
                text = (await opt.inner_text()).strip()
                if text:
                    options.append(text)

            fields.append(
                FormField(
                    field_type="select",
                    label=label,
                    name=name,
                    required=required,
                    options=options,
                    selector=selector,
                )
            )

        # ------------------------------------------------------------------ #
        # 3. input elements
        # ------------------------------------------------------------------ #
        input_handles = await page.query_selector_all("input")
        for idx, handle in enumerate(input_handles):
            raw_type = (await handle.get_attribute("type") or "text").lower()

            # Skip non-fillable types
            if raw_type in ("submit", "button", "image", "reset"):
                continue

            field_type = _INPUT_TYPE_MAP.get(raw_type, "text")

            # Skip hidden fields — they carry no user value
            if field_type == "hidden":
                continue

            name_attr = await handle.get_attribute("name") or ""
            id_attr = await handle.get_attribute("id") or ""
            name = name_attr or id_attr or f"input_{idx}"

            # Build a reasonably unique selector
            if name_attr:
                selector = f"input[name='{name_attr}']"
            elif id_attr:
                selector = f"input[id='{id_attr}']"
            else:
                selector = f"input[type='{raw_type}']:nth-of-type({idx + 1})"

            label = await self._resolve_label(page, handle, name)
            required = await handle.get_attribute("required") is not None

            fields.append(
                FormField(
                    field_type=field_type,
                    label=label,
                    name=name,
                    required=required,
                    selector=selector,
                )
            )

        logger.debug("FormDetector found %d fillable fields", len(fields))
        return fields

    # ---------------------------------------------------------------------- #
    # Private helpers
    # ---------------------------------------------------------------------- #

    async def _resolve_label(self, page: object, handle: object, fallback: str) -> str:
        """Attempt to find the human-readable label for a form element.

        Resolution order:
        1. <label for="..."> matching the element's id attribute.
        2. aria-label attribute on the element.
        3. placeholder attribute on the element.
        4. parent <label> text content.
        5. fallback (HTML name/id).

        Args:
            page: Playwright Page.
            handle: Playwright ElementHandle for the field.
            fallback: String to return when no label can be resolved.

        Returns:
            Label string.
        """
        try:
            id_attr = await handle.get_attribute("id")
            if id_attr:
                label_el = await page.query_selector(f"label[for='{id_attr}']")
                if label_el:
                    text = (await label_el.inner_text()).strip()
                    if text:
                        return text

            aria = await handle.get_attribute("aria-label")
            if aria and aria.strip():
                return aria.strip()

            placeholder = await handle.get_attribute("placeholder")
            if placeholder and placeholder.strip():
                return placeholder.strip()

            # Walk up to find a wrapping <label>
            parent = await handle.evaluate_handle("el => el.closest('label')")
            if parent:
                text = await parent.evaluate("el => el ? el.innerText : ''")
                if text and text.strip():
                    return text.strip()
        except Exception as exc:
            logger.debug("Label resolution failed for %s: %s", fallback, exc)

        return fallback
