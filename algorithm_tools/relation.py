from typing import Any


def _normalize_matrix(matrix: list[list[Any]]) -> list[list[int]]:
    if not matrix:
        raise ValueError("matrix must not be empty")

    size = len(matrix)
    normalized: list[list[int]] = []

    for row in matrix:
        if len(row) != size:
            raise ValueError("matrix must be a square matrix")

        normalized_row: list[int] = []
        for value in row:
            if isinstance(value, bool):
                normalized_row.append(int(value))
            elif value in (0, 1):
                normalized_row.append(value)
            else:
                raise ValueError("matrix values must be 0/1 or true/false")
        normalized.append(normalized_row)

    return normalized


def is_reflexive(matrix: list[list[Any]]) -> bool:
    normalized = _normalize_matrix(matrix)
    return all(normalized[i][i] == 1 for i in range(len(normalized)))


def is_irreflexive(matrix: list[list[Any]]) -> bool:
    normalized = _normalize_matrix(matrix)
    return all(normalized[i][i] == 0 for i in range(len(normalized)))


def is_symmetric(matrix: list[list[Any]]) -> bool:
    normalized = _normalize_matrix(matrix)
    size = len(normalized)
    return all(normalized[i][j] == normalized[j][i] for i in range(size) for j in range(size))


def is_antisymmetric(matrix: list[list[Any]]) -> bool:
    normalized = _normalize_matrix(matrix)
    size = len(normalized)
    return all(
        normalized[i][j] == 0 or normalized[j][i] == 0
        for i in range(size)
        for j in range(size)
        if i != j
    )


def is_transitive(matrix: list[list[Any]]) -> bool:
    normalized = _normalize_matrix(matrix)
    size = len(normalized)

    for i in range(size):
        for j in range(size):
            if normalized[i][j] == 0:
                continue
            for k in range(size):
                if normalized[j][k] == 1 and normalized[i][k] == 0:
                    return False
    return True


def analyze_relation(matrix: list[list[Any]]) -> dict[str, bool]:
    normalized = _normalize_matrix(matrix)

    return {
        "reflexive": is_reflexive(normalized),
        "irreflexive": is_irreflexive(normalized),
        "symmetric": is_symmetric(normalized),
        "antisymmetric": is_antisymmetric(normalized),
        "transitive": is_transitive(normalized),
    }
