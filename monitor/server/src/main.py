import os
import threading
import time
from concurrent import futures
from pprint import pprint

import grpc
from dotenv import load_dotenv
from shared_lib.protos import information_service_pb2_grpc

from src.rabbitmq.connection import Connection
from src.services.db_operations.operations import DBOperations
from src.services.information_servicer import InformationServicer


def consume_results(ip_results: dict):
    connection = Connection()

    initial_results = connection.get_initial_messages("results")
    for msg in initial_results:
        user_ip = msg.get("user")
        result = msg.get("result")
        ip_results.setdefault(user_ip, {"user": user_ip, "results": []})[
            "results"
        ].append(result)

    for msg in connection.message_stream("results"):
        if not msg:
            continue

        print(f"Resultado consumido: {msg}")
        user_ip = msg.get("user")
        result = msg.get("result")

        ip_results.setdefault(user_ip, {"user": user_ip, "results": []})[
            "results"
        ].append(result)


def consume_functions(functions: set):
    connection = Connection()
    for func in connection.message_stream("functions"):
        if not func:
            continue

        if func in functions:
            continue

        print(f"Funcion recibida: {func}")
        functions.add(func)


def update_scenarios_count(scenarios: dict, stop_event: threading.Event):
    connection = Connection()
    while not stop_event.is_set():
        try:
            scenarios["value"] = connection.get_amount_scenarios()
        except Exception as e:
            print(f"Error actualizando escenarios: {e}")
        time.sleep(1)  # Actualiza cada segundo


def main():
    amount_scenarios = {"value": 0}
    connection = Connection()
    load_dotenv()

    buffer_results, functions = DBOperations().loadDB()
    if buffer_results:
        print("Resultados en cache cargados")
        pprint(buffer_results)
    if functions:
        print("Funciones:", functions)

    # Evento para detener el thread
    stop_event = threading.Event()

    # threads separados para consumir cada cola
    results_thread = threading.Thread(
        target=consume_results, args=(buffer_results,), daemon=True
    )

    functions_thread = threading.Thread(
        target=consume_functions, args=(functions,), daemon=True
    )

    scenarios_thread = threading.Thread(
        target=update_scenarios_count, args=(amount_scenarios, stop_event), daemon=True
    )

    # publicamos servicio InformationServicer
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    information_service_pb2_grpc.add_InformationServiceServicer_to_server(
        InformationServicer(
            buffer=buffer_results, functions=functions, scenarios=amount_scenarios
        ),
        server,
    )

    server_address = f"{os.getenv('SERVER_HOST')}:{os.getenv('SERVER_PORT')}"
    server.add_insecure_port(server_address)

    # Iniciar server y todos los threads
    server.start()
    results_thread.start()
    functions_thread.start()
    scenarios_thread.start()

    print(f"Iniciado server consumidor/cache de resultados en {server_address}")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\nTerminando servidor, guardando base de datos...")
        stop_event.set()
        DBOperations().saveDB(buffer_results, functions)
        connection.close_connection()
        server.stop(0)


if __name__ == "__main__":
    main()
