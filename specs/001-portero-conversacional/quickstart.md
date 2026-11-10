# Quickstart: validar el portero conversacional

Requisitos: `.venv` del proyecto. Las pruebas no consultan Power BI. Ver
[contrato](contracts/portero.md) y [modelo de datos](data-model.md).

## 1. Unitarias, banco y barrido ciego (solo reglas)

```powershell
.venv\Scripts\python.exe -X utf8 -m unittest tests.portero.test_portero
```
Esperado: OK. Incluye 0 intercepciones en todas las preguntas de `tests/real/banco_*.json`
y ≥75 % de conversacionales del banco reconocidos.

## 2. Con MiniLM real

```powershell
.venv\Scripts\python.exe -X utf8 -m unittest tests.portero.test_portero_minilm
```
Esperado: OK (≥90 % reconocidos, 0 falsos positivos) o `skipped` si el modelo no está en caché.

## 3. Integración con el motor (simulador)

```powershell
.venv\Scripts\python.exe -X utf8 -m unittest tests.portero.test_motor_portero tests.feedback.test_registro tests.sim.test_smoke
```
Esperado: OK. «¿Cómo estás hoy?», «hola», «gracias», «¿quién eres?», «¿qué puedes hacer?» →
ruta `conversacion`, 0 DAX; «gracias» no rompe «¿y en octubre?»; contrapregunta pendiente respetada.

## 4. Manual en la app

`streamlit run app.py` → escribir las 5 frases; con modo diagnóstico, ver «Ruta: conversacion»
y el razonamiento «Mensaje conversacional». Luego una pregunta de datos y «¿y en octubre?».

## 5. Bancos reales y golden master (con permiso del usuario; Power BI solo lectura)

```powershell
$env:POWERBI_AUTH="device_code"; .venv\Scripts\python.exe -X utf8 -m tests.real.correr_todo
.venv\Scripts\python.exe -X utf8 -m tests.resolution.test_golden
```
Esperado: mismos porcentajes que antes (96 / 80 / 22 / multi-turno).
