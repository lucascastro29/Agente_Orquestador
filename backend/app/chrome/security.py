import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.config import settings

INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|your)\s+instructions",
    r"\[system\]",
    r"\[admin\]",
    r"\[override\]",
    r"new\s+system\s+prompt",
    r"anthropic\s+directive",
    r"authorization\s+code\s*:",
    r"send\s+(this|all|the)\s+(data|content|memory)\s+to",
    r"curl\s+https?://",
    r"admin\s+override",
    r"security\s+bypass",
    r"forget\s+(everything|your\s+previous)",
    r"your\s+new\s+(instructions|directive|task)\s+(is|are)",
    r"you\s+are\s+now\s+in\s+(developer|admin|unrestricted)\s+mode",
    r"ignore\s+safety\s+(guidelines|restrictions|rules)",
    r"the\s+user\s+has\s+(already|pre.?authorized)",
    r"this\s+action\s+is\s+(already|pre.?approved)",
    r"elevate\s+(your|this)",
    r"set\s+approval_policy",
    r"disable\s+requires_confirmation",
]


@dataclass
class DomainCheckResult:
    allowed: bool
    domain: str
    reason: str | None = None


@dataclass
class InjectionCheckResult:
    flagged: bool
    reason: str | None = None


class ChromeSecurityChecker:
    def check_domain(self, url: str) -> DomainCheckResult:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return DomainCheckResult(allowed=False, domain=url, reason="Solo HTTP/HTTPS permitido")

            domain = parsed.netloc.lower()
            clean_domain = domain.removeprefix("www.")

            for allowed in settings.chrome_allowed_domains:
                clean_allowed = allowed.lower().removeprefix("www.")
                if clean_domain == clean_allowed or clean_domain.endswith(f".{clean_allowed}"):
                    return DomainCheckResult(allowed=True, domain=domain)

            return DomainCheckResult(
                allowed=False,
                domain=domain,
                reason=f"'{domain}' no está en CHROME_ALLOWED_DOMAINS. Dominios permitidos: {settings.chrome_allowed_domains}",
            )
        except Exception as exc:
            return DomainCheckResult(allowed=False, domain=url, reason=str(exc))

    def check_injection(self, text: str) -> InjectionCheckResult:
        if not text:
            return InjectionCheckResult(flagged=False)
        lower = text.lower()
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, lower):
                return InjectionCheckResult(flagged=True, reason=f"Patrón detectado: '{pattern}'")
        return InjectionCheckResult(flagged=False)
