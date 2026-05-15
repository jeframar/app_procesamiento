from tkinter import Tk
from tkinter.filedialog import askdirectory, askopenfilename


def _ocultar_root_tk() -> Tk:
    root = Tk()
    root.withdraw()
    return root


def seleccionar_archivo(titulo: str, tipos=None) -> str:
    root = _ocultar_root_tk()
    try:
        ruta = askopenfilename(title=titulo, filetypes=tipos)
    finally:
        root.destroy()

    if not ruta:
        raise ValueError("No se selecciono archivo.")
    return ruta


def seleccionar_archivo_opcional(titulo: str, tipos=None) -> str | None:
    root = _ocultar_root_tk()
    try:
        ruta = askopenfilename(title=titulo, filetypes=tipos)
    finally:
        root.destroy()

    return ruta or None


def seleccionar_carpeta(titulo: str) -> str:
    root = _ocultar_root_tk()
    try:
        ruta = askdirectory(title=titulo)
    finally:
        root.destroy()

    if not ruta:
        raise ValueError("No se selecciono carpeta.")
    return ruta

