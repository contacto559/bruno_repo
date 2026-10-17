<!-- Reference copy from workspace-julio. VPS paths in this file are Julio runtime, not Bruno. Bruno credentials live in this workspace .env. -->

# Pautas inviolables — Recepciones y entregas Acopen

Estas reglas son normativas para cualquier tarea de logística en Julio.

## Regla madre

Antes de actuar sobre una recepción, entrega o guía, Julio debe distinguir primero si se trata de:

- una **salida a cliente** (`WH/OUT`, GDE de venta), o
- una **recepción de proveedor** (`WH/IN`, compra)

Si el contexto no está claro, debe aclararlo antes de ejecutar nada.

## Alcance

Estas pautas cubren:

- confirmación de venta
- abastecimiento
- recepción de compra
- preparación de salida
- entrega a cliente
- GDE y DTE asociados
- validaciones previas a `button_validate`
- trazabilidad documental

## Modelos y campos críticos

Modelos clave:

- `sale.order`
- `purchase.order`
- `stock.picking`
- `stock.move`
- `stock.move.line`

Campos críticos:

- `state`
- `picking_type_code`
- `scheduled_date`
- `date_done`
- `user_id`
- `qty_done`
- `l10n_latam_document_number`
- `l10n_cl_dte_status`
- `l10n_cl_sii_send_ident`

## Reglas operativas inviolables

### Recepciones proveedor

- Nunca usar el flujo de GDE de cliente para recepciones proveedor
- Validar la recepción solo con confirmación explícita del usuario
- Si llega una referencia de guía proveedor, primero intentar mapearla a un `WH/IN` o a una factura proveedor

### Entregas cliente

- La GDE aplica al flujo de salida hacia cliente
- El picking debe estar listo para el flujo definido por Odoo y Chile
- Crear, enviar, verificar o imprimir una guía cambia estado y requiere confirmación previa

#### REGLA INVIOLABLE — No recrear GDE ya aceptada

**Antes de ejecutar `create_delivery_guide()`**, leer siempre `l10n_cl_dte_status` del `stock.picking`:

- Si `accepted` o `objected` → **TERMINANTEMENTE PROHIBIDO** ejecutar `create_delivery_guide()`. No existen excepciones. En su lugar, solo imprimir el PDF con `print_delivery_guide_pdf()` (descarga por sesión web + CSRF).
- Si `ask_for_status` → no recrear; usar `l10n_cl_verify_dte_status()` para consultar estado.
- Si `not_sent`, `rejected`, `cancelled` o vacío → se puede ejecutar `create_delivery_guide()`.

Ejecutar `create_delivery_guide()` sobre una guía aceptada la destruye: resetea el estado a `not_sent`, borra el DTE firmado y los adjuntos legales. El resultado es una guía rechazada.

### Validaciones previas

- La operación debe ejecutarse en el ambiente correcto: producción o test
- Deben incluirse `allowed_company_ids` y, si aplica, `company_id`
- No validar una transferencia vacía o incoherente
- No ocultar errores funcionales detrás de una explicación técnica

## Flujo alternativo con foto de GDE

Si el usuario entrega evidencia documental o foto:

- extraer folio
- extraer fecha
- extraer emisor y receptor
- extraer referencia comercial
- extraer líneas y cantidades cuando sea posible
- usar eso para buscar el picking o el documento relacionado

El objetivo es unir evidencia documental con el registro Odoo correcto para trazabilidad.

## Política de respuesta

- Con usuarios no técnicos, responder en lenguaje simple
- Si el usuario pide detalle técnico, explicarlo después de aclarar el impacto operativo
- Antes de cualquier acción que cambie estado, resumir y pedir confirmación

## Regla de lectura obligatoria

Para cualquier tarea de recepción o entrega, este archivo se lee primero y prevalece sobre notas secundarias.
