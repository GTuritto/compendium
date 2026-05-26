# C4 — Deployment

Compendium is local-first: it runs entirely on one machine. `docker compose`
is the only orchestration the project uses, and that is the deliberate
ceiling — no Kubernetes, no managed services, no cloud deployment.

```mermaid
C4Deployment
  title Deployment Diagram — Compendium (single machine)

  Deployment_Node(laptop, "Developer machine", "macOS laptop") {
    Deployment_Node(uv, "uv environment", "Python 3.12") {
      Container(app, "Compendium application", "Python", "CLI and Textual TUI")
    }
    Deployment_Node(fs, "Local filesystem", "APFS") {
      ContainerDb(vault, "Markdown vault", "Files", "Canonical wiki")
    }
    Deployment_Node(dmr, "Docker Model Runner", "Metal-accelerated") {
      Container(models, "Local models", "GGUF", "Embeddings; optionally synthesis")
    }
    Deployment_Node(docker, "Docker Engine", "docker compose") {
      ContainerDb(pg, "postgres", "postgres:16", "Operational record")
      ContainerDb(os, "opensearch", "OpenSearch 2.x", "Lexical index")
      ContainerDb(qd, "qdrant", "Qdrant", "Vector index")
      ContainerDb(mg, "memgraph", "Memgraph", "Knowledge graph")
    }
  }

  Deployment_Node(cloud, "OpenRouter", "Cloud, optional") {
    Container(router, "LLM gateway", "OpenAI-compatible", "Synthesis models")
  }

  Rel(app, vault, "Reads/writes", "filesystem")
  Rel(app, pg, "psycopg 3", "localhost:5432")
  Rel(app, os, "HTTP", "localhost:9200")
  Rel(app, qd, "HTTP", "localhost:6533")
  Rel(app, mg, "Bolt (neo4j driver)", "localhost:7688")
  Rel(app, models, "OpenAI-compatible API", "localhost:12434")
  Rel(app, router, "OpenAI-compatible API", "HTTPS")

  UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

## Notes

- **One machine.** The application runs natively under `uv`; the four data
  stores run as Docker containers from a single dev `docker-compose.yml`;
  Docker Model Runner runs models on the host with Metal acceleration; the
  vault is a directory on the local filesystem.
- **The application is not containerized.** Only the backing stores are.
  `docker compose up -d` starts them; the app runs outside Docker.
- **OpenRouter is the synthesis default** (`anthropic/claude-sonnet-4.5`),
  config-selectable against a local Docker Model Runner to keep ingested notes
  on-device. Embeddings always run locally on Docker Model Runner
  (`BAAI/bge-m3`, `localhost:12434`).
- **Host ports are remapped** so Compendium coexists with other local stacks:
  Qdrant is published on `6533` (container `6333`) and Memgraph on `7688`
  (container `7687`). PostgreSQL `5432` and OpenSearch `9200` keep their
  defaults. All four services live in one dev `docker-compose.yml`.
