"""
PII Detection and Masking using Microsoft Presidio
Detects personally identifiable information and masks/redacts it
"""

from typing import Optional, List, Dict
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig


class PIIDetector:
    """Detect personally identifiable information in text"""

    def __init__(self, language: str = "en"):
        """Initialize PII detector with language-specific rules"""
        self.analyzer = AnalyzerEngine()
        self.language = language

    def detect(
        self, text: str, entities: Optional[List[str]] = None, threshold: float = 0.5
    ) -> List[Dict]:
        """
        Detect PII entities in text.

        Args:
            text: Text to analyze
            entities: Specific entities to detect (e.g., ["PERSON", "EMAIL_ADDRESS"])
            threshold: Confidence threshold (0-1)

        Returns:
            List of detected PII entities with positions and confidence
        """
        try:
            results = self.analyzer.analyze(
                text=text,
                language=self.language,
                entities=entities,
                score_threshold=threshold,
            )

            return [
                {
                    "entity_type": result.entity_type,
                    "start": result.start,
                    "end": result.end,
                    "score": result.score,
                    "text": text[result.start : result.end],
                }
                for result in results
            ]
        except Exception as e:
            # If analysis fails, return empty list (don't block message)
            return []

    def has_pii(self, text: str, threshold: float = 0.5) -> bool:
        """Check if text contains any PII"""
        return len(self.detect(text, threshold=threshold)) > 0


class PIIMasker:
    """Mask/redact personally identifiable information in text"""

    def __init__(self):
        """Initialize PII masker"""
        self.anonymizer = AnonymizerEngine()

    def mask(
        self,
        text: str,
        entities: Optional[List[str]] = None,
        strategy: str = "redact",
    ) -> tuple[str, List[Dict]]:
        """
        Mask PII entities in text.

        Args:
            text: Text to mask
            entities: Specific entity types to mask
            strategy: Masking strategy - "redact" (****), "replace", "hash"

        Returns:
            Tuple of (masked_text, list of redacted entities)
        """
        try:
            analyzer = AnalyzerEngine()
            detected = analyzer.analyze(text=text, language="en", entities=entities)

            if not detected:
                return text, []

            # Define masking operators
            operators = {
                "DEFAULT": OperatorConfig("redact"),
                "PERSON": OperatorConfig("redact"),
                "EMAIL_ADDRESS": OperatorConfig("redact"),
                "PHONE_NUMBER": OperatorConfig("redact"),
                "CREDIT_CARD": OperatorConfig("redact"),
                "DATE_TIME": OperatorConfig("redact"),
                "LOCATION": OperatorConfig("redact"),
                "URL": OperatorConfig("redact"),
                "IP_ADDRESS": OperatorConfig("redact"),
                "MEDICAL_LICENSE": OperatorConfig("redact"),
                "US_PASSPORT": OperatorConfig("redact"),
                "US_DRIVER_LICENSE": OperatorConfig("redact"),
                "US_SSN": OperatorConfig("redact"),
                "ORGANIZATION": OperatorConfig("redact"),
            }

            masked_text = self.anonymizer.anonymize(
                text=text, analyzer_results=detected, operators=operators
            )

            redacted_entities = [
                {
                    "entity_type": result.entity_type,
                    "text": text[result.start : result.end],
                    "position": {"start": result.start, "end": result.end},
                }
                for result in detected
            ]

            return masked_text.text, redacted_entities

        except Exception as e:
            # If masking fails, return original text
            return text, []


class PIIProcessor:
    """High-level interface for PII detection and masking"""

    def __init__(self):
        """Initialize PII processor"""
        self.detector = PIIDetector()
        self.masker = PIIMasker()

    def process(
        self, text: str, mask: bool = True
    ) -> Dict:
        """
        Process text for PII: detect and optionally mask.

        Args:
            text: Text to process
            mask: Whether to mask detected PII

        Returns:
            Dictionary with:
            - original: Original text
            - masked: Masked text (if mask=True)
            - detected: List of detected entities
            - has_pii: Whether PII was found
        """
        detected = self.detector.detect(text)
        has_pii = len(detected) > 0

        masked_text = text
        redacted = detected

        if mask and has_pii:
            masked_text, redacted = self.masker.mask(text)

        return {
            "original": text,
            "masked": masked_text,
            "detected": detected,
            "redacted": redacted,
            "has_pii": has_pii,
            "pii_count": len(detected),
            "pii_types": list(set(e["entity_type"] for e in detected)),
        }


# Global instances
detector = PIIDetector()
masker = PIIMasker()
processor = PIIProcessor()


def detect_pii(text: str) -> List[Dict]:
    """Detect PII in text - convenience function"""
    return detector.detect(text)


def mask_pii(text: str) -> tuple[str, List[Dict]]:
    """Mask PII in text - convenience function"""
    return masker.mask(text)


def process_pii(text: str, mask: bool = True) -> Dict:
    """Process text for PII - convenience function"""
    return processor.process(text, mask=mask)
