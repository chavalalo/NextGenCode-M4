# Pipeline de la fábrica

```mermaid
flowchart LR
  s0["architect<br/>184 s"]:::ok
  s1["qa-unit<br/>303 s"]:::ok
  s2["verify unit<br/>20 s"]:::fail
  s3["costs<br/>514 s"]:::ok
  s4["qa-e2e<br/>101 s"]:::ok
  s5["verify unit<br/>20 s"]:::ok
  s6["verify contract<br/>15 s"]:::ok
  s7["verify qa<br/>39 s"]:::fail
  s8["qa-unit<br/>80 s"]:::ok
  s9["verify unit<br/>19 s"]:::ok
  s10["verify contract<br/>14 s"]:::ok
  s11["verify qa<br/>43 s"]:::ok
  s12["verify e2e<br/>26 s"]:::ok
  s13["verify evaluate<br/>11 s"]:::ok
  s14["qa-style<br/>96 s"]:::ok
  s0 --> s1
  s1 --> s2
  s2 --> s3
  s2 --> s4
  s3 --> s5
  s4 --> s5
  s5 --> s6
  s6 --> s7
  s7 --> s8
  s8 --> s9
  s9 --> s10
  s10 --> s11
  s11 --> s12
  s12 --> s13
  s13 --> s14
  classDef ok fill:#d4f4dd,stroke:#1e7b3a
  classDef fail fill:#fde2e2,stroke:#a12a2a
```

| # | Paso | Resultado | Segundos |
| --- | --- | --- | --- |
| 1 | architect | pasó | 184 |
| 2 | qa-unit | pasó | 303 |
| 3 | verify unit | falló | 20 |
| 4 | costs | pasó | 514 |
| 5 | qa-e2e | pasó | 101 |
| 6 | verify unit | pasó | 20 |
| 7 | verify contract | pasó | 15 |
| 8 | verify qa | falló | 39 |
| 9 | qa-unit | pasó | 80 |
| 10 | verify unit | pasó | 19 |
| 11 | verify contract | pasó | 14 |
| 12 | verify qa | pasó | 43 |
| 13 | verify e2e | pasó | 26 |
| 14 | verify evaluate | pasó | 11 |
| 15 | qa-style | pasó | 96 |
