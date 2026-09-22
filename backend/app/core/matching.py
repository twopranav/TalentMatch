"""
Skill normalization and matching for candidate ranking.

No elimination happens here or anywhere downstream of it: every
applicant who applies is scored and ranked, never filtered out for
missing compulsory skills, a missing skills section, or anything else.
compulsory_skill_match_ratio() feeds the *score* -- it does not gate
who gets scored. Recruiters see the full applicant list, sorted by
score, and make the final call themselves.
"""

def compulsory_skill_match_ratio(
    matched_count: int,
    compulsory_count: int,
) -> float:
    """
    Fraction of compulsory JD skills the candidate matched, in [0, 1].

    This is one input into the eventual weighted score (alongside
    experience/education matching) -- NOT a pass/fail gate. A candidate
    who matches 0 of 3 compulsory skills still gets scored and shown to
    the recruiter; they just score lower on this component.

    A JD with no compulsory skills contributes a neutral 1.0, since
    there's nothing explicit to score against.
    """
    if compulsory_count == 0:
        return 1.0

    return min(matched_count / compulsory_count, 1.0)


SKILL_ALIASES = {
    # =========================
    # Languages
    # =========================
    "py": "python",
    "python3": "python",
    "python 3": "python",
    "python3.x": "python",
    "js": "javascript",
    "javascript es6": "javascript",
    "javascript es2015": "javascript",
    "ecmascript": "javascript",
    "es6": "javascript",
    "es2015": "javascript",
    "es2020": "javascript",
    "es2021": "javascript",
    "es2022": "javascript",
    "es2023": "javascript",
    "ts": "typescript",
    "typescriptlang": "typescript",
    "golang": "go",
    "go lang": "go",
    "go-lang": "go",
    "c sharp": "c#",
    "c-sharp": "c#",
    "csharp": "c#",
    "c plus plus": "c++",
    "cpp": "c++",
    "c/c++": "c++",
    "objective c": "objective-c",
    "objc": "objective-c",
    "shell scripting": "shell",
    "shell script": "shell",
    "bash scripting": "bash",
    "bash shell": "bash",
    "zsh shell": "zsh",
    "powershell scripting": "powershell",
    "ps": "powershell",

    # =========================
    # Frontend
    # =========================
    "reactjs": "react",
    "react.js": "react",
    "react js": "react",
    "reactjs.js": "react",
    "vuejs": "vue",
    "vue.js": "vue",
    "vue js": "vue",
    "angularjs": "angular",
    "angular.js": "angular",
    "angular js": "angular",
    "nextjs": "next.js",
    "next js": "next.js",
    "next": "next.js",
    "nuxtjs": "nuxt",
    "nuxt.js": "nuxt",
    "sveltejs": "svelte",
    "svelte.js": "svelte",
    "jquery.js": "jquery",
    "j query": "jquery",
    "html5": "html",
    "html 5": "html",
    "css3": "css",
    "css 3": "css",
    "scss": "sass",
    "sass/scss": "sass",
    "lesscss": "less",
    "tailwindcss": "tailwind css",
    "tailwind": "tailwind css",
    "material ui": "mui",
    "material-ui": "mui",
    "materialui": "mui",
    "chakraui": "chakra ui",
    "chakra-ui": "chakra ui",
    "react-native": "react native",

    # =========================
    # Node / JavaScript
    # =========================
    "node": "node.js",
    "nodejs": "node.js",
    "node js": "node.js",
    "node.js runtime": "node.js",
    "expressjs": "express",
    "express.js": "express",
    "express js": "express",
    "nestjs": "nest.js",
    "nest js": "nest.js",
    "npmjs": "npm",
    "npm.js": "npm",
    "pnpmjs": "pnpm",
    "yarnpkg": "yarn",
    "webpackjs": "webpack",
    "vitejs": "vite",
    "rollupjs": "rollup",

    # =========================
    # Python
    # =========================
    "fast api": "fastapi",
    "fast-api": "fastapi",
    "fast_api": "fastapi",
    "django-rest-framework": "django rest framework",
    "drf": "django rest framework",
    "flask api": "flask",
    "sql alchemy": "sqlalchemy",
    "sql-alchemy": "sqlalchemy",
    "pydantic v2": "pydantic",
    "pydantic2": "pydantic",
    "pytest framework": "pytest",
    "py test": "pytest",
    "pandas python": "pandas",
    "numpy python": "numpy",
    "scikit learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "scikit_learn": "scikit-learn",

    # =========================
    # SQL
    # =========================
    "postgres": "postgresql",
    "postgresql db": "postgresql",
    "postgres db": "postgresql",
    "postgres database": "postgresql",
    "postgresql database": "postgresql",
    "psql": "postgresql",
    "pgsql": "postgresql",
    "mysql db": "mysql",
    "mysql database": "mysql",
    "mariadb db": "mariadb",
    "mssql": "sql server",
    "ms sql": "sql server",
    "ms-sql": "sql server",
    "microsoft sql server": "sql server",
    "sqlserver": "sql server",
    "sql server database": "sql server",
    "oracle db": "oracle",
    "oracle database": "oracle",
    "sqlite3": "sqlite",
    "sqlite db": "sqlite",
    "sqlite database": "sqlite",

    # =========================
    # NoSQL
    # =========================
    "mongo": "mongodb",
    "mongo db": "mongodb",
    "mongodb db": "mongodb",
    "mongodb database": "mongodb",
    "redis db": "redis",
    "redis cache": "redis",
    "elastic search": "elasticsearch",
    "elastic-search": "elasticsearch",
    "elastic": "elasticsearch",
    "cassandra db": "cassandra",
    "dynamodb db": "dynamodb",
    "dynamo db": "dynamodb",
    "amazon dynamodb": "dynamodb",
    "cosmos db": "azure cosmos db",
    "cosmosdb": "azure cosmos db",

    # =========================
    # SQL / DB concepts
    # =========================
    "structured query language": "sql",
    "sql queries": "sql",
    "sql query": "sql",
    "pl/sql": "plsql",
    "pl sql": "plsql",
    "t-sql": "tsql",
    "t sql": "tsql",
    "db design": "database design",
    "database schema design": "database design",
    "dbms": "database management",
    "rdbms": "relational database",
    "relational db": "relational database",
    "object relational mapping": "orm",
    "object-relational mapping": "orm",

    # =========================
    # AWS
    # =========================
    "amazon web services": "aws",
    "amazon aws": "aws",
    "aws cloud": "aws",
    "amazon ec2": "aws ec2",
    "ec2": "aws ec2",
    "amazon s3": "aws s3",
    "s3": "aws s3",
    "s3 bucket": "aws s3",
    "amazon rds": "aws rds",
    "rds": "aws rds",
    "lambda": "aws lambda",
    "amazon eks": "aws eks",
    "eks": "aws eks",
    "amazon ecs": "aws ecs",
    "ecs": "aws ecs",
    "cloudwatch": "aws cloudwatch",
    "aws cloud watch": "aws cloudwatch",

    # =========================
    # Azure
    # =========================
    "microsoft azure": "azure",
    "azure cloud": "azure",
    "ms azure": "azure",
    "azure vm": "azure virtual machines",
    "azure virtual machine": "azure virtual machines",
    "azure blob": "azure blob storage",
    "blob storage": "azure blob storage",
    "azure adls": "azure data lake storage",
    "adls": "azure data lake storage",
    "adls gen2": "azure data lake storage",
    "azure data lake": "azure data lake storage",
    "azure data lake storage gen2": "azure data lake storage",
    "azure function": "azure functions",
    "azure sql": "azure sql database",
    "azure sql db": "azure sql database",

    # =========================
    # GCP
    # =========================
    "google cloud": "gcp",
    "google cloud platform": "gcp",
    "google compute engine": "gcp compute engine",
    "gce": "gcp compute engine",
    "google cloud storage": "gcp cloud storage",
    "gcs": "gcp cloud storage",
    "google kubernetes engine": "gke",
    "google cloud functions": "gcp cloud functions",

    # =========================
    # Containers / DevOps
    # =========================
    "docker container": "docker",
    "docker containers": "docker",
    "dockerized": "docker",
    "dockerisation": "docker",
    "dockerization": "docker",
    "k8s": "kubernetes",
    "kube": "kubernetes",
    "kubernetes cluster": "kubernetes",
    "kubernetes orchestration": "kubernetes",
    "containerisation": "containerization",
    "docker-compose": "docker compose",
    "helm charts": "helm",
    "helm chart": "helm",
    "tf": "terraform",
    "ansible automation": "ansible",
    "ansible playbooks": "ansible",

    # =========================
    # CI/CD
    # =========================
    "ci cd": "ci/cd",
    "ci/cd pipeline": "ci/cd",
    "cicd": "ci/cd",
    "ci-cd": "ci/cd",
    "continuous integration": "ci/cd",
    "continuous deployment": "ci/cd",
    "continuous delivery": "ci/cd",
    "github-action": "github actions",
    "gitlab ci": "gitlab ci/cd",
    "gitlab-ci": "gitlab ci/cd",
    "gitlab cicd": "gitlab ci/cd",
    "jenkins pipeline": "jenkins",
    "jenkins ci": "jenkins",
    "ado": "azure devops",

    # =========================
    # Git
    # =========================
    "git version control": "git",
    "git scm": "git",
    "version control": "git",
    "git hub": "github",
    "git lab": "gitlab",
    "svn": "subversion",
    "apache subversion": "subversion",

    # =========================
    # APIs / Backend
    # =========================
    "rest": "rest api",
    "restful": "rest api",
    "restful api": "rest api",
    "rest apis": "rest api",
    "restful apis": "rest api",
    "http api": "rest api",
    "http apis": "rest api",
    "web api": "rest api",
    "web apis": "rest api",
    "graphql api": "graphql",
    "graph ql": "graphql",
    "grpc api": "grpc",
    "g-rpc": "grpc",
    "soap api": "soap",
    "soap web services": "soap",
    "microservice": "microservices",
    "micro-services": "microservices",
    "micro service": "microservices",
    "oauth2": "oauth 2.0",
    "oauth 2": "oauth 2.0",
    "oauth2.0": "oauth 2.0",
    "jwt auth": "jwt",
    "jwt authentication": "jwt",
    "json web token": "jwt",
    "json web tokens": "jwt",

    # =========================
    # Messaging
    # =========================
    "apache kafka": "kafka",
    "kafka streaming": "kafka",
    "rabbitmq broker": "rabbitmq",
    "rabbit mq": "rabbitmq",
    "apache pulsar": "pulsar",
    "message queues": "message queue",
    "message queueing": "message queue",
    "messaging queues": "message queue",

    # =========================
    # AI / ML / NLP
    # =========================
    "artificial intelligence": "ai",
    "machine intelligence": "ai",
    "ml": "machine learning",
    "dl": "deep learning",
    "natural language processing": "nlp",
    "natural-language processing": "nlp",
    "text processing": "nlp",
    "large language model": "llm",
    "large language models": "llm",
    "llms": "llm",
    "gen ai": "generative ai",
    "genai": "generative ai",
    "huggingface": "hugging face",
    "hugging-face": "hugging face",
    "hf": "hugging face",
    "transformers library": "hugging face transformers",
    "huggingface transformers": "hugging face transformers",
    "hf transformers": "hugging face transformers",
    "sentence transformers": "sentence-transformers",
    "sentence_transformers": "sentence-transformers",
    "vector db": "vector database",
    "vector databases": "vector database",
    "vector store": "vector database",
    "pinecone db": "pinecone",
    "chroma db": "chromadb",
    "chromadb database": "chromadb",

    # =========================
    # Data / Analytics
    # =========================
    "data analysis": "data analytics",
    "extract transform load": "etl",
    "extract-transform-load": "etl",
    "apache spark": "spark",
    "spark sql": "spark",
    "py spark": "pyspark",
    "apache airflow": "airflow",
    "airflow orchestration": "airflow",
    "powerbi": "power bi",
    "tableau desktop": "tableau",

    # =========================
    # Testing
    # =========================
    "unit tests": "unit testing",
    "integration tests": "integration testing",
    "automated testing": "test automation",
    "jestjs": "jest",
    "jest.js": "jest",
    "mocha.js": "mocha",
    "mochajs": "mocha",
    "cypress.io": "cypress",
    "playwright testing": "playwright",
    "selenium webdriver": "selenium",
    "selenium web driver": "selenium",

    # =========================
    # Observability / SRE
    # =========================
    "prometheus monitoring": "prometheus",
    "grafana dashboards": "grafana",
    "elk": "elk stack",
    "elastic stack": "elk stack",
    "application performance monitoring": "apm",
    "opentelemetry": "open telemetry",
    "otel": "open telemetry",

    # =========================
    # Security
    # =========================
    "application security": "appsec",
    "app security": "appsec",
    "cyber security": "cybersecurity",
    "cyber-security": "cybersecurity",
    "infosec": "information security",
    "iam": "identity and access management",
    "role based access control": "rbac",
    "role-based access control": "rbac",
    "single sign on": "sso",
    "single-sign-on": "sso",
    "multi factor authentication": "mfa",
    "multi-factor authentication": "mfa",
    "2fa": "mfa",
    "two factor authentication": "mfa",

    # =========================
    # Architecture
    # =========================
    "system architecture": "system design",
    "object oriented programming": "oop",
    "object-oriented programming": "oop",
    "oops": "oop",
    "data structures and algorithms": "dsa",
    "data structures & algorithms": "dsa",
    "ds and algo": "dsa",
    "event driven architecture": "event-driven architecture",
    "domain driven design": "domain-driven design",
    "ddd": "domain-driven design",

    # =========================
    # Java
    # =========================
    "java 8": "java",
    "java 11": "java",
    "java 17": "java",
    "java 21": "java",
    "jdk": "java",
    "jre": "java",
    "springboot": "spring boot",
    "spring-boot": "spring boot",
    "spring framework": "spring",
    "hibernate orm": "hibernate",
    "hibernate framework": "hibernate",
    "maven build": "maven",
    "apache maven": "maven",
    "gradle build": "gradle",

    # =========================
    # .NET
    # =========================
    "dotnet": ".net",
    "dot net": ".net",
    "microsoft .net": ".net",
    "aspnet core": "asp.net core",
    "asp net core": "asp.net core",
    "ef core": "entity framework core",

    # =========================
    # Mobile
    # =========================
    "android development": "android",
    "android sdk": "android",
    "ios development": "ios",
    "ios sdk": "ios",
    "flutter development": "flutter",
    "dart language": "dart",

    # =========================
    # Infrastructure
    # =========================
    "linux os": "linux",
    "gnu/linux": "linux",
    "unix system": "unix",
    "nginx web server": "nginx",
    "nginx server": "nginx",
    "apache http server": "apache",
    "load balancer": "load balancing",

    # =========================
    # Infrastructure as Code
    # =========================
    "iac": "infrastructure as code",
    "infrastructure-as-code": "infrastructure as code",
    "terraform iac": "terraform",
    "terraform cloud": "terraform",

    # =========================
    # Project / Agile
    # =========================
    "agile methodology": "agile",
    "agile development": "agile",
    "scrum methodology": "scrum",
    "scrum framework": "scrum",
    "kanban methodology": "kanban",
    "jira software": "jira",
    "atlassian jira": "jira",
    "confluence atlassian": "confluence",

    # =========================
    # Common abbreviations
    # =========================
    "apis": "api",
    "db": "database",
    "dbs": "database",
    "dev ops": "devops",
    "dev-ops": "devops",
    "devops engineering": "devops",
    "sre": "site reliability engineering",
    "qa": "quality assurance",
    "quality engineering": "quality assurance",
    "ui ux": "ui/ux",
    "ui/ux design": "ui/ux",
    "ux ui": "ui/ux",
    "frontend": "frontend development",
    "front end": "frontend development",
    "front-end": "frontend development",
    "backend": "backend development",
    "back end": "backend development",
    "back-end": "backend development",
    "fullstack": "full-stack development",
    "full stack": "full-stack development",
    "full-stack": "full-stack development",
}


def test_skill_aliases_are_acyclic() -> None:
    """
    Ensure no canonical alias target is itself another alias key.

    This prevents accidental multi-hop normalization.
    """
    alias_keys = set(SKILL_ALIASES)

    for value in SKILL_ALIASES.values():
        assert value not in alias_keys, (
            f"'{value}' is both an alias target and an alias key"
        )


def normalize_skill(raw: str) -> str:
    """
    Normalize one skill for matching.
    """
    key = raw.strip().lower()
    return SKILL_ALIASES.get(key, key)


def normalize_skills(skills: list[str]) -> set[str]:
    """
    Normalize and deduplicate a skill collection.
    """
    return {
        normalize_skill(skill)
        for skill in skills
        if skill and skill.strip()
    }


def count_matched_skills(
    candidate_skills: list[str],
    jd_skills: list[str],
) -> int:
    """
    Count normalized JD skills present in candidate skills.
    """
    candidate_set = normalize_skills(candidate_skills)

    return sum(
        1
        for skill in jd_skills
        if normalize_skill(skill) in candidate_set
    )


def count_matched_compulsory_skills(
    candidate_skills: list[str],
    compulsory_skills: list[str],
) -> int:
    """
    Count only explicitly compulsory JD skills matched by the candidate.

    Feeds compulsory_skill_match_ratio() for scoring -- not a gate.
    """
    return count_matched_skills(
        candidate_skills,
        compulsory_skills,
    )


# Backward-compatible alias for any older caller still using the old name.
def count_matched_required_skills(
    candidate_skills: list[str],
    required_skills: list[str],
) -> int:
    return count_matched_compulsory_skills(
        candidate_skills,
        required_skills,
    )