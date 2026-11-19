# Pipeline de la fábrica

```mermaid
flowchart LR
  s0["architect<br/>228 s"]:::ok
  s1["qa-unit<br/>273 s"]:::ok
  s2["verify unit<br/>14 s"]:::fail
  s3["security<br/>401 s"]:::ok
  s4["deploy<br/>114 s"]:::ok
  s5["qa-e2e<br/>191 s"]:::ok
  s6["verify unit<br/>18 s"]:::ok
  s7["verify contract<br/>21 s"]:::ok
  s8["verify qa<br/>42 s"]:::fail
  s9["qa-unit<br/>65 s"]:::ok
  s10["verify unit<br/>14 s"]:::ok
  s11["verify contract<br/>15 s"]:::ok
  s12["verify qa<br/>36 s"]:::ok
  s13["verify e2e<br/>25 s"]:::ok
  s14["verify evaluate<br/>15 s"]:::ok
  s15["qa-style<br/>106 s"]:::ok
  s16["triage<br/>358 s"]:::ok
  s17["verify evaluate<br/>3 s"]:::ok
  s0 --> s1
  s1 --> s2
  s2 --> s3
  s2 --> s4
  s2 --> s5
  s3 --> s6
  s4 --> s6
  s5 --> s6
  s6 --> s7
  s7 --> s8
  s8 --> s9
  s9 --> s10
  s10 --> s11
  s11 --> s12
  s12 --> s13
  s13 --> s14
  s14 --> s15
  s15 --> s16
  s16 --> s17
  classDef ok fill:#d4f4dd,stroke:#1e7b3a
  classDef fail fill:#fde2e2,stroke:#a12a2a
```

| # | Paso | Resultado | Segundos |
| --- | --- | --- | --- |
| 1 | architect | pasó | 228 |
| 2 | qa-unit | pasó | 273 |
| 3 | verify unit | falló | 14 |
| 4 | security | pasó | 401 |
| 5 | deploy | pasó | 114 |
| 6 | qa-e2e | pasó | 191 |
| 7 | verify unit | pasó | 18 |
| 8 | verify contract | pasó | 21 |
| 9 | verify qa | falló | 42 |
| 10 | qa-unit | pasó | 65 |
| 11 | verify unit | pasó | 14 |
| 12 | verify contract | pasó | 15 |
| 13 | verify qa | pasó | 36 |
| 14 | verify e2e | pasó | 25 |
| 15 | verify evaluate | pasó | 15 |
| 16 | qa-style | pasó | 106 |
| 17 | triage | pasó | 358 |
| 18 | verify evaluate | pasó | 3 |
