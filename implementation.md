# Implementation Workflow

## End-to-End Workflow Graph

```mermaid
flowchart TD
    U[User] --> FE[Frontend React App\nApp.jsx]

    subgraph Frontend
      FE --> RT[ReadingTable\nAdd Reading Form]
      FE --> CSV[CSV Upload Control]
      FE --> DS[DashboardSummary]
      FE --> API[Axios Client\napi.js]
    end

    RT -->|POST /readings\npayload: household, amount| API
    CSV -->|POST /import-csv\nmultipart/form-data| API
    FE -->|GET /readings| API

    API --> BE[FastAPI Backend\nmain.py]

    subgraph Backend
      BE --> AR[add_reading()]
      BE --> IR[import_csv()]
      BE --> GR[get_readings()]
    end

    AR --> ORM[SQLAlchemy ORM\nReading model]
    IR --> ORM
    GR --> ORM

    ORM --> DB[(SQLite Database)]

    DB --> ORM
    ORM --> GR
    GR -->|JSON readings list| API
    API --> FE

    AR -->|Created reading response| API
    IR -->|Import status message| API

    FE -->|Update table + summary| U
```
