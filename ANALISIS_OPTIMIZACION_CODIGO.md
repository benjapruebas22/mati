# Analisis de Duplicacion y Optimizacion de Codigo

Fecha: 2026-03-26
Proyecto analizado: `mati`

## Totales globales (numeros exactos)

- Lineas **borrables directas**: **922**
- Lineas **optimizables/reusables** (sin borrar funcionalidad): **292**
- Lineas **totales** (borrar + optimizar/reusar): **1214**

## Como se calcularon esos 1214

- `922` = duplicacion exacta y redefiniciones reales detectadas por AST.
- `292` = duplicacion casi identica medida con LCS (coincidencia estructural), descontando overhead minimo de extraccion a helper.

Formula total:

`1214 = 922 + 292`

## SQL innecesaria / optimizable (total global)

- Consultas SQL literales unicas detectadas: `668`
- Consultas SQL repetidas (mismo texto en 2+ lugares): `83`
- Ocurrencias SQL duplicadas evitables: **157**
- `SELECT *` detectados: `46`
- SELECT con `date(columna)` (impacta indices) detectados: `30`

## Impacto esperado al aplicar estas optimizaciones

- Menos codigo duplicado y menos riesgo de comportamiento inconsistente.
- Menos consultas por request en dashboard (hay patron N+1 fuerte en `modules/sst.py`).
- Mejor aprovechamiento de indices si se reemplaza `date(columna)` por comparaciones directas de fecha ISO.

## Prioridad recomendada (para capturar el impacto rapido)

1. Eliminar duplicacion exacta (las **922** lineas borrables).
2. Consolidar funciones casi identicas (las **292** lineas reusables).
3. Centralizar SQL repetida (las **157** ocurrencias evitables).
4. Corregir filtros de fecha y agregar indices en `viajes`, `combustible`, `personal_sede`, `matafuegos_sede`.
