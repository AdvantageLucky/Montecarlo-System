# Montecarlo-System

Distributed Monte Carlo simulation system. A server publishes mathematical functions and scenarios (random samples) through RabbitMQ; multiple clients consume that data, evaluate the function with the received scenario and publish the results. A central monitor aggregates the results per user and visualizes them in real time.

## Architecture

```
                       ┌──────────────────┐
                       │  funcs_servicer  │  GUI (customtkinter)
                       │   (publisher)    │  Publishes functions and scenarios
                       └────────┬─────────┘
                    exchange    │    queue
                "exchange.models"    "scenarios"
                       (fanout) │
                       ┌────────▼─────────┐
                       │     RabbitMQ     │
                       └────────┬─────────┘
                                │  "<ip>.models" and "scenarios" queues
                 ┌──────────────┼──────────────┐
        ┌────────▼───────┐ ┌────▼───────────┐  ...
        │ funcs_consumer │ │ funcs_consumer │   N clients
        │  (evaluator)   │ │  (evaluator)   │
        └────────┬───────┘ └────┬───────────┘
                 │   "results" queue
                 └───────┬──────┘
                 ┌───────▼────────┐   gRPC    ┌──────────────┐
                 │ monitor/server │◄──────────│ monitor/app  │
                 │ (cache + gRPC) │           │ (dashboard)  │
                 └────────────────┘           └──────────────┘
```

### Components

| Component | Description |
|---|---|
| `funcs_servicer/` | GUI that loads a functions file (`fns.txt`), publishes the current function through the fanout exchange `exchange.models` and generates random scenarios (numpy) that it publishes to the `scenarios` queue. It also exposes a gRPC server (`FunctionService.GetFuncModel`) so a newly connected client can fetch the function currently in effect. |
| `funcs_consumer/` | Headless client. Consumes the current function (its own `<ip>.models` queue, bound to the fanout, with `x-max-length=1`) and the scenarios (`scenarios` queue with fair dispatch). It parses the function with regex, evaluates it safely with `ast` (no `eval`) and publishes the result to the `results` queue, identifying itself with its IP. |
| `monitor/server/` | Aggregation server. Consumes `results` and `functions`, counts the scenarios pending in the queue and exposes everything through gRPC (`InformationService.GetInformation`). On shutdown with `Ctrl+C` it persists its state to `database/results.csv`. |
| `monitor/app/` | Dashboard (customtkinter + matplotlib) that polls the monitor's gRPC service and shows per-user cards, published functions, total scenarios and historical charts. |
| `monitor/shared_lib/` | Shared library with the compiled `InformationService` protos, installed as an editable dependency in `server` and `app`. |

### Message flow

1. `funcs_servicer` publishes a function to the `exchange.models` fanout; when doing so it purges the `scenarios` queue (old scenarios no longer apply to the new function).
2. Each `funcs_consumer` receives the function through its exclusive `<ip>.models` queue (max length 1: only the latest one matters).
3. `funcs_servicer` publishes scenarios (lists of random values, one per function variable) to `scenarios`; with `prefetch_count=1` each scenario is processed by exactly one client.
4. The client evaluates `f(scenario)` and publishes `{"user": ip, "result": value}` to `results` (persistent messages).
5. `monitor/server` aggregates results per IP and `monitor/app` charts them.

## Requirements

- Python >= 3.14 and [uv](https://docs.astral.sh/uv/)
- A reachable RabbitMQ broker (e.g. `docker run -d -p 5672:5672 -p 15672:15672 rabbitmq:4-management`)

## Configuration

Each component reads its own `.env` (see the `.env.example` in each folder):

| Variable | Used by | Description |
|---|---|---|
| `RABBIT_HOST` | servicer, consumer, monitor/server | RabbitMQ broker host |
| `RABBIT_USER` / `RABBIT_PWD` | servicer, consumer, monitor/server | RabbitMQ credentials |
| `SERVER_HOST` / `SERVER_PORT` | servicer and consumer | Address of the servicer's `FunctionService` gRPC endpoint |
| `SERVER_HOST` / `SERVER_PORT` | monitor/server and monitor/app | Address of the monitor's `InformationService` gRPC endpoint |

> Note: `SERVER_HOST`/`SERVER_PORT` point to different services depending on the component pair; use different ports if you run everything on the same machine.

## Running

Each component runs from its own folder:

```bash
# 1. Function and scenario generator (GUI)
cd funcs_servicer
uv run python -m src.App

# 2. One or more evaluator clients
cd funcs_consumer
uv run python -m src.main

# 3. Monitoring server (cache/aggregator)
cd monitor/server
uv run python -m src.main

# 4. Monitoring dashboard (GUI)
cd monitor/app
uv run python -m src.App
```

## Functions file format

One function per line: `expression,distribution` (the distribution goes after the last comma).

```
f(x,y)=x+y,normal
f(x)=x^2,binomial
f(x,y,z)=x*y*z,exponential
```

- Variables: the ones declared inside the parentheses; the generated scenario will have one value per variable.
- Operators supported by the evaluator: `+ - * / % ^` (power) and unary negation.
- Supported distributions: `normal`, `binomial`, `poisson`, `uniform`, `exponential`, `gamma`, `beta`, `geometric`, `lognormal`.
