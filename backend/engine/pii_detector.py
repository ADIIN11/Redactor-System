import re
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from backend.engine.validators import (
    verify_ifsc_structure,
    verify_luhn,
    verify_pan_structure,
    verify_verhoeff,
)
from backend.models.schemas import DetectedEntity

_BANK_CONTEXT_KEYWORDS: Tuple[str, ...] = (
    "account",
    "a/c",
    "acct",
    "iban",
    "saving",
    "savings",
    "current",
    "beneficiary",
    "ifsc",
    "bank",
    "neft",
    "rtgs",
    "branch",
)


@dataclass
class Pattern:
    name: str
    regex: str
    score: float


@dataclass
class RecognizerResult:
    entity_type: str
    start: int
    end: int
    score: float


class PatternRecognizer:
    """
    Self-contained, zero-dependency Presidio-compatible PatternRecognizer.
    Runs compiled regex patterns, optional mathematical checksum validation,
    and 60-character context-window confidence boosting.
    """

    def __init__(
        self,
        supported_entity: str,
        patterns: Sequence[Pattern],
        context: Optional[Sequence[str]] = None,
        supported_language: str = "en",
    ) -> None:
        self.supported_entity = supported_entity
        self.supported_entities = [supported_entity]
        self.patterns = list(patterns)
        self.context = [c.lower() for c in (context or [])]
        self.supported_language = supported_language
        self._compiled: List[Tuple[Pattern, re.Pattern[str]]] = [
            (p, re.compile(p.regex)) for p in self.patterns
        ]

    def validate_result(self, pattern_text: str) -> Optional[bool]:
        return None

    def analyze(
        self,
        text: str,
        entities: Optional[Sequence[str]] = None,
        nlp_artifacts: object = None,
    ) -> List[RecognizerResult]:
        if entities and self.supported_entity not in entities:
            return []

        results: List[RecognizerResult] = []
        for pattern_def, compiled_re in self._compiled:
            for match in compiled_re.finditer(text):
                start, end = match.span()
                matched_str = match.group(0)
                if not matched_str.strip():
                    continue

                score = pattern_def.score
                validation = self.validate_result(matched_str)
                if validation is True:
                    score = max(score, 0.95)
                elif validation is False:
                    score = 0.05

                if score >= 0.50:
                    results.append(
                        RecognizerResult(
                            entity_type=self.supported_entity,
                            start=start,
                            end=end,
                            score=score,
                        )
                    )
        return results


class IndianAadhaarRecognizer(PatternRecognizer):
    """
    Detects 12-digit Indian national IDs and enforces Verhoeff mathematical
    checksum validation to eliminate false positives on arbitrary 12-digit numbers.
    """

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="aadhaar_12_digit_pattern",
                regex=r"\b[2-9]\d{3}[\s\-]?\d{4}[\s\-]?\d{4}\b",
                score=0.65,
            )
        ]
        super().__init__(
            supported_entity="IN_AADHAAR",
            patterns=patterns,
            context=[
                "uidai",
                "vid",
                "government of india",
                "dob",
                "male",
                "female",
                "enrollment",
                "aadhaar",
                "aadhar",
            ],
        )

    def validate_result(self, pattern_text: str) -> Optional[bool]:
        return verify_verhoeff(pattern_text)


class IndianPanRecognizer(PatternRecognizer):
    """
    Detects 10-character Indian PAN identifiers with entity category verification.
    """

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="pan_card_pattern",
                regex=r"\b[A-Z]{3}[ABCFGHLJPTF][A-Z][0-9]{4}[A-Z]\b",
                score=0.92,
            )
        ]
        super().__init__(
            supported_entity="IN_PAN",
            patterns=patterns,
            context=["pan", "permanent account number", "income tax", "assessee", "tax"],
        )

    def validate_result(self, pattern_text: str) -> Optional[bool]:
        return verify_pan_structure(pattern_text)


class CreditCardLuhnRecognizer(PatternRecognizer):
    """
    Detects 13-19 digit payment cards (Visa, Mastercard, RuPay, Amex)
    and validates via the Luhn mod-10 checksum.
    """

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="credit_card_13_19_digits",
                regex=r"\b(?:\d[\s\-]?){12,18}\d\b",
                score=0.65,
            )
        ]
        super().__init__(
            supported_entity="CREDIT_CARD",
            patterns=patterns,
            context=["card", "visa", "mastercard", "rupay", "amex", "cvv", "expiry", "credit", "debit"],
        )

    def validate_result(self, pattern_text: str) -> Optional[bool]:
        return verify_luhn(pattern_text)


class IndianIfscRecognizer(PatternRecognizer):
    """
    Detects 11-character Indian bank IFSC codes.
    """

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="ifsc_code_pattern",
                regex=r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
                score=0.92,
            )
        ]
        super().__init__(
            supported_entity="IN_IFSC",
            patterns=patterns,
            context=["ifsc", "branch", "neft", "rtgs", "imps", "bank"],
        )

    def validate_result(self, pattern_text: str) -> Optional[bool]:
        return verify_ifsc_structure(pattern_text)


class IndianPhoneRecognizer(PatternRecognizer):
    """
    Detects Indian 10-digit mobile numbers (+91 / 6-9 start) and STD landlines.
    """

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="in_mobile_number",
                regex=r"(?:\+91[\-\s]?)?\b[6-9]\d{9}\b",
                score=0.88,
            ),
            Pattern(
                name="in_std_landline",
                regex=r"\b0\d{2,4}[\-\s]?\d{6,8}\b",
                score=0.78,
            ),
        ]
        super().__init__(
            supported_entity="PHONE_NUMBER",
            patterns=patterns,
            context=["phone", "mobile", "contact", "tel", "call", "cell", "whatsapp"],
        )


class EmailAddressRecognizer(PatternRecognizer):
    """
    Detects RFC-5322 compliant email addresses.
    """

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="rfc5322_email",
                regex=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
                score=0.96,
            )
        ]
        super().__init__(
            supported_entity="EMAIL_ADDRESS",
            patterns=patterns,
            context=["email", "e-mail", "mail", "contact"],
        )


class ContextualPersonLocationRecognizer(PatternRecognizer):
    """
    Detects Person names using honorifics and structured form field labels.
    """

    def __init__(self) -> None:
        person_patterns = [
            Pattern(
                name="honorific_person",
                regex=r"\b(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?|Shri|Smt\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b",
                score=0.85,
            )
        ]
        super().__init__(
            supported_entity="PERSON",
            patterns=person_patterns,
            context=["name", "applicant", "beneficiary", "customer", "client", "holder"],
        )


class DateOfBirthRecognizer(PatternRecognizer):
    """
    Detects dd/mm/yyyy style dates, but only keeps them when a date-of-birth cue
    is within the 60-character context window.

    A bare date scores 0.50, which HybridPIIDetector.analyze_line drops (< 0.55).
    The +0.08 context boost lifts it to 0.58, so invoice or issue dates are left alone
    while 'DOB : 11/04/2005' style lines are caught.

    Digit boundaries use look-arounds instead of \\b: OCR frequently glues garbled
    regional-script characters onto the date, and \\b does not fire next to them.
    """

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="date_dd_mm_yyyy",
                regex=(
                    r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])[/\-.]"
                    r"(?:0?[1-9]|1[0-2])[/\-.](?:19|20)\d{2}(?!\d)"
                ),
                score=0.50,
            )
        ]
        super().__init__(
            supported_entity="DATE_OF_BIRTH",
            patterns=patterns,
            context=["dob", "d.o.b", "date of birth", "birth", "born"],
        )


class HybridPIIDetector:
    """
    Executes PatternRecognizers + Mathematical Checksum Validators
    + Context-Window Score Boosting for high-precision PII detection.
    """

    ENTITY_CATEGORY_MAP: Dict[str, str] = {
        "IN_AADHAAR": "GOV_ID",
        "IN_PAN": "GOV_ID",
        "CREDIT_CARD": "FINANCIAL",
        "IN_IFSC": "FINANCIAL",
        "BANK_ACCOUNT": "FINANCIAL",
        "PHONE_NUMBER": "CONTACT_PII",
        "EMAIL_ADDRESS": "CONTACT_PII",
        "PERSON": "CONTACT_PII",
        "LOCATION": "CONTACT_PII",
        "DATE_OF_BIRTH": "CONTACT_PII",
    }

    ENTITY_VALIDATOR_LABEL: Dict[str, str] = {
        "IN_AADHAAR": "Verhoeff Checksum Verified",
        "IN_PAN": "Tax Entity Structure Verified",
        "CREDIT_CARD": "Luhn Mod-10 Verified",
        "IN_IFSC": "IFSC 11-Char Format Verified",
        "BANK_ACCOUNT": "60-Char Banking Context Verified",
        "PHONE_NUMBER": "Indian Telecom Regex Verified",
        "EMAIL_ADDRESS": "RFC-5322 Syntax Verified",
        "PERSON": "Contextual Entity Extraction",
        "LOCATION": "Contextual Entity Extraction",
        "DATE_OF_BIRTH": "DOB Context Verified",
    }

    ENTITY_PRIORITY: Dict[str, int] = {
        "IN_AADHAAR": 100,
        "IN_PAN": 95,
        "CREDIT_CARD": 90,
        "IN_IFSC": 88,
        "EMAIL_ADDRESS": 85,
        "BANK_ACCOUNT": 80,
        "PHONE_NUMBER": 75,
        "DATE_OF_BIRTH": 70,
        "PERSON": 50,
        "LOCATION": 45,
    }

    def __init__(self) -> None:
        self.recognizers: List[PatternRecognizer] = [
            IndianAadhaarRecognizer(),
            IndianPanRecognizer(),
            CreditCardLuhnRecognizer(),
            IndianIfscRecognizer(),
            IndianPhoneRecognizer(),
            EmailAddressRecognizer(),
            ContextualPersonLocationRecognizer(),
            DateOfBirthRecognizer(),
        ]
        self._bank_acct_regex = re.compile(r"\b\d{9,18}\b")
        self._labeled_person_regex = re.compile(
            r"(?:Name|Applicant|Beneficiary|Holder|Customer|Client|Payee)\s*[:\-]\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})"
        )

    def _detect_context_bank_accounts(self, text: str) -> List[RecognizerResult]:
        results: List[RecognizerResult] = []
        lower_text = text.lower()

        for match in self._bank_acct_regex.finditer(text):
            start, end = match.span()
            candidate = match.group(0)

            if len(candidate) == 12 and verify_verhoeff(candidate):
                continue

            window_start = max(0, start - 60)
            window_end = min(len(text), end + 60)
            context_slice = lower_text[window_start:window_end]

            if any(kw in context_slice for kw in _BANK_CONTEXT_KEYWORDS):
                results.append(
                    RecognizerResult(
                        entity_type="BANK_ACCOUNT",
                        start=start,
                        end=end,
                        score=0.90,
                    )
                )
        return results

    def _detect_labeled_persons(self, text: str) -> List[RecognizerResult]:
        results: List[RecognizerResult] = []
        for match in self._labeled_person_regex.finditer(text):
            start, end = match.span(1)
            results.append(
                RecognizerResult(
                    entity_type="PERSON",
                    start=start,
                    end=end,
                    score=0.88,
                )
            )
        return results

    def _apply_context_boost(
        self, text: str, recognizer: PatternRecognizer, results: List[RecognizerResult]
    ) -> List[RecognizerResult]:
        if not recognizer.context:
            return results

        lower_text = text.lower()
        for res in results:
            w_start = max(0, res.start - 60)
            w_end = min(len(text), res.end + 60)
            window = lower_text[w_start:w_end]
            if any(ctx_word in window for ctx_word in recognizer.context):
                res.score = min(0.99, round(res.score + 0.08, 2))
        return results

    def _resolve_overlaps(
        self, candidates: List[RecognizerResult]
    ) -> List[RecognizerResult]:
        sorted_candidates = sorted(
            candidates,
            key=lambda r: (
                round(r.score, 2),
                self.ENTITY_PRIORITY.get(r.entity_type, 10),
                r.end - r.start,
            ),
            reverse=True,
        )

        accepted: List[RecognizerResult] = []
        occupied_ranges: List[Tuple[int, int]] = []

        for cand in sorted_candidates:
            overlaps = any(
                not (cand.end <= occ_start or cand.start >= occ_end)
                for occ_start, occ_end in occupied_ranges
            )
            if not overlaps:
                accepted.append(cand)
                occupied_ranges.append((cand.start, cand.end))

        return sorted(accepted, key=lambda r: r.start)

    def analyze_line(
        self, text: str, page: int = 1, line_number: int = 1
    ) -> List[DetectedEntity]:
        if not text or not text.strip():
            return []

        raw_results: List[RecognizerResult] = []
        for recognizer in self.recognizers:
            rec_matches = recognizer.analyze(
                text=text,
                entities=[recognizer.supported_entities[0]],
            )
            boosted = self._apply_context_boost(text, recognizer, list(rec_matches))
            raw_results.extend(boosted)

        raw_results.extend(self._detect_context_bank_accounts(text))
        raw_results.extend(self._detect_labeled_persons(text))

        filtered = [r for r in raw_results if r.score >= 0.55]
        merged_results = self._resolve_overlaps(filtered)

        detected_entities: List[DetectedEntity] = []
        for res in merged_results:
            raw_span = text[res.start : res.end]

            # Strict Privacy Rule: Never expose raw national ID digits in text_preview
            if res.entity_type == "IN_AADHAAR":
                preview_text = "[Aadhaar Redacted]"
            else:
                preview_text = raw_span

            deterministic_seed = (
                f"p{page}_l{line_number}_{res.start}_{res.end}_{res.entity_type}"
            )
            entity_id = str(uuid.uuid5(uuid.NAMESPACE_OID, deterministic_seed))

            detected_entities.append(
                DetectedEntity(
                    id=entity_id,
                    page=page,
                    line_number=line_number,
                    entity_type=res.entity_type,
                    category=self.ENTITY_CATEGORY_MAP.get(
                        res.entity_type, "CONTACT_PII"
                    ),
                    text_preview=preview_text,
                    start_char=res.start,
                    end_char=res.end,
                    confidence=round(float(res.score), 2),
                    validator_passed=self.ENTITY_VALIDATOR_LABEL.get(
                        res.entity_type, "Contextual NER"
                    ),
                    bbox=None,
                    selected_for_redaction=True,
                )
            )

        return detected_entities