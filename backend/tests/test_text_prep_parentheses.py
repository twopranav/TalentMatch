from app.core.skills_text_prep import normalize_parentheses


def test_short_skill_entries_still_expand():
    assert normalize_parentheses("AWS (ECS, S3)") == "aws, aws ecs, aws s3"
    assert normalize_parentheses("JavaScript (ES6+)") == "javascript, javascript es6+"
    assert normalize_parentheses("Cloud Azure (basic)") == "azure, azure basic"


def test_prose_sentence_with_parenthetical_is_not_duplicated():
    text = (
        "Proficiency in client-side JavaScript frameworks, predominantly React.js. "
        "Solid experience building scalable server-side microservices using Node.js and Express framework. "
        "Familiarity with cloud hosting services (AWS/GCP), Redis caching, and CI/CD tools."
    )
    out = normalize_parentheses(text)
    assert out == text.lower()
    assert out.count("react.js") == 1
    assert out.count("node.js") == 1
