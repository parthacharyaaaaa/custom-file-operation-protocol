from typing import Optional

def missing_response_claim(*expected_claims: str) -> str:
    return f'Malformed response body, expected claims: {", ".join(expected_claims)}'

def malformed_response_body(message: Optional[str] = None) -> str:
    return "\n".join((f'Malformed response body:', "Unknown cause. Possible data type mismatch or illogical values" if not message else message))