import sys

from app_procesamiento.preparar_calificaciones import crear_parser, ejecutar_limpieza


def main() -> None:
    parser = crear_parser()
    args = parser.parse_args(["limpiar", *sys.argv[1:]])
    ejecutar_limpieza(args)


if __name__ == "__main__":
    main()
