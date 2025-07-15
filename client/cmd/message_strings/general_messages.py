def malformed_response_body(*expected_claims: str) -> str:
    return f'Malformed response body, expected claims: {expected_claims}'