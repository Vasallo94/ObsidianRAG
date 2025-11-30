# ObsidianRAG Architecture

This document describes the high-level architecture of ObsidianRAG v3, which consists of a TypeScript plugin for Obsidian and a Python backend for RAG capabilities.

## High-Level Overview

```mermaid
graph TD
    User[User] -->|Interacts with| Plugin[Obsidian Plugin]
    Plugin -->|Spawns/Manages| Backend[Python Backend]
    Plugin -->|HTTP Requests| Backend
    Backend -->|Queries| VectorDB[(ChromaDB)]
    Backend -->|Inference| Ollama[Ollama LLM]
    Backend -->|Reads| Vault[Obsidian Vault]
```

## Component Interaction

### 1. Startup Flow

```mermaid
sequenceDiagram
    participant Obsidian
    participant Plugin
    participant Backend
    participant Ollama

    Obsidian->>Plugin: onload()
    Plugin->>Plugin: Load Settings
    Plugin->>Backend: Spawn Process (obsidianrag serve)
    loop Health Check
        Plugin->>Backend: GET /health
        Backend-->>Plugin: 200 OK
    end
    Plugin->>Ollama: GET /api/tags (Check Models)
    Ollama-->>Plugin: List of Models
    Plugin->>User: Ready (Status: Online)
```

### 2. RAG Query Flow (Streaming)

```mermaid
sequenceDiagram
    participant User
    participant Plugin
    participant Backend
    participant VectorDB
    participant Ollama

    User->>Plugin: Ask Question
    Plugin->>Backend: POST /ask/stream
    
    rect rgb(240, 248, 255)
        note right of Backend: Retrieval Phase
        Backend->>VectorDB: Query Embeddings
        VectorDB-->>Backend: Top K Chunks
        Backend->>Backend: Rerank Results
        Backend-->>Plugin: SSE: phase="rerank"
    end

    rect rgb(255, 250, 240)
        note right of Backend: Generation Phase
        Backend->>Ollama: Generate(Prompt + Context)
        loop Stream Tokens
            Ollama-->>Backend: Token
            Backend-->>Plugin: SSE: token="word"
        end
    end

    Backend-->>Plugin: SSE: done
    Plugin->>User: Display Full Answer
```

## Data Flow

```mermaid
flowchart LR
    subgraph "Obsidian Vault"
        MD[Markdown Files]
    end

    subgraph "Python Backend"
        Watcher[File Watcher]
        Chunker[Text Chunker]
        Embedder[Embedding Model]
        DB[(ChromaDB)]
    end

    MD --> Watcher
    Watcher -->|New/Modified| Chunker
    Chunker -->|Chunks| Embedder
    Embedder -->|Vectors| DB
```
