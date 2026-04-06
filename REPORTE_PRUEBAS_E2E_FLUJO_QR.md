# Reporte de Pruebas E2E - Flujo QR Camionetas

- Fecha/hora: 2026-04-01 10:58:43
- Entorno: Flask test_client (automatizado)
- DB usada para pruebas: `C:\Users\Usuario 1\Desktop\Nueva carpeta\mati\_tmp_mpd_e2e.db` (copia temporal de `mpd.db`)
- Vehiculo probado: `AE856GE` (G-02)
- Personal ID: `1`
- Destino ID: `1`
- KM sugerido: `95809.0`
- Viaje previo detectado: id `426` / chofer `Agustin Gonzalez`

## Resumen
- Total: **12**
- OK: **12**
- Fallidos: **0**

## Detalle por caso
1. **PASS** - QR sin login redirige a login conservando patente
   - Evidencia: status=302 location=/login?next=/vehiculos/viajes/chofer?patente%3DAE856GE
2. **PASS** - Login chofer vuelve al flujo con patente
   - Evidencia: status=302 location=/vehiculos/viajes/chofer?patente=AE856GE
3. **PASS** - Pantalla flujo chofer carga con boton Informar diferencia
   - Evidencia: status=200
4. **PASS** - POST iniciar viaje responde redireccion
   - Evidencia: status=302 location=/vehiculos/viajes/chofer?patente=AE856GE
5. **PASS** - Viaje iniciado guarda ajuste KM informado
   - Evidencia: trip_id=427 estado=ABIERTO km_ini=95816.0 km_ini_original=95809.0 prev_chofer_id=53
6. **PASS** - Finalizar con KM menor rechaza cierre
   - Evidencia: status=302 estado=ABIERTO km_fin=None
7. **PASS** - Finalizar con KM valido cierra viaje y calcula recorrido
   - Evidencia: status=302 estado=CERRADO km_fin=95825.2 recorrido=9.19999999999709
8. **PASS** - Chofer en control diario redirige a flujo exclusivo
   - Evidencia: status=302 location=/vehiculos/viajes/chofer?patente=AE856GE
9. **PASS** - Chofer no puede acceder a /vehiculos/qr
   - Evidencia: status=302 location=/acceso-denegado
10. **PASS** - Login usuario full exitoso
   - Evidencia: status=302 location=/
11. **PASS** - Usuario full accede a /vehiculos/qr
   - Evidencia: status=200
12. **PASS** - Control diario muestra badge de KM informado con tooltip
   - Evidencia: status=200 contiene_badge=True contiene_tooltip=True prev_chofer_ref=Agustin Gonzalez

## Diagnostico
Todas las pruebas pertinentes del flujo solicitado pasaron correctamente en entorno automatizado.
