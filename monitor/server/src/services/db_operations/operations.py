import csv
import os
from typing import Dict, Set, Tuple


class DBOperations:
    def __init__(self):
        self.BASE_DIR = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../../")
        )
        self.csv_path = os.path.join(self.BASE_DIR, "database", "results.csv")

    def loadDB(self) -> Tuple[Dict, Set[str]]:
        user_results = {}
        published_functions = set()

        # si el archivo no existe retornamos config default vacia
        if not os.path.exists(self.csv_path):
            return {}, set()

        try:
            with open(self.csv_path, "r", newline="") as file:
                reader = csv.reader(file)
                for row in reader:
                    if not row:
                        continue
                    key = row[0].strip()

                    # functions - fila especial
                    if key == "functions":
                        # Las funciones estan en las columnas siguientes, una por celda
                        for func in row[1:]:
                            func = func.strip()
                            if func:
                                published_functions.add(func)
                        continue

                    # ips y resultados
                    try:
                        results = [float(val.strip()) for val in row[1:] if val.strip()]
                    except ValueError:  # fila con errores (corrupta)
                        continue

                    user_results[key] = {"user": key, "results": results}

        except Exception as e:
            print(f"Error loading DB: {e}")
            return {}, set()
        
        return user_results, published_functions

    def saveDB(self, buffer, functions):
        # solo omitimos el guardado si no hay absolutamente nada que persistir
        if not buffer and not functions:
            return

        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        with open(self.csv_path, "w", newline="") as file:
            writer = csv.writer(file, quoting=csv.QUOTE_ALL)

            # ips y resultados
            for user_ip, data in buffer.items():
                row = [user_ip] + data.get("results", [])
                writer.writerow(row)

            # functions - cada funcion como una celda separada
            if functions:
                writer.writerow(["functions"] + list(functions))
