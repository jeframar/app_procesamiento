import sys

from app_procesamiento.preparar_calificaciones import crear_parser, ejecutar_finalizacion


def main() -> None:
    parser = crear_parser()
    args = parser.parse_args(["finalizar", *sys.argv[1:]])
    ejecutar_finalizacion(args)


if __name__ == "__main__":
    main()
