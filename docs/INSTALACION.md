# Guía de instalación de Gwensper

Esta guía es para instalar Gwensper en Windows sin saber programar. Solo necesitas descargar un archivo y darle doble clic.

## Requisitos

- Windows 10 u 11 de 64 bits.
- Conexión a internet durante la instalación.
- Espacio libre en disco:
  - **Sin tarjeta gráfica NVIDIA:** unos 1.5 GB (librerías y el modelo de voz `small`).
  - **Con tarjeta gráfica NVIDIA:** unos 4.5 GB (se agregan las librerías de aceleración y el modelo `large-v3-turbo`, más preciso).
- Un micrófono.

No necesitas tener Python: si no lo tienes, el instalador lo instala por ti.

## Instalar

1. Descarga el instalador: **[Instalar-Gwensper.bat](https://github.com/whosluisnoris/gwensper/releases/latest/download/Instalar-Gwensper.bat)**.
2. Abre la carpeta de Descargas y haz doble clic en **Instalar-Gwensper.bat**.
3. Windows probablemente mostrará un aviso azul: *«Windows protegió tu PC»*. Es normal con programas descargados que no están firmados. Haz clic en **Más información** y luego en **Ejecutar de todas formas**.
4. Se abre una ventana negra que muestra cada paso. Déjala trabajar; tarda entre 5 y 15 minutos según tu conexión:
   - Busca Python y, si no hay uno compatible, lo instala.
   - Instala Gwensper y sus librerías.
   - Si detecta una tarjeta gráfica NVIDIA, instala la aceleración para usarla.
   - Descarga el modelo de voz.
   - Crea el acceso directo en el menú Inicio.
5. Al terminar, Gwensper se abre solo. Presiona una tecla para cerrar la ventana del instalador.

Todo queda en `%LOCALAPPDATA%\Programs\Gwensper`, separado del resto de tu computadora.

## Primer uso

1. Abre Gwensper desde el menú Inicio (escribe «Gwensper»).
2. Pon el cursor donde quieras escribir: un documento, un chat, el navegador.
3. Presiona **Ctrl+Alt+D** y habla. Aparece un indicador flotante mientras te escucha.
4. Presiona **Ctrl+Alt+D** otra vez para terminar.

Si Windows pregunta si Gwensper puede usar el micrófono, acepta.

Al cerrar la ventana de Gwensper, sigue funcionando en la bandeja del sistema, junto al reloj. Para salir del todo: clic derecho en su icono → **Salir**.

## Actualizar

Vuelve a ejecutar **Instalar-Gwensper.bat**. Instala la última versión y conserva tu configuración y tus modelos. Si Gwensper está abierto, el instalador lo cierra.

## Desinstalar

**Configuración de Windows → Aplicaciones → Aplicaciones instaladas → Gwensper → Desinstalar.**

Al desinstalar, te pregunta si también quieres borrar tu configuración y los modelos de voz descargados.

## Problemas frecuentes

**El texto no aparece en una aplicación en particular.**
Windows no deja que los programas normales escriban en aplicaciones abiertas «como administrador». Abre esa aplicación de forma normal, o prueba en *Dictado → Cómo escribir → Pegar la frase completa*.

**No me escucha o escribe cosas sin sentido.**
- Revisa *Configuración de Windows → Privacidad y seguridad → Micrófono*: deben estar activados «Acceso al micrófono» y «Permitir que las aplicaciones de escritorio accedan al micrófono».
- En Gwensper → *Dictado*, elige el micrófono correcto y el idioma en el que hablas.
- Si capta el ruido de fondo, sube el **Umbral de voz**.

**Dice que el atajo está en uso.**
Otra aplicación ya usa Ctrl+Alt+D. En Gwensper → *Dictado → Atajo para dictar*, haz clic en el campo y presiona otra combinación.

**Tengo una tarjeta NVIDIA pero Gwensper usa el procesador.**
Actualiza el controlador de tu tarjeta desde [nvidia.com](https://www.nvidia.com/Download/index.aspx) y vuelve a ejecutar el instalador. En *Modelos* puedes ver si Gwensper está usando la GPU o la CPU.

**Va lento.**
Sin tarjeta NVIDIA, prueba en *Modelos* con `base` o `tiny`: son más rápidos, aunque algo menos precisos.

**El instalador muestra un error.**
Revisa tu conexión a internet y vuelve a ejecutarlo. Si sigue fallando, [abre un issue](https://github.com/whosluisnoris/gwensper/issues) con una captura de la ventana.

## Instalación avanzada (con pip)

Si ya usas Python 3.10–3.13 de 64 bits:

```powershell
pip install https://github.com/whosluisnoris/gwensper/archive/refs/heads/main.zip
gwensper
```

Con tarjeta NVIDIA:

```powershell
pip install "gwensper[cuda] @ https://github.com/whosluisnoris/gwensper/archive/refs/heads/main.zip"
```

El instalador acepta opciones si lo ejecutas desde PowerShell. Por ejemplo, `-Mode cpu` para no instalar la aceleración NVIDIA, o `-InstallDir` para elegir otra carpeta. Están descritas al principio de [install/install.ps1](../install/install.ps1).
