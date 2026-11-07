import re
from .models import KnowledgeArticle

TOKEN_RE = re.compile(r"[\wа-яіїєґА-ЯІЇЄҐ]{3,}", re.UNICODE)

def retrieve(query: str, limit: int = 3):
    terms = set(TOKEN_RE.findall(query.lower()))
    results = []
    for article in KnowledgeArticle.objects.all():
        title = set(TOKEN_RE.findall(article.title.lower()))
        keywords = set(TOKEN_RE.findall(" ".join(article.keywords).lower()))
        content = set(TOKEN_RE.findall(article.content.lower()))
        score = 5 * len(terms & keywords) + 3 * len(terms & title) + len(terms & content)
        if score:
            results.append((score, article))
    results.sort(key=lambda entry: (-entry[0], entry[1].slug))
    return [article for _, article in results[:limit]]
