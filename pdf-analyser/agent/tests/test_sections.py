from app.canonical.sections import (
    assign_text_blocks_to_sections,
    attach_elements_to_sections,
    build_section_structure,
    build_section_tree,
)


def test_nested_tei_sections_and_element_links() -> None:
    tei = """
    <TEI xmlns="http://www.tei-c.org/ns/1.0">
      <text>
        <body>
          <div xml:id="s1">
            <head n="1" coords="1,50,80,200,20">Methods</head>
            <p xml:id="p1" coords="1,50,110,400,60">Overview of the method.</p>
            <div xml:id="s11">
              <head n="1.1" coords="2,50,80,200,20">Dataset</head>
              <p xml:id="p2" coords="2,50,110,400,60">The dataset contains samples.</p>
              <figure xml:id="fig1" coords="2,50,200,300,180">
                <head>Figure 1</head>
                <figDesc>Dataset overview</figDesc>
              </figure>
              <figure xml:id="tab1" type="table" coords="2,50,400,300,100">
                <head>Table 1</head>
                <figDesc>Dataset statistics</figDesc>
              </figure>
              <formula xml:id="eq1" n="1" coords="2,50,550,200,40">x = y + 1</formula>
            </div>
          </div>
        </body>
      </text>
    </TEI>
    """

    structure = build_section_structure(tei_xml=tei, flat_sections=[])
    sections = structure["sections"]
    paragraphs = structure["paragraphs"]

    assert len(sections) == 2
    assert sections[0]["title"] == "Methods"
    assert sections[0]["level"] == 1
    assert sections[1]["title"] == "Dataset"
    assert sections[1]["level"] == 2
    assert sections[1]["parent_id"] == sections[0]["id"]
    assert sections[1]["path"] == ["Methods", "Dataset"]
    assert paragraphs[1]["section_id"] == sections[1]["id"]
    assert structure["source_element_to_section"]["fig1"] == sections[1]["id"]
    assert structure["source_element_to_section"]["tab1"] == sections[1]["id"]
    assert structure["source_element_to_section"]["eq1"] == sections[1]["id"]

    text_blocks = [
        {"id": "b1", "label": "section_header", "text": "Methods"},
        {"id": "b2", "label": "text", "text": "Overview of the method."},
        {"id": "b3", "label": "section_header", "text": "Dataset"},
        {"id": "b4", "label": "text", "text": "The dataset contains samples."},
    ]
    assign_text_blocks_to_sections(
        text_blocks,
        sections=sections,
        paragraphs=paragraphs,
    )
    assert text_blocks[1]["section_path"] == ["Methods"]
    assert text_blocks[3]["section_path"] == ["Methods", "Dataset"]
    assert text_blocks[3]["paragraph_id"] == paragraphs[1]["id"]

    figures = [{"id": "figure_001", "page": 2, "sources": {"grobid": {"id": "fig1"}}}]
    tables = [{"id": "table_001", "page": 2, "sources": {"grobid": {"id": "tab1"}}}]
    formulas = [{"id": "formula_001", "page": 2, "sources": {"grobid": {"id": "eq1"}}}]
    attach_elements_to_sections(
        sections=sections,
        source_element_to_section=structure["source_element_to_section"],
        figures=figures,
        tables=tables,
        formulas=formulas,
    )
    assert figures[0]["section_path"] == ["Methods", "Dataset"]
    assert tables[0]["section_id"] == sections[1]["id"]
    assert formulas[0]["section_title"] == "Dataset"
    assert sections[1]["figure_ids"] == ["figure_001"]
    assert sections[1]["table_ids"] == ["table_001"]
    assert sections[1]["formula_ids"] == ["formula_001"]

    tree = build_section_tree(sections)
    assert len(tree) == 1
    assert tree[0]["title"] == "Methods"
    assert tree[0]["children"][0]["title"] == "Dataset"


def test_flat_section_fallback_infers_subsection_levels() -> None:
    structure = build_section_structure(
        tei_xml=None,
        flat_sections=[
            {"id": "s1", "heading": "Methods", "number": "2", "paragraphs": ["A"]},
            {"id": "s2", "heading": "Dataset", "number": "2.1", "paragraphs": ["B"]},
            {"id": "s3", "heading": "Model", "number": "2.2", "paragraphs": ["C"]},
        ],
    )
    sections = structure["sections"]
    assert sections[1]["parent_id"] == sections[0]["id"]
    assert sections[2]["parent_id"] == sections[0]["id"]
    assert sections[1]["path"] == ["Methods", "Dataset"]
