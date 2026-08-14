"""Judge determinístico: avaliação por rubrica sem LLM (apenas stdlib)."""

import re
from collections import Counter

# Stopwords comuns PT-BR + EN (sem dependências externas: nada de NLTK/spacy).
_STOPWORDS = frozenset(
    {
        # pt-br
        "a", "o", "as", "os", "de", "do", "da", "dos", "das", "em", "na", "no",
        "nas", "nos", "para", "por", "com", "sem", "sob", "sobre", "entre",
        "como", "mas", "que", "se", "é", "são", "foi", "era", "ser", "estar",
        "está", "este", "esta", "isso", "isto", "aquilo", "ele", "ela", "eles",
        "elas", "meu", "minha", "seu", "sua", "nosso", "nossa", "uma", "um",
        # en
        "the", "and", "for", "with", "from", "that", "this", "have", "has",
        "was", "were", "will", "would", "can", "could", "should", "not", "are",
        "you", "your", "its", "his", "her", "their", "them", "they", "what",
        "when", "where", "which", "who", "how", "into", "about", "than", "then",
        "there", "here", "all", "also", "some", "any", "out", "been", "being",
    }
)

_WORD_RE = re.compile(r"[a-záàâãéêíóôõúüç0-9]+")


def _tokenize(text: str) -> list[str]:
    """Extrai tokens (palavras/números) em minúsculas."""
    return _WORD_RE.findall(text.lower())


class DeterministicJudge:
    """Avalia respostas com heurísticas locais (fidelity, coherence, instruction).

    Todos os scores retornam float em 0.0–1.0.
    """

    def score_fidelity(self, expected: str, actual: str) -> float:
        """Mede sobreposição de palavras entre expected e actual.

        Usa token overlap: palavras em comum / total de palavras únicas
        (similaridade de Jaccard sobre os conjuntos de tokens).
        """
        expected_tokens = set(_tokenize(expected))
        actual_tokens = set(_tokenize(actual))
        union = expected_tokens | actual_tokens
        if not union:
            return 0.0
        return len(expected_tokens & actual_tokens) / len(union)

    def score_coherence(self, actual: str) -> float:
        """Heurística de coerência baseada em:

        - Comprimento mínimo (< 10 palavras → penalidade)
        - Presença de pontuação final
        - Ausência de repetição excessiva (mesma palavra > 30% do texto → penalidade)
        """
        tokens = _tokenize(actual)
        if not tokens:
            return 0.0
        score = 1.0
        if len(tokens) < 10:
            score -= 0.3
        if not re.search(r"[.!?…]\s*$", actual.strip()):
            score -= 0.2
        _most_common, count = Counter(tokens).most_common(1)[0]
        if count / len(tokens) > 0.3:
            score -= 0.3
        return max(0.0, min(1.0, score))

    def score_instruction(self, input_prompt: str, actual: str) -> float:
        """Verifica se palavras-chave do prompt aparecem na resposta.

        Extrai substantivos e verbos relevantes do input (palavras > 4 chars,
        não stopwords). Score = palavras_encontradas / total_palavras_chave.
        """
        keywords = {
            token
            for token in _tokenize(input_prompt)
            if len(token) > 4 and token not in _STOPWORDS
        }
        if not keywords:
            return 0.0
        actual_tokens = set(_tokenize(actual))
        found = keywords & actual_tokens
        return len(found) / len(keywords)

    def evaluate(self, input_prompt: str, expected: str, actual: str) -> dict[str, float]:
        """Retorna dict com score_fidelity, score_coherence, score_instruction."""
        return {
            "score_fidelity": self.score_fidelity(expected, actual),
            "score_coherence": self.score_coherence(actual),
            "score_instruction": self.score_instruction(input_prompt, actual),
        }
