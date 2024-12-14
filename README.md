# JSON Elemző és Típusregiszter

Ez a repó egy Python projektet tartalmaz, amely a `ply` (Python Lex-Yacc) használatával valósít meg egy JSON elemzőt és típusregisztert. A program JSON struktúrákat elemez, és típusdefiníciókat generál, amelyek támogatják az összetett típusokat és azok egyesítését.

## Funkciók

- **Lexikai és Szintaktikai Elemzés:** JSON szövegek tokenizálása a `ply.lex`, valamint szintaktikai elemzése a `ply.yacc` segítségével.
- **Típusregiszter:** Típusdefiníciókat tart nyilván, amelyeket a JSON objektumokból nyer ki.
- **Típusok Egyesítése:** Attribútumok egyesítése és típuskonfliktusok feloldása elemzés közben.
- **Null Értékek Kezelése:** Kezeli a `null` értékeket, és az attribútumokat szükség esetén nullázhatóként jelöli.
- **Rugalmas Típusdefiníciók:** Támogatja az objektumtípusokat, értékcsomópontokat és listákat, beleértve az összetett és beágyazott attribútumokat.
