import os
import threading
import time
from concurrent import futures
from tkinter import filedialog

import customtkinter as ctk
import grpc
from dotenv import load_dotenv

from src.protos import function_service_pb2_grpc
from src.rabbitmq.connection import Connection
from src.services.function_servicer import FunctionServicer
from src.services.functions_in_file import FileFunctionReader
from src.services.scenario_generator import ScenarioGenerator

# Paleta de colores
COLORS = {
    "background": "#111822",
    "panel": "#243347",
    "primary": "#4299E1",
    "accent_green": "#00F5A0",
    "accent_red": "#E53E3E",
    "text_white": "#FFFFFF",
    "text_muted": "#92a9c8",
    "input_bg": "#1A2634",
}


class Dashboard(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        super().__init__()

        self.title("Generador de Funciones y Escenarios")
        self.geometry("1200x800")
        self.configure(fg_color=COLORS["background"])

        # variables de entorno
        load_dotenv()

        # servicios
        self.function_reader = FileFunctionReader()
        self.scenario_generator = None
        self.rabbitmq_connection = None

        # variables para ejecucion
        self.is_running = False
        self.gRPC_server = None

        # variables de UI
        self.function_interval = 1
        self.scenario_interval = 1
        self.current_function = ". . ."
        self.current_distribution = ". . ."
        self.current_scenario = []
        self.current_sample_size = 1
        self.publishing_thread = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # header
        self.create_header()

        # panel Izquierdo
        self.left_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.left_frame.grid(row=1, column=0, sticky="nsew", padx=(40, 20), pady=20)
        self.create_left_column()

        # panel Derecho
        self.right_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.right_frame.grid(row=1, column=1, sticky="nsew", padx=(20, 40), pady=20)
        self.create_right_column()

    def create_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=40, pady=(40, 20)
        )

        title_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_frame.pack(side="left")
        ctk.CTkLabel(
            title_frame,
            text="Generador de Funciones y Escenarios",
            font=("Roboto", 28, "bold"),
            text_color=COLORS["text_white"],
        ).pack(anchor="w")

        controls_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        controls_frame.pack(side="right")

        self.stop_btn = ctk.CTkButton(
            controls_frame,
            text="Iniciar publicacion",
            fg_color=COLORS["accent_green"],
            hover_color="#00d185",
            text_color="black",
            font=("Roboto", 13, "bold"),
            height=40,
            corner_radius=8,
            command=self.toggle_process,
        )
        self.stop_btn.pack(side="left")
        self.is_running = False

    def create_left_column(self):
        ctk.CTkLabel(
            self.left_frame,
            text="Monitor y Configuracion",
            font=("Roboto", 20, "bold"),
            text_color=COLORS["text_white"],
        ).pack(anchor="w", pady=(0, 20))

        self.create_card(self.left_frame, self.card_content_process)
        self.create_card(
            self.left_frame,
            lambda p: self.card_content_slider(
                p, "Intervalo de Funciones", "seg", 1, 30
            ),
        )
        self.create_card(self.left_frame, self.card_content_distribution)
        self.create_card(
            self.left_frame,
            lambda p: self.card_content_slider(
                p, "Intervalo de Generacion", "seg", 1, 30
            ),
        )

    def create_right_column(self):
        ctk.CTkLabel(
            self.right_frame,
            text="Carga de Funciones",
            font=("Roboto", 20, "bold"),
            text_color=COLORS["text_white"],
        ).pack(anchor="w", pady=(0, 20))

        ctk.CTkButton(
            self.right_frame,
            text="Cargar Archivo Funciones",
            fg_color=COLORS["primary"],
            font=("Roboto", 14, "bold"),
            height=45,
            corner_radius=8,
            command=self.load_file,
        ).pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            self.right_frame,
            text="Vista Previa del Contenido",
            font=("Roboto", 18, "bold"),
            text_color=COLORS["text_white"],
        ).pack(anchor="w", pady=(0, 10))

        preview_textbox = ctk.CTkTextbox(
            self.right_frame,
            fg_color=COLORS["panel"],
            text_color=COLORS["text_muted"],
            font=("Courier New", 12),
            corner_radius=10,
            border_width=1,
            border_color="#334866",
        )
        preview_textbox.pack(fill="both", expand=True)

        sample_text = ". . ."
        preview_textbox.insert("0.0", sample_text)
        preview_textbox.configure(state="disabled")

        self.preview_textbox = preview_textbox

    def create_card(self, parent, content_func):
        card = ctk.CTkFrame(
            parent,
            fg_color=COLORS["panel"],
            corner_radius=12,
            border_width=1,
            border_color="gray25",
        )
        card.pack(fill="x", pady=(0, 20))
        content_func(card)

    def card_content_process(self, parent):
        parent.configure(fg_color=COLORS["panel"])
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(padx=20, pady=20, fill="x")

        ctk.CTkLabel(
            frame,
            text="FUNCION ACTUAL CARGADA",
            font=("Roboto", 11, "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w")
        self.function_label = ctk.CTkLabel(
            frame,
            text=". . .",
            font=("Roboto", 24, "bold"),
            text_color=COLORS["primary"],
        )
        self.function_label.pack(anchor="w", pady=(5, 5))

    def card_content_slider(self, parent, label_text, unit, min_val, max_val):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(padx=20, pady=20, fill="x")

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            header, text=label_text, font=("Roboto", 14, "bold"), text_color="white"
        ).pack(side="left")

        val_box = ctk.CTkFrame(
            header,
            fg_color=COLORS["background"],
            corner_radius=6,
            border_width=1,
            border_color="gray30",
        )
        val_box.pack(side="right")

        lbl_val = ctk.CTkLabel(
            val_box, text=str(min_val), width=30, font=("Roboto", 13, "bold")
        )
        lbl_val.pack(side="left", padx=(5, 0), pady=2)
        ctk.CTkLabel(
            val_box, text=unit, font=("Roboto", 11), text_color=COLORS["text_muted"]
        ).pack(side="left", padx=(2, 5))

        def update_value(v):
            val = int(v)
            lbl_val.configure(text=str(val))
            if label_text == "Intervalo de Funciones":
                self.function_interval = val
            elif label_text == "Intervalo de Generacion":
                self.scenario_interval = val

        slider = ctk.CTkSlider(
            frame,
            from_=min_val,
            to=max_val,
            number_of_steps=max_val - min_val if max_val > min_val else 1,
            button_color=COLORS["primary"],
            progress_color=COLORS["primary"],
            command=update_value,
        )
        slider.set(min_val)
        slider.pack(fill="x")

    def card_content_distribution(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(padx=20, pady=20, fill="both", expand=True)

        ctk.CTkLabel(
            frame,
            text="FUNCION DE DISTRIBUCION",
            font=("Roboto", 10, "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w")
        self.distribution_label = ctk.CTkLabel(
            frame,
            text=". . .",
            font=("Roboto", 18, "bold"),
            text_color=COLORS["primary"],
        )
        self.distribution_label.pack(anchor="w", pady=(2, 15))

        ctk.CTkLabel(
            frame,
            text="ESCENARIOS PUBLICADOS",
            font=("Roboto", 10, "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", pady=(10, 5))

        self.scenario_textbox = ctk.CTkTextbox(
            frame,
            fg_color=COLORS["background"],
            text_color=COLORS["text_muted"],
            font=("Courier New", 10),
            corner_radius=8,
            border_width=1,
            border_color="#334866",
            height=150,
        )
        self.scenario_textbox.pack(fill="both", expand=True)
        self.scenario_textbox.insert("0.0", "Esperando escenarios...")
        self.scenario_textbox.configure(state="disabled")

    def show_error_dialog(self, title, message):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("450x220")
        dialog.configure(fg_color=COLORS["background"])
        dialog.resizable(False, False)

        dialog.transient(self)
        dialog.update_idletasks()

        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_width = self.winfo_width()
        main_height = self.winfo_height()

        dialog_width = dialog.winfo_width()
        dialog_height = dialog.winfo_height()

        x = main_x + (main_width - dialog_width) // 2
        y = main_y + (main_height - dialog_height) // 2

        dialog.geometry(f"+{x}+{y}")

        content_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=30, pady=30)

        ctk.CTkLabel(
            content_frame,
            text=message,
            font=("Roboto", 13),
            text_color=COLORS["text_white"],
            wraplength=390,
            justify="center",
        ).pack(pady=(0, 20))

        ctk.CTkButton(
            content_frame,
            text="OK",
            fg_color=COLORS["accent_red"],
            hover_color="#cc3333",
            command=dialog.destroy,
            width=100,
        ).pack()

        try:
            dialog.wait_visibility()
            dialog.grab_set()
        except Exception:
            pass

    def load_file(self):
        filename = filedialog.askopenfilename(
            title="Seleccionar archivo de funciones",
            filetypes=(("Archivos de texto", "*.txt"), ("Todos los archivos", "*.*")),
        )

        if filename:
            try:
                self.function_reader.load_functions(filename)

                if not self.function_reader.stored_functions:
                    self.show_error_dialog(
                        "Error: Archivo vacio o invalido",
                        "El archivo no contiene funciones validas",
                    )
                    return

                self.preview_textbox.configure(state="normal")
                self.preview_textbox.delete("0.0", "end")

                try:
                    with open(filename, "r") as f:
                        content = f.read()
                        self.preview_textbox.insert("0.0", content)
                except Exception as e:
                    self.preview_textbox.insert("0.0", f"Error cargando archivo: {e}")
                self.preview_textbox.configure(state="disabled")

                distributions = list(set(self.function_reader.stored_func_scenarios))
                self.scenario_generator = ScenarioGenerator(distributions)

            except Exception:
                self.show_error_dialog(
                    "Error al cargar archivo",
                    "No se pudo cargar el archivo de funciones",
                )

    def parse_function_variables(self, function_str: str) -> int:
        import re

        match = re.search(r"f\((.*?)\)", function_str)
        if match:
            vars_str = match.group(1)
            variables = [v.strip() for v in vars_str.split(",") if v.strip()]
            return len(variables)
        return 1

    def start_grpc_server(self):
        # si ya hay un server corriendo, no hacemos nada
        if self.gRPC_server is not None:
            return

        # publicamos servicio FunctionServicer
        self.gRPC_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        servicer = FunctionServicer(self.function_reader)
        function_service_pb2_grpc.add_FunctionServiceServicer_to_server(
            servicer, self.gRPC_server
        )

        bind_addr = f"{os.getenv('SERVER_HOST')}:{os.getenv('SERVER_PORT')}"
        self.gRPC_server.add_insecure_port(bind_addr)
        self.gRPC_server.start()

    def stop_grpc_server(self, grace: int = 0):
        if self.gRPC_server is None:
            return
        self.gRPC_server.stop(grace).wait()
        self.gRPC_server = None

    def toggle_process(self):
        if not self.function_reader.stored_functions:
            self.show_error_dialog(
                "Error: No hay funciones cargadas",
                "Por favor, carga un archivo de funciones antes de iniciar el envio",
            )
            return

        self.is_running = not self.is_running
        if self.is_running:
            self.stop_btn.configure(
                text="Parar publicacion",
                fg_color=COLORS["accent_red"],
                hover_color="#cc3333",
                text_color="white",
            )
            if self.rabbitmq_connection is None:
                try:
                    self.rabbitmq_connection = Connection()
                except Exception:
                    self.is_running = False
                    self.stop_btn.configure(
                        text="Iniciar publicacion",
                        fg_color=COLORS["accent_green"],
                        hover_color="#00d185",
                        text_color="black",
                    )
                    self.show_error_dialog(
                        "Error de conexion con RabbitMQ",
                        "No se pudo conectar con RabbitMQ",
                    )
                    return

                # Inciar servidor para informar sobre la funcion del modelo actual
                try:
                    self.start_grpc_server()
                except Exception as e:
                    self.is_running = False
                    self.stop_btn.configure(
                        text="Iniciar publicacion",
                        fg_color=COLORS["accent_green"],
                        hover_color="#00d185",
                        text_color="black",
                    )
                    self.show_error_dialog(
                        "Error gRPC",
                        f"No se pudo iniciar el servidor gRPC\n{e}",
                    )
                    self.stop_grpc_server()
                    return

            if self.publishing_thread is None or not self.publishing_thread.is_alive():
                self.publishing_thread = threading.Thread(
                    target=self.publish_loop, daemon=True
                )
                self.publishing_thread.start()
        else:
            self.stop_btn.configure(
                text="Iniciar publicacion",
                fg_color=COLORS["accent_green"],
                hover_color="#00d185",
                text_color="black",
            )
            self.function_label.configure(text=". . .")
            self.distribution_label.configure(text=". . .")
            self.scenario_textbox.configure(state="normal")
            self.scenario_textbox.delete("0.0", "end")
            self.scenario_textbox.insert("0.0", "Esperando escenarios...")
            self.scenario_textbox.configure(state="disabled")

    def publish_loop(self):
        last_function_time = 0
        last_scenario_time = 0
        function = None
        scenario = None

        while self.is_running:
            current_time = time.time()

            # Publicar nueva funcion si es tiempo (solo si intervalo > 0)
            if (
                self.function_interval > 0
                and current_time - last_function_time >= self.function_interval
            ):
                try:
                    function = self.function_reader.read_function()
                    distribution = self.function_reader.read_scenario()

                    if function:
                        try:
                            self.rabbitmq_connection.public_function(function)
                        except Exception:
                            self.is_running = False
                            # descartamos la conexion muerta para forzar
                            # una reconexion en el siguiente inicio
                            self.rabbitmq_connection = None
                            self.after(
                                0,
                                lambda: self.show_error_dialog(
                                    "Error de Publicacion",
                                    "Se perdio la conexion con RabbitMQ",
                                ),
                            )
                            self.after(
                                0,
                                lambda: self.stop_btn.configure(
                                    text="Iniciar publicacion",
                                    fg_color=COLORS["accent_red"],
                                    hover_color="#cc3333",
                                    text_color="white",
                                ),
                            )
                            return

                        # parseamos cuantas variables tiene la func actual
                        num_variables = self.parse_function_variables(function)

                        # actualizamos variables de UI
                        self.current_function = function
                        self.current_distribution = distribution
                        self.current_sample_size = num_variables
                        self.after(0, self.update_function_display)

                        last_function_time = current_time
                        last_scenario_time = current_time

                except Exception as e:
                    self.is_running = False
                    self.after(
                        0, lambda err=e: self.show_error_dialog("Error", f"{err}")
                    )
                    self.after(
                        0,
                        lambda: self.stop_btn.configure(
                            text="Iniciar Publicacion",
                            fg_color=COLORS["accent_red"],
                            hover_color="#cc3333",
                            text_color="white",
                        ),
                    )

            if (
                self.scenario_interval > 0
                and self.current_distribution != ". . ."
                and current_time - last_scenario_time >= self.scenario_interval
            ):
                try:
                    scenario = self.scenario_generator.get_scenario(
                        self.current_sample_size, self.current_distribution
                    )

                    if scenario and function:
                        self.current_scenario = scenario

                        try:
                            self.rabbitmq_connection.public_scenario(scenario)
                            self.after(0, self.update_scenario_display)
                        except Exception:
                            self.is_running = False
                            # descartamos la conexion muerta para forzar
                            # una reconexion en el siguiente inicio
                            self.rabbitmq_connection = None
                            self.after(
                                0,
                                lambda: self.show_error_dialog(
                                    "Error de Publicacion",
                                    "Se perdio la conexion con RabbitMQ",
                                ),
                            )
                            self.after(
                                0,
                                lambda: self.stop_btn.configure(
                                    text="Iniciar publicacion",
                                    fg_color=COLORS["accent_red"],
                                    hover_color="#cc3333",
                                    text_color="white",
                                ),
                            )
                            return
                    elif not scenario:
                        error_msg = f"No se pudo generar escenario.\n\nDistribucion '{
                            self.current_distribution
                        }' no reconocida."
                        self.after(
                            0,
                            lambda msg=error_msg: self.update_scenario_error_display(
                                msg
                            ),
                        )

                    last_scenario_time = current_time

                except Exception as e:
                    self.is_running = False
                    self.after(
                        0, lambda err=e: self.show_error_dialog("Error", f"{err}")
                    )
                    self.after(
                        0,
                        lambda: self.stop_btn.configure(
                            text="Iniciar Publicacion",
                            fg_color=COLORS["accent_red"],
                            hover_color="#cc3333",
                            text_color="white",
                        ),
                    )

            time.sleep(0.1)

    def update_function_display(self):
        self.function_label.configure(text=self.current_function)
        self.distribution_label.configure(text=self.current_distribution)

    def update_scenario_display(self):
        if self.current_scenario:
            rounded = [round(x, 2) for x in self.current_scenario]
            scenario_text = ", ".join(map(str, rounded))
            scenario_text = f"[{scenario_text}]"
            scenario_text += f"\n\nTotal de valores: {len(self.current_scenario)}"

            self.scenario_textbox.configure(
                state="normal", text_color=COLORS["text_muted"]
            )
            self.scenario_textbox.delete("0.0", "end")
            self.scenario_textbox.insert("0.0", scenario_text)
            self.scenario_textbox.configure(state="disabled")

    def update_scenario_error_display(self, error_message):
        self.scenario_textbox.configure(state="normal", text_color=COLORS["accent_red"])
        self.scenario_textbox.delete("0.0", "end")
        self.scenario_textbox.insert("0.0", error_message)
        self.scenario_textbox.configure(state="disabled")


if __name__ == "__main__":
    app = Dashboard()
    app.mainloop()
