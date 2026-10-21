# Flujograma de Preliquidación y Liquidación

Este documento describe el flujo actual ajustado para el proceso de sensibilidad y liquidación final de la base catastral.

## Flujo Objetivo

```mermaid
graph TD
    A[Inicio: Recepción de Insumos] --> B{Preflight & Validación}
    B -- "Inconsistencias de entrada" --> C[Pre-inconsistencias]
    B -- "Ok" --> D[Construcción Base Canónica]
    D --> E[Homologación y Uso Predominante]
    E --> F[Motor de Reglas por Vigencia]
    
    subgraph Motores de Liquidación
        F --> G1[Reglas 2024]
        F --> G2[Reglas 2025]
        F --> G3[Reglas 2026/Actual]
        
        G1 --> H[Liquidación Tablas]
        G2 --> H
        G3 --> H
        
        H --> I[Modelos de Valor]
        I --> J1[Urbano]
        I --> J2[Rural Apartamentos]
    end
    
    J1 --> K[Cálculo Predial y Controles]
    J2 --> K
    
    K --> L{Validación Final}
    L -- "Falta regla o dato" --> M[Post-inconsistencias]
    L -- "Ok" --> N[Escenarios y Comparación]
    
    N --> O[Visualizador de Sensibilidad]
    O --> P{Aprobación Sensibilidad?}
    
    P -- "Ajustar Insumos" --> A
    P -- "Aprobado" --> Q[Congelar Insumos Económicos]
    Q --> R[Liquidación Definitiva en Sistemas]
    R --> S[Aprobación de Avalúos Final]
```

## Diccionario de Variables a Conservar (Matriz)

*Las siguientes variables no deben ser renombradas en ninguna etapa del pipeline para garantizar la compatibilidad con las fuentes de Sistemas:*

- `ID_PREDIO`
- `ZHF`
- `LATITUDE`
- `LONGITUDE`
- `AVALPRED` (o variantes con vigencia `AVALPRED_2025`, `AVAL_CAT_2026`)
- `VM2_COM_*` y `VM2_CAT_*`
- Constantes de destinos `DESTINOS_MODELO_*` (Usos 001, 028, 034 condición 9)

