"""Email address permutation generator for B2B prospecting."""

import re
from typing import List
from prospector.models import EmailPermutation


# Prior probabilities based on B2B email pattern frequency studies
PATTERN_PRIORS = {
    "first.last": 0.50,
    "flast": 0.20,
    "first": 0.15,
    "firstlast": 0.05,
    "f.last": 0.04,
    "first_last": 0.03,
    "last.first": 0.01,
    "last": 0.01,
    "first.l": 0.01,
}


class EmailPermutator:
    """Generates normalized and valid email permutations for a prospect."""

    @classmethod
    def sanitize(cls, text: str) -> str:
        """Sanitize name parts: lowercase, remove accents/non-ascii, strip spaces."""
        cleaned = re.sub(r"[^a-zA-Z0-9]", "", text.lower())
        return cleaned

    @classmethod
    def generate(cls, first_name: str, last_name: str, domain: str) -> List[EmailPermutation]:
        """Generate a ranked list of corporate email permutations."""
        first = cls.sanitize(first_name)
        last = cls.sanitize(last_name)
        clean_domain = domain.lower().strip()

        if not first or not clean_domain:
            return []

        permutations: List[EmailPermutation] = []
        f_initial = first[0] if first else ""
        l_initial = last[0] if last else ""

        # Build patterns
        candidates = []

        if first and last:
            candidates.append(("first.last", f"{first}.{last}@{clean_domain}"))
            candidates.append(("flast", f"{f_initial}{last}@{clean_domain}"))
            candidates.append(("first", f"{first}@{clean_domain}"))
            candidates.append(("firstlast", f"{first}{last}@{clean_domain}"))
            candidates.append(("f.last", f"{f_initial}.{last}@{clean_domain}"))
            candidates.append(("first_last", f"{first}_{last}@{clean_domain}"))
            candidates.append(("first.l", f"{first}.{l_initial}@{clean_domain}"))
            candidates.append(("last.first", f"{last}.{first}@{clean_domain}"))
            candidates.append(("last", f"{last}@{clean_domain}"))
        else:
            # Only single name provided
            candidates.append(("first", f"{first}@{clean_domain}"))
            candidates.append(("flast", f"{first}@{clean_domain}"))

        seen = set()
        for pattern_name, email in candidates:
            if email not in seen:
                seen.add(email)
                prior = PATTERN_PRIORS.get(pattern_name, 0.02)
                permutations.append(
                    EmailPermutation(
                        email=email,
                        pattern_name=pattern_name,
                        confidence_score=prior,
                        verification_status="unverified",
                    )
                )

        return permutations
