from app.parsers.tei import parse_tei

TEI = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="en">
  <teiHeader>
    <fileDesc>
      <titleStmt><title type="main">Example Paper</title></titleStmt>
      <publicationStmt><p>Test</p></publicationStmt>
      <sourceDesc>
        <biblStruct>
          <analytic>
            <author><persName><forename>Ada</forename><surname>Lovelace</surname></persName></author>
          </analytic>
          <idno type="DOI">10.1000/example</idno>
        </biblStruct>
      </sourceDesc>
    </fileDesc>
    <profileDesc><abstract><p>An abstract.</p></abstract></profileDesc>
  </teiHeader>
  <text>
    <body>
      <div xml:id="s1"><head n="1">Introduction</head><p>Hello world.</p></div>
      <formula xml:id="f1" n="1" coords="1,1,2,3,4">E = mc²</formula>
      <figure xml:id="t1" type="table" coords="1,1,2,3,4">
        <head>Table 1</head><figDesc>Results</figDesc><table><row><cell>A</cell></row></table>
      </figure>
    </body>
    <back>
      <listBibl>
        <biblStruct xml:id="b1"><analytic><title>Reference</title></analytic></biblStruct>
      </listBibl>
    </back>
  </text>
</TEI>
"""


def test_parse_tei_extracts_core_structures():
    parsed = parse_tei(TEI)

    assert parsed["metadata"]["title"] == "Example Paper"
    assert parsed["metadata"]["doi"] == "10.1000/example"
    assert parsed["counts"] == {
        "authors": 1,
        "sections": 1,
        "references": 1,
        "figures": 0,
        "tables": 1,
        "formulas": 1,
    }
    assert parsed["sections"][0]["heading"] == "Introduction"
    assert parsed["formulas"][0]["text"] == "E = mc²"
