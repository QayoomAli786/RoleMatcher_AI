"""Shared skill alias normalization used across multiple services.

Centralised here to avoid duplication in resume_parser, skill_matcher,
and skill_gap_engine.
"""

from __future__ import annotations

import re

SKILL_ALIASES: dict[str, str] = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "react.js": "react",
    "reactjs": "react",
    "react js": "react",
    "vue.js": "vue",
    "vuejs": "vue",
    "vue js": "vue",
    "angular.js": "angular",
    "angularjs": "angular",
    "node.js": "node",
    "nodejs": "node",
    "next.js": "next.js",
    "nextjs": "next.js",
    "nuxt.js": "nuxt.js",
    "nuxtjs": "nuxt.js",
    "golang": "go",
    "c sharp": "c#",
    "c plus plus": "c++",
    "postgres": "postgresql",
    "mongo": "mongodb",
    "dynamo": "dynamodb",
    "k8s": "kubernetes",
    "tf": "tensorflow",
    "pt": "pytorch",
    "sklearn": "scikit-learn",
    "gcp": "google cloud",
    "fast api": "fastapi",
    "fastapi": "fastapi",
    "spring boot": "spring boot",
    "springboot": "spring boot",
    "ruby on rails": "rails",
    "open ai": "openai",
    "openai": "openai",
    "hugging face": "huggingface",
    "lang chain": "langchain",
    "ml flow": "mlflow",
    "wandb": "weights & biases",
    "apache spark": "spark",
    "apache kafka": "kafka",
    "apache airflow": "airflow",
    "apache flink": "flink",
    "docker compose": "docker-compose",
    "github ci": "github actions",
    "gh actions": "github actions",
    "gitlab ci": "gitlab-ci",
    "circle ci": "circleci",
    "travis": "travis ci",
    "tailwind css": "tailwindcss",
    "styled components": "styled-components",
    "material ui": "material-ui",
    "ant design": "antd",
    "mui": "material-ui",
    "ci/cd": "ci/cd",
    "rest api": "rest api",
    "restful": "rest api",
    "graphql api": "graphql",
    "jest": "jest",
    "cypress": "cypress",
    "playwright": "playwright",
    "vitest": "vitest",
    "mocha": "mocha",
    "webpack": "webpack",
    "vite": "vite",
    "dynamodb": "dynamodb",
    "cosmos db": "cosmosdb",
    "snowflake": "snowflake",
    "bigquery": "bigquery",
    "data lake": "data lake",
}


def normalize_skill(raw: str) -> str:
    """Normalize a skill string: lowercase, strip non-alnum, resolve alias."""
    s = raw.strip().lower()
    s = re.sub(r"[^a-z0-9+#\-. ]", "", s)
    return SKILL_ALIASES.get(s, s)
