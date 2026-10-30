"""Receipt extraction: drafts never write application data or files."""
import re
import subprocess
import warnings
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.expenses.services.money import paise_to_rupees, rupees_to_paise


def receipt_draft(text):
    items, total = [], None
    for line in text.splitlines()[:1000]:
        line = line.strip()
        # Printed table borders and their OCR equivalents follow the last column.
        table = re.match(
            r"^(.+?)\s+(\d+)\s+(\d[\d,]*(?:\.\d{1,2})?)\s+"
            r"(\d[\d,]*(?:\.\d{1,2})?)(?:\s+[^\d]*)?$", line)
        if table:
            name, _quantity, _rate, value = table.groups()
            name = re.sub(r"^[^\w]+", "", name)
            name = re.sub(r"^[A-Za-z]=\s*[^\w]*", "", name)
            name = re.sub(r"^(?:\d+|[LlI])[.]\s*", "", name)
            # Preserve the printed line total: it already includes the quantity.
            line = f"{name} {value}"
        match = re.match(
            r"^(.+?)\s+(?:[:=]\s*)?(?:INR\s*|Rs\.?\s*|₹\s*)?"
            r"(-?(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{1,2})?)"
            r"\s*(?:INR|Rs\.?|₹)?\s*[^\w\d]*$", line, re.I)
        if not match:
            continue
        name, value = match.groups()
        name = re.sub(r"^[^\w]+", "", name)
        if not any(character.isalpha() for character in name):
            continue
        try:
            price = rupees_to_paise(value.replace(",", ""))
        except ValueError:
            continue
        label = name.lower().strip(" :.-")
        if re.match(r"^(?:contact|phone|tel|mobile|gstin|gst\s*(?:no|number)|invoice|bill\s*(?:no|number)|receipt\s*(?:no|number)|date|time|table|order\s*(?:no|number)|fssai|pin\s*code|total\s+(?:qty|quantity|items))\b", label):
            continue
        if re.match(r"^(?:sub\s*total|cash|change|balance|round\s*off|rounding)\b", label):
            continue
        if ("total" in label and not any(word in label for word in ["tax", "gst", "vat", "service", "tip", "discount"])) or label in {"amount due", "net amount"}:
            total = paise_to_rupees(price)
            continue
        kind = "item"
        for key, words in [("discount", ["discount", "coupon"]), ("tax", ["tax", "gst", "vat"]), ("service", ["service"]), ("tip", ["tip", "gratuity"])]:
            if any(word in label for word in words):
                kind = key
                break
        price = -abs(price) if kind == "discount" else price
        if price == 0 or kind != "discount" and price < 0:
            continue
        items.append({"kind": kind, "name": name[:120], "amount": paise_to_rupees(price), "payees": []})
        if len(items) >= 100:
            break
    try:
        amount = total or paise_to_rupees(sum(rupees_to_paise(row["amount"]) for row in items))
    except ValueError:
        amount = ""
    notices = ["Check every item, charge and total against your receipt. OCR may miss or misread lines."]
    if not any(row["kind"] == "item" for row in items):
        notices.insert(0, "No receipt items were recognized. Expand Extracted text to see what was read; try a clearer crop or add lines manually.")
    elif total is not None and sum(rupees_to_paise(row["amount"]) for row in items) != rupees_to_paise(total):
        notices.insert(0, "The extracted lines do not match the printed total. Some lines may be missing or incorrect.")
    if not text.strip():
        notices.insert(0, "No readable text was found in this image.")
    return {"items": items, "amount": amount, "warnings": notices, "text": text[:20000]}


def parse_receipt(upload):
    if upload is None:
        raise ValidationError("Choose a JPEG, PNG or WebP receipt image.")
    data = upload.read(settings.RECEIPT_MAX_BYTES + 1)
    if not data or len(data) > settings.RECEIPT_MAX_BYTES:
        raise ValidationError("Receipt images must be between 1 byte and 8 MiB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"} or original.width * original.height > settings.RECEIPT_MAX_PIXELS:
                    raise ValidationError("Use a JPEG, PNG or WebP image of at most 20 megapixels.")
                image = ImageOps.grayscale(ImageOps.exif_transpose(original))
                image.thumbnail((2400, 3200))
                image = ImageOps.autocontrast(image)
                buffer = BytesIO()
                image.save(buffer, format="PNG")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ValidationError("The receipt image is invalid or too large.") from None
    try:
        result = subprocess.run(["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "6"],
                                input=buffer.getvalue(), capture_output=True, timeout=25, check=True)
    except (OSError, subprocess.SubprocessError):
        raise ValidationError("Receipt recognition is unavailable. Try again or enter the expense manually.") from None
    return receipt_draft(result.stdout.decode("utf-8", errors="replace"))
