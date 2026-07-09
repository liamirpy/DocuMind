from typing import Any

from lxml import etree

NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _node_text(node: etree._Element | None) -> str | None:
    if node is None:
        return None
    return _clean(" ".join(node.itertext()))


def _first_text(root: etree._Element, xpath: str) -> str | None:
    nodes = root.xpath(xpath, namespaces=NS)
    if not nodes:
        return None
    first = nodes[0]
    if isinstance(first, etree._Element):
        return _node_text(first)
    return _clean(str(first))


def _all_text(root: etree._Element, xpath: str) -> list[str]:
    values: list[str] = []
    for node in root.xpath(xpath, namespaces=NS):
        text = _node_text(node) if isinstance(node, etree._Element) else _clean(str(node))
        if text:
            values.append(text)
    return values


def _coords(node: etree._Element) -> str | None:
    return node.get("coords")


def _parse_authors(root: etree._Element) -> list[dict[str, Any]]:
    author_nodes = root.xpath(
        ".//tei:teiHeader//tei:sourceDesc//tei:analytic/tei:author",
        namespaces=NS,
    )
    if not author_nodes:
        author_nodes = root.xpath(".//tei:teiHeader//tei:titleStmt/tei:author", namespaces=NS)

    authors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for author in author_nodes:
        full_name = _node_text(author)
        if not full_name or full_name in seen:
            continue
        seen.add(full_name)
        authors.append(
            {
                "full_name": full_name,
                "forename": _first_text(author, ".//tei:forename[1]"),
                "surname": _first_text(author, ".//tei:surname[1]"),
                "orcid": _first_text(author, ".//tei:idno[@type='ORCID'][1]"),
                "email": _first_text(author, ".//tei:email[1]"),
                "coords": _coords(author),
            }
        )
    return authors


def _parse_sections(root: etree._Element) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for index, div in enumerate(
        root.xpath(".//tei:text/tei:body//tei:div", namespaces=NS),
        start=1,
    ):
        heading_node = div.find("{http://www.tei-c.org/ns/1.0}head")
        paragraphs = [
            text
            for paragraph in div.xpath("./tei:p", namespaces=NS)
            if (text := _node_text(paragraph))
        ]
        sections.append(
            {
                "id": div.get(XML_ID) or f"section-{index}",
                "heading": _node_text(heading_node),
                "number": heading_node.get("n") if heading_node is not None else None,
                "paragraphs": paragraphs,
                "coords": _coords(heading_node) if heading_node is not None else None,
            }
        )
    return sections


def _parse_references(root: etree._Element) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for index, bibl in enumerate(
        root.xpath(".//tei:text/tei:back//tei:listBibl/tei:biblStruct", namespaces=NS),
        start=1,
    ):
        date_nodes = bibl.xpath(".//tei:imprint/tei:date[1]", namespaces=NS)
        year = None
        if date_nodes:
            year = date_nodes[0].get("when") or _node_text(date_nodes[0])
        references.append(
            {
                "id": bibl.get(XML_ID) or f"reference-{index}",
                "title": _first_text(bibl, ".//tei:analytic/tei:title[1]"),
                "authors": _all_text(bibl, ".//tei:analytic/tei:author/tei:persName"),
                "year": year,
                "doi": _first_text(bibl, ".//tei:idno[@type='DOI'][1]"),
                "raw": _first_text(bibl, ".//tei:note[@type='raw_reference'][1]"),
                "coords": _coords(bibl),
            }
        )
    return references


def _parse_figures(root: etree._Element) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    for index, figure in enumerate(root.xpath(".//tei:text//tei:figure", namespaces=NS), start=1):
        figures.append(
            {
                "id": figure.get(XML_ID) or f"figure-{index}",
                "type": figure.get("type") or "figure",
                "label": _first_text(figure, "./tei:head[1]"),
                "caption": _first_text(figure, "./tei:figDesc[1]"),
                "content": _first_text(figure, "./tei:table[1]"),
                "coords": _coords(figure),
            }
        )
    return figures


def _parse_formulas(root: etree._Element) -> list[dict[str, Any]]:
    formulas: list[dict[str, Any]] = []
    for index, formula in enumerate(root.xpath(".//tei:text//tei:formula", namespaces=NS), start=1):
        formulas.append(
            {
                "id": formula.get(XML_ID) or f"formula-{index}",
                "label": formula.get("n"),
                "text": _node_text(formula),
                "coords": _coords(formula),
            }
        )
    return formulas


def parse_tei(tei_xml: str) -> dict[str, Any]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    root = etree.fromstring(tei_xml.encode("utf-8"), parser=parser)

    sections = _parse_sections(root)
    references = _parse_references(root)
    figures = _parse_figures(root)
    formulas = _parse_formulas(root)
    authors = _parse_authors(root)

    title = _first_text(
        root,
        ".//tei:teiHeader//tei:titleStmt/tei:title[@type='main'][1]",
    ) or _first_text(root, ".//tei:teiHeader//tei:titleStmt/tei:title[1]")

    metadata = {
        "title": title,
        "authors": authors,
        "abstract": _first_text(root, ".//tei:teiHeader//tei:profileDesc/tei:abstract[1]"),
        "doi": _first_text(root, ".//tei:teiHeader//tei:idno[@type='DOI'][1]"),
        "journal": _first_text(
            root,
            ".//tei:teiHeader//tei:sourceDesc//tei:monogr/tei:title[@level='j'][1]",
        ),
        "publication_date": _first_text(
            root,
            ".//tei:teiHeader//tei:sourceDesc//tei:imprint/tei:date[1]/@when",
        ),
        "language": root.get("{http://www.w3.org/XML/1998/namespace}lang"),
    }

    table_count = sum(1 for item in figures if item["type"] == "table")
    figure_count = len(figures) - table_count

    return {
        "metadata": metadata,
        "sections": sections,
        "references": references,
        "figures_and_tables": figures,
        "formulas": formulas,
        "counts": {
            "authors": len(authors),
            "sections": len(sections),
            "references": len(references),
            "figures": figure_count,
            "tables": table_count,
            "formulas": len(formulas),
        },
    }
